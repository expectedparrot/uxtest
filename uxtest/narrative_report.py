from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_text
from .trace import study_runs


def write_narrative_report(
    store: Store,
    study_id: str,
    *,
    formats: list[str],
    output_dir: Path | None = None,
    embed_resources: bool = True,
) -> list[Path]:
    requested = _normalize_formats(formats)
    study_dir = store.study_dir(study_id)
    analysis_dir = output_dir or study_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    study = store.load_study(study_id)
    findings = _read_json_if_exists(study_dir / "analysis" / "findings.json")
    scores = _read_json_if_exists(study_dir / "analysis" / "scores.json")
    markdown = render_narrative_markdown(store, study_id, study=study, findings=findings, scores=scores)

    artifacts: list[Path] = []
    md_path = analysis_dir / "narrative_report.md"
    atomic_write_text(md_path, markdown)
    if "md" in requested:
        artifacts.append(md_path)
    if "html" in requested:
        html_path = analysis_dir / "narrative_report.html"
        extra_args = ["--standalone"]
        if embed_resources:
            extra_args.append("--embed-resources")
        _run_pandoc(md_path, html_path, extra_args=extra_args)
        artifacts.append(html_path)
    if "pdf" in requested:
        pdf_path = analysis_dir / "narrative_report.pdf"
        _run_pandoc(md_path, pdf_path, extra_args=[])
        artifacts.append(pdf_path)
    return artifacts


def render_narrative_markdown(
    store: Store,
    study_id: str,
    *,
    study: dict[str, Any] | None = None,
    findings: dict[str, Any] | None = None,
    scores: dict[str, Any] | None = None,
) -> str:
    study = study or store.load_study(study_id)
    findings = findings or {}
    scores = scores or {}
    runs = study_runs(store, study_id)
    title = str(study.get("title") or study_id)

    lines = [
        f"# {title}",
        "",
        "## Context",
        "",
        f"This study evaluated `{study.get('url', '')}` with synthetic visitors controlled through Playwright and EDSL remote inference.",
        "",
        f"Task: {study.get('task', '')}",
        "",
        f"Success criteria: {study.get('success_criteria') or 'Not specified.'}",
        "",
        "## Method",
        "",
        f"- Personas: {', '.join(study.get('personas') or []) or 'Not specified.'}",
        f"- Runs analyzed: {scores.get('runs_analyzed', len(runs))}",
        f"- Mean steps: {_fmt(scores.get('mean_steps'))}",
        f"- Task completion rate: {_percent(scores.get('task_completion_rate'))}",
        f"- Peak frustration: {_fmt(scores.get('max_frustration'))}",
        "",
        "## Main Results",
        "",
    ]

    finding_items = findings.get("findings") if isinstance(findings.get("findings"), list) else []
    if finding_items:
        for item in finding_items:
            lines.extend(
                [
                    f"### {item.get('title') or item.get('id') or 'Finding'}",
                    "",
                    str(item.get("description") or "").strip(),
                    "",
                ]
            )
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            for ev in evidence[:3]:
                details = [str(ev.get("run_id") or "").strip(), f"step {ev.get('step')}" if ev.get("step") else ""]
                lines.append(f"- Evidence: {', '.join(part for part in details if part)}")
            if evidence:
                lines.append("")
    else:
        lines.extend(["No generated findings were available. Review the journey evidence below.", ""])

    lines.extend(["## Journey Evidence", ""])
    for run in runs:
        meta = run["meta"]
        trace = run["trace"]
        persona = ((meta.get("persona_instance") or {}).get("name")) or "unknown persona"
        lines.extend(
            [
                f"### {persona} ({meta.get('run_id') or run['run_dir'].name})",
                "",
                f"Outcome: `{meta.get('outcome')}`. Final URL: `{meta.get('final_url') or ''}`.",
                "",
            ]
        )
        for event in trace:
            action = event.get("action") or {}
            observation = event.get("observation") or {}
            screenshot = observation.get("screenshot")
            lines.extend(
                [
                    f"#### Step {event.get('step')}",
                    "",
                    f"- URL: `{event.get('url') or ''}`",
                    f"- Action: `{action.get('type') or ''}` {action.get('text') or action.get('ref') or ''}",
                    f"- Status: `{event.get('status') or ''}`",
                    f"- Frustration: {_fmt(event.get('frustration'))}",
                ]
            )
            thinking = event.get("thinking") or ((event.get("model_decision") or {}).get("thinking"))
            if thinking:
                lines.append(f"- Thinking: {thinking}")
            if screenshot:
                screenshot_path = run["run_dir"] / str(screenshot)
                rel = _relative_markdown_path(screenshot_path, store.study_dir(study_id) / "analysis")
                lines.extend(["", f"![Step {event.get('step')} screenshot]({rel})"])
            lines.append("")

    lines.extend(
        [
            "## Follow-On Steps",
            "",
            "1. Review the screenshots and EDSL reasoning for each high-friction or failed step.",
            "2. Decide which findings need product/content changes and which need another targeted study.",
            "3. Re-run the same fixture after changes so outcomes can be compared against this baseline.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _normalize_formats(formats: list[str]) -> list[str]:
    requested: list[str] = []
    for value in formats or ["md"]:
        for item in value.split(","):
            normalized = item.strip().lower()
            if normalized:
                requested.append(normalized)
    invalid = sorted(set(requested) - {"md", "html", "pdf"})
    if invalid:
        raise StoreError(f"Unknown report format(s): {', '.join(invalid)}. Use md, html, or pdf.", exit_code=2)
    return requested or ["md"]


def _run_pandoc(input_path: Path, output_path: Path, *, extra_args: list[str]) -> None:
    if shutil.which("pandoc") is None:
        raise StoreError("pandoc is required for HTML/PDF narrative reports. Install pandoc or request --format md.", exit_code=2)
    command = ["pandoc", str(input_path), "-o", str(output_path), *extra_args]
    result = subprocess.run(command, cwd=input_path.parent, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise StoreError(f"pandoc failed writing {output_path.name}: {detail}", exit_code=1)


def _relative_markdown_path(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve()).replace(os.sep, "/")


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.0f}%"
    return "n/a"
