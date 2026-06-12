from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from .store import Store, atomic_write_json, read_json, utc_now
from .report import write_report
from .log_report import write_log_report
from .eval import RULES, detect_patterns
from .uxr import write_uxr_artifacts

AnalysisDriver = Literal["local", "edsl"]


def analyze_study(
    store: Store,
    study_id: str,
    *,
    include_interrupted: bool = False,
    driver: AnalysisDriver = "local",
) -> tuple[Path, Path, Path, Path]:
    store.recover_stale_runs(study_id)
    study_dir = store.study_dir(study_id)
    analysis_dir = study_dir / "analysis"
    analysis_dir.mkdir(exist_ok=True)

    study = store.load_study(study_id)
    runs = _load_runs(store, study_id, include_interrupted=include_interrupted)
    local_findings = _build_findings(study_id, runs)
    local_scores = _build_scores(study_id, runs)
    if driver == "edsl":
        findings, scores = _edsl_analysis(store, study, study_dir, runs, local_findings, local_scores)
    else:
        findings, scores = local_findings, local_scores

    findings_path = analysis_dir / "findings.json"
    scores_path = analysis_dir / "scores.json"
    report_path = analysis_dir / "report.html"
    log_path = analysis_dir / "log.html"
    atomic_write_json(findings_path, findings)
    atomic_write_json(scores_path, scores)
    write_report(report_path, study=study, findings=findings, scores=scores, study_dir=study_dir)
    write_log_report(log_path, study=study, runs=runs, study_dir=study_dir)
    write_uxr_artifacts(analysis_dir, study=study, findings=findings, scores=scores)
    return findings_path, scores_path, report_path, log_path


def _load_runs(store: Store, study_id: str, *, include_interrupted: bool) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for run_dir in store.list_runs(study_id):
        meta_path = run_dir / "meta.json"
        if not meta_path.exists():
            continue
        meta = read_json(meta_path)
        outcome = meta.get("outcome")
        if outcome is None:
            continue
        if outcome == "interrupted" and not include_interrupted:
            continue
        trace = _read_trace(run_dir / "trace.jsonl")
        loaded.append({"run_dir": run_dir, "meta": meta, "trace": trace})
    return loaded


