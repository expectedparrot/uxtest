from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_json, atomic_write_text, read_yaml
from .rendering import esc_md, md_link, normalize_formats, rel_path, run_pandoc
from .stop_quality import classify_run_stop_quality
from .trace import study_bundle


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def run_batch_manifest(
    store: Store,
    manifest_path: Path,
    *,
    formats: list[str],
    open_reports: bool = False,
) -> list[Path]:
    from .fixtures import run_fixture

    manifest_path = manifest_path.expanduser().resolve()
    manifest = read_yaml(manifest_path)
    fixture_paths = _manifest_fixture_paths(manifest, base_dir=manifest_path.parent)
    if not fixture_paths:
        raise StoreError(f"Batch manifest must list at least one fixture: {manifest_path}", exit_code=2)

    study_ids: list[str] = []
    comparison_paths: list[Path] = []
    for fixture_path in fixture_paths:
        result = run_fixture(store, fixture_path, open_report=open_reports)
        study_ids.extend(str(item) for item in result.get("study_ids") or [])
        comparison = result.get("comparison")
        if isinstance(comparison, Path):
            comparison_paths.append(comparison)

    output_name = str(manifest.get("output_name") or manifest.get("id") or manifest_path.stem)
    title = str(manifest.get("title") or manifest.get("name") or output_name.replace("-", " ").title())
    return write_batch_report(
        store,
        title=title,
        study_ids=study_ids,
        comparison_paths=comparison_paths,
        output_name=output_name,
        formats=formats or _manifest_formats(manifest),
        output_dir=_manifest_output_dir(manifest, base_dir=manifest_path.parent),
    )


