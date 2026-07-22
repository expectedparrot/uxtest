from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .store import atomic_write_text


def write_report(
    path: Path,
    *,
    study: dict[str, Any],
    findings: dict[str, Any],
    scores: dict[str, Any],
    study_dir: Path | None = None,
) -> None:
    atomic_write_text(
        path,
        render_report(study=study, findings=findings, scores=scores, study_dir=study_dir),
    )


def render_report(
    *,
    study: dict[str, Any],
    findings: dict[str, Any],
    scores: dict[str, Any],
    study_dir: Path | None = None,
) -> str:
    title = str(study.get("title") or study.get("id") or "UX Study Report")
    completion = float(scores.get("task_completion_rate") or 0)
    completion_pct = round(completion * 100)
    findings_list = findings.get("findings") or []
    severity_counts = _severity_counts(findings_list)
    generated_at = str(scores.get("generated_at") or findings.get("generated_at") or "")
    animation_link = _animation_link(study_dir)
    journey = _journey_html(study_dir)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{_h(title)} - uxtest report</title>
    <style>
      :root {{
        color-scheme: light;
        --ink: #1f252d;
        --muted: #606976;
        --line: #d8dde5;
        --paper: #ffffff;
        --band: #f5f7fa;
        --accent: #176b5c;
        --bad: #9d2f22;
        --warn: #946200;
        --ok: #176b5c;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        color: var(--ink);
        background: var(--paper);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1.45;
      }}
      header {{
        padding: 36px 32px 28px;
        color: #fff;
        background: #23313b;
      }}
      main {{ max-width: 1120px; margin: 0 auto; padding: 28px 32px 48px; }}
      h1, h2, h3, p {{ margin-top: 0; }}
      h1 {{ max-width: 850px; margin-bottom: 10px; font-size: 2.4rem; line-height: 1.05; letter-spacing: 0; }}
      h2 {{ margin-bottom: 14px; font-size: 1.35rem; }}
      h3 {{ margin-bottom: 8px; font-size: 1.05rem; }}
      .meta {{ color: #d7dde6; margin: 0; }}
      .section {{ margin-top: 28px; }}
      .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
      .tile, .finding {{
        border: 1px solid var(--line);
        border-radius: 8px;
        background: #fff;
      }}
      .tile {{ padding: 16px; }}
      .tile .label {{ color: var(--muted); font-size: .82rem; font-weight: 700; text-transform: uppercase; }}
      .tile .value {{ margin-top: 6px; font-size: 1.75rem; font-weight: 800; }}
      .summary {{
        display: grid;
        grid-template-columns: 1.2fr .8fr;
        gap: 18px;
        align-items: start;
      }}
      .panel {{
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 18px;
        background: var(--band);
      }}
      .finding {{ margin-bottom: 14px; overflow: hidden; }}
      .finding-head {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        padding: 16px 18px;
        border-bottom: 1px solid var(--line);
        background: var(--band);
      }}
      .finding-body {{ padding: 16px 18px; }}
      .badge {{
        display: inline-flex;
        align-items: center;
        min-height: 26px;
        border-radius: 999px;
        padding: 0 10px;
        font-size: .78rem;
        font-weight: 800;
        text-transform: uppercase;
        background: #e8edf2;
      }}
      .badge.critical, .badge.high {{ color: #fff; background: var(--bad); }}
      .badge.medium {{ color: #332100; background: #f5d27a; }}
      .badge.low {{ color: #163d33; background: #cce9df; }}
      .evidence {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 12px;
        margin-top: 12px;
      }}
      .evidence-item {{
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 10px;
        background: #fff;
      }}
      .evidence-item img {{
        display: block;
        width: 100%;
        max-height: 220px;
        object-fit: contain;
        border: 1px solid var(--line);
        border-radius: 6px;
        background: #f9fafb;
      }}
      .evidence-link {{
        display: block;
        width: 100%;
        padding: 0;
        border: 0;
        background: transparent;
        cursor: zoom-in;
      }}
      .lightbox {{
        position: fixed;
        inset: 0;
        z-index: 20;
        display: none;
        align-items: center;
        justify-content: center;
        padding: 24px;
        background: rgba(18, 25, 33, .84);
      }}
      .lightbox.open {{ display: flex; }}
      .lightbox img {{
        max-width: 96vw;
        max-height: 90vh;
        object-fit: contain;
        border-radius: 8px;
        background: #fff;
      }}
      .journey-preview {{
        display: block; width: 100%; height: 320px; padding: 12px; cursor: zoom-in;
        overflow: hidden; border: 1px solid var(--line); border-radius: 8px; background: var(--band);
      }}
      .journey-preview img {{ display: block; width: 100%; height: 100%; object-fit: contain; }}
      .journey-modal {{ position: fixed; inset: 0; z-index: 30; display: none; padding: 28px; background: rgba(18,25,33,.88); }}
      .journey-modal.open {{ display: grid; grid-template-rows: auto minmax(0,1fr); }}
      .journey-modal-bar {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; color: #fff; background: #23313b; }}
      .journey-modal-bar button {{ padding: 7px 11px; color: #fff; border: 1px solid #89959e; border-radius: 5px; background: transparent; cursor: pointer; }}
      .journey-scroll {{ overflow: auto; background: #f5f7fa; }}
      .journey-scroll img {{ display: block; width: auto; max-width: none; height: auto; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; }}
      th {{ color: var(--muted); font-size: .82rem; text-transform: uppercase; }}
      code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .92em; }}
      .muted {{ color: var(--muted); }}
      @media (max-width: 760px) {{
        header, main {{ padding-left: 18px; padding-right: 18px; }}
        .grid, .summary {{ grid-template-columns: 1fr; }}
        h1 {{ font-size: 2rem; }}
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>{_h(title)}</h1>
      <p class="meta">Study {_h(str(study.get("id") or ""))} | generated {_h(generated_at)}</p>
    </header>
    <main>
      <section class="section grid" aria-label="Score summary">
        {_tile("Completion", f"{completion_pct}%")}
        {_tile("Runs", scores.get("runs_analyzed", 0))}
        {_tile("Mean steps", _round(scores.get("mean_steps")))}
        {_tile("Max frustration", scores.get("max_frustration", 0))}
      </section>

      <section class="section summary">
        <div class="panel">
          <h2>Study</h2>
          <p>{_h(str(study.get("task") or ""))}</p>
          {animation_link}
          <table>
            <tbody>
              <tr><th>URL</th><td>{_h(str(study.get("url") or ""))}</td></tr>
              <tr><th>Status</th><td>{_h(str(study.get("status") or ""))}</td></tr>
              <tr><th>Personas</th><td>{_h(", ".join(study.get("personas") or []))}</td></tr>
            </tbody>
          </table>
        </div>
        <div class="panel">
          <h2>Severity</h2>
          <table>
            <tbody>
              {_severity_rows(severity_counts)}
            </tbody>
          </table>
        </div>
      </section>

      <section class="section">
        <h2>Findings</h2>
        {_findings_html(findings_list, study_dir=study_dir)}
      </section>

      {journey}

      <section class="section">
        <h2>Methodology</h2>
        <p class="muted">{_h(str(scores.get("methodology") or ""))}</p>
      </section>
    </main>
    <div id="lightbox" class="lightbox" role="dialog" aria-modal="true" aria-label="Screenshot preview" onclick="closeShot()">
      <img id="lightbox-image" alt="Expanded evidence screenshot" />
    </div>
    <div id="journey-modal" class="journey-modal" role="dialog" aria-modal="true" aria-label="Journey tree">
      <div class="journey-modal-bar"><strong>Journey tree</strong><button type="button" onclick="closeJourney()">Close</button></div>
      <div class="journey-scroll"><img src="journey/journey.svg" alt="Full-size screenshot-backed journey tree" /></div>
    </div>
    <script>
      function openShot(src) {{
        const box = document.getElementById("lightbox");
        const image = document.getElementById("lightbox-image");
        image.src = src;
        box.classList.add("open");
      }}
      function closeShot() {{
        const box = document.getElementById("lightbox");
        const image = document.getElementById("lightbox-image");
        box.classList.remove("open");
        image.src = "";
      }}
      function openJourney() {{ document.getElementById("journey-modal").classList.add("open"); }}
      function closeJourney() {{ document.getElementById("journey-modal").classList.remove("open"); }}
      document.addEventListener("keydown", function(event) {{
        if (event.key === "Escape") {{ closeShot(); closeJourney(); }}
      }});
    </script>
  </body>
</html>
"""


def _tile(label: str, value: Any) -> str:
    return f"""<div class="tile"><div class="label">{_h(label)}</div><div class="value">{_h(str(value))}</div></div>"""


def _animation_link(study_dir: Path | None) -> str:
    if study_dir is None:
        return ""
    index = study_dir / "analysis" / "animations" / "index.html"
    if not index.exists():
        return ""
    return '<p><a href="animations/index.html">View run animations</a></p>'


def _journey_html(study_dir: Path | None) -> str:
    if study_dir is None:
        return ""
    journey = study_dir / "analysis" / "journey" / "journey.svg"
    if not journey.exists():
        return ""
    return '''<section class="section">
        <h2>Journey tree</h2>
        <p class="muted">Screenshot-backed paths through the interface. Shared prefixes merge; divergent actions branch.</p>
        <button class="journey-preview" type="button" onclick="openJourney()" aria-label="Open full-size journey tree"><img src="journey/journey.svg" alt="Screenshot-backed journey tree preview" /></button>
        <p class="muted">Select the preview to inspect the full-size diagram with horizontal and vertical scrolling.</p>
      </section>'''


def _severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for finding in findings:
        severity = str(finding.get("severity") or "low").lower()
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _severity_rows(counts: dict[str, int]) -> str:
    rows = []
    for severity in ["critical", "high", "medium", "low"]:
        rows.append(f"<tr><th>{_h(severity)}</th><td>{counts.get(severity, 0)}</td></tr>")
    return "\n".join(rows)


def _findings_html(findings: list[dict[str, Any]], *, study_dir: Path | None) -> str:
    if not findings:
        return '<p class="muted">No findings were generated from the analyzed runs.</p>'
    return "\n".join(_finding_html(finding, study_dir=study_dir) for finding in findings)


def _finding_html(finding: dict[str, Any], *, study_dir: Path | None) -> str:
    severity = str(finding.get("severity") or "low").lower()
    frequency = finding.get("frequency") or {}
    affected = frequency.get("affected_runs", 0)
    total = frequency.get("total_runs", 0)
    locations = ", ".join(
        str(location.get("url_path") or "")
        for location in finding.get("locations") or []
        if isinstance(location, dict)
    )
    return f"""<article class="finding">
  <div class="finding-head">
    <div>
      <h3>{_h(str(finding.get("title") or ""))}</h3>
      <div class="muted">{_h(str(finding.get("category") or ""))} | {_h(locations)}</div>
    </div>
    <span class="badge {_h(severity)}">{_h(severity)}</span>
  </div>
  <div class="finding-body">
    <p>{_h(str(finding.get("description") or ""))}</p>
    <p class="muted">Affected runs: {_h(str(affected))} / {_h(str(total))}</p>
    {_evidence_html(finding.get("evidence") or [], study_dir=study_dir)}
  </div>
</article>"""


def _evidence_html(evidence: list[dict[str, Any]], *, study_dir: Path | None) -> str:
    if not evidence:
        return ""
    items = []
    for item in evidence[:6]:
        screenshot = item.get("screenshot")
        image = ""
        if screenshot:
            src = _screenshot_src(str(screenshot), study_dir=study_dir)
            alt = f'Evidence screenshot for {str(item.get("run_id") or "")}'
            image = (
                '<button class="evidence-link" type="button" '
                'onclick="openShot(this.querySelector(&quot;img&quot;).src)">'
                f'<img src="{_h(src)}" alt="{_h(alt)}" />'
                "</button>"
            )
        steps = ", ".join(str(step) for step in item.get("steps") or [] if step is not None)
        evidence_id = str(item.get("evidence_id") or "")
        items.append(
            f"""<div class="evidence-item">
  {image}
  <p class="muted"><code>{_h(evidence_id or str(item.get("run_id") or ""))}</code><br><code>{_h(str(item.get("run_id") or ""))}</code> step {_h(steps)}</p>
</div>"""
        )
    return f'<div class="evidence">{"".join(items)}</div>'


def _screenshot_src(screenshot: str, *, study_dir: Path | None) -> str:
    if study_dir is not None:
        path = study_dir / screenshot
        if path.exists():
            # report.html lives in analysis/, one level below the study root.
            # Link retained evidence rather than copying large base64 payloads
            # into every derived dashboard.
            return f"../{screenshot}"
    return f"../{screenshot}"


def _round(value: Any) -> str:
    try:
        return str(round(float(value), 1))
    except (TypeError, ValueError):
        return "0"


def _h(value: str) -> str:
    return html.escape(value, quote=True)
