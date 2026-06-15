from __future__ import annotations

import json
import os
import pprint
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_json, atomic_write_text
from .trace import event_screenshot_path, event_thinking, persona_name, run_id, study_bundle


DEFAULT_INTERVIEW_QUESTIONS = [
    "Looking back at your session, what were you trying to accomplish and what did you understand first?",
    "Which moment, if any, was most confusing or confidence-reducing?",
    "Why did you choose your first action?",
    "What evidence or visual cue mattered most to your decision-making?",
    "What change would make this experience easier for someone like you?",
]


def export_agent_list(
    store: Store,
    study_id: str,
    *,
    output: Path | None = None,
    include_screenshots: bool = True,
) -> tuple[Path, Path]:
    study_dir = store.study_dir(study_id)
    analysis_dir = study_dir / "analysis"
    output_path = output or analysis_dir / "agent_list.py"
    if not output_path.is_absolute():
        output_path = (store.root / output_path).resolve()
    agent_rows = collect_agent_rows(store, study_id, script_dir=output_path.parent, include_screenshots=include_screenshots)
    if not agent_rows:
        raise StoreError(f"Study {study_id!r} has no run traces to export as agents.", exit_code=2)
    study = study_bundle(store, study_id)["study"]
    script = render_agent_list_script(study=study, agent_rows=agent_rows)
    manifest_path = output_path.with_suffix(".manifest.json")
    atomic_write_text(output_path, script)
    atomic_write_json(
        manifest_path,
        {
            "schema_version": 1,
            "study_id": study_id,
            "agent_count": len(agent_rows),
            "script": str(output_path),
            "include_screenshots": include_screenshots,
            "agents": [_manifest_agent(row) for row in agent_rows],
        },
    )
    return output_path, manifest_path


def export_interview_script(
    store: Store,
    study_id: str,
    *,
    output: Path | None = None,
    model: str = "gpt-4o",
    questions: list[str] | None = None,
) -> tuple[Path, Path]:
    study_dir = store.study_dir(study_id)
    analysis_dir = study_dir / "analysis"
    output_path = output or analysis_dir / "agent_interview.py"
    if not output_path.is_absolute():
        output_path = (store.root / output_path).resolve()
    agent_rows = collect_agent_rows(store, study_id, script_dir=output_path.parent, include_screenshots=True)
    if not agent_rows:
        raise StoreError(f"Study {study_id!r} has no run traces to interview.", exit_code=2)
    study = study_bundle(store, study_id)["study"]
    script = render_interview_script(
        study=study,
        agent_rows=agent_rows,
        model=model,
        questions=questions or DEFAULT_INTERVIEW_QUESTIONS,
    )
    manifest_path = output_path.with_suffix(".manifest.json")
    atomic_write_text(output_path, script)
    atomic_write_json(
        manifest_path,
        {
            "schema_version": 1,
            "study_id": study_id,
            "agent_count": len(agent_rows),
            "script": str(output_path),
            "model": model,
            "questions": questions or DEFAULT_INTERVIEW_QUESTIONS,
            "agents": [_manifest_agent(row) for row in agent_rows],
        },
    )
    return output_path, manifest_path


