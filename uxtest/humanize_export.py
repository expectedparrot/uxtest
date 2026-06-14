from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_json, atomic_write_text, read_json, read_yaml


@dataclass(frozen=True)
class ScreenshotScenario:
    scenario_id: str
    run_id: str
    persona: str
    step: int | str
    url: str
    page_title: str
    screenshot_path: Path
    screenshot_relative_to_script: str
    visible_text_preview: str
    synthetic_action: str
    synthetic_thinking: str
    synthetic_status: str
    frustration: int | float | None
    outcome: str
    selection_reason: str
    choice_options: list[str]

    def to_manifest(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "persona": self.persona,
            "step": self.step,
            "url": self.url,
            "page_title": self.page_title,
            "screenshot": str(self.screenshot_path),
            "visible_text_preview": self.visible_text_preview,
            "synthetic_action": self.synthetic_action,
            "synthetic_thinking": self.synthetic_thinking,
            "synthetic_status": self.synthetic_status,
            "frustration": self.frustration,
            "outcome": self.outcome,
            "selection_reason": self.selection_reason,
            "choice_options": self.choice_options,
        }


TEMPLATE_QUESTIONS = {
    "task-discovery": [
        (
            "interpretation",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "What do you think this page is for? Mention anything that is unclear.",
        ),
        (
            "next_click",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "What would you click next? Choose the closest option.",
        ),
        (
            "next_click_reason",
            "Look at this screenshot again: {{ scenario.screenshot }}\n\n"
            "Why did you choose that next action?",
        ),
        (
            "confidence",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "How confident are you that you know what to do next?",
        ),
    ],
    "credibility": [
        (
            "credibility_evidence",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "What evidence makes this company or product seem credible or not credible?",
        ),
        (
            "missing_proof",
            "Look at this screenshot again: {{ scenario.screenshot }}\n\n"
            "What proof, details, or reassurance would you need before taking the next step?",
        ),
        (
            "next_click",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "If you wanted to keep evaluating credibility, what would you click next?",
        ),
        (
            "confidence",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "How confident would you feel continuing evaluation from this screen?",
        ),
    ],
    "conversion": [
        (
            "target_path",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "If your goal were to take the main next step, which visible option would you choose?",
        ),
        (
            "conversion_friction",
            "Look at this screenshot again: {{ scenario.screenshot }}\n\n"
            "What, if anything, makes the next step confusing, risky, or less appealing?",
        ),
        (
            "confidence",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "How confident are you that this screen gives you a clear path forward?",
        ),
    ],
    "comprehension": [
        (
            "summary",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "In your own words, summarize what this content is saying.",
        ),
        (
            "confusing_terms",
            "Look at this screenshot again: {{ scenario.screenshot }}\n\n"
            "Which words, claims, or visual elements are confusing or too vague?",
        ),
        (
            "next_click",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "If you wanted to learn more, what would you click next?",
        ),
        (
            "confidence",
            "Look at this screenshot: {{ scenario.screenshot }}\n\n"
            "How confident are you that you understood the message?",
        ),
    ],
}


DEFAULT_HUMANIZE_CSS = """
.edsl-question img,
.edsl-question-text img,
.edsl-question-presentation img,
.edsl-scenario img,
main img,
form img,
img {
  display: block;
  width: auto !important;
  max-width: min(100%, 760px) !important;
  max-height: 70vh !important;
  height: auto !important;
  object-fit: contain !important;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  margin: 0.75rem 0 1rem;
}
""".strip()


def export_humanize_survey(
    store: Store,
    study_id: str,
    *,
    template: str = "task-discovery",
    screenshots: str = "representative",
    max_screenshots: int = 8,
    output: Path | None = None,
    survey_name: str | None = None,
) -> tuple[Path, Path]:
    if template not in TEMPLATE_QUESTIONS:
        raise StoreError(f"Unsupported humanize template {template!r}.", exit_code=2)
    if max_screenshots < 1:
        raise StoreError("--max-screenshots must be at least 1.", exit_code=2)

    study_dir = store.study_dir(study_id)
    study = read_yaml(study_dir / "study.yaml")
    analysis_dir = study_dir / "analysis"
    output_path = output or analysis_dir / "humanize_survey.py"
    if not output_path.is_absolute():
        output_path = (store.root / output_path).resolve()
    manifest_path = output_path.with_suffix(".manifest.json")

    scenarios = collect_screenshot_scenarios(
        store,
        study_id,
        selection=screenshots,
        max_screenshots=max_screenshots,
        script_dir=output_path.parent,
    )
    if not scenarios:
        raise StoreError(
            f"Study {study_id!r} has no trace screenshots to export. Run the study with screenshots enabled.",
            exit_code=2,
        )

    script = render_humanize_script(
        study=study,
        scenarios=scenarios,
        template=template,
        survey_name=survey_name or f"{study.get('title') or study_id} Human Validation",
    )
    atomic_write_text(output_path, script)
    atomic_write_json(
        manifest_path,
        {
            "schema_version": 1,
            "study_id": study_id,
            "template": template,
            "screenshots": screenshots,
            "max_screenshots": max_screenshots,
            "scenario_count": len(scenarios),
            "script": str(output_path),
            "scenarios": [scenario.to_manifest() for scenario in scenarios],
        },
    )
    return output_path, manifest_path


