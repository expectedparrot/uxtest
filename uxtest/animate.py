from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_text, read_json


def animate_study(store: Store, study_id: str, *, delay_cs: int = 250, max_width: int = 520) -> Path:
    study_dir = store.study_dir(study_id)
    if not study_dir.exists():
        raise StoreError(f"Study {study_id!r} not found.", exit_code=2)
    animations_dir = study_dir / "analysis" / "animations"
    animations_dir.mkdir(parents=True, exist_ok=True)

    generated: list[dict[str, str]] = []
    for run_dir in store.list_runs(study_id):
        meta_path = run_dir / "meta.json"
        trace_path = run_dir / "trace.jsonl"
        if not meta_path.exists() or not trace_path.exists():
            continue
        meta = read_json(meta_path)
        trace = _read_trace(trace_path)
        frames = _frames_for_run(run_dir, trace)
        if not frames:
            continue
        gif_path = animations_dir / f"{run_dir.name}.gif"
        _write_gif(frames, gif_path, meta=meta, trace=trace, delay_cs=delay_cs, max_width=max_width)
        generated.append(
            {
                "run_id": run_dir.name,
                "persona": str((meta.get("persona_instance") or {}).get("name") or ""),
                "gif": gif_path.name,
            }
        )

    index_path = animations_dir / "index.html"
    atomic_write_text(index_path, _render_index(study_id=study_id, generated=generated))
    return index_path


def _read_trace(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
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


def _frames_for_run(run_dir: Path, trace: list[dict[str, Any]]) -> list[tuple[Path, dict[str, Any]]]:
    frames: list[tuple[Path, dict[str, Any]]] = []
    for event in trace:
        screenshot = (event.get("observation") or {}).get("screenshot")
        if not screenshot:
            continue
        path = run_dir / str(screenshot)
        if path.exists():
            frames.append((path, event))
    return frames


def _write_gif(
    frames: list[tuple[Path, dict[str, Any]]],
    output: Path,
    *,
    meta: dict[str, Any],
    trace: list[dict[str, Any]],
    delay_cs: int,
    max_width: int,
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:  # pragma: no cover - depends on optional environment
        raise StoreError("GIF generation requires Pillow. Install the project dependencies and retry.", exit_code=1) from exc

    persona = str((meta.get("persona_instance") or {}).get("name") or "")
    run_id = str(meta.get("run_id") or "")
    font = ImageFont.load_default()
    header_height = 116
    rendered = []
    for path, event in frames:
        with Image.open(path) as image:
            frame = image.convert("RGB")
        if frame.width > max_width:
            height = max(1, int(frame.height * (max_width / frame.width)))
            frame = frame.resize((max_width, height))
        canvas = Image.new("RGB", (frame.width, frame.height + header_height), "white")
        canvas.paste(frame, (0, header_height))
        draw = ImageDraw.Draw(canvas)
        action = event.get("action") or {}
        action_text = str(action.get("text") or action.get("type") or "")
        if len(action_text) > 82:
            action_text = f"{action_text[:79]}..."
        url = str(event.get("url") or "").replace("https://www.expectedparrot.com", "")
        draw.text((12, 12), f"{persona} / {run_id}", fill="#111827", font=font)
        draw.text((12, 38), f"Step {event.get('step')} | {event.get('status')} | {url}", fill="#374151", font=font)
        draw.text((12, 64), action_text, fill="#006b43", font=font)
        result = event.get("result") or {}
        if result.get("ok") is False:
            error = str(result.get("error") or "")
            draw.text((12, 88), f"Action failed: {error[:78]}", fill="#9d2f22", font=font)
        rendered.append(canvas)

    if not rendered:
        return
    duration_ms = max(10, int(delay_cs) * 10)
    rendered[0].save(
        output,
        save_all=True,
        append_images=rendered[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )


def _render_index(*, study_id: str, generated: list[dict[str, str]]) -> str:
    cards = "\n".join(_card(item) for item in generated) or '<p class="muted">No animations generated.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_h(study_id)} animations</title>
  <style>
    body {{
      color: #111827;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 32px auto;
      max-width: 1180px;
      padding: 0 20px;
    }}
    h1 {{ margin-bottom: 8px; }}
    .muted {{ color: #4b5563; }}
    .grid {{
      display: grid;
      gap: 24px;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      margin-top: 28px;
    }}
    figure {{ margin: 0; }}
    figcaption {{ font-weight: 650; margin-bottom: 8px; }}
    img {{
      border: 1px solid #d1d5db;
      border-radius: 8px;
      max-width: 100%;
    }}
  </style>
</head>
<body>
  <h1>{_h(study_id)} animations</h1>
  <p class="muted">Each GIF stitches per-step screenshots with action/status overlays.</p>
  <section class="grid">
    {cards}
  </section>
</body>
</html>
"""


def _card(item: dict[str, str]) -> str:
    label = item.get("persona") or item.get("run_id") or ""
    return f"""<figure>
  <figcaption>{_h(label)} <span class="muted">{_h(item.get("run_id") or "")}</span></figcaption>
  <img src="{_h(item.get("gif") or "")}" alt="{_h(label)} run animation">
</figure>"""


def _h(value: str) -> str:
    return html.escape(value, quote=True)
