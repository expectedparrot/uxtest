from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import Store, atomic_write_text
from .rendering import normalize_formats, rel_path, run_pandoc
from .trace import event_screenshot_path, event_thinking, study_bundle


def write_narrative_report(
    store: Store,
    study_id: str,
    *,
    formats: list[str],
    output_dir: Path | None = None,
    embed_resources: bool = True,
) -> list[Path]:
    requested = normalize_formats(formats, allowed={"md", "html", "pdf"}, default=["md"], label="report")
    study_dir = store.study_dir(study_id)
    analysis_dir = output_dir or study_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    bundle = study_bundle(store, study_id)
    study = bundle["study"]
    findings = bundle["findings_doc"]
    scores = bundle["scores"]
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
        run_pandoc(md_path, html_path, extra_args=extra_args, label="narrative report")
        artifacts.append(html_path)
    if "pdf" in requested:
        pdf_path = analysis_dir / "narrative_report.pdf"
        run_pandoc(md_path, pdf_path, extra_args=[], label="narrative report")
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
    bundle = study_bundle(store, study_id)
    runs = bundle["runs"]
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

    lines.extend(_trust_signal_section(runs))

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
            thinking = event_thinking(event)
            if thinking:
                lines.append(f"- Thinking: {thinking}")
            if screenshot:
                screenshot_path = event_screenshot_path(run, event)
                if screenshot_path is None:
                    continue
                rel = rel_path(screenshot_path, store.study_dir(study_id) / "analysis")
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

def _trust_signal_section(runs: list[dict[str, Any]]) -> list[str]:
    signals = _collect_trust_signals(runs)
    lines = [
        "## Trust And Seriousness Signals",
        "",
        "This section lists credibility cues the synthetic visitors actually saw or mentioned during the run. Use it to separate visible evidence from assumptions made after the fact.",
        "",
    ]
    if not signals:
        lines.extend(
            [
                "No explicit trust, proof, pricing, security, customer, team, case study, or demo cues were detected in the recorded text or model reasoning.",
                "",
            ]
        )
        return lines
    for signal in signals[:12]:
        lines.append(
            f"- Step {signal['step']} ({signal['persona']}, {signal['run_id']}): "
            f"{signal['category']} cue: {signal['excerpt']}"
        )
    lines.append("")
    return lines


def _collect_trust_signals(runs: list[dict[str, Any]]) -> list[dict[str, str]]:
    keywords = {
        "customer proof": ["customer", "customers", "case study", "case studies", "logo", "logos", "testimonial", "trusted by"],
        "company substance": ["about", "team", "founder", "leadership", "company", "research", "publication"],
        "commercial readiness": ["demo", "sales", "enterprise", "pricing", "dashboard", "support", "contact"],
        "risk reduction": ["security", "privacy", "compliance", "documentation", "docs", "api", "open-source", "open source"],
    }
    signals: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for run in runs:
        meta = run["meta"]
        persona = ((meta.get("persona_instance") or {}).get("name")) or "unknown persona"
        run_id = str(meta.get("run_id") or run["run_dir"].name)
        for event in run["trace"]:
            observation = event.get("observation") if isinstance(event.get("observation"), dict) else {}
            parts = [
                str(observation.get("visible_text_preview") or ""),
                str(event.get("thinking") or ""),
                str(((event.get("model_decision") or {}).get("thinking")) or ""),
            ]
            text = " ".join(part for part in parts if part).strip()
            if not text:
                continue
            lower_text = text.lower()
            for category, terms in keywords.items():
                if not any(term in lower_text for term in terms):
                    continue
                excerpt = _excerpt(text, terms)
                key = (run_id, category, excerpt)
                if key in seen:
                    continue
                seen.add(key)
                signals.append(
                    {
                        "run_id": run_id,
                        "persona": str(persona),
                        "step": str(event.get("step") or "?"),
                        "category": category,
                        "excerpt": excerpt,
                    }
                )
    return signals


def _excerpt(text: str, terms: list[str], *, max_length: int = 180) -> str:
    normalized = " ".join(text.split())
    lower = normalized.lower()
    index = min((lower.find(term) for term in terms if term in lower), default=0)
    start = max(0, index - 70)
    end = min(len(normalized), start + max_length)
    excerpt = normalized[start:end].strip()
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(normalized):
        excerpt = excerpt + "..."
    return excerpt


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