def collect_screenshot_scenarios(
    store: Store,
    study_id: str,
    *,
    selection: str,
    max_screenshots: int,
    script_dir: Path,
) -> list[ScreenshotScenario]:
    candidates: list[tuple[dict[str, Any], Path, dict[str, Any], str]] = []
    for run_dir in store.list_runs(study_id):
        meta_path = run_dir / "meta.json"
        trace_path = run_dir / "trace.jsonl"
        if not meta_path.exists() or not trace_path.exists():
            continue
        try:
            meta = read_json(meta_path)
        except Exception:
            continue
        trace = _read_trace(trace_path)
        events = [event for event in trace if _event_screenshot_path(run_dir, event) is not None]
        if not events:
            continue
        for event, reason in _select_events(events, selection=selection):
            candidates.append((event, run_dir, meta, reason))

    deduped: list[tuple[dict[str, Any], Path, dict[str, Any], str]] = []
    seen: set[tuple[str, str]] = set()
    for event, run_dir, meta, reason in candidates:
        screenshot = str((event.get("observation") or {}).get("screenshot") or "")
        key = (run_dir.name, screenshot)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((event, run_dir, meta, reason))
        if len(deduped) >= max_screenshots:
            break

    scenarios: list[ScreenshotScenario] = []
    for index, (event, run_dir, meta, reason) in enumerate(deduped, start=1):
        screenshot_path = _event_screenshot_path(run_dir, event)
        if screenshot_path is None:
            continue
        scenarios.append(_scenario_from_event(index, event, run_dir, meta, screenshot_path, script_dir, reason))
    return scenarios


