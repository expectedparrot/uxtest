from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from uuid import uuid4

from edsl.caching import Cache

from .browser import (
    capture_state as _capture_state,
    classify_action_outcome as _classify_action_outcome,
    execute_action as _execute_action,
    find_text_on_page as _find_text_on_page,
    safe_page_title as _safe_page_title,
    settle_page as _settle_page,
    wait_after_action as _wait_after_action,
)
from .decisions import heuristic_decision as _heuristic_decision, scripted_decision as _scripted_decision
from .models import ActionType, BrowserAction, BrowserDecision, BrowserDecisionAnswer, RunDriver
from .store import Store, StoreError, atomic_write_json, utc_now
from .stop_quality import compact_stop_hint, event_has_enough_evidence


PYDANTIC_ANSWERING_INSTRUCTIONS = (
    "Return ONLY one minified JSON object that directly matches the response schema. "
    "Do not wrap it in an answer key. Do not include a comment key. Do not include markdown."
)


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
                    decision = _edsl_decision(study, persona_doc, resolved_config, state, run_dir, store.root, recent_events, step)
                decision = _normalize_stop_decision(study, resolved_config, decision)
                action_key = (state["url"], decision.action.type, decision.action.ref, decision.action.text, decision.action.value)
                repeated_action_count = repeated_action_count + 1 if action_key == last_action_key else 1
                last_action_key = action_key
                if repeated_action_count >= 3 and decision.status == "continue":
                    decision.status = "gave_up"
                    decision.thinking = f"{decision.thinking}\nStopped after repeating the same action {repeated_action_count} times."
                result = _execute_action(page, state, decision.action)
                if _should_stop_after_action(study, decision, result):
                    decision = decision.model_copy(
                        update={
                            "status": "done",
                            "thinking": _append_observed_stop_reason(decision.thinking, result),
                        }
                    )
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


def _normalize_stop_decision(study: dict[str, Any], config: dict[str, Any], decision: BrowserDecision) -> BrowserDecision:
    if decision.status == "done" and decision.action.type != "none":
        return decision.model_copy(
            update={
                "action": BrowserAction(type="none"),
                "thinking": _append_done_action_override_reason(decision.thinking, decision.action),
            }
        )
    if _should_auto_stop_with_evidence(study, config, decision):
        return decision.model_copy(
            update={
                "action": BrowserAction(type="none"),
                "status": "done",
                "thinking": _append_auto_stop_reason(decision.thinking),
            }
        )
    return decision


def _should_auto_stop_with_evidence(study: dict[str, Any], config: dict[str, Any], decision: BrowserDecision) -> bool:
    if decision.status != "continue":
        return False
    if decision.driver not in {"edsl", "scripted"}:
        return False
    if config.get("auto_stop_on_enough_evidence") is False:
        return False
    if not _is_exploratory_study(study):
        return False
    return _decision_has_enough_evidence(decision)


def _decision_has_enough_evidence(decision: BrowserDecision) -> bool:
    return event_has_enough_evidence(
        {
            "thinking": decision.thinking,
            "action": {
                "text": decision.action.text,
            },
        }
    )


def _is_exploratory_study(study: dict[str, Any]) -> bool:
    mode = str(study.get("mode") or "").lower()
    if mode:
        if any(term in mode for term in ("task-discovery", "content-comprehension", "information-architecture", "feature-findability", "credibility", "conversion", "enterprise-demo")):
            return True
        if any(term in mode for term in ("checkout", "transaction", "form-submit")):
            return False
    text = " ".join(str(study.get(key) or "") for key in ("task", "success_criteria")).lower()
    exploratory_markers = (
        "can explain",
        "explain why",
        "figure out",
        "identify",
        "what is confusing",
        "what they would do next",
        "would click next",
        "evidence",
        "credibility",
        "find the path",
        "blocked",
        "missing",
    )
    transactional_markers = (
        "place order",
        "complete checkout",
        "submit the form",
        "make a purchase",
        "finish payment",
    )
    return any(marker in text for marker in exploratory_markers) and not any(marker in text for marker in transactional_markers)