def write_batch_report(
    store: Store,
    *,
    title: str,
    study_ids: list[str],
    comparison_paths: list[Path] | None = None,
    output_name: str = "batch-report",
    formats: list[str] | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    requested = normalize_formats(formats or ["md"], allowed={"md", "html", "pdf"}, default=["md"], label="batch report")
    studies = collect_batch_studies(store, study_ids)
    if not studies:
        raise StoreError("Batch report requires at least one study id.", exit_code=2)

    comparisons_dir = output_dir or (store.path / "comparisons")
    comparisons_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(output_name)
    markdown = render_batch_markdown(
        store,
        title=title,
        studies=studies,
        comparison_paths=comparison_paths or [],
        output_dir=comparisons_dir,
    )

    manifest = {
        "schema_version": 1,
        "title": title,
        "study_ids": [study["study_id"] for study in studies],
        "comparison_paths": [rel_path(path, comparisons_dir) for path in comparison_paths or []],
        "output_name": stem,
        "formats": requested,
    }
    atomic_write_json(comparisons_dir / f"{stem}.manifest.json", manifest)

    artifacts: list[Path] = []
    md_path = comparisons_dir / f"{stem}.md"
    atomic_write_text(md_path, markdown)
    if "md" in requested:
        artifacts.append(md_path)
    if "html" in requested:
        html_path = comparisons_dir / f"{stem}.html"
        run_pandoc(md_path, html_path, extra_args=["--standalone", "--embed-resources"], label="batch report")
        artifacts.append(html_path)
    if "pdf" in requested:
        pdf_path = comparisons_dir / f"{stem}.pdf"
        run_pandoc(md_path, pdf_path, extra_args=[], label="batch report")
        artifacts.append(pdf_path)
    return artifacts


def collect_batch_studies(store: Store, study_ids: list[str]) -> list[dict[str, Any]]:
    studies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for study_id in study_ids:
        if study_id in seen:
            continue
        seen.add(study_id)
        studies.append(study_bundle(store, study_id))
    return studies


def render_batch_markdown(
    store: Store,
    *,
    title: str,
    studies: list[dict[str, Any]],
    comparison_paths: list[Path],
    output_dir: Path,
) -> str:
    rollup = _rollup(studies)
    recurring = _recurring_findings(studies)
    reliability = _reliability(studies)
    stop_quality = _stop_quality(studies)
    evidence = _representative_evidence(studies, output_dir=output_dir)

    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        _summary_paragraph(rollup, recurring, reliability),
        "",
        "## Batch Scope",
        "",
        f"- Studies: {rollup['study_count']}",
        f"- Runs analyzed: {rollup['runs_analyzed']}",
        f"- Completed runs: {rollup['outcomes'].get('done', 0)}",
        f"- `max_steps` runs: {rollup['outcomes'].get('max_steps', 0)}",
        f"- Other outcomes: {_outcome_text(rollup['outcomes'], exclude={'done', 'max_steps'})}",
        "",
        "## Study Outcomes",
        "",
        "| Study | Runs | Outcomes | Mean steps | Completion | Report |",
        "|---|---:|---|---:|---:|---|",
    ]
    for item in studies:
        scores = item["scores"]
        outcomes = scores.get("outcomes") if isinstance(scores.get("outcomes"), dict) else {}
        report = item["analysis_dir"] / "report.html"
        report_link = md_link("report.html", report, output_dir) if report.exists() else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    esc_md(str((item["study"].get("title") or item["study_id"]))),
                    str(scores.get("runs_analyzed") or len(item["runs"])),
                    f"`{json.dumps(outcomes, sort_keys=True)}`",
                    _fmt(scores.get("mean_steps")),
                    _percent(scores.get("task_completion_rate")),
                    report_link,
                ]
            )
            + " |"
        )

    lines.extend(["", "## Recurring Findings", ""])
    if recurring:
        for finding in recurring[:12]:
            lines.append(
                f"- **{finding['title']}** ({finding['severity']}, {finding['count']} occurrences across {finding['study_count']} studies): "
                f"{finding['summary']}"
            )
    else:
        lines.append("No repeated findings were detected across the selected studies.")

    lines.extend(["", "## Trace Reliability And Run Quality", ""])
    lines.extend(_reliability_lines(reliability))

    lines.extend(["", "## Run Resolution", ""])
    lines.extend(_stop_quality_lines(stop_quality))

    lines.extend(["", "## Evidence Examples", ""])
    if evidence:
        for item in evidence:
            lines.extend(
                [
                    f"### {item['title']}",
                    "",
                    f"- Study: `{item['study_id']}`",
                    f"- Run: `{item['run_id']}`",
                    f"- Outcome: `{item['outcome']}`",
                    f"- Final URL: `{item['final_url']}`",
                    f"- Why this matters: {item['why']}",
                    "",
                    f"![{item['title']}]({item['screenshot']})",
                    "",
                ]
            )
    else:
        lines.append("No representative screenshots were available.")

    lines.extend(["", "## Comparison Reports", ""])
    if comparison_paths:
        for path in comparison_paths:
            lines.append(f"- {md_link(path.name, path, output_dir)}")
    else:
        lines.append("No comparison report paths were supplied.")

    lines.extend(["", "## Detailed Study Logs", ""])
    for item in studies:
        log_path = item["analysis_dir"] / "log.html"
        if log_path.exists():
            lines.append(f"- `{item['study_id']}`: {md_link('log.html', log_path, output_dir)}")

    lines.extend(
        [
            "",
            "## Recommended Next Steps",
            "",
            *_recommendations(recurring, rollup),
            "",
            "## Caveats",
            "",
            "- This is synthetic UX research using model-controlled personas, not statistical human research.",
            "- Use screenshots, traces, and `log.html` evidence before treating any generated finding as product fact.",
            "- Completion scores are deterministic run summaries, not validated usability metrics.",
            "- Partial EDSL remote results and no-visible-advance actions are surfaced as trace-quality signals.",
            "",
        ]
    )
    return "\n".join(lines)


