from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .store import atomic_write_text, utc_now


def write_uxr_artifacts(
    analysis_dir: Path,
    *,
    study: dict[str, Any],
    findings: dict[str, Any],
    scores: dict[str, Any],
) -> tuple[Path, Path, Path]:
    plan_path = analysis_dir / "study_plan.md"
    report_path = analysis_dir / "uxr_report.html"
    protocol_path = analysis_dir / "human_test_protocol.md"
    atomic_write_text(plan_path, render_study_plan(study))
    atomic_write_text(report_path, render_uxr_report(study=study, findings=findings, scores=scores))
    atomic_write_text(protocol_path, render_human_protocol(study=study, findings=findings, scores=scores))
    return plan_path, report_path, protocol_path


def render_study_plan(study: dict[str, Any]) -> str:
    method = _method_for_study(study)
    research_question = str(study.get("research_question") or _infer_research_question(study))
    hypotheses = study.get("hypotheses") if isinstance(study.get("hypotheses"), list) else []
    hypothesis_lines = "\n".join(f"- {item}" for item in hypotheses) or "- Synthetic users will reveal task friction before human testing."
    personas = ", ".join(study.get("personas") or [])
    return f"""# Study Plan: {study.get("title") or study.get("id")}

Generated: {utc_now()}

## Research Question
{research_question}

## Method
{method}

## Task
{study.get("task") or ""}

## Target URL
{study.get("url") or ""}

## Success Criteria
{study.get("success_criteria") or "Not specified."}

## Personas
{personas or "Not specified."}

## Hypotheses
{hypothesis_lines}

## Evidence To Collect
- Browser path and final URL
- Step-level screenshots
- Persona reasoning and frustration
- Failed actions, detours, repeated actions, and task completion

## Limitations
- Synthetic findings are product signals, not a substitute for recruited human participants.
- Findings should be reviewed against screenshots and traces before roadmap decisions.
"""


