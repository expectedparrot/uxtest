from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import Store, StoreError, read_json


def read_trace(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                break
            if isinstance(event, dict):
                events.append(event)
    return events


def study_runs(store: Store, study_id: str) -> list[dict[str, Any]]:
    study_dir = store.study_dir(study_id)
    runs_dir = study_dir / "runs"
    runs: list[dict[str, Any]] = []
    if not runs_dir.exists():
        return runs
    for run_dir in sorted(child for child in runs_dir.iterdir() if child.is_dir()):
        meta_path = run_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = read_json(meta_path)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        runs.append({"run_dir": run_dir, "meta": meta, "trace": read_trace(run_dir / "trace.jsonl")})
    return runs


def study_analysis(store: Store, study_id: str) -> dict[str, Any]:
    study_dir = store.study_dir(study_id)
    analysis_dir = study_dir / "analysis"
    findings_doc = read_json_if_exists(analysis_dir / "findings.json")
    scores = read_json_if_exists(analysis_dir / "scores.json")
    findings = findings_doc.get("findings") if isinstance(findings_doc.get("findings"), list) else []
    return {
        "analysis_dir": analysis_dir,
        "findings_doc": findings_doc,
        "findings": findings,
        "scores": scores,
        "report_path": analysis_dir / "report.html",
        "log_path": analysis_dir / "log.html",
        "narrative_report_path": analysis_dir / "narrative_report.md",
    }


def study_bundle(store: Store, study_id: str) -> dict[str, Any]:
    study_dir = store.study_dir(study_id)
    analysis = study_analysis(store, study_id)
    return {
        "study_id": study_id,
        "study": store.load_study(study_id),
        "study_dir": study_dir,
        "runs": study_runs(store, study_id),
        **analysis,
    }


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = read_json(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def run_id(run: dict[str, Any]) -> str:
    meta = run.get("meta") if isinstance(run.get("meta"), dict) else {}
    run_dir = run.get("run_dir")
    fallback = run_dir.name if isinstance(run_dir, Path) else ""
    return str(meta.get("run_id") or fallback)


def persona_name(run: dict[str, Any]) -> str:
    meta = run.get("meta") if isinstance(run.get("meta"), dict) else {}
    persona = meta.get("persona_instance") if isinstance(meta.get("persona_instance"), dict) else {}
    return str(persona.get("name") or "")


def event_screenshot_path(run: dict[str, Any], event: dict[str, Any]) -> Path | None:
    observation = event.get("observation") if isinstance(event.get("observation"), dict) else {}
    screenshot = observation.get("screenshot")
    run_dir = run.get("run_dir")
    if not screenshot or not isinstance(run_dir, Path):
        return None
    return run_dir / str(screenshot)


def event_thinking(event: dict[str, Any]) -> str:
    return str(event.get("thinking") or ((event.get("model_decision") or {}).get("thinking")) or "")


def event_edsl_job(event: dict[str, Any]) -> dict[str, Any]:
    decision = event.get("model_decision") if isinstance(event.get("model_decision"), dict) else {}
    edsl = decision.get("edsl") if isinstance(decision.get("edsl"), dict) else {}
    job = edsl.get("job") if isinstance(edsl.get("job"), dict) else {}
    return job


def summarize_study_trace(store: Store, study_id: str) -> dict[str, Any]:
    runs = study_runs(store, study_id)
    if not runs:
        raise StoreError(f"Study {study_id!r} has no completed run metadata.", exit_code=2)
    return {
        "study_id": study_id,
        "runs": [_summarize_run(run["run_dir"], run["meta"], run["trace"]) for run in runs],
    }


def edsl_jobs_for_study(store: Store, study_id: str) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    for run in study_runs(store, study_id):
        current_run_id = run_id(run)
        persona = persona_name(run)
        for event in run["trace"]:
            decision = event.get("model_decision") or {}
            edsl = decision.get("edsl") or {}
            job = event_edsl_job(event)
            if not isinstance(job, dict) or not job:
                continue
            jobs.append(
                {
                    "run_id": current_run_id,
                    "persona": persona,
                    "step": event.get("step"),
                    "question_type": edsl.get("question_type"),
                    "question_name": edsl.get("question_name"),
                    "model": edsl.get("model"),
                    "job_uuid": job.get("job_uuid"),
                    "progress_url": job.get("progress_url"),
                    "results_url": job.get("results_url"),
                }
            )
    return {"study_id": study_id, "edsl_jobs": jobs}


def _summarize_run(run_dir: Path, meta: dict[str, Any], trace: list[dict[str, Any]]) -> dict[str, Any]:
    persona = (meta.get("persona_instance") or {}).get("name")
    steps = []
    for event in trace:
        action = event.get("action") or {}
        observation = event.get("observation") or {}
        steps.append(
            {
                "step": event.get("step"),
                "status": event.get("status"),
                "url": event.get("url"),
                "page_title": event.get("page_title"),
                "action_type": action.get("type"),
                "action_ref": action.get("ref"),
                "action_text": action.get("text"),
                "thinking": event.get("thinking") or ((event.get("model_decision") or {}).get("thinking")),
                "frustration": event.get("frustration"),
                "screenshot": observation.get("screenshot"),
            }
        )
    return {
        "run_id": meta.get("run_id") or run_dir.name,
        "persona": persona,
        "outcome": meta.get("outcome"),
        "steps_taken": meta.get("steps_taken"),
        "final_url": meta.get("final_url"),
        "steps": steps,
    }
