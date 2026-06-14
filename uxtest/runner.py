from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, StrictStr

from .store import Store, StoreError, atomic_write_json, utc_now


ActionType = Literal["click", "type", "scroll", "find", "select", "back", "wait", "none"]
RunDriver = Literal["edsl", "heuristic", "scripted"]
PYDANTIC_ANSWERING_INSTRUCTIONS = (
    "Return ONLY one minified JSON object that directly matches the response schema. "
    "Do not wrap it in an answer key. Do not include a comment key. Do not include markdown."
)


class BrowserAction(BaseModel):
    type: ActionType = Field(description="Browser action to take.")
    ref: str | None = Field(default=None, description="Element ref from the supplied interactive elements.")
    text: str | None = Field(default=None, description="Short action description, or text/topic to find for find actions.")
    value: str | None = Field(default=None, description="Optional value for selects.")


class BrowserDecision(BaseModel):
    action: BrowserAction
    thinking: str
    frustration: int = Field(ge=0, le=10)
    status: Literal["continue", "done", "gave_up"]
    driver: RunDriver = "heuristic"
    raw_response: str | None = None
    edsl: dict[str, Any] = Field(default_factory=dict)


class BrowserDecisionAnswer(BaseModel):
    action_type: ActionType = Field(description="Browser action to take.")
    ref: str | None = Field(default=None, description="Element ref from the supplied interactive elements.")
    text: str | None = Field(default=None, description="Short action description, or text/topic to find for find actions.")
    value: str | None = Field(default=None, description="Exact value to enter for type/select actions.")
    thinking: StrictStr = Field(description="Brief rationale for the next action.")
    frustration: int = Field(ge=0, le=10, description="Current frustration from 0 to 10.")
    status: Literal["continue", "done", "gave_up"] = Field(description="Agent assessment of task status.")


def run_study(
    store: Store,
    study_id: str,
    *,
    persona_name: str | None = None,
    max_steps: int | None = None,
    driver: RunDriver = "edsl",
    max_concurrent_runs: int = 1,
    continue_on_error: bool = False,
    run_overrides: dict[str, Any] | None = None,
) -> list[Path]:
    study = store.load_study(study_id)
    if run_overrides:
        study = dict(study)
        overrides = dict(study.get("overrides") or {})
        overrides.update(run_overrides)
        study["overrides"] = overrides
    config = store.load_config()
    defaults = config.get("defaults", {})
    browser_config = config.get("browser", {})
    personas = [persona_name] if persona_name else list(study.get("personas") or [])
    if not personas:
        raise StoreError(f"Study {study_id!r} has no personas.", exit_code=2)

    steps_limit = max_steps or int(study.get("overrides", {}).get("max_steps") or defaults.get("max_steps", 30))
    completed: list[Path] = []
    errors: list[tuple[Path, Exception]] = []
    store.recover_stale_runs(study_id)
    with store.study_lock(study_id):
        store.set_study_status(study_id, "running")

        runs_per_persona = 1 if persona_name else int(study.get("runs_per_persona") or defaults.get("runs_per_persona", 1) or 1)
        jobs = []
        next_sequence = _next_run_sequence(store, study_id)
        for persona in personas:
            persona_doc = store.load_persona(persona)
            for _ in range(runs_per_persona):
                run_id = f"run-{next_sequence:03d}-{persona}-{uuid4().hex[:4]}"
                next_sequence += 1
                run_dir = store.study_dir(study_id) / "runs" / run_id
                jobs.append({"persona_doc": persona_doc, "run_id": run_id, "run_dir": run_dir})

        workers = max(1, min(int(max_concurrent_runs or 1), len(jobs) or 1))
        run_kwargs = {
            "max_steps": steps_limit,
            "headless": bool(browser_config.get("headless", True)),
            "slow_mo_ms": int(browser_config.get("slow_mo_ms", 0) or 0),
            "driver": driver,
        }
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="uxtest-run") as executor:
            futures = {
                executor.submit(
                    _run_once,
                    store,
                    study,
                    config,
                    job["persona_doc"],
                    run_id=job["run_id"],
                    **run_kwargs,
                ): job
                for job in jobs
            }
            for future in as_completed(futures):
                job = futures[future]
                try:
                    completed.append(future.result())
                except Exception as exc:
                    errors.append((job["run_dir"], exc))
                    completed.append(job["run_dir"])

        if errors and not continue_on_error:
            store.set_study_status(study_id, "failed")
            first_run, first_error = errors[0]
            raise StoreError(
                f"{len(errors)} run(s) failed. First failure in {first_run.name}: {first_error}",
                exit_code=1,
            )
        store.set_study_status(study_id, "complete_with_errors" if errors else "complete")

    return completed