def collect_agent_rows(
    store: Store,
    study_id: str,
    *,
    script_dir: Path,
    include_screenshots: bool,
) -> list[dict[str, Any]]:
    bundle = study_bundle(store, study_id)
    study = bundle["study"]
    rows: list[dict[str, Any]] = []
    for run in bundle["runs"]:
        meta = run["meta"]
        trace = run["trace"]
        run_dir = Path(run["run_dir"])
        persona_instance = meta.get("persona_instance") if isinstance(meta.get("persona_instance"), dict) else {}
        persona_snapshot = persona_instance.get("snapshot") if isinstance(persona_instance.get("snapshot"), dict) else {}
        current_persona_name = persona_name(run) or str(meta.get("run_id") or run_dir.name)
        steps = [_step_row(event, run_dir, script_dir, include_screenshots=include_screenshots) for event in trace]
        screenshot_refs = [step["screenshot"] for step in steps if step.get("screenshot")]
        traits = {
            "source": "uxtest",
            "study_id": study_id,
            "study_title": study.get("title"),
            "task": study.get("task"),
            "success_criteria": study.get("success_criteria"),
            "target_url": study.get("url"),
            "run_id": run_id(run),
            "outcome": meta.get("outcome"),
            "outcome_detail": meta.get("outcome_detail"),
            "steps_taken": meta.get("steps_taken"),
            "final_url": meta.get("final_url"),
            "persona_name": current_persona_name,
            "persona_resolved": persona_instance.get("resolved") or {},
            "persona_snapshot": persona_snapshot,
            "journey": steps,
            "screenshot_paths": screenshot_refs,
            "first_impression": _first_thinking(steps),
            "highest_frustration_step": _highest_frustration_step(steps),
            "final_thinking": _final_thinking(steps),
        }
        rows.append(
            {
                "name": f"{current_persona_name}-{run_id(run)}",
                "instruction": _agent_instruction(persona_snapshot, current_persona_name),
                "traits": traits,
                "screenshot_paths": screenshot_refs,
            }
        )
    return rows


