from __future__ import annotations

import base64
import html
import json
import mimetypes
from pathlib import Path
from typing import Any

from .store import atomic_write_text


def write_log_report(path: Path, *, study: dict[str, Any], runs: list[dict[str, Any]], study_dir: Path) -> None:
    atomic_write_text(path, render_log_report(study=study, runs=runs, study_dir=study_dir))


def render_log_report(*, study: dict[str, Any], runs: list[dict[str, Any]], study_dir: Path) -> str:
    title = str(study.get("title") or study.get("id") or "UX Study")
    sorted_runs = sorted(runs, key=lambda run: str((run.get("meta") or {}).get("started_at") or ""), reverse=True)
    run_sections = "\n".join(
        _run_html(run, study_dir=study_dir, open_by_default=index == 0)
        for index, run in enumerate(sorted_runs)
    ) or '<p class="muted">No runs found.</p>'
    driver_counts = _driver_counts(sorted_runs)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{_h(title)} - uxtest log</title>
    <style>
      :root {{
        --ink: #17202a;
        --muted: #66717f;
        --line: #d7dde4;
        --paper: #fff;
        --band: #f4f6f8;
        --code: #101820;
        --accent: #176b5c;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        color: var(--ink);
        background: var(--paper);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1.42;
      }}
      header {{
        padding: 24px 28px;
        color: #fff;
        background: #202b34;
      }}
      main {{ max-width: 1280px; margin: 0 auto; padding: 24px 28px 48px; }}
      h1, h2, h3, p {{ margin-top: 0; }}
      h1 {{ margin-bottom: 8px; font-size: 2rem; line-height: 1.08; letter-spacing: 0; }}
      h2 {{ margin: 26px 0 12px; font-size: 1.25rem; }}
      h3 {{ margin-bottom: 8px; font-size: 1rem; }}
      .muted {{ color: var(--muted); }}
      .summary {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
        margin-top: 18px;
      }}
      .tile, .run, .step {{
        border: 1px solid var(--line);
        border-radius: 8px;
        background: #fff;
      }}
      .tile {{ padding: 12px; }}
      .tile strong {{ display: block; margin-top: 4px; font-size: 1.15rem; }}
      .run {{ margin-top: 18px; overflow: hidden; }}
      .run-head {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 16px;
        padding: 14px 16px;
        background: var(--band);
        border-bottom: 1px solid var(--line);
        cursor: pointer;
        list-style: none;
      }}
      .run-head::-webkit-details-marker {{ display: none; }}
      .run-head h3 {{ margin-bottom: 4px; }}
      .run-head .run-title::before {{ content: ">"; display: inline-block; width: 1.1em; color: var(--muted); }}
      .run[open] .run-head .run-title::before {{ content: "v"; }}
      .run-body {{ padding: 14px 16px; }}
      .step {{
        display: grid;
        grid-template-columns: minmax(240px, 420px) minmax(0, 1fr);
        gap: 14px;
        margin: 14px 0;
        padding: 12px;
      }}
      .shot {{
        display: block;
        width: 100%;
        max-height: 360px;
        object-fit: contain;
        border: 1px solid var(--line);
        border-radius: 6px;
        background: #f9fafb;
      }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ padding: 7px 8px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }}
      th {{ width: 150px; color: var(--muted); font-size: .78rem; text-transform: uppercase; }}
      details {{
        margin-top: 10px;
        border: 1px solid var(--line);
        border-radius: 6px;
        background: #fff;
      }}
      summary {{ cursor: pointer; padding: 8px 10px; font-weight: 700; }}
      .run > summary {{ padding: 14px 16px; }}
      pre {{
        margin: 0;
        padding: 10px;
        overflow: auto;
        color: #e8eef5;
        background: var(--code);
        border-radius: 0 0 6px 6px;
        font-size: .82rem;
      }}
      code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .9em; }}
      .badge {{
        display: inline-flex;
        align-items: center;
        min-height: 24px;
        border-radius: 999px;
        padding: 0 9px;
        background: #e5ebf0;
        font-size: .78rem;
        font-weight: 800;
      }}
      .badge.done {{ color: #fff; background: var(--accent); }}
      .badge.error, .badge.gave_up, .badge.max_steps {{ color: #fff; background: #9d2f22; }}
      @media (max-width: 860px) {{
        header, main {{ padding-left: 16px; padding-right: 16px; }}
        .summary, .step {{ grid-template-columns: 1fr; }}
        .run-head {{ display: block; }}
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>{_h(title)} Developer Log</h1>
      <p class="muted">Study {_h(str(study.get("id") or ""))}</p>
    </header>
    <main>
      <section>
        <h2>Study Inputs</h2>
        <div class="summary">
          {_tile("URL", study.get("url", ""))}
          {_tile("Personas", ", ".join(study.get("personas") or []))}
          {_tile("Runs", len(runs))}
          {_tile("Drivers", ", ".join(f"{name}: {count}" for name, count in driver_counts.items()) or "none")}
          {_tile("Status", study.get("status", ""))}
        </div>
        <details open>
          <summary>Task and Success Criteria</summary>
          <pre>{_h(json.dumps({"task": study.get("task"), "success_criteria": study.get("success_criteria")}, indent=2, sort_keys=True))}</pre>
        </details>
      </section>
      <section>
        <h2>Runs</h2>
        {run_sections}
      </section>
    </main>
  </body>
</html>
"""


def _run_html(run: dict[str, Any], *, study_dir: Path, open_by_default: bool) -> str:
    meta = run.get("meta") or {}
    trace = run.get("trace") or []
    run_id = str(meta.get("run_id") or "")
    persona = meta.get("persona_instance") or {}
    drivers = sorted({str((event.get("model_decision") or {}).get("driver") or "") for event in trace if (event.get("model_decision") or {}).get("driver")})
    steps = "\n".join(_step_html(event, run_id=run_id, study_dir=study_dir) for event in trace)
    open_attr = " open" if open_by_default else ""
    animation = _run_animation_link(study_dir, run_id)
    return f"""<details class="run"{open_attr}>
  <summary class="run-head">
    <div class="run-title">
      <h3>{_h(run_id)}</h3>
      <div class="muted">Persona {_h(str(persona.get("name") or ""))} | {_h(str(meta.get("started_at") or ""))}</div>
    </div>
    <span class="badge {_h(str(meta.get("outcome") or ""))}">{_h(str(meta.get("outcome") or "unknown"))}</span>
  </summary>
  <div class="run-body">
    <table>
      <tbody>
        <tr><th>Outcome Detail</th><td>{_h(str(meta.get("outcome_detail") or ""))}</td></tr>
        <tr><th>Animation</th><td>{animation}</td></tr>
        <tr><th>Driver</th><td>{_h(", ".join(drivers) or "unknown")}</td></tr>
        <tr><th>Final URL</th><td>{_h(str(meta.get("final_url") or ""))}</td></tr>
        <tr><th>Steps Taken</th><td>{_h(str(meta.get("steps_taken") or 0))}</td></tr>
      </tbody>
    </table>
    <details>
      <summary>Persona Snapshot</summary>
      <pre>{_json(persona)}</pre>
    </details>
    <details>
      <summary>Resolved Config and Environment</summary>
      <pre>{_json({"resolved_config": meta.get("resolved_config"), "environment": meta.get("environment"), "costs": meta.get("costs")})}</pre>
    </details>
    {steps or '<p class="muted">No trace events recorded.</p>'}
  </div>
</details>"""


def _step_html(event: dict[str, Any], *, run_id: str, study_dir: Path) -> str:
    observation = event.get("observation") or {}
    decision = event.get("model_decision") or {}
    edsl = decision.get("edsl") if isinstance(decision.get("edsl"), dict) else {}
    job = edsl.get("job") if isinstance(edsl.get("job"), dict) else {}
    screenshot = observation.get("screenshot")
    image = ""
    if screenshot:
        src = _screenshot_src(study_dir / "runs" / run_id / str(screenshot))
        image = f'<img class="shot" src="{_h(src)}" alt="Screenshot for step {_h(str(event.get("step") or ""))}" />'
    return f"""<section class="step">
  <div>
    {image or '<p class="muted">No screenshot captured.</p>'}
  </div>
  <div>
    <table>
      <tbody>
        <tr><th>Step</th><td>{_h(str(event.get("step") or ""))}</td></tr>
        <tr><th>URL</th><td>{_h(str(event.get("url") or ""))}</td></tr>
        <tr><th>Page</th><td>{_h(str(event.get("page_title") or ""))}</td></tr>
        <tr><th>Driver</th><td>{_h(str(decision.get("driver") or ""))}</td></tr>
        <tr><th>Question</th><td>{_question_summary(edsl, driver=str(decision.get("driver") or ""))}</td></tr>
        <tr><th>EDSL Job</th><td>{_job_links(job, driver=str(decision.get("driver") or ""))}</td></tr>
        <tr><th>Status</th><td>{_h(str(event.get("status") or ""))}</td></tr>
        <tr><th>Frustration</th><td>{_h(str(event.get("frustration") or 0))}</td></tr>
        <tr><th>Action</th><td><code>{_h(json.dumps(event.get("action") or {}, sort_keys=True))}</code></td></tr>
        <tr><th>Result</th><td><code>{_h(json.dumps(event.get("result") or {}, sort_keys=True))}</code></td></tr>
        <tr><th>Thinking</th><td>{_h(str(event.get("thinking") or ""))}</td></tr>
      </tbody>
    </table>
    {_attempts_html(edsl)}
    <details>
      <summary>Visible Text Preview</summary>
      <pre>{_h(str(observation.get("visible_text_preview") or ""))}</pre>
    </details>
    <details>
      <summary>Interactive Elements Sample</summary>
      <pre>{_json(observation.get("interactive_elements_sample") or [])}</pre>
    </details>
    <details>
      <summary>Model Decision Raw Data</summary>
      <pre>{_json(decision)}</pre>
    </details>
    <details>
      <summary>Full Trace Event</summary>
      <pre>{_json(event)}</pre>
    </details>
  </div>
</section>"""


def _tile(label: str, value: Any) -> str:
    return f'<div class="tile"><span class="muted">{_h(label)}</span><strong>{_h(str(value))}</strong></div>'


def _run_animation_link(study_dir: Path, run_id: str) -> str:
    gif_path = study_dir / "analysis" / "animations" / f"{run_id}.gif"
    if not gif_path.exists():
        return '<span class="muted">Run animation not generated.</span>'
    return f'<a href="animations/{_h(run_id)}.gif">Play session GIF</a>'


def _driver_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        drivers = {
            str((event.get("model_decision") or {}).get("driver") or "")
            for event in run.get("trace") or []
            if (event.get("model_decision") or {}).get("driver")
        }
        label = "+".join(sorted(drivers)) if drivers else "unknown"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _job_links(job: dict[str, Any], *, driver: str) -> str:
    if not job:
        if driver == "edsl":
            return '<span class="muted">EDSL step; remote job metadata was not captured for this legacy run.</span>'
        return '<span class="muted">Heuristic/local step; no EDSL remote job.</span>'
    bits = []
    job_uuid = job.get("job_uuid")
    if job_uuid:
        bits.append(f'<code>{_h(str(job_uuid))}</code>')
    if job.get("progress_url"):
        bits.append(f'<a href="{_h(str(job["progress_url"]))}" target="_blank" rel="noopener">progress</a>')
    if job.get("results_url"):
        bits.append(f'<a href="{_h(str(job["results_url"]))}" target="_blank" rel="noopener">results</a>')
    return " | ".join(bits) if bits else '<span class="muted">No remote job metadata captured.</span>'


def _question_summary(edsl: dict[str, Any], *, driver: str) -> str:
    if driver != "edsl":
        return '<span class="muted">No EDSL question; local heuristic decision.</span>'
    question_type = str(edsl.get("question_type") or "unknown")
    fallback = edsl.get("pydantic_fallback")
    if isinstance(fallback, dict):
        attempts = fallback.get("attempts")
        count = len(attempts) if isinstance(attempts, list) else 0
        return (
            f'<span class="badge">QuestionFreeText fallback</span> '
            f'<span class="muted">after {count} QuestionPydantic attempt(s)</span>'
        )
    if question_type == "pydantic":
        return '<span class="badge done">QuestionPydantic</span>'
    if question_type == "free_text_fallback":
        return '<span class="badge">QuestionFreeText fallback</span>'
    return f'<span class="badge">{_h(question_type)}</span>'


def _attempts_html(edsl: dict[str, Any]) -> str:
    fallback = edsl.get("pydantic_fallback")
    attempts = fallback.get("attempts") if isinstance(fallback, dict) else None
    rows = []
    if isinstance(attempts, list):
        for attempt in attempts:
            if isinstance(attempt, dict):
                rows.append(_attempt_row("QuestionPydantic", attempt))
    if edsl.get("question_type"):
        rows.append(
            _attempt_row(
                str(edsl.get("question_type")),
                {
                    "attempt": edsl.get("attempt"),
                    "ok": not isinstance(fallback, dict),
                    "job": edsl.get("job"),
                    "answer": edsl.get("raw_response") or edsl.get("validated_answer"),
                    "error": (fallback or {}).get("last_error") if isinstance(fallback, dict) else "",
                },
            )
        )
    if not rows:
        return ""
    return f"""<details>
      <summary>Question Attempts</summary>
      <table>
        <thead>
          <tr><th>Question</th><th>Attempt</th><th>OK</th><th>Job</th><th>Answer/Error</th></tr>
        </thead>
        <tbody>
          {"".join(rows)}
        </tbody>
      </table>
    </details>"""


def _attempt_row(label: str, attempt: dict[str, Any]) -> str:
    job = attempt.get("job") if isinstance(attempt.get("job"), dict) else {}
    ok = attempt.get("ok")
    answer = attempt.get("answer")
    error = attempt.get("error")
    detail = error if error else answer
    if not isinstance(detail, str):
        detail = json.dumps(detail, sort_keys=True, default=str)
    return f"""<tr>
      <td>{_h(label)}</td>
      <td>{_h(str(attempt.get("attempt") or ""))}</td>
      <td>{_h("yes" if ok else "no")}</td>
      <td>{_job_links(job, driver="edsl")}</td>
      <td><code>{_h(detail[:500])}</code></td>
    </tr>"""


def _screenshot_src(path: Path) -> str:
    if not path.exists():
        return ""
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(_image_bytes(path)).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def _image_bytes(path: Path) -> bytes:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.thumbnail((1200, 900))
            import io

            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except Exception:
        return path.read_bytes()


def _json(value: Any) -> str:
    return _h(json.dumps(value, indent=2, sort_keys=True, default=str))


def _h(value: str) -> str:
    return html.escape(value, quote=True)