def _run_once(
    store: Store,
    study: dict[str, Any],
    config: dict[str, Any],
    persona_doc: dict[str, Any],
    *,
    max_steps: int,
    headless: bool,
    slow_mo_ms: int,
    driver: RunDriver,
    run_id: str | None = None,
) -> Path:
    from playwright.sync_api import sync_playwright

    study_id = str(study["id"])
    persona_name = str(persona_doc["name"])
    run_id = run_id or store.next_run_id(study_id, persona_name)
    study_dir = store.study_dir(study_id)
    run_dir = study_dir / "runs" / run_id
    screenshots_dir = run_dir / "screenshots"
    a11y_dir = run_dir / "a11y"
    screenshots_dir.mkdir(parents=True)
    a11y_dir.mkdir()

    resolved_config = _resolved_config(config, study)
    persona_instance = _persona_instance(persona_doc)
    meta_path = run_dir / "meta.json"
    meta = {
        "schema_version": 1,
        "run_id": run_id,
        "study_id": study_id,
        "started_at": utc_now(),
        "finished_at": None,
        "outcome": None,
        "outcome_detail": None,
        "steps_taken": 0,
        "final_url": None,
        "seed": None,
        "persona_instance": persona_instance,
        "resolved_config": resolved_config,
        "environment": {
            "uxtest_version": "0.1.0",
            "playwright_version": _playwright_version(),
            "browser": "chromium",
            "os": f"{platform.system().lower()}-{platform.machine().lower()}",
        },
        "costs": {},
    }
    atomic_write_json(meta_path, meta)

    outcome = "max_steps"
    outcome_detail = f"Reached max_steps={max_steps}"
    trace_path = run_dir / "trace.jsonl"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo_ms)
        _load_env(Path.cwd() / ".env")
        _load_env(store.root / ".env")
        env_file = resolved_config.get("env_file") or ((resolved_config.get("secrets") or {}).get("env_file") if isinstance(resolved_config.get("secrets"), dict) else None)
        if env_file:
            _load_env(_resolve_project_path(store.root, str(env_file)))
        viewport_config = resolved_config.get("viewport", {})
        page_options: dict[str, Any] = {
            "viewport": {
                "width": int(viewport_config.get("width", 1280)),
                "height": int(viewport_config.get("height", 800)),
            }
        }
        if "device_scale_factor" in resolved_config:
            page_options["device_scale_factor"] = float(resolved_config["device_scale_factor"])
        if "is_mobile" in resolved_config:
            page_options["is_mobile"] = bool(resolved_config["is_mobile"])
        if "has_touch" in resolved_config:
            page_options["has_touch"] = bool(resolved_config["has_touch"])
        if resolved_config.get("user_agent"):
            page_options["user_agent"] = str(resolved_config["user_agent"])
        auth_state = resolved_config.get("auth_state")
        if isinstance(auth_state, dict) and auth_state.get("load"):
            state_path = _resolve_project_path(store.root, str(auth_state["load"]))
            if state_path.exists():
                page_options["storage_state"] = str(state_path)
        context = browser.new_context(**page_options)
        page = context.new_page()
        try:
            page.goto(str(study["url"]), wait_until="networkidle")
            setup_steps = resolved_config.get("setup_steps")
            if isinstance(setup_steps, list) and setup_steps:
                _execute_setup_steps(page, run_dir, trace_path, setup_steps, resolved_config)
            recent_events: list[dict[str, Any]] = []
            repeated_action_count = 0
            last_action_key: tuple[Any, ...] | None = None
            for step in range(1, max_steps + 1):
                _settle_page(page)
                state = _capture_state(page, run_dir, step, resolved_config)
                if driver == "heuristic":
                    decision = _heuristic_decision(study, state)
                elif driver == "scripted":
                    decision = _scripted_decision(study, state, recent_events)
                else:
                    decision = _edsl_decision(study, persona_doc, resolved_config, state, run_dir, store.root, recent_events)
                action_key = (state["url"], decision.action.type, decision.action.ref, decision.action.text, decision.action.value)
                repeated_action_count = repeated_action_count + 1 if action_key == last_action_key else 1
                last_action_key = action_key
                if repeated_action_count >= 3 and decision.status == "continue":
                    decision.status = "gave_up"
                    decision.thinking = f"{decision.thinking}\nStopped after repeating the same action {repeated_action_count} times."
                result = _execute_action(page, state, decision.action)
                event = _trace_event(step, state, decision, result, resolved_config)
                _append_jsonl(trace_path, event)
                recent_events.append(_compact_trace_event(event))
                recent_events = recent_events[-5:]

                if decision.status == "done" or _is_success(page, study):
                    outcome = "done"
                    outcome_detail = "Success criteria reached."
                    break
                if decision.status == "gave_up":
                    outcome = "gave_up"
                    outcome_detail = "Agent gave up."
                    break
        except Exception as exc:
            outcome = "error"
            outcome_detail = str(exc)
            raise
        finally:
            if isinstance(resolved_config.get("auth_state"), dict) and resolved_config["auth_state"].get("save"):
                state_path = _resolve_project_path(store.root, str(resolved_config["auth_state"]["save"]))
                state_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(state_path))
            meta["finished_at"] = utc_now()
            meta["outcome"] = outcome
            meta["outcome_detail"] = outcome_detail
            meta["steps_taken"] = _count_trace_lines(trace_path)
            meta["final_url"] = page.url if not page.is_closed() else None
            atomic_write_json(meta_path, meta)
            context.close()
            browser.close()

    return run_dir


def _next_run_sequence(store: Store, study_id: str) -> int:
    max_sequence = 0
    for run_dir in store.list_runs(study_id):
        match = re.match(r"run-(\d+)-", run_dir.name)
        if match:
            max_sequence = max(max_sequence, int(match.group(1)))
    return max_sequence + 1