def _read_trace(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                break
            if isinstance(value, dict):
                events.append(value)
    return events


def _build_findings(study_id: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    total_runs = len(runs)
    for run in runs:
        meta = run["meta"]
        trace = run["trace"]
        run_id = meta.get("run_id", "")
        persona = (meta.get("persona_instance") or {}).get("name")

        if meta.get("outcome") == "done" and trace:
            last = trace[-1]
            key = ("navigation", _url_path(meta.get("final_url") or last.get("url")), "completed-flow")
            _add_evidence(
                grouped,
                key,
                title="Task completed successfully",
                severity="low",
                description="At least one run reached the success criteria. Evidence shows the final successful step.",
                run_id=run_id,
                persona=persona,
                event=last,
            )

        if meta.get("outcome") in {"gave_up", "max_steps", "error"}:
            last = trace[-1] if trace else {}
            title, description, category, kind = _outcome_finding(meta, trace)
            key = (category, _url_path(meta.get("final_url") or last.get("url")), kind)
            _add_evidence(
                grouped,
                key,
                title=title,
                severity="high" if meta.get("outcome") != "error" else "critical",
                description=description,
                run_id=run_id,
                persona=persona,
                event=last,
            )

        for event in trace:
            result = event.get("result") or {}
            if result.get("ok") is False:
                key = ("error-handling", _url_path(event.get("url")), "failed-action")
                _add_evidence(
                    grouped,
                    key,
                    title="Browser action failed",
                    severity="medium",
                    description=str(result.get("error") or "A browser action failed."),
                    run_id=run_id,
                    persona=persona,
                    event=event,
                )
            if int(event.get("frustration") or 0) >= 6:
                key = ("trust", _url_path(event.get("url")), "high-frustration")
                _add_evidence(
                    grouped,
                    key,
                    title="High frustration during task",
                    severity="medium",
                    description="One or more runs reached frustration >= 6.",
                    run_id=run_id,
                    persona=persona,
                    event=event,
                )
            recovery = (((event.get("model_decision") or {}).get("edsl") or {}).get("action_recovery") or {})
            if recovery.get("reason") in {"static_text_request", "missing_ref"}:
                recovered_action = recovery.get("recovered_action") or {}
                if recovered_action.get("type") == "find":
                    key = ("navigation", _url_path(event.get("url")), "static-heading-recovery")
                    _add_evidence(
                        grouped,
                        key,
                        title="Model tried to use a static heading as navigation",
                        severity="medium",
                        description="The persona asked to click or explore visible section text that was not an interactive element; uxtest recovered by finding that text on the page.",
                        run_id=run_id,
                        persona=persona,
                        event=event,
                    )

    for pattern in detect_patterns(runs):
        rule = RULES.get(pattern["id"], {})
        for evidence in pattern.get("evidence") or []:
            event = _event_for_evidence(runs, evidence)
            if not event:
                continue
            key = (
                str(rule.get("category") or pattern.get("category") or "navigation"),
                _url_path(evidence.get("url")),
                str(pattern["id"]),
            )
            run_id = str(evidence.get("run_id") or "")
            persona = _persona_for_run(runs, run_id)
            _add_evidence(
                grouped,
                key,
                title=str(rule.get("title") or pattern.get("title") or pattern["id"]),
                severity=str(rule.get("severity") or pattern.get("severity") or "medium"),
                description=_pattern_description(pattern["id"]),
                run_id=run_id,
                persona=persona,
                event=event,
            )

    findings = []
    for index, item in enumerate(grouped.values(), start=1):
        affected_runs = sorted(item.pop("_affected_runs"))
        personas = sorted(p for p in item.pop("_personas") if p)
        finding_id = f"f-{index:03d}"
        item["finding_id"] = finding_id
        for evidence_index, evidence in enumerate(item.get("evidence") or [], start=1):
            evidence["evidence_id"] = f"{finding_id}-e{evidence_index:02d}"
        item["frequency"] = {"affected_runs": len(affected_runs), "total_runs": total_runs}
        item["personas_affected"] = personas
        findings.append(item)

    return {
        "schema_version": 1,
        "study_id": study_id,
        "generated_at": utc_now(),
        "analyzer": {"name": "uxtest-local", "version": "0.1.0"},
        "runs_analyzed": total_runs,
        "findings": findings,
    }


def _add_evidence(
    grouped: dict[tuple[str, str, str], dict[str, Any]],
    key: tuple[str, str, str],
    *,
    title: str,
    severity: str,
    description: str,
    run_id: str,
    persona: str | None,
    event: dict[str, Any],
) -> None:
    category, url_path, _kind = key
    item = grouped.setdefault(
        key,
        {
            "finding_id": "",
            "category": category,
            "severity": severity,
            "title": title,
            "description": description,
            "locations": [{"url_path": url_path, "page_title": event.get("page_title", "")}],
            "evidence": [],
            "wcag_refs": [],
            "_affected_runs": set(),
            "_personas": set(),
        },
    )
    item["_affected_runs"].add(run_id)
    item["_personas"].add(persona)
    screenshot = (event.get("observation") or {}).get("screenshot")
    evidence = {"run_id": run_id, "steps": [event.get("step")]}
    if screenshot:
        evidence["screenshot"] = f"runs/{run_id}/{screenshot}"
    item["evidence"].append(evidence)


def _outcome_finding(meta: dict[str, Any], trace: list[dict[str, Any]]) -> tuple[str, str, str, str]:
    outcome = str(meta.get("outcome") or "unknown")
    if outcome == "error":
        return ("Run ended with an execution error", str(meta.get("outcome_detail") or "Run errored."), "error-handling", "run-error")
    if _mostly_static_heading_attempts(trace):
        return (
            "User looked for section navigation that was not interactive",
            "The persona repeatedly tried to click or explore headings/sections instead of using available links or scrolling.",
            "navigation",
            "static-section-navigation",
        )
    if _ends_in_repeated_non_navigation(trace):
        return (
            "Repeated action did not advance the task",
            "The persona repeated the same action without navigation or observable state advance.",
            "navigation",
            "repeated-non-navigation-outcome",
        )
    if _found_relevant_external_content(trace):
        return (
            "Found relevant external content but did not close the task",
            "The persona reached a relevant external paper/profile page but did not mark the exploratory task complete before the step limit.",
            "content",
            "external-content-no-close",
        )
    return (f"Run ended with {outcome}", str(meta.get("outcome_detail") or "Run did not complete successfully."), "navigation", outcome)


def _mostly_static_heading_attempts(trace: list[dict[str, Any]]) -> bool:
    none_events = [
        event for event in trace
        if ((event.get("action") or {}).get("type") == "none")
        and _looks_like_static_section_request(str((event.get("action") or {}).get("text") or ""))
    ]
    return len(none_events) >= 2 and len(none_events) >= max(2, len(trace) // 2)


def _looks_like_static_section_request(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in ("bio", "research", "publication", "section", "heading"))


def _ends_in_repeated_non_navigation(trace: list[dict[str, Any]]) -> bool:
    if len(trace) < 2:
        return False
    latest = trace[-1]
    previous = trace[-2]
    latest_action = latest.get("action") or {}
    previous_action = previous.get("action") or {}
    return (
        latest_action.get("type"),
        latest_action.get("ref"),
        latest_action.get("text"),
    ) == (
        previous_action.get("type"),
        previous_action.get("ref"),
        previous_action.get("text"),
    ) and (latest.get("result") or {}).get("navigation") is False and (previous.get("result") or {}).get("navigation") is False


def _found_relevant_external_content(trace: list[dict[str, Any]]) -> bool:
    for event in trace:
        result = event.get("result") or {}
        final_url = str(result.get("final_url") or event.get("url") or "")
        if any(host in final_url for host in ("arxiv.org", "nber.org", "scholar.google", "papers.ssrn.com")):
            return True
    return False


def _build_scores(study_id: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(runs)
    outcomes = Counter(run["meta"].get("outcome") for run in runs)
    completed = outcomes.get("done", 0)
    steps = [int(run["meta"].get("steps_taken") or 0) for run in runs]
    frustrations = [
        int(event.get("frustration") or 0)
        for run in runs
        for event in run["trace"]
    ]
    abandonment = Counter(
        _url_path(run["meta"].get("final_url"))
        for run in runs
        if run["meta"].get("outcome") in {"gave_up", "max_steps", "error"}
    )
    completion_rate = completed / total if total else 0
    return {
        "schema_version": 1,
        "study_id": study_id,
        "generated_at": utc_now(),
        "runs_analyzed": total,
        "task_completion_rate": completion_rate,
        "outcomes": dict(sorted(outcomes.items())),
        "mean_steps": mean(steps) if steps else 0,
        "mean_frustration": mean(frustrations) if frustrations else 0,
        "max_frustration": max(frustrations) if frustrations else 0,
        "abandonment_points": dict(sorted(abandonment.items())),
        "synthetic_sus_score": round(50 + (completion_rate * 40) - min(20, mean(frustrations) * 2 if frustrations else 0), 1),
        "methodology": "Local deterministic summary from run meta.json and trace.jsonl; not a validated SUS instrument.",
    }


def _edsl_analysis(
    store: Store,
    study: dict[str, Any],
    study_dir: Path,
    runs: list[dict[str, Any]],
    local_findings: dict[str, Any],
    local_scores: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from .runner import _load_env, _parse_json_object

    _load_env(Path.cwd() / ".env")
    _load_env(store.root / ".env")
    from edsl import FileStore, Model, QuestionFreeText, Scenario

    config = store.load_config()
    defaults = config.get("defaults", {})
    summaries = [_run_summary(run) for run in runs]
    scenario_data: dict[str, Any] = {
        "study": study,
        "run_summaries": summaries,
        "local_findings": local_findings,
        "local_scores": local_scores,
    }
    first_screenshot = _first_screenshot_path(study_dir, runs)
    screenshot_instruction = ""
    if first_screenshot is not None:
        scenario_data["evidence_screenshot"] = FileStore(str(first_screenshot))
        screenshot_instruction = "Evidence screenshot: {{ scenario.evidence_screenshot }}\n"

    scenario = Scenario(scenario_data)
    model = Model(str(defaults.get("model", "gpt-4o")), temperature=float(defaults.get("temperature", 0.2)))
    question = QuestionFreeText(
        question_name="ux_analysis",
        question_text=(
            "You are analyzing browser-agent UX study runs.\n"
            "Study:\n{{ scenario.study }}\n"
            "Run summaries:\n{{ scenario.run_summaries }}\n"
            "Local deterministic findings:\n{{ scenario.local_findings }}\n"
            "Local deterministic scores:\n{{ scenario.local_scores }}\n"
            f"{screenshot_instruction}"
            "Return only compact JSON with keys findings and score_adjustments.\n"
            "findings must be a list. Each finding should include title, severity, category, description, "
            "locations, evidence, and personas_affected when known. Use only evidence run ids and steps present in run_summaries. "
            "score_adjustments may include methodology_notes but must not invent completion counts."
        ),
    )
    results = question.by(scenario).by(model).run(cache=True)
    answer = results.to_dict()["data"][0]["answer"]["ux_analysis"]
    parsed = _parse_json_object(answer if isinstance(answer, str) else str(answer))
    findings = _normalize_edsl_findings(study, runs, parsed, local_findings)
    scores = dict(local_scores)
    notes = (parsed.get("score_adjustments") or {}).get("methodology_notes") if isinstance(parsed.get("score_adjustments"), dict) else None
    scores["analyzer"] = {"name": "uxtest-edsl", "model": str(defaults.get("model", "gpt-4o"))}
    if notes:
        scores["methodology"] = f"{scores.get('methodology', '')} EDSL analysis notes: {notes}"
    return findings, scores


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    meta = run.get("meta") or {}
    persona = meta.get("persona_instance") or {}
    return {
        "run_id": meta.get("run_id"),
        "outcome": meta.get("outcome"),
        "outcome_detail": meta.get("outcome_detail"),
        "final_url": meta.get("final_url"),
        "persona": persona.get("name"),
        "persona_traits": persona.get("resolved"),
        "steps": [
            {
                "step": event.get("step"),
                "url": event.get("url"),
                "page_title": event.get("page_title"),
                "screenshot": (event.get("observation") or {}).get("screenshot"),
                "thinking": event.get("thinking"),
                "frustration": event.get("frustration"),
                "action": event.get("action"),
                "result": event.get("result"),
                "status": event.get("status"),
            }
            for event in (run.get("trace") or [])
        ],
    }


def _first_screenshot_path(study_dir: Path, runs: list[dict[str, Any]]) -> Path | None:
    for run in runs:
        run_id = (run.get("meta") or {}).get("run_id")
        if not run_id:
            continue
        for event in run.get("trace") or []:
            screenshot = (event.get("observation") or {}).get("screenshot")
            if not screenshot:
                continue
            path = study_dir / "runs" / str(run_id) / str(screenshot)
            if path.exists():
                return path
    return None


def _event_for_evidence(runs: list[dict[str, Any]], evidence: dict[str, Any]) -> dict[str, Any] | None:
    run_id = str(evidence.get("run_id") or "")
    step = evidence.get("step")
    for run in runs:
        if str((run.get("meta") or {}).get("run_id") or "") != run_id:
            continue
        for event in run.get("trace") or []:
            if event.get("step") == step:
                return event
    return None


def _persona_for_run(runs: list[dict[str, Any]], run_id: str) -> str | None:
    for run in runs:
        meta = run.get("meta") or {}
        if str(meta.get("run_id") or "") == run_id:
            return ((meta.get("persona_instance") or {}).get("name"))
    return None


def _pattern_description(rule_id: str) -> str:
    return {
        "login_detour": "An exploratory action led to a login/sign-up page before the persona had enough product information.",
        "dead_docs_link": "A docs or pricing action was selected, but the browser observed no navigation.",
        "generic_cta_confusion": "A generic CTA such as Get started, Continue, or Open example caused a detour or failed action.",
        "repeated_non_navigation": "The same action was repeated without a navigation or observable state advance.",
    }.get(rule_id, f"Detected trace pattern {rule_id}.")


def _normalize_edsl_findings(
    study: dict[str, Any],
    runs: list[dict[str, Any]],
    parsed: dict[str, Any],
    local_findings: dict[str, Any],
) -> dict[str, Any]:
    raw_findings = parsed.get("findings")
    if not isinstance(raw_findings, list) or not raw_findings:
        findings = dict(local_findings)
        findings["analyzer"] = {"name": "uxtest-edsl", "fallback": "no_model_findings"}
        return findings

    run_ids = {str((run.get("meta") or {}).get("run_id")) for run in runs if (run.get("meta") or {}).get("run_id")}
    normalized = []
    for index, item in enumerate(raw_findings, start=1):
        if not isinstance(item, dict):
            continue
        evidence = []
        for ev in item.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            run_id = str(ev.get("run_id") or "")
            if run_id not in run_ids:
                continue
            steps = ev.get("steps") if isinstance(ev.get("steps"), list) else [ev.get("step")]
            entry = {"run_id": run_id, "steps": [step for step in steps if step is not None]}
            screenshot = _evidence_screenshot_for_run_step(runs, run_id, entry["steps"][0] if entry["steps"] else None)
            if screenshot:
                entry["screenshot"] = f"runs/{run_id}/{screenshot}"
            evidence.append(entry)
        normalized.append(
            {
                "finding_id": f"f-{index:03d}",
                "category": str(item.get("category") or "navigation"),
                "severity": str(item.get("severity") or "medium"),
                "title": str(item.get("title") or "Model-generated finding"),
                "description": str(item.get("description") or ""),
                "locations": item.get("locations") if isinstance(item.get("locations"), list) else [],
                "evidence": _with_evidence_ids(f"f-{index:03d}", evidence),
                "wcag_refs": item.get("wcag_refs") if isinstance(item.get("wcag_refs"), list) else [],
                "personas_affected": item.get("personas_affected") if isinstance(item.get("personas_affected"), list) else [],
                "frequency": {"affected_runs": len({ev["run_id"] for ev in evidence}), "total_runs": len(runs)},
            }
        )
    return {
        "schema_version": 1,
        "study_id": study.get("id"),
        "generated_at": utc_now(),
        "analyzer": {"name": "uxtest-edsl", "version": "0.1.0"},
        "runs_analyzed": len(runs),
        "findings": normalized or local_findings.get("findings", []),
    }


def _with_evidence_ids(finding_id: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, item in enumerate(evidence, start=1):
        item["evidence_id"] = f"{finding_id}-e{index:02d}"
    return evidence


def _evidence_screenshot_for_run_step(runs: list[dict[str, Any]], run_id: str, step: Any) -> str | None:
    for run in runs:
        if str((run.get("meta") or {}).get("run_id")) != run_id:
            continue
        for event in run.get("trace") or []:
            if step is not None and event.get("step") != step:
                continue
            screenshot = (event.get("observation") or {}).get("screenshot")
            if screenshot:
                return str(screenshot)
    return None


def _url_path(url: Any) -> str:
    if not url:
        return ""
    text = str(url)
    if "://" not in text:
        return text
    tail = text.split("://", 1)[1]
    path = tail.split("/", 1)[1] if "/" in tail else ""
    path = "/" + path
    return path.split("?", 1)[0] or "/"