def _append_auto_stop_reason(thinking: str) -> str:
    marker = "Auto-stopped because the rationale contains enough evidence to answer this exploratory task."
    thinking = str(thinking or "").strip()
    if marker in thinking:
        return thinking
    return f"{thinking}\n{marker}" if thinking else marker


def _append_done_action_override_reason(thinking: str, action: BrowserAction) -> str:
    marker = f"Status was done, so the requested {action.type} action was not executed."
    thinking = str(thinking or "").strip()
    if marker in thinking:
        return thinking
    return f"{thinking}\n{marker}" if thinking else marker


def _should_stop_after_action(study: dict[str, Any], decision: BrowserDecision, result: dict[str, Any]) -> bool:
    if decision.status != "continue":
        return False
    if not _is_exploratory_study(study):
        return False
    if _action_reached_auth_next_step(study, result):
        return True
    return False


def _action_reached_auth_next_step(study: dict[str, Any], result: dict[str, Any]) -> bool:
    final_url = str(result.get("final_url") or "").lower()
    if not any(part in final_url for part in ("/login", "/signin", "/sign-in", "/signup", "/sign-up", "/auth")):
        return False
    text = " ".join(str(study.get(key) or "") for key in ("task", "success_criteria")).lower()
    return any(marker in text for marker in ("demo", "request access", "contact", "sales", "signup", "sign up", "dashboard", "blocked", "buying next step"))


def _append_observed_stop_reason(thinking: str, result: dict[str, Any]) -> str:
    final_url = str(result.get("final_url") or "")
    marker = f"Stopped after the action reached an authentication or account next-step path: {final_url}."
    thinking = str(thinking or "").strip()
    if marker in thinking:
        return thinking
    return f"{thinking}\n{marker}" if thinking else marker


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


def _edsl_decision(
    study: dict[str, Any],
    persona_doc: dict[str, Any],
    config: dict[str, Any],
    state: dict[str, Any],
    run_dir: Path,
    project_root: Path,
    recent_events: list[dict[str, Any]],
    step: int,
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
    description = _edsl_job_description(study, persona_doc, step)
    last_answer = ""
    last_error = ""
    pydantic_attempts: list[dict[str, Any]] = []
    for attempt in range(1, 3):
        results = None
        result_dict: dict[str, Any] | None = None
        try:
            results = _run_remote_edsl(question, agent, scenario, model, description)
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
                    description,
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
    description: str,
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
    results = _run_remote_edsl(question, agent, scenario, model, f"{description} (json-fallback)")
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


def _run_remote_edsl(
    question: Any, agent: Any, scenario: Any, model: Any, description: str
) -> Any:
    return question.by(agent).by(scenario).by(model).run(
        cache=Cache(),
        disable_remote_inference=False,
        remote_inference_description=description,
        results_description=description,
    )


def _edsl_job_description(study: dict[str, Any], persona_doc: dict[str, Any], step: int) -> str:
    study_name = str(study.get("name") or study.get("title") or study.get("id") or "study")
    persona = str(persona_doc.get("name") or "persona")
    return f"UX Test: {study_name} - {persona}, step {step}"


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
    stop_hint = compact_stop_hint(recent_events)
    events_with_hint = [*recent_events, stop_hint] if stop_hint else recent_events
    if len(recent_events) < 2:
        return events_with_hint
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
        return events_with_hint
    return [
        *events_with_hint,
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


def _trace_event(step: int, state: dict[str, Any], decision: BrowserDecision, result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    event = {
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
    event["stop_signal"] = {
        "enough_evidence": decision.status == "done" or event_has_enough_evidence(event),
        "should_stop_if_exploratory": decision.status == "done" or event_has_enough_evidence(event),
    }
    return event


def _compact_trace_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": event.get("step"),
        "url": event.get("url"),
        "status": event.get("status"),
        "action": event.get("action"),
        "result": event.get("result"),
        "frustration": event.get("frustration"),
        "stop_signal": event.get("stop_signal"),
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