def _rollup(studies: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes: Counter[str] = Counter()
    runs_analyzed = 0
    for item in studies:
        scores = item["scores"]
        score_outcomes = scores.get("outcomes") if isinstance(scores.get("outcomes"), dict) else {}
        if score_outcomes:
            outcomes.update({str(key): int(value) for key, value in score_outcomes.items()})
            runs_analyzed += int(scores.get("runs_analyzed") or sum(score_outcomes.values()))
        else:
            for run in item["runs"]:
                outcomes[str(run["meta"].get("outcome") or "unknown")] += 1
                runs_analyzed += 1
    return {"study_count": len(studies), "runs_analyzed": runs_analyzed, "outcomes": dict(outcomes)}


def _recurring_findings(studies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in studies:
        for finding in item["findings"]:
            title = str(finding.get("title") or finding.get("id") or "Finding").strip()
            if not title:
                continue
            key = _normalize_key(title)
            existing = grouped.setdefault(
                key,
                {
                    "title": title,
                    "severity": str(finding.get("severity") or "low"),
                    "summary": str(finding.get("summary") or finding.get("description") or "").strip(),
                    "studies": set(),
                    "count": 0,
                },
            )
            existing["count"] += 1
            existing["studies"].add(item["study_id"])
            if SEVERITY_ORDER.get(str(finding.get("severity") or "low"), 9) < SEVERITY_ORDER.get(existing["severity"], 9):
                existing["severity"] = str(finding.get("severity") or "low")
    results = []
    for value in grouped.values():
        if len(value["studies"]) < 2 and value["count"] < 2:
            continue
        value = dict(value)
        value["studies"] = sorted(value["studies"])
        value["study_count"] = len(value["studies"])
        results.append(value)
    return sorted(results, key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), -int(item["count"]), item["title"]))


def _reliability(studies: list[dict[str, Any]]) -> dict[str, Any]:
    partial_jobs: list[dict[str, Any]] = []
    no_visible_change_clicks = 0
    action_outcomes: Counter[str] = Counter()
    max_steps = 0
    enough_evidence_candidates = 0
    for item in studies:
        for run in item["runs"]:
            meta = run["meta"]
            if meta.get("outcome") == "max_steps":
                max_steps += 1
            trace = run["trace"]
            if meta.get("outcome") == "max_steps" and classify_run_stop_quality(meta, trace).get("class") == "enough_evidence_but_continued":
                enough_evidence_candidates += 1
            for event in trace:
                decision = event.get("model_decision") if isinstance(event.get("model_decision"), dict) else {}
                edsl = decision.get("edsl") if isinstance(decision.get("edsl"), dict) else {}
                if edsl.get("partial") or "partial" in str(edsl.get("status") or "").lower():
                    partial_jobs.append({"study_id": item["study_id"], "run_id": meta.get("run_id"), "step": event.get("step")})
                result = event.get("result") if isinstance(event.get("result"), dict) else {}
                action = event.get("action") if isinstance(event.get("action"), dict) else {}
                outcome = str(result.get("action_outcome") or "")
                if outcome:
                    action_outcomes[outcome] += 1
                if action.get("type") == "click" and result.get("ok") and _no_observed_advance(result):
                    no_visible_change_clicks += 1
    return {
        "partial_jobs": partial_jobs,
        "no_visible_change_clicks": no_visible_change_clicks,
        "repeated_no_navigation": no_visible_change_clicks,
        "action_outcomes": dict(sorted(action_outcomes.items())),
        "max_steps": max_steps,
        "enough_evidence_candidates": enough_evidence_candidates,
    }


