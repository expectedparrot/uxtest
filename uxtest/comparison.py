from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .store import Store, atomic_write_text, read_json, utc_now


def write_comparison_report(
    store: Store,
    *,
    title: str,
    study_ids: list[str],
    output_name: str,
) -> Path:
    comparisons_dir = store.path / "comparisons"
    comparisons_dir.mkdir(exist_ok=True)
    path = comparisons_dir / output_name
    studies = [_load_study_summary(store, study_id) for study_id in study_ids]
    atomic_write_text(path, render_comparison_report(title=title, studies=studies))
    return path


def render_comparison_report(*, title: str, studies: list[dict[str, Any]]) -> str:
    rows = "\n".join(_study_row(study) for study in studies)
    finding_sections = "\n".join(_finding_section(study) for study in studies)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{_h(title)} - uxtest comparison</title>
    <style>
      :root {{
        --ink: #17202a;
        --muted: #66717f;
        --line: #d7dde4;
        --band: #f4f6f8;
        --accent: #176b5c;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        color: var(--ink);
        background: #fff;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1.42;
      }}
      header {{ padding: 24px 28px; color: #fff; background: #202b34; }}
      main {{ max-width: 1180px; margin: 0 auto; padding: 24px 28px 48px; }}
      h1, h2, h3, p {{ margin-top: 0; }}
      h1 {{ margin-bottom: 8px; font-size: 2rem; line-height: 1.08; letter-spacing: 0; }}
      h2 {{ margin: 26px 0 12px; font-size: 1.25rem; }}
      table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--line); }}
      th, td {{ padding: 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }}
      th {{ color: var(--muted); background: var(--band); font-size: .78rem; text-transform: uppercase; }}
      .muted {{ color: var(--muted); }}
      .badge {{
        display: inline-flex;
        align-items: center;
        min-height: 24px;
        border-radius: 999px;
        padding: 0 9px;
        color: #fff;
        background: var(--accent);
        font-size: .78rem;
        font-weight: 800;
      }}
      .finding {{
        margin: 12px 0;
        padding: 12px;
        border: 1px solid var(--line);
        border-radius: 8px;
      }}
      .links a {{ margin-right: 10px; }}
      @media (max-width: 820px) {{
        header, main {{ padding-left: 16px; padding-right: 16px; }}
        table, thead, tbody, th, td, tr {{ display: block; }}
        thead {{ display: none; }}
        td {{ border-bottom: 0; }}
        tr {{ border-bottom: 1px solid var(--line); }}
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>{_h(title)}</h1>
      <p class="muted">Generated {_h(utc_now())}</p>
    </header>
    <main>
      <section>
        <h2>Variant Summary</h2>
        <table>
          <thead>
            <tr>
              <th>Study</th>
              <th>Mode</th>
              <th>Completion</th>
              <th>Mean Steps</th>
              <th>Mean Frustration</th>
              <th>Max Frustration</th>
              <th>Runs</th>
              <th>Personas</th>
              <th>Latest Run</th>
              <th>EDSL Questions</th>
              <th>Outcomes</th>
              <th>Artifacts</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Findings</h2>
        {finding_sections}
      </section>
    </main>
  </body>
</html>
"""


def _load_study_summary(store: Store, study_id: str) -> dict[str, Any]:
    study = store.load_study(study_id)
    study_dir = store.study_dir(study_id)
    analysis_dir = store.study_dir(study_id) / "analysis"
    findings = read_json(analysis_dir / "findings.json") if (analysis_dir / "findings.json").exists() else {"findings": []}
    scores = read_json(analysis_dir / "scores.json") if (analysis_dir / "scores.json").exists() else {}
    runs = _load_runs(study_dir)
    rel_base = Path("..") / "studies" / study_id / "analysis"
    return {
        "study": study,
        "findings": findings,
        "scores": scores,
        "runs": runs,
        "trace_summary": _trace_summary(runs),
        "report_href": str(rel_base / "report.html"),
        "log_href": str(rel_base / "log.html"),
    }


def _study_row(summary: dict[str, Any]) -> str:
    study = summary["study"]
    scores = summary["scores"]
    trace_summary = summary["trace_summary"]
    report_href = str(summary["report_href"])
    log_href = str(summary["log_href"])
    latest = trace_summary["latest_run"] or {}
    return f"""<tr>
  <td><strong>{_h(str(study.get("title") or study.get("id")))}</strong><br><span class="muted">{_h(str(study.get("url") or ""))}</span></td>
  <td>{_h(_tag_value(study, "driver") or "n/a")}<br><span class="muted">{_h(_tag_value(study, "device") or "")}</span></td>
  <td>{_pct(scores.get("task_completion_rate"))}</td>
  <td>{_num(scores.get("mean_steps"))}</td>
  <td>{_num(scores.get("mean_frustration"))}</td>
  <td>{_num(scores.get("max_frustration"))}</td>
  <td>{_h(str(trace_summary["run_count"]))}</td>
  <td>{_h(", ".join(trace_summary["personas"]) or "n/a")}</td>
  <td><code>{_h(str(latest.get("run_id") or "n/a"))}</code><br><span class="muted">{_h(str(latest.get("outcome") or ""))} / {_h(str(latest.get("steps_taken") or ""))} steps</span></td>
  <td>{_h(str(trace_summary["pydantic_steps"]))} pydantic<br>{_h(str(trace_summary["fallback_steps"]))} fallback</td>
  <td><code>{_h(json.dumps(scores.get("outcomes") or {}, sort_keys=True))}</code></td>
  <td class="links"><a href="{_h(report_href)}">report</a><a href="{_h(log_href)}">log</a></td>
</tr>"""


def _load_runs(study_dir: Path) -> list[dict[str, Any]]:
    runs_dir = study_dir / "runs"
    runs: list[dict[str, Any]] = []
    if not runs_dir.exists():
        return runs
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        meta_path = run_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = read_json(meta_path)
        except Exception:
            continue
        runs.append({"meta": meta, "trace": _read_trace(run_dir / "trace.jsonl")})
    return runs


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


def _trace_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_runs = sorted(runs, key=lambda run: str((run.get("meta") or {}).get("started_at") or ""))
    latest = (sorted_runs[-1].get("meta") if sorted_runs else None) or {}
    personas = sorted(
        {
            str(((run.get("meta") or {}).get("persona_instance") or {}).get("name"))
            for run in runs
            if ((run.get("meta") or {}).get("persona_instance") or {}).get("name")
        }
    )
    pydantic_steps = 0
    fallback_steps = 0
    for run in runs:
        for event in run.get("trace") or []:
            edsl = ((event.get("model_decision") or {}).get("edsl") or {})
            if edsl.get("question_type") == "pydantic":
                pydantic_steps += 1
            if edsl.get("pydantic_fallback") or edsl.get("question_type") == "free_text_fallback":
                fallback_steps += 1
    return {
        "run_count": len(runs),
        "personas": personas,
        "latest_run": latest,
        "pydantic_steps": pydantic_steps,
        "fallback_steps": fallback_steps,
    }


def _finding_section(summary: dict[str, Any]) -> str:
    study = summary["study"]
    findings = (summary["findings"] or {}).get("findings") or []
    items = "\n".join(_finding_html(finding) for finding in findings) or '<p class="muted">No findings.</p>'
    return f"""<section>
  <h3>{_h(str(study.get("title") or study.get("id")))}</h3>
  {items}
</section>"""


def _finding_html(finding: dict[str, Any]) -> str:
    frequency = finding.get("frequency") or {}
    return f"""<article class="finding">
  <span class="badge">{_h(str(finding.get("severity") or "unknown"))}</span>
  <h3>{_h(str(finding.get("title") or "Finding"))}</h3>
  <p>{_h(str(finding.get("description") or ""))}</p>
  <p class="muted">Affected runs: {_h(str(frequency.get("affected_runs") or 0))} / {_h(str(frequency.get("total_runs") or 0))}</p>
</article>"""


def _tag_value(study: dict[str, Any], prefix: str) -> str:
    needle = f"{prefix}-"
    for tag in study.get("tags") or []:
        text = str(tag)
        if text.startswith(needle):
            return text[len(needle) :]
    return ""


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _h(value: str) -> str:
    return html.escape(value, quote=True)