def _resolved_config(config: dict[str, Any], study: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(config.get("defaults", {}))
    resolved.update(study.get("overrides") or {})
    return resolved


def _persona_instance(persona_doc: dict[str, Any]) -> dict[str, Any]:
    source = json.dumps(persona_doc, sort_keys=True).encode("utf-8")
    return {
        "name": persona_doc["name"],
        "resolved": persona_doc.get("attributes", {}),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "snapshot": persona_doc,
    }


def _capture_state(page: Any, run_dir: Path, step: int, config: dict[str, Any]) -> dict[str, Any]:
    screenshot_rel = None
    if config.get("screenshot", "full") != "off":
        suffix = "jpg" if config.get("screenshot_format") == "jpeg" else "png"
        screenshot_rel = f"screenshots/step-{step:03d}.{suffix}"
        screenshot_path = run_dir / screenshot_rel
        # Full-page screenshots can scroll the page internally and collapse
        # transient UI such as nav menus. Browser-decision screenshots must
        # preserve the current viewport state.
        kwargs: dict[str, Any] = {"path": str(screenshot_path), "full_page": False}
        if suffix == "jpg":
            kwargs["quality"] = int(config.get("screenshot_quality", 80))
            kwargs["type"] = "jpeg"
        page.screenshot(**kwargs)

    elements = page.evaluate(
        """
        () => {
          document.querySelectorAll('[data-uxtest-ref]').forEach((el) => el.removeAttribute('data-uxtest-ref'));
          const nearestLandmark = (el) => {
            const landmark = el.closest('nav,header,main,footer,aside,[role="navigation"],[role="banner"],[role="main"]');
            if (!landmark) return '';
            return (landmark.getAttribute('aria-label') || landmark.getAttribute('role') || landmark.tagName || '').toLowerCase();
          };
          const rawLabelFor = (el) => {
            const aria = (el.getAttribute('aria-label') || '').trim();
            if (aria) return { label: aria, source: 'aria-label' };
            const title = (el.getAttribute('title') || '').trim();
            if (title) return { label: title, source: 'title' };
            const alt = (el.querySelector('img[alt]')?.getAttribute('alt') || '').trim();
            if (alt) return { label: alt, source: 'img-alt' };
            const svgTitle = (el.querySelector('svg title')?.textContent || '').trim();
            if (svgTitle) return { label: svgTitle, source: 'svg-title' };
            const text = (el.innerText || '').trim();
            if (text) return { label: text, source: 'innerText' };
            const placeholder = (el.getAttribute('placeholder') || '').trim();
            if (placeholder) return { label: placeholder, source: 'placeholder' };
            const value = (el.value || '').trim();
            if (value) return { label: value, source: 'value' };
            const name = (el.getAttribute('name') || '').trim();
            if (name) return { label: name, source: 'name' };
            if (el.tagName.toLowerCase() === 'button') {
              const landmark = nearestLandmark(el);
              const expanded = el.getAttribute('aria-expanded');
              if (expanded !== null || landmark.includes('nav') || landmark.includes('header') || landmark.includes('banner')) {
                return { label: 'Menu', source: 'inferred-menu-button' };
              }
              return { label: 'Unlabeled button', source: 'inferred-unlabeled-button' };
            }
            return { label: '', source: '' };
          };
          const contextFor = (el, label) => {
            const elRect = el.getBoundingClientRect();
            const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
              .map((heading) => ({ text: (heading.innerText || '').replace(/\\s+/g, ' ').trim(), rect: heading.getBoundingClientRect() }))
              .filter((heading) => heading.text && heading.rect.bottom <= elRect.top && heading.rect.right > elRect.left && heading.rect.left < elRect.right)
              .sort((a, b) => b.rect.bottom - a.rect.bottom);
            if (headings.length > 0) {
              return headings[0].text;
            }
            let current = el.parentElement;
            for (let depth = 0; current && depth < 5; depth += 1, current = current.parentElement) {
              const text = (current.innerText || '').replace(/\\s+/g, ' ').trim();
              if (!text || text === label || text.length > 500) continue;
              return text.slice(0, 240);
            }
            return '';
          };
          const nodes = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role="button"],[role="link"]'))
            .filter((el) => {
              const style = window.getComputedStyle(el);
              const rect = el.getBoundingClientRect();
              const inViewport = rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth;
              return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0 && inViewport;
            });
          return nodes.slice(0, 80).map((el, index) => {
            const ref = `e${index + 1}`;
            el.setAttribute('data-uxtest-ref', ref);
            const labelInfo = rawLabelFor(el);
            const label = labelInfo.label;
            return {
              ref,
              tag: el.tagName.toLowerCase(),
              role: el.getAttribute('role') || '',
              type: el.getAttribute('type') || '',
              name: el.getAttribute('name') || '',
              value: el.value || '',
              label,
              label_source: labelInfo.source,
              context: contextFor(el, label),
              selector_hint: `[data-uxtest-ref="${ref}"]`
            };
          });
        }
        """
    )
    visible_text = page.evaluate(
        """
        () => {
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          const chunks = [];
          while (walker.nextNode()) {
            const node = walker.currentNode;
            const text = (node.textContent || '').replace(/\\s+/g, ' ').trim();
            if (!text) continue;
            const parent = node.parentElement;
            if (!parent) continue;
            const style = window.getComputedStyle(parent);
            if (style.visibility === 'hidden' || style.display === 'none') continue;
            const range = document.createRange();
            range.selectNodeContents(node);
            const rects = Array.from(range.getClientRects());
            range.detach();
            if (rects.some((rect) => rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth)) {
              chunks.push(text);
            }
          }
          return chunks.join('\\n');
        }
        """
    )
    headings = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
          .map((el) => {
            const rect = el.getBoundingClientRect();
            return {
              text: (el.innerText || '').replace(/\\s+/g, ' ').trim(),
              level: el.tagName.toLowerCase(),
              in_viewport: rect.bottom > 0 && rect.top < window.innerHeight,
              y: Math.round(rect.top + window.scrollY)
            };
          })
          .filter((item) => item.text)
          .slice(0, 80)
        """
    )
    return {
        "url": page.url,
        "page_title": page.title(),
        "screenshot": screenshot_rel,
        "interactive_elements": elements,
        "headings": headings,
        "visible_text": visible_text[:6000],
    }


def _edsl_decision(
    study: dict[str, Any],
    persona_doc: dict[str, Any],
    config: dict[str, Any],
    state: dict[str, Any],
    run_dir: Path,
    project_root: Path,
    recent_events: list[dict[str, Any]],
) -> BrowserDecision:
    _load_env(Path.cwd() / ".env")
    _load_env(project_root / ".env")
    from edsl import Agent, FileStore, Model, QuestionFreeText, QuestionPydantic, Scenario

    scenario_data: dict[str, Any] = {
        "task": study["task"],
        "success_criteria": study.get("success_criteria", ""),
        "current_url": state["url"],
        "page_title": state["page_title"],
        "visible_text": state["visible_text"],
        "headings": state.get("headings") or [],
        "interactive_elements": state["interactive_elements"],
        "recent_events": _with_recovery_hint(recent_events),
    }
    screenshot = state.get("screenshot")
    screenshot_ref = ""
    if screenshot:
        scenario_data["screenshot"] = FileStore(str(run_dir / screenshot))
        screenshot_ref = " Screenshot: {{ scenario.screenshot }}"
    scenario = Scenario(scenario_data)
    agent = Agent(
        traits=persona_doc.get("attributes", {}),
        name=persona_doc.get("name"),
        instruction=str(persona_doc.get("goals_bias", "")),
    )
    model = Model(str(config.get("model", "gpt-4o")), temperature=float(config.get("temperature", 0.7)))
    question_text = (
        "You are controlling a browser to complete this UX study task.\n"
        "Task: {{ scenario.task }}\n"
        "Success criteria: {{ scenario.success_criteria }}\n"
        "Current URL: {{ scenario.current_url }}\n"
        "Page title: {{ scenario.page_title }}\n"
        "Recent events:\n{{ scenario.recent_events }}\n"
        "Visible text:\n{{ scenario.visible_text }}\n"
        "Page headings:\n{{ scenario.headings }}\n"
        "Interactive elements, with allowed refs:\n{{ scenario.interactive_elements }}\n"
        f"{screenshot_ref}\n"
        "Return exactly one next browser action. Only use refs from the supplied elements.\n"
        "If this is an exploratory task and you have enough evidence to answer it, set status=done and use action_type=none.\n"
        "Do not click headings or section names unless they appear in Interactive elements with a ref. "
        "For long pages, use action_type=find with text set to a heading/topic, or action_type=scroll.\n"
        "If recent events show the same click or non-navigation repeated, choose a different strategy.\n"
        "For type and select actions, put the exact value to enter in value; use text only as a short action description.\n"
        "thinking must be a short prose rationale, and frustration must be an integer from 0 to 10.\n"
        "action_type must be one of click, type, scroll, find, select, back, wait, none. "
        "status must be one of continue, done, gave_up."
    )
    question = QuestionPydantic(
        question_name="browser_decision",
        question_text=question_text,
        pydantic_model=BrowserDecisionAnswer,
        answering_instructions=PYDANTIC_ANSWERING_INSTRUCTIONS,
    )
    last_answer = ""
    last_error = ""
    pydantic_attempts: list[dict[str, Any]] = []
    for attempt in range(1, 3):
        results = None
        result_dict: dict[str, Any] | None = None
        try:
            results = _run_remote_edsl(question, agent, scenario, model)
            result_dict = results.to_dict()
            answer = result_dict["data"][0]["answer"]["browser_decision"]
            last_answer = json.dumps(answer, sort_keys=True) if isinstance(answer, dict) else str(answer)
            typed_answer = BrowserDecisionAnswer.model_validate(answer)
            pydantic_attempts.append(
                {
                    "attempt": attempt,
                    "ok": True,
                    "job": _edsl_job_metadata(results),
                    "results": _compact_edsl_results(result_dict),
                    "answer": last_answer,
                }
            )
            return _decision_from_answer(
                typed_answer,
                persona_doc=persona_doc,
                config=config,
                question_type="pydantic",
                question_text=question_text,
                scenario_data=scenario_data,
                run_dir=run_dir,
                results=results,
                result_dict=result_dict,
                attempt=attempt,
                state=state,
                raw_response=last_answer,
            )
        except Exception as exc:
            last_error = str(exc)
            attempt_log: dict[str, Any] = {
                "attempt": attempt,
                "ok": False,
                "error": last_error,
                "answer": last_answer,
            }
            if results is not None:
                attempt_log["job"] = _edsl_job_metadata(results)
            if result_dict is not None:
                attempt_log["results"] = _compact_edsl_results(result_dict)
            pydantic_attempts.append(attempt_log)
            if attempt == 2:
                return _edsl_decision_fallback(
                    study,
                    persona_doc,
                    config,
                    state,
                    run_dir,
                    scenario,
                    scenario_data,
                    agent,
                    model,
                    question_text,
                    last_error=last_error,
                    last_answer=last_answer,
                    pydantic_attempts=pydantic_attempts,
                )
    raise StoreError(f"EDSL browser decision failed: {last_error}; last response: {last_answer[:200]}", exit_code=1)


def _edsl_decision_fallback(
    study: dict[str, Any],
    persona_doc: dict[str, Any],
    config: dict[str, Any],
    state: dict[str, Any],
    run_dir: Path,
    scenario: Any,
    scenario_data: dict[str, Any],
    agent: Any,
    model: Any,
    question_text: str,
    *,
    last_error: str,
    last_answer: str,
    pydantic_attempts: list[dict[str, Any]],
) -> BrowserDecision:
    from edsl import QuestionFreeText

    fallback_text = (
        f"{question_text}\n"
        "Return only compact JSON with keys: action_type, ref, text, value, thinking, frustration, status."
    )
    question = QuestionFreeText(question_name="browser_decision", question_text=fallback_text)
    results = _run_remote_edsl(question, agent, scenario, model)
    result_dict = results.to_dict()
    answer = result_dict["data"][0]["answer"]["browser_decision"]
    raw_response = answer if isinstance(answer, str) else json.dumps(answer, sort_keys=True)
    if not isinstance(answer, str) or not answer.strip():
        raise StoreError(f"EDSL returned no browser_decision text after Pydantic fallback. Pydantic error: {last_error}", exit_code=1)
    parsed = _parse_json_object(answer)
    typed_answer = BrowserDecisionAnswer(
        action_type=parsed.get("action_type", parsed.get("type", "none")),
        ref=_empty_to_none(parsed.get("ref")),
        text=_empty_to_none(parsed.get("text")),
        value=_empty_to_none(parsed.get("value")),
        thinking=str(parsed.get("thinking") or ""),
        frustration=_coerce_frustration(parsed.get("frustration")),
        status=parsed.get("status") or "continue",
    )
    decision = _decision_from_answer(
        typed_answer,
        persona_doc=persona_doc,
        config=config,
        question_type="free_text_fallback",
        question_text=fallback_text,
        scenario_data=scenario_data,
        run_dir=run_dir,
        results=results,
        result_dict=result_dict,
        attempt=1,
        state=state,
        raw_response=raw_response,
    )
    decision.edsl["pydantic_fallback"] = {
        "last_error": last_error,
        "last_answer": last_answer,
        "attempts": pydantic_attempts,
    }
    return decision


def _run_remote_edsl(question: Any, agent: Any, scenario: Any, model: Any) -> Any:
    return question.by(agent).by(scenario).by(model).run(
        cache=False,
        offload_execution=True,
        use_api_proxy=False,
        disable_remote_inference=False,
    )


def _decision_from_answer(
    answer: BrowserDecisionAnswer,
    *,
    persona_doc: dict[str, Any],
    config: dict[str, Any],
    question_type: str,
    question_text: str,
    scenario_data: dict[str, Any],
    run_dir: Path,
    results: Any,
    result_dict: dict[str, Any],
    attempt: int,
    state: dict[str, Any],
    raw_response: str,
) -> BrowserDecision:
    decision = BrowserDecision(
        action=BrowserAction(
            type=answer.action_type,
            ref=_empty_to_none(answer.ref),
            text=_empty_to_none(answer.text),
            value=_empty_to_none(answer.value),
        ),
        thinking=answer.thinking,
        frustration=answer.frustration,
        status=answer.status,
        driver="edsl",
        raw_response=raw_response,
        edsl={
            "agent_name": persona_doc.get("name"),
            "agent_traits": persona_doc.get("attributes", {}),
            "agent_instruction": persona_doc.get("goals_bias", ""),
            "model": str(config.get("model", "gpt-4o")),
            "temperature": float(config.get("temperature", 0.7)),
            "question_name": "browser_decision",
            "question_type": question_type,
            "question_text": question_text,
            "scenario": _edsl_scenario_log(scenario_data, run_dir=run_dir),
            "attempt": attempt,
            "job": _edsl_job_metadata(results),
            "results": _compact_edsl_results(result_dict),
            "validated_answer": answer.model_dump(),
        },
    )
    allowed_refs = {str(element.get("ref")) for element in state.get("interactive_elements") or []}
    if decision.action.ref and decision.action.ref not in allowed_refs:
        original = decision.action.model_dump()
        decision.action.ref = None
        recovered = _recover_static_text_action(decision.action, state)
        if recovered:
            decision.action = recovered
            decision.thinking = f"{decision.thinking}\nModel selected a ref that was not present; converted to a page find action."
            decision.edsl["action_recovery"] = {"reason": "missing_ref", "original_action": original, "recovered_action": recovered.model_dump()}
        else:
            decision.action.type = "none"
            decision.thinking = f"{decision.thinking}\nModel selected a ref that was not present in the observed elements."
            decision.edsl["action_recovery"] = {"reason": "missing_ref", "original_action": original, "recovered_action": decision.action.model_dump()}
    elif decision.action.type in {"click", "none"} and not decision.action.ref:
        recovered = _recover_static_text_action(decision.action, state)
        if recovered:
            original = decision.action.model_dump()
            decision.action = recovered
            decision.thinking = f"{decision.thinking}\nConverted a non-interactive section/heading request to a page find action."
            decision.edsl["action_recovery"] = {"reason": "static_text_request", "original_action": original, "recovered_action": recovered.model_dump()}
    return decision


def _with_recovery_hint(recent_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(recent_events) < 2:
        return recent_events
    previous, latest = recent_events[-2], recent_events[-1]
    previous_action = previous.get("action") or {}
    latest_action = latest.get("action") or {}
    previous_result = previous.get("result") or {}
    latest_result = latest.get("result") or {}
    same_action = (
        previous.get("url"),
        previous_action.get("type"),
        previous_action.get("ref"),
        previous_action.get("text"),
    ) == (
        latest.get("url"),
        latest_action.get("type"),
        latest_action.get("ref"),
        latest_action.get("text"),
    )
    non_navigation = previous_result.get("navigation") is False and latest_result.get("navigation") is False
    if not same_action or not non_navigation:
        return recent_events
    return [
        *recent_events,
        {
            "event_type": "recovery_hint",
            "message": "The last two actions repeated without navigation or visible progress. Choose a different strategy: find a heading/topic, scroll, go back, or finish if enough evidence has been gathered.",
        },
    ]


def _recover_static_text_action(action: BrowserAction, state: dict[str, Any]) -> BrowserAction | None:
    text = _static_action_target(action.text or action.value or "")
    if not text:
        return None
    if _page_contains_text_or_heading(state, text):
        return BrowserAction(type="find", text=text)
    return None


def _static_action_target(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text).strip(" .")
    if not cleaned:
        return None
    quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"", cleaned)
    if quoted:
        for first, second in quoted:
            candidate = (first or second).strip()
            if candidate:
                return candidate[:120]
    lowered = cleaned.lower()
    prefixes = [
        "click on the ",
        "click on ",
        "click ",
        "explore the ",
        "explore ",
        "view the ",
        "view ",
        "find the ",
        "find ",
        "scroll to the ",
        "scroll to ",
    ]
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return _clean_static_target(cleaned[len(prefix):])
    return None


def _clean_static_target(text: str) -> str:
    cleaned = text.strip(" .")
    cleaned = re.sub(r"\s+(section|heading|area)$", "", cleaned, flags=re.IGNORECASE).strip(" .")
    return cleaned[:120] or text.strip(" .")[:120]


def _page_contains_text_or_heading(state: dict[str, Any], text: str) -> bool:
    needle = text.lower()
    if not needle:
        return False
    for heading in state.get("headings") or []:
        if needle in str(heading.get("text") or "").lower():
            return True
    return needle in str(state.get("visible_text") or "").lower()


def _heuristic_decision(study: dict[str, Any], state: dict[str, Any]) -> BrowserDecision:
    text = state["visible_text"].lower()
    elements = state["interactive_elements"]

    if "order number" in text or "order confirmed" in text:
        return BrowserDecision(action=BrowserAction(type="none"), thinking="The confirmation page is visible.", frustration=0, status="done", driver="heuristic")

    field_values = {
        "email": "tester@example.com",
        "name": "Test Shopper",
        "card": "4242424242424242",
        "zip": "02139",
    }
    for key, value in field_values.items():
        found = _find_element(elements, name=key)
        if found and str(found.get("value") or "") != value:
            return BrowserDecision(action=BrowserAction(type="type", ref=found["ref"], text=value), thinking=f"Fill {key}.", frustration=1, status="continue", driver="heuristic")

    for label in ["place order", "checkout as guest", "continue", "add to cart"]:
        found = _find_element(elements, label=label)
        if found:
            return BrowserDecision(action=BrowserAction(type="click", ref=found["ref"]), thinking=f"Click {label}.", frustration=1, status="continue", driver="heuristic")

    return BrowserDecision(action=BrowserAction(type="wait"), thinking="Wait for the page to settle.", frustration=3, status="continue", driver="heuristic")


def _scripted_decision(study: dict[str, Any], state: dict[str, Any], recent_events: list[dict[str, Any]] | None = None) -> BrowserDecision:
    text = state["visible_text"].lower()
    url = state["url"].lower()
    elements = state["interactive_elements"]
    recent_events = recent_events or []
    recent_actions = [
        str((event.get("action") or {}).get("text") or (event.get("action") or {}).get("type") or "").lower()
        for event in recent_events
    ]
    is_flawed_saas = "variant=flawed" in str(study.get("url", "")).lower() or "variant=flawed" in url

    if "order number" in text or "order confirmed" in text:
        return BrowserDecision(action=BrowserAction(type="none"), thinking="The confirmation page is visible.", frustration=0, status="done", driver="scripted")

    if "northstar" in text or "research agent" in text or "ai interviewer" in text:
        if is_flawed_saas:
            for label in ["view examples", "open example", "docs", "pricing", "menu"]:
                found = _find_element(elements, label=label)
                if found and not _scripted_recently_clicked(label, recent_actions, limit=2):
                    return BrowserDecision(
                        action=BrowserAction(type="click", ref=found["ref"], text=str(found.get("label") or label)),
                        thinking=f"Click {label} to follow the fixture's flawed discovery path.",
                        frustration=2,
                        status="continue",
                        driver="scripted",
                    )
            repeated_docs = _find_element(elements, label="docs")
            if repeated_docs:
                return BrowserDecision(
                    action=BrowserAction(type="click", ref=repeated_docs["ref"], text=str(repeated_docs.get("label") or "Docs")),
                    thinking="Repeat Docs to verify whether the page advances after an acknowledged click.",
                    frustration=5,
                    status="continue",
                    driver="scripted",
                )
        else:
            for label in ["explore products", "menu", "docs", "quickstart", "overview"]:
                found = _find_element(elements, label=label)
                if found and not _scripted_recently_clicked(label, recent_actions, limit=1):
                    return BrowserDecision(
                        action=BrowserAction(type="click", ref=found["ref"], text=str(found.get("label") or label)),
                        thinking=f"Click {label} to follow the fixture's clear discovery path.",
                        frustration=1,
                        status="continue",
                        driver="scripted",
                    )
            return BrowserDecision(action=BrowserAction(type="none"), thinking="The clear discovery route has enough evidence.", frustration=1, status="done", driver="scripted")

    return _heuristic_decision(study, state).model_copy(update={"driver": "scripted"})


def _scripted_recently_clicked(label: str, recent_actions: list[str], *, limit: int) -> bool:
    normalized = label.lower()
    return sum(1 for action in recent_actions if normalized in action) >= limit


def _edsl_scenario_log(scenario_data: dict[str, Any], *, run_dir: Path) -> dict[str, Any]:
    logged: dict[str, Any] = {}
    for key, value in scenario_data.items():
        if key == "screenshot":
            logged[key] = str(getattr(value, "path", value))
            continue
        logged[key] = _jsonable(value)
    return logged


def _edsl_job_metadata(results: Any) -> dict[str, Any]:
    job_uuid = getattr(results, "job_uuid", None)
    results_uuid = getattr(results, "results_uuid", None)
    base_url = os.environ.get("EXPECTED_PARROT_URL", "https://www.expectedparrot.com").rstrip("/")
    job: dict[str, Any] = {
        "job_uuid": str(job_uuid) if job_uuid else None,
        "progress_url": f"{base_url}/home/remote-job-progress/{job_uuid}" if job_uuid else None,
        "results_uuid": str(results_uuid) if results_uuid else None,
        "results_url": f"{base_url}/content/{results_uuid}" if results_uuid else None,
    }
    job_info = getattr(results, "job_info", None)
    if job_info is not None:
        job["job_info"] = _jsonable(job_info)
    return job


def _compact_edsl_results(result_dict: dict[str, Any]) -> dict[str, Any]:
    rows = result_dict.get("data") if isinstance(result_dict, dict) else None
    return {
        "columns": result_dict.get("columns") if isinstance(result_dict, dict) else None,
        "data": rows[:1] if isinstance(rows, list) else rows,
    }


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return str(value)


def _redact_obj(value: Any, *, config: dict[str, Any], force_redact: set[str] | None = None, key: str | None = None) -> Any:
    force_redact = force_redact or set()
    if key in force_redact:
        return "[REDACTED]"
    if isinstance(value, str):
        return _redact_text(value, config)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [_redact_obj(item, config=config, force_redact=force_redact) for item in value]
    if isinstance(value, tuple):
        return [_redact_obj(item, config=config, force_redact=force_redact) for item in value]
    if isinstance(value, dict):
        return {
            str(item_key): _redact_obj(item_value, config=config, force_redact=force_redact, key=str(item_key))
            for item_key, item_value in value.items()
        }
    return _redact_text(str(value), config)


def _redact_text(text: str, config: dict[str, Any]) -> str:
    redacted = text
    patterns: list[str] = []
    configured = config.get("redact_patterns")
    if isinstance(configured, list):
        patterns.extend(str(item) for item in configured)
    secrets = config.get("secrets")
    if isinstance(secrets, dict) and isinstance(secrets.get("redact_patterns"), list):
        patterns.extend(str(item) for item in secrets["redact_patterns"])
    for pattern in patterns:
        if not pattern:
            continue
        try:
            redacted = re.sub(pattern, "[REDACTED]", redacted)
        except re.error:
            redacted = redacted.replace(pattern, "[REDACTED]")
    return redacted


def _find_element(elements: list[dict[str, Any]], *, label: str | None = None, name: str | None = None) -> dict[str, Any] | None:
    for element in elements:
        if name and element.get("name") == name:
            return element
        if label and label in str(element.get("label", "")).lower():
            return element
    return None


def _execute_setup_steps(page: Any, run_dir: Path, trace_path: Path, steps: list[Any], config: dict[str, Any]) -> None:
    for index, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, dict):
            raise StoreError(f"setup_steps[{index}] must be a mapping.", exit_code=2)
        step = dict(raw_step)
        action_type = str(step.get("type") or "").lower()
        if action_type not in {"click", "type", "select", "wait", "back", "find", "scroll"}:
            raise StoreError(f"Unsupported setup step type {action_type!r}.", exit_code=2)
        sensitive = bool(step.get("sensitive")) or bool(step.get("env")) or action_type == "type" and _setup_step_looks_sensitive(step)
        value = _setup_step_value(step)
        before_url = page.url
        ok = True
        error = None
        try:
            if action_type == "wait":
                page.wait_for_timeout(int(step.get("ms") or 750))
            elif action_type == "back":
                page.go_back(wait_until="networkidle")
            elif action_type == "scroll":
                page.mouse.wheel(0, int(step.get("dy") or 700))
                page.wait_for_timeout(300)
            elif action_type == "find":
                ok = _find_text_on_page(page, str(step.get("text") or value or ""))
            else:
                locator = _setup_locator(page, step)
                if action_type == "click":
                    locator.click(timeout=5000)
                elif action_type == "type":
                    locator.fill(value, timeout=5000)
                elif action_type == "select":
                    locator.select_option(value, timeout=5000)
            _wait_after_action(page, before_url)
        except Exception as exc:
            ok = False
            error = str(exc)
        event = {
            "schema_version": 1,
            "event_type": "setup_step",
            "step": f"setup-{index:03d}",
            "ts": utc_now(),
            "url": before_url,
            "page_title": _safe_page_title(page),
            "action": _redacted_setup_action(step, action_type=action_type, value=value, sensitive=sensitive, config=config),
            "result": {
                "ok": ok,
                "navigation": page.url != before_url,
                "final_url": page.url,
                "console_errors": 0,
                **({"error": error} if error else {}),
            },
            "thinking": "Deterministic setup step executed before model-controlled browser actions.",
            "frustration": 0,
            "status": "continue",
        }
        _append_jsonl(trace_path, event)
        if not ok:
            raise StoreError(f"Setup step {index} failed: {error}", exit_code=1)


def _setup_step_value(step: dict[str, Any]) -> str:
    if step.get("env"):
        name = str(step["env"])
        if name not in os.environ:
            raise StoreError(f"Setup step references missing env var {name!r}.", exit_code=2)
        return os.environ[name]
    return str(step.get("value") or step.get("text") or "")


def _setup_step_looks_sensitive(step: dict[str, Any]) -> bool:
    text = " ".join(str(step.get(key) or "") for key in ("selector", "name", "label", "placeholder", "text", "value")).lower()
    return any(token in text for token in ("password", "secret", "token", "otp", "mfa", "code", "email"))


def _setup_locator(page: Any, step: dict[str, Any]) -> Any:
    if step.get("selector"):
        return page.locator(str(step["selector"])).first
    if step.get("name"):
        name = str(step["name"])
        return page.locator(f'[name="{_css_escape(name)}"], input[id="{_css_escape(name)}"], textarea[id="{_css_escape(name)}"]').first
    if step.get("placeholder"):
        return page.get_by_placeholder(str(step["placeholder"])).first
    if step.get("label"):
        label = str(step["label"])
        try:
            return page.get_by_role("button", name=re.compile(re.escape(label), re.I)).first
        except Exception:
            return page.get_by_text(label, exact=False).first
    raise StoreError("Setup step requires selector, name, placeholder, or label.", exit_code=2)


def _redacted_setup_action(step: dict[str, Any], *, action_type: str, value: str, sensitive: bool, config: dict[str, Any]) -> dict[str, Any]:
    action = {
        "type": action_type,
        "selector": step.get("selector"),
        "name": step.get("name"),
        "label": step.get("label"),
        "placeholder": step.get("placeholder"),
        "text": step.get("text"),
        "value": value,
        "env": step.get("env"),
        "sensitive": sensitive,
    }
    return _redact_obj(action, config=config, force_redact={"value", "text"} if sensitive else set())


def _css_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _safe_page_title(page: Any) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def _execute_action(page: Any, state: dict[str, Any], action: BrowserAction) -> dict[str, Any]:
    try:
        before_url = page.url
        if action.type == "none":
            return {"ok": True, "navigation": False, "console_errors": 0}
        if action.type == "wait":
            page.wait_for_timeout(750)
            return {"ok": True, "navigation": False, "console_errors": 0}
        if action.type == "back":
            page.go_back(wait_until="networkidle")
            return {"ok": True, "navigation": page.url != before_url, "console_errors": 0, "final_url": page.url}
        if action.type == "scroll":
            page.mouse.wheel(0, 700)
            page.wait_for_timeout(300)
            return {"ok": True, "navigation": False, "console_errors": 0}
        if action.type == "find":
            found = _find_text_on_page(page, action.text or action.value or "")
            page.wait_for_timeout(300)
            return {"ok": found, "navigation": False, "console_errors": 0, "found": found}
        if not action.ref:
            return {"ok": False, "error": f"Action {action.type} requires ref.", "navigation": False, "console_errors": 0}
        locator = page.locator(f'[data-uxtest-ref="{action.ref}"]').first
        if action.type == "click":
            locator.click(timeout=5000)
        elif action.type == "type":
            locator.fill(action.value or action.text or "", timeout=5000)
        elif action.type == "select":
            locator.select_option(action.value or action.text or "", timeout=5000)
        _wait_after_action(page, before_url)
        return {"ok": True, "navigation": page.url != before_url, "console_errors": 0, "final_url": page.url}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "navigation": page.url != before_url if 'before_url' in locals() else False, "console_errors": 0, "final_url": page.url}


def _find_text_on_page(page: Any, text: str) -> bool:
    target = re.sub(r"\s+", " ", text).strip()
    if not target:
        return False
    return bool(
        page.evaluate(
            """
            (target) => {
              const needle = target.toLowerCase();
              const candidates = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6,a,button,p,li,dt,dd,div,section,article'))
                .filter((el) => {
                  const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                  if (!text || !text.toLowerCase().includes(needle)) return false;
                  const style = window.getComputedStyle(el);
                  return style.visibility !== 'hidden' && style.display !== 'none';
                })
                .sort((a, b) => {
                  const ah = /^H[1-6]$/.test(a.tagName) ? 0 : 1;
                  const bh = /^H[1-6]$/.test(b.tagName) ? 0 : 1;
                  if (ah !== bh) return ah - bh;
                  return a.getBoundingClientRect().top - b.getBoundingClientRect().top;
                });
              const found = candidates[0];
              if (!found) {
                return window.find(target, false, false, true, false, true, false);
              }
              found.scrollIntoView({ block: 'center', inline: 'nearest' });
              return true;
            }
            """,
            target,
        )
    )


def _settle_page(page: Any) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=2000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=2000)
    except Exception:
        pass
    page.wait_for_timeout(150)


def _wait_after_action(page: Any, before_url: str) -> None:
    try:
        page.wait_for_function("url => window.location.href !== url", arg=before_url, timeout=3000)
    except Exception:
        pass
    _settle_page(page)


def _trace_event(step: int, state: dict[str, Any], decision: BrowserDecision, result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_type": "step",
        "step": step,
        "ts": utc_now(),
        "url": state["url"],
        "page_title": state["page_title"],
        "observation": {
            "screenshot": state.get("screenshot"),
            "a11y_audit": None,
            "interactive_elements": len(state.get("interactive_elements") or []),
            "interactive_elements_sample": (state.get("interactive_elements") or [])[:20],
            "headings": (state.get("headings") or [])[:20],
            "visible_text_preview": state.get("visible_text", "")[:1200],
        },
        "model_decision": {
            "driver": decision.driver,
            "thinking": decision.thinking,
            "frustration": decision.frustration,
            "status": decision.status,
            "raw_response": _redact_obj(decision.raw_response, config=config),
            "edsl": _redact_obj(decision.edsl, config=config),
        },
        "action": _redact_obj(decision.action.model_dump(), config=config),
        "result": result,
        "thinking": decision.thinking,
        "frustration": decision.frustration,
        "status": decision.status,
    }


def _compact_trace_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": event.get("step"),
        "url": event.get("url"),
        "status": event.get("status"),
        "action": event.get("action"),
        "result": event.get("result"),
        "frustration": event.get("frustration"),
    }


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _count_trace_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _is_success(page: Any, study: dict[str, Any]) -> bool:
    body = page.locator("body").inner_text(timeout=3000).lower()
    criteria = str(study.get("success_criteria") or "").lower()
    if "order number" in body or "order confirmed" in body:
        return True
    if criteria and all(token in body for token in re.findall(r"[a-z0-9]+", criteria)[:4]):
        return True
    return False


def _playwright_version() -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version("playwright")
    except Exception:
        return "unknown"


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _resolve_project_path(project_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else project_root / path


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise StoreError(f"EDSL response did not contain JSON: {text[:200]}", exit_code=1)
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise StoreError("EDSL response JSON was not an object.", exit_code=1)
    return data


def _empty_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _coerce_frustration(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, min(10, int(value)))
    text = str(value).strip().lower()
    labels = {
        "none": 0,
        "low": 2,
        "medium": 5,
        "moderate": 5,
        "high": 8,
        "critical": 10,
    }
    if text in labels:
        return labels[text]
    match = re.search(r"\d+", text)
    if match:
        return max(0, min(10, int(match.group(0))))
    return 0