def _stop_quality(studies: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    for item in studies:
        for run in item["runs"]:
            quality = classify_run_stop_quality(run.get("meta") or {}, run.get("trace") or [])
            class_name = str(quality.get("class") or "unresolved")
            counts[class_name] += 1
            if class_name != "done" and len(examples) < 8:
                examples.append(
                    {
                        "study_id": item["study_id"],
                        "run_id": (run.get("meta") or {}).get("run_id"),
                        "class": class_name,
                        "label": quality.get("label"),
                        "reason": quality.get("reason"),
                        "step": quality.get("step"),
                        "url": quality.get("url"),
                    }
                )
    return {"counts": dict(sorted(counts.items())), "examples": examples}


def _representative_evidence(studies: list[dict[str, Any]], *, output_dir: Path) -> list[dict[str, str]]:
    candidates: list[dict[str, Any]] = []
    for item in studies:
        for run in item["runs"]:
            trace = run["trace"]
            if not trace:
                continue
            selected = _select_evidence_event(trace)
            if selected is None:
                continue
            observation = selected.get("observation") if isinstance(selected.get("observation"), dict) else {}
            screenshot = observation.get("screenshot")
            if not screenshot:
                continue
            run_dir = run["run_dir"]
            screenshot_path = run_dir / str(screenshot)
            if not screenshot_path.exists():
                continue
            meta = run["meta"]
            candidates.append(
                {
                    "study_id": item["study_id"],
                    "run_id": str(meta.get("run_id") or run_dir.name),
                    "outcome": str(meta.get("outcome") or ""),
                    "final_url": str(meta.get("final_url") or ""),
                    "title": _evidence_title(item, run, selected),
                    "why": _evidence_why(run, selected),
                    "screenshot": rel_path(screenshot_path, output_dir),
                    "priority": _evidence_priority(meta, selected),
                }
            )
    selected: list[dict[str, str]] = []
    seen_kind: set[str] = set()
    for item in sorted(candidates, key=lambda value: int(value["priority"])):
        kind = _normalize_key(item["title"])
        if kind in seen_kind:
            continue
        seen_kind.add(kind)
        selected.append({key: str(value) for key, value in item.items() if key != "priority"})
        if len(selected) >= 6:
            break
    return selected


def _select_evidence_event(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(trace):
        status = str(event.get("status") or "")
        observation = event.get("observation") if isinstance(event.get("observation"), dict) else {}
        if status == "done" and observation.get("screenshot"):
            return event
    for event in reversed(trace):
        observation = event.get("observation") if isinstance(event.get("observation"), dict) else {}
        result = event.get("result") if isinstance(event.get("result"), dict) else {}
        if observation.get("screenshot") and _no_observed_advance(result):
            return event
    for event in reversed(trace):
        observation = event.get("observation") if isinstance(event.get("observation"), dict) else {}
        if observation.get("screenshot"):
            return event
    return None


def _evidence_title(item: dict[str, Any], run: dict[str, Any], event: dict[str, Any]) -> str:
    outcome = str(run["meta"].get("outcome") or "")
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    if outcome == "max_steps":
        return "Unresolved path at max steps"
    if event.get("status") == "done":
        return "Successful stopping evidence"
    if action.get("type") == "click":
        return "Click did not visibly advance"
    return str(item["study"].get("title") or item["study_id"])


def _evidence_why(run: dict[str, Any], event: dict[str, Any]) -> str:
    thinking = str(event.get("thinking") or "").strip()
    if thinking:
        return thinking
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    if action.get("text"):
        return f"Representative step selected action: {action.get('text')}."
    return "Representative screenshot from the trace."


def _evidence_priority(meta: dict[str, Any], event: dict[str, Any]) -> int:
    if meta.get("outcome") == "max_steps":
        return 0
    if event.get("status") == "done":
        return 1
    return 2


def _summary_paragraph(rollup: dict[str, Any], recurring: list[dict[str, Any]], reliability: dict[str, Any]) -> str:
    outcomes = rollup["outcomes"]
    top = recurring[0]["title"] if recurring else "No recurring finding dominated the batch"
    return (
        f"This batch synthesized {rollup['study_count']} studies and {rollup['runs_analyzed']} analyzed runs. "
        f"{outcomes.get('done', 0)} runs completed and {outcomes.get('max_steps', 0)} hit `max_steps`. "
        f"The strongest repeated pattern was: {top}. "
        f"The report also flags {reliability['no_visible_change_clicks']} click steps with no visible advance "
        "so reviewers can separate product friction from possible browser-observation limitations."
    )


def _reliability_lines(reliability: dict[str, Any]) -> list[str]:
    lines = [
        f"- Runs ending at `max_steps`: {reliability['max_steps']}",
        f"- `max_steps` runs that may already contain enough evidence: {reliability['enough_evidence_candidates']}",
        f"- Click actions with no visible advance: {reliability['no_visible_change_clicks']}",
        f"- Explicit partial EDSL job markers found in traces: {len(reliability['partial_jobs'])}",
    ]
    outcome_text = _outcome_text({key: int(value) for key, value in (reliability.get("action_outcomes") or {}).items()}, exclude=set())
    if outcome_text != "none":
        lines.append(f"- Action outcomes observed: {outcome_text}")
    if reliability["max_steps"]:
        lines.append("- Treat `max_steps` as an unresolved-run signal, not automatically as a product failure.")
    if reliability["no_visible_change_clicks"]:
        lines.append("- Inspect no-visible-advance clicks in `log.html`; they are the strongest candidates for true dead clicks or selector mismatches.")
    return lines


def _stop_quality_lines(stop_quality: dict[str, Any]) -> list[str]:
    counts = stop_quality.get("counts") if isinstance(stop_quality.get("counts"), dict) else {}
    lines = [f"- Resolution classes: {_outcome_text({key: int(value) for key, value in counts.items()}, exclude=set())}"]
    examples = stop_quality.get("examples") if isinstance(stop_quality.get("examples"), list) else []
    if examples:
        lines.extend(["", "| Study | Run | Class | Step | Reason |", "|---|---|---|---:|---|"])
        for item in examples:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{item.get('study_id')}`",
                        f"`{item.get('run_id')}`",
                        f"`{item.get('class')}`",
                        str(item.get("step") or ""),
                        esc_md(str(item.get("reason") or "")),
                    ]
                )
                + " |"
            )
    return lines


def _no_observed_advance(result: dict[str, Any]) -> bool:
    outcome = result.get("action_outcome")
    if outcome:
        return outcome == "no_visible_change"
    return result.get("navigation") is False


def _recommendations(recurring: list[dict[str, Any]], rollup: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if recurring:
        lines.append("1. Address recurring findings before tuning individual study prompts.")
        lines.append("2. Convert stable repeated findings into expected-flaw checks for future regression runs.")
    else:
        lines.append("1. Inspect individual `log.html` files for high-friction runs.")
    if rollup["outcomes"].get("max_steps", 0):
        lines.append("3. Review `max_steps` traces and decide whether the site needs changes, the task needs narrowing, or the agent needs a stronger stop condition.")
    else:
        lines.append("3. Re-run this batch after product changes to compare outcome stability.")
    lines.append("4. Use human screenshot validation for high-stakes claims before making major product decisions.")
    return lines


def _manifest_fixture_paths(manifest: dict[str, Any], *, base_dir: Path) -> list[Path]:
    values = manifest.get("fixtures")
    if not isinstance(values, list):
        return []
    paths: list[Path] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("path")
        if not isinstance(value, str):
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = base_dir / path
        paths.append(path)
    return paths


def _manifest_formats(manifest: dict[str, Any]) -> list[str]:
    value = manifest.get("formats")
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return ["md", "html"]


def _manifest_output_dir(manifest: dict[str, Any], *, base_dir: Path) -> Path | None:
    value = manifest.get("output_dir")
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _safe_stem(value: str) -> str:
    return _normalize_key(value) or "batch-report"


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    if value is None:
        return ""
    return str(value)


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return ""


def _outcome_text(outcomes: dict[str, int], *, exclude: set[str]) -> str:
    items = [f"{key}={value}" for key, value in sorted(outcomes.items()) if key not in exclude]
    return ", ".join(items) or "none"