def render_uxr_report(*, study: dict[str, Any], findings: dict[str, Any], scores: dict[str, Any]) -> str:
    title = str(study.get("title") or study.get("id") or "UX Research Report")
    findings_list = findings.get("findings") or []
    top_findings = _sorted_findings(findings_list)[:5]
    completion = round(float(scores.get("task_completion_rate") or 0) * 100)
    recommendations = "\n".join(_recommendation_item(finding) for finding in top_findings) or "<li>No major design changes recommended from this run set.</li>"
    finding_cards = "\n".join(_finding_card(finding) for finding in top_findings) or '<p class="muted">No findings generated.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_h(title)} - UXR Report</title>
  <style>
    :root {{ --ink: #17202a; --muted: #66717f; --line: #d7dde4; --band: #f5f7fa; --accent: #176b5c; --bad: #9d2f22; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.45; }}
    header {{ padding: 32px; color: #fff; background: #202b34; }}
    main {{ max-width: 1060px; margin: 0 auto; padding: 28px 32px 48px; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ max-width: 860px; margin-bottom: 8px; font-size: 2.2rem; line-height: 1.08; letter-spacing: 0; }}
    h2 {{ margin: 28px 0 12px; font-size: 1.25rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .tile, .finding {{ border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .tile {{ padding: 16px; }}
    .label {{ color: var(--muted); font-size: .78rem; font-weight: 800; text-transform: uppercase; }}
    .value {{ margin-top: 4px; font-size: 1.7rem; font-weight: 800; }}
    .finding {{ margin: 12px 0; padding: 16px; }}
    .badge {{ display: inline-flex; min-height: 24px; align-items: center; border-radius: 999px; padding: 0 9px; background: #e8edf2; font-size: .76rem; font-weight: 800; text-transform: uppercase; }}
    .badge.high, .badge.critical {{ color: #fff; background: var(--bad); }}
    .badge.medium {{ background: #f5d27a; }}
    .muted {{ color: var(--muted); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    @media (max-width: 760px) {{ header, main {{ padding-left: 18px; padding-right: 18px; }} .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{_h(title)}</h1>
    <p class="muted">Stakeholder report generated {_h(utc_now())}</p>
  </header>
  <main>
    <section class="grid">
      {_tile("Task completion", f"{completion}%")}
      {_tile("Runs analyzed", scores.get("runs_analyzed", 0))}
      {_tile("Findings", len(findings_list))}
    </section>

    <section>
      <h2>Executive Summary</h2>
      <p>{_h(_executive_summary(study, findings_list, completion))}</p>
    </section>

    <section>
      <h2>Recommended Design Actions</h2>
      <ol>{recommendations}</ol>
    </section>

    <section>
      <h2>Top Findings</h2>
      {finding_cards}
    </section>

    <section>
      <h2>Research Notes</h2>
      <p class="muted">Review <code>report.html</code> for screenshots and <code>log.html</code> for step-level traces, prompts, persona state, and EDSL job metadata.</p>
    </section>
  </main>
</body>
</html>
"""


def render_human_protocol(*, study: dict[str, Any], findings: dict[str, Any], scores: dict[str, Any]) -> str:
    findings_list = _sorted_findings(findings.get("findings") or [])
    probe_lines = "\n".join(_probe_for_finding(finding) for finding in findings_list[:6]) or "- What, if anything, felt unclear during the task?"
    personas = ", ".join(study.get("personas") or [])
    return f"""# Human Test Protocol: {study.get("title") or study.get("id")}

Generated: {utc_now()}

## Study Goal
Validate whether issues observed in synthetic runs reproduce with recruited participants.

## Participant Profile
Recruit participants matching or approximating: {personas or "the study personas"}.

## Moderator Setup
- Start URL: {study.get("url") or ""}
- Ask participant to think aloud.
- Do not explain labels or rescue the participant unless they are blocked.
- Capture screen recording, final URL, task success, time on task, and post-task confidence.

## Task Scenario
{study.get("task") or ""}

## Success Criteria
{study.get("success_criteria") or "Participant reaches the intended endpoint and can explain what happened."}

## Follow-Up Probes From Synthetic Findings
{probe_lines}

## Post-Task Questions
- What did you expect would happen when you clicked the last primary action?
- Was there any point where you were unsure what to do next?
- What information did you need but could not find?
- How confident are you that you completed the task successfully? Why?

## Metrics To Record
- Task success
- Time on task
- Number of major detours
- Confidence rating
- Severity of observed breakdowns
"""


def _method_for_study(study: dict[str, Any]) -> str:
    tags = {str(tag) for tag in study.get("tags") or []}
    if any(tag.startswith("driver-edsl") for tag in tags):
        return "Synthetic moderated usability simulation with EDSL vision-capable personas."
    if any(tag.startswith("driver-scripted") for tag in tags):
        return "Deterministic scripted UX regression fixture."
    return "Synthetic usability study against a live browser session."


def _infer_research_question(study: dict[str, Any]) -> str:
    return f"Can target users complete the task, and where do they encounter friction? Task: {study.get('task') or ''}"


def _sorted_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(findings, key=lambda finding: (order.get(str(finding.get("severity") or "low"), 4), str(finding.get("finding_id") or "")))


def _executive_summary(study: dict[str, Any], findings: list[dict[str, Any]], completion: int) -> str:
    high = [finding for finding in findings if str(finding.get("severity")) in {"critical", "high"}]
    if high:
        return f"Synthetic runs found {len(high)} high-priority issue(s) for the task, with {completion}% completion. The strongest evidence should be reviewed before human validation or release."
    if findings:
        return f"Synthetic runs completed with {completion}% task completion and produced lower-severity usability signals worth reviewing."
    return f"Synthetic runs completed with {completion}% task completion and produced no major findings."


def _recommendation_item(finding: dict[str, Any]) -> str:
    title = str(finding.get("title") or "Finding")
    category = str(finding.get("category") or "ux")
    return f"<li><strong>{_h(title)}:</strong> {_h(_recommendation_for_category(category))}</li>"


def _recommendation_for_category(category: str) -> str:
    if category == "navigation":
        return "Clarify destination labels and ensure clicks visibly advance the user toward the task goal."
    if category == "content":
        return "Replace generic CTA language with specific action labels and supporting context."
    if category == "error-handling":
        return "Fix failed interactions and expose recoverable feedback for blocked actions."
    if category == "trust":
        return "Add reassurance, progress cues, or clearer explanations at the point of uncertainty."
    return "Review the evidence and convert the observation into a concrete design change."


def _finding_card(finding: dict[str, Any]) -> str:
    severity = str(finding.get("severity") or "low").lower()
    evidence = finding.get("evidence") or []
    evidence_ids = ", ".join(str(item.get("evidence_id") or item.get("run_id") or "") for item in evidence[:4])
    return f"""<article class="finding">
  <span class="badge {severity}">{_h(severity)}</span>
  <h3>{_h(str(finding.get("finding_id") or ""))}: {_h(str(finding.get("title") or ""))}</h3>
  <p>{_h(str(finding.get("description") or ""))}</p>
  <p class="muted">Evidence: {_h(evidence_ids or "none")}</p>
</article>"""


def _probe_for_finding(finding: dict[str, Any]) -> str:
    title = str(finding.get("title") or "the observed issue").lower()
    return f"- When you reached the area related to '{title}', what did you expect would happen next?"


def _tile(label: str, value: Any) -> str:
    return f'<div class="tile"><div class="label">{_h(label)}</div><div class="value">{_h(str(value))}</div></div>'


def _h(value: str) -> str:
    return html.escape(value, quote=True)