def render_humanize_script(
    *,
    study: dict[str, Any],
    scenarios: list[ScreenshotScenario],
    template: str,
    survey_name: str,
) -> str:
    scenario_rows = [
        {
            "scenario_id": scenario.scenario_id,
            "run_id": scenario.run_id,
            "persona": scenario.persona,
            "step": scenario.step,
            "url": scenario.url,
            "page_title": scenario.page_title,
            "screenshot": scenario.screenshot_relative_to_script,
            "visible_text_preview": scenario.visible_text_preview,
            "synthetic_action": scenario.synthetic_action,
            "synthetic_thinking": scenario.synthetic_thinking,
            "synthetic_status": scenario.synthetic_status,
            "frustration": scenario.frustration,
            "outcome": scenario.outcome,
            "selection_reason": scenario.selection_reason,
            "choice_options": scenario.choice_options,
        }
        for scenario in scenarios
    ]
    question_specs = TEMPLATE_QUESTIONS[template]
    free_text_import = "QuestionFreeText"
    lines = [
        "from __future__ import annotations",
        "",
        "import argparse",
        "from pathlib import Path",
        "",
        "from edsl import FileStore, Scenario, ScenarioList, Survey",
        f"from edsl.questions import {free_text_import}, QuestionLinearScale, QuestionMultipleChoice",
        "",
        "",
        "BASE_DIR = Path(__file__).resolve().parent",
        f"STUDY_ID = {str(study.get('id') or '').__repr__()}",
        f"STUDY_TITLE = {str(study.get('title') or '').__repr__()}",
        f"DEFAULT_SURVEY_NAME = {survey_name.__repr__()}",
        f"HUMANIZE_SCHEMA = {{'survey': {{'custom_css': {DEFAULT_HUMANIZE_CSS.__repr__()}}}}}",
        f"SCENARIO_ROWS = {json.dumps(scenario_rows, indent=2)}",
        "",
        "",
        "def build_scenarios() -> ScenarioList:",
        "    scenarios = []",
        "    for row in SCENARIO_ROWS:",
        "        data = dict(row)",
        "        data['screenshot'] = FileStore(str(BASE_DIR / row['screenshot']))",
        "        scenarios.append(Scenario(data))",
        "    return ScenarioList(scenarios)",
        "",
        "",
        "def build_survey() -> Survey:",
        "    questions = [",
    ]
    for name, text in question_specs:
        if name == "confidence":
            lines.extend(
                [
                    "        QuestionLinearScale(",
                    f"            question_name={name.__repr__()},",
                    f"            question_text={text.__repr__()},",
                    "            question_options=[1, 2, 3, 4, 5],",
                    "            option_labels={1: 'Not confident', 5: 'Very confident'},",
                    "        ),",
                ]
            )
        elif name in {"next_click", "target_path"}:
            lines.extend(
                [
                    "        QuestionMultipleChoice(",
                    f"            question_name={name.__repr__()},",
                    f"            question_text={text.__repr__()},",
                    "            question_options='{{ scenario.choice_options }}',",
                    "        ),",
                ]
            )
        else:
            lines.extend(
                [
                    "        QuestionFreeText(",
                    f"            question_name={name.__repr__()},",
                    f"            question_text={text.__repr__()},",
                    "        ),",
                ]
            )
    lines.extend(
        [
            "    ]",
            "    return Survey(questions)",
            "",
            "",
            "def main() -> None:",
            "    parser = argparse.ArgumentParser(description='Launch or inspect a uxtest screenshot validation survey.')",
            "    parser.add_argument('--launch', action='store_true', help='Call EDSL humanize() and create the human survey.')",
            "    parser.add_argument('--name', default=DEFAULT_SURVEY_NAME, help='Human survey name.')",
            "    parser.add_argument('--visibility', default='private', choices=['private', 'public', 'unlisted'])",
            "    args = parser.parse_args()",
            "",
            "    survey = build_survey()",
            "    scenarios = build_scenarios()",
            "    print(f'Study: {STUDY_ID} - {STUDY_TITLE}')",
            "    print(f'Scenarios: {len(scenarios)} screenshot(s)')",
            "    if not args.launch:",
            "        print('Dry run only. Re-run with --launch to call humanize().')",
            "        return",
            "    info = survey.by(scenarios).humanize(",
        "        human_survey_name=args.name,",
        "        scenario_list_method='ordered',",
        "        survey_visibility=args.visibility,",
        "        humanize_schema=HUMANIZE_SCHEMA,",
        "    )",
            "    print(info)",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )
    return "\n".join(lines)


def _select_events(events: list[dict[str, Any]], *, selection: str) -> list[tuple[dict[str, Any], str]]:
    if selection == "all":
        return [(event, "all") for event in events]
    if selection == "first":
        return [(events[0], "first")]
    if selection == "last":
        return [(events[-1], "last")]
    if selection == "first-last":
        return [(events[0], "first"), (events[-1], "last")]
    if selection in {"high-frustration", "confusing"}:
        return [(max(events, key=lambda event: float(event.get("frustration") or 0)), selection)]
    if selection == "representative":
        selected = [(events[0], "first")]
        high = max(events, key=lambda event: float(event.get("frustration") or 0))
        selected.append((high, "highest_frustration"))
        selected.append((events[-1], "last"))
        return selected
    raise StoreError(f"Unsupported screenshot selection {selection!r}.", exit_code=2)


def _scenario_from_event(
    index: int,
    event: dict[str, Any],
    run_dir: Path,
    meta: dict[str, Any],
    screenshot_path: Path,
    script_dir: Path,
    reason: str,
) -> ScreenshotScenario:
    action = event.get("action") or {}
    result = event.get("result") or {}
    observation = event.get("observation") or {}
    persona = meta.get("persona_instance") or {}
    action_text = " ".join(
        str(value)
        for value in (action.get("type"), action.get("text"), action.get("ref"), result.get("description"))
        if value
    )
    return ScreenshotScenario(
        scenario_id=f"screenshot_{index:03d}",
        run_id=str(meta.get("run_id") or run_dir.name),
        persona=str(persona.get("name") or meta.get("persona") or ""),
        step=event.get("step") or "",
        url=str(event.get("url") or ""),
        page_title=str(event.get("page_title") or ""),
        screenshot_path=screenshot_path,
        screenshot_relative_to_script=_relative_path(screenshot_path, script_dir),
        visible_text_preview=str(observation.get("visible_text_preview") or "")[:1200],
        synthetic_action=action_text[:500],
        synthetic_thinking=str(event.get("thinking") or "")[:1000],
        synthetic_status=str(event.get("status") or ""),
        frustration=event.get("frustration"),
        outcome=str(meta.get("outcome") or ""),
        selection_reason=reason,
        choice_options=_choice_options_from_event(event),
    )


def _event_screenshot_path(run_dir: Path, event: dict[str, Any]) -> Path | None:
    screenshot = (event.get("observation") or {}).get("screenshot")
    if not screenshot:
        return None
    path = run_dir / str(screenshot)
    return path if path.exists() else None


def _read_trace(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("event_type", "step") == "step":
                events.append(value)
    return events


def _choice_options_from_event(event: dict[str, Any], *, max_options: int = 12) -> list[str]:
    observation = event.get("observation") or {}
    elements = observation.get("interactive_elements_sample") or []
    options: list[str] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        label = _element_label(element)
        if label:
            options.append(label)
    options.extend(
        [
            "Scroll down",
            "Go back",
            "I would not click yet / I need more information",
            "Other visible option",
        ]
    )
    return _dedupe_options(options)[:max_options]


def _element_label(element: dict[str, Any]) -> str:
    text_keys = ("text", "label", "name", "accessible_name", "placeholder", "alt")
    text = ""
    for key in text_keys:
        value = element.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            break
    if not text:
        href = element.get("href")
        if isinstance(href, str) and href.strip():
            text = href.strip()
    if not text:
        ref = element.get("ref")
        text = str(ref).strip() if ref else ""
    if not text:
        return ""
    role = str(element.get("role") or element.get("tag") or "").strip()
    text = " ".join(text.split())[:80]
    if role and role.lower() not in text.lower():
        return f"{text} ({role})"
    return text


def _dedupe_options(options: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for option in options:
        normalized = " ".join(str(option).split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output


def _relative_path(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())