def render_agent_list_script(*, study: dict[str, Any], agent_rows: list[dict[str, Any]]) -> str:
    return _script_prelude(study=study, agent_rows=agent_rows) + "\n".join(
        [
            "",
            "",
            "def main() -> None:",
            "    agents = build_agent_list()",
            "    print(f'Study: {STUDY_ID} - {STUDY_TITLE}')",
            "    print(f'Agents: {len(agents)}')",
            "    for agent in agents:",
            "        print(f\"- {agent.name}: {agent.traits.get('outcome')} / {agent.traits.get('steps_taken')} steps\")",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )


def render_interview_script(
    *,
    study: dict[str, Any],
    agent_rows: list[dict[str, Any]],
    model: str,
    questions: list[str],
) -> str:
    question_rows = [{"name": f"q{index:02d}", "text": question} for index, question in enumerate(questions, start=1)]
    return _script_prelude(study=study, agent_rows=agent_rows) + "\n".join(
        [
            "",
            f"DEFAULT_MODEL = {model.__repr__()}",
            f"QUESTION_ROWS = {pprint.pformat(question_rows, width=100)}",
            "",
            "",
            "def build_survey() -> Survey:",
            "    return Survey([",
            "        QuestionFreeText(",
            "            question_name=row['name'],",
            "            question_text=(",
            "                row['text']",
            "                + '\\n\\nYou are answering as the synthetic visitor from this completed UX run.'",
            "                + '\\nUse your persona, journey, screenshots, decisions, and final outcome in your traits.'",
            "            ),",
            "        )",
            "        for row in QUESTION_ROWS",
            "    ])",
            "",
            "",
            "def main() -> None:",
            "    parser = argparse.ArgumentParser(description='Interview rich uxtest trace agents with EDSL.')",
            "    parser.add_argument('--launch', action='store_true', help='Run the interview with EDSL remote inference.')",
            "    parser.add_argument('--model', default=DEFAULT_MODEL)",
            "    args = parser.parse_args()",
            "",
            "    agents = build_agent_list()",
            "    survey = build_survey()",
            "    print(f'Study: {STUDY_ID} - {STUDY_TITLE}')",
            "    print(f'Agents: {len(agents)}')",
            "    print(f'Questions: {len(QUESTION_ROWS)}')",
            "    if not args.launch:",
            "        print('Dry run only. Re-run with --launch to call EDSL remote inference.')",
            "        return",
            "    results = survey.by(agents).by(Model(args.model)).run(remote=True)",
            "    print(results)",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )


def _script_prelude(*, study: dict[str, Any], agent_rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import argparse",
            "from pathlib import Path",
            "",
            "from edsl import Agent, AgentList, FileStore, Model, Survey",
            "from edsl.questions import QuestionFreeText",
            "",
            "BASE_DIR = Path(__file__).resolve().parent",
            f"STUDY_ID = {str(study.get('id') or '').__repr__()}",
            f"STUDY_TITLE = {str(study.get('title') or '').__repr__()}",
            f"AGENT_ROWS = {pprint.pformat(agent_rows, width=120)}",
            "",
            "",
            "def _materialize_screenshots(paths):",
            "    return [FileStore(str(BASE_DIR / path)) for path in paths]",
            "",
            "",
            "def build_agent_list() -> AgentList:",
            "    agents = []",
            "    for row in AGENT_ROWS:",
            "        traits = dict(row['traits'])",
            "        traits['screenshot_files'] = _materialize_screenshots(row.get('screenshot_paths', []))",
            "        agents.append(Agent(name=row['name'], traits=traits, instruction=row.get('instruction') or ''))",
            "    return AgentList(agents)",
        ]
    )


def _step_row(event: dict[str, Any], run_dir: Path, script_dir: Path, *, include_screenshots: bool) -> dict[str, Any]:
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    observation = event.get("observation") if isinstance(event.get("observation"), dict) else {}
    result = event.get("result") if isinstance(event.get("result"), dict) else {}
    screenshot = None
    if include_screenshots and observation.get("screenshot"):
        screenshot_path = event_screenshot_path({"run_dir": run_dir}, event)
        if screenshot_path.exists():
            screenshot = os.path.relpath(screenshot_path.resolve(), script_dir.resolve()).replace(os.sep, "/")
    return {
        "step": event.get("step"),
        "url": event.get("url"),
        "page_title": event.get("page_title"),
        "status": event.get("status"),
        "thinking": event_thinking(event),
        "frustration": event.get("frustration"),
        "action": {
            "type": action.get("type"),
            "ref": action.get("ref"),
            "text": action.get("text"),
            "value": action.get("value"),
        },
        "result": {
            "ok": result.get("ok"),
            "navigation": result.get("navigation"),
            "error": result.get("error"),
            "console_errors": result.get("console_errors"),
        },
        "visible_text_preview": observation.get("visible_text_preview"),
        "headings": observation.get("headings") if isinstance(observation.get("headings"), list) else [],
        "interactive_elements_sample": observation.get("interactive_elements_sample")
        if isinstance(observation.get("interactive_elements_sample"), list)
        else [],
        "screenshot": screenshot,
    }


def _agent_instruction(persona_snapshot: dict[str, Any], persona_name: str) -> str:
    bias = persona_snapshot.get("goals_bias") if isinstance(persona_snapshot, dict) else None
    if bias:
        return str(bias)
    return f"You are the synthetic UX participant {persona_name}. Answer using your recorded journey and evidence."


def _first_thinking(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        if step.get("thinking"):
            return str(step["thinking"])
    return ""


def _final_thinking(steps: list[dict[str, Any]]) -> str:
    for step in reversed(steps):
        if step.get("thinking"):
            return str(step["thinking"])
    return ""


def _highest_frustration_step(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    with_scores = [step for step in steps if isinstance(step.get("frustration"), (int, float))]
    if not with_scores:
        return None
    return max(with_scores, key=lambda step: step.get("frustration") or 0)


def _manifest_agent(row: dict[str, Any]) -> dict[str, Any]:
    traits = row.get("traits") if isinstance(row.get("traits"), dict) else {}
    return {
        "name": row.get("name"),
        "run_id": traits.get("run_id"),
        "persona_name": traits.get("persona_name"),
        "outcome": traits.get("outcome"),
        "steps_taken": traits.get("steps_taken"),
        "screenshot_count": len(row.get("screenshot_paths") or []),
    }
