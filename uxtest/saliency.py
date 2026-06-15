from __future__ import annotations

import html
import os
import shutil
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .humanize_export import ScreenshotScenario, collect_screenshot_scenarios
from .store import Store, StoreError, atomic_write_json, atomic_write_text


SUPPORTED_ENGINES = {"command"}
ENGINE_LABELS = {
    "command": "External saliency command",
}
ENGINE_WARNINGS = {
    "command": "This overlay was produced by an external command. Check the manifest for the exact invocation and errors.",
}


def run_saliency(
    store: Store,
    study_id: str,
    *,
    engine: str = "command",
    screenshots: str = "representative",
    max_screenshots: int = 12,
    output_dir: Path | None = None,
    command_template: str | None = None,
) -> tuple[Path, Path, Path]:
    if engine not in SUPPORTED_ENGINES:
        raise StoreError(f"Unsupported saliency engine {engine!r}. Use command.", exit_code=2)
    if max_screenshots < 1:
        raise StoreError("--max-screenshots must be at least 1.", exit_code=2)
    if not (command_template or os.environ.get("UXTEST_SALIENCY_COMMAND")):
        raise StoreError(
            "Saliency requires a real external model command. Use --sum, --command-template, or UXTEST_SALIENCY_COMMAND.",
            exit_code=2,
        )

    study_dir = store.study_dir(study_id)
    study = store.load_study(study_id)
    root = output_dir or study_dir / "analysis" / "saliency"
    if not root.is_absolute():
        root = (store.root / root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    scenarios = collect_screenshot_scenarios(
        store,
        study_id,
        selection=screenshots,
        max_screenshots=max_screenshots,
        script_dir=root,
    )
    if not scenarios:
        raise StoreError(
            f"Study {study_id!r} has no trace screenshots for saliency. Run the study with screenshots enabled.",
            exit_code=2,
        )

    items = []
    for scenario in scenarios:
        item = _run_command_engine(
            scenario,
            root,
            command_template=command_template or os.environ["UXTEST_SALIENCY_COMMAND"],
        )
        items.append(item)

    manifest_path = root / "manifest.json"
    html_path = root / "index.html"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": 1,
            "study_id": study_id,
            "study_title": study.get("title"),
            "engine": engine,
            "engine_label": ENGINE_LABELS.get(engine, engine),
            "engine_warning": ENGINE_WARNINGS.get(engine),
            "screenshots": screenshots,
            "max_screenshots": max_screenshots,
            "item_count": len(items),
            "items": items,
        },
    )
    atomic_write_text(html_path, _render_saliency_index(study, items, root))
    return root, manifest_path, html_path


def _run_command_engine(scenario: ScreenshotScenario, output_dir: Path, *, command_template: str) -> dict[str, Any]:
    prefix = _scenario_prefix(scenario)
    scenario_dir = output_dir / prefix
    scenario_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = output_dir / f"{prefix}-overlay.png"
    map_path = output_dir / f"{prefix}-map.png"
    formatted = command_template.format(
        input=str(scenario.screenshot_path),
        output=str(overlay_path),
        map=str(map_path),
        output_dir=str(scenario_dir),
        scenario_id=scenario.scenario_id,
    )
    result = subprocess.run(
        shlex.split(formatted),
        cwd=scenario_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    discovered = None
    if not overlay_path.exists():
        discovered = _latest_image(scenario_dir)
        if discovered is not None:
            shutil.copyfile(discovered, overlay_path)
    return _item_manifest(
        scenario,
        engine="command",
        output_dir=output_dir,
        map_path=map_path if map_path.exists() else None,
        overlay_path=overlay_path if overlay_path.exists() else None,
        command=formatted,
        returncode=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
        discovered_output=str(discovered) if discovered else None,
    )


def _item_manifest(
    scenario: ScreenshotScenario,
    *,
    engine: str,
    output_dir: Path,
    map_path: Path | None,
    overlay_path: Path | None,
    **extra: Any,
) -> dict[str, Any]:
    item = {
        "scenario_id": scenario.scenario_id,
        "run_id": scenario.run_id,
        "persona": scenario.persona,
        "step": scenario.step,
        "url": scenario.url,
        "page_title": scenario.page_title,
        "selection_reason": scenario.selection_reason,
        "engine": engine,
        "screenshot": _rel(scenario.screenshot_path, output_dir),
        "saliency_map": _rel(map_path, output_dir) if map_path else None,
        "overlay": _rel(overlay_path, output_dir) if overlay_path else None,
        "synthetic_action": scenario.synthetic_action,
        "synthetic_thinking": scenario.synthetic_thinking,
        "frustration": scenario.frustration,
    }
    item.update({key: value for key, value in extra.items() if value not in (None, "")})
    return item


def _render_saliency_index(study: dict[str, Any], items: list[dict[str, Any]], base_dir: Path) -> str:
    title = str(study.get("title") or study.get("id") or "UX Study")
    engine = str(items[0].get("engine") if items else "")
    engine_label = ENGINE_LABELS.get(engine, engine or "Saliency")
    warning = ENGINE_WARNINGS.get(engine, "")
    cards = "\n".join(_render_card(item, base_dir) for item in items)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{_h(title)} - saliency</title>
    <style>
      body {{ margin: 0; color: #17201c; background: #f7f8f6; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      header {{ padding: 28px 32px; color: #fff; background: #21342d; }}
      main {{ max-width: 1180px; margin: 0 auto; padding: 24px 32px 48px; }}
      h1, h2, h3, p {{ margin-top: 0; }}
      .meta {{ color: #d7e1dc; margin-bottom: 0; }}
      .warning {{ margin: 18px 0 0; padding: 12px 14px; border: 1px solid #f0c36d; border-radius: 8px; color: #2f2410; background: #fff4d8; font-weight: 700; }}
      .engine {{ display: inline-flex; align-items: center; min-height: 24px; padding: 0 9px; border-radius: 999px; color: #17372e; background: #d8eee6; font-size: .82rem; font-weight: 800; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
      article {{ border: 1px solid #d7ded9; border-radius: 8px; background: #fff; overflow: hidden; }}
      .body {{ padding: 14px; }}
      .shot-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 8px; background: #eef2ef; }}
      figure {{ margin: 0; }}
      img {{ display: block; width: 100%; height: 220px; object-fit: contain; border: 1px solid #d7ded9; background: #fff; }}
      figcaption {{ margin-top: 4px; color: #5d6862; font-size: .82rem; }}
      code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .92em; }}
      .muted {{ color: #5d6862; }}
      @media (max-width: 760px) {{ header, main {{ padding-left: 18px; padding-right: 18px; }} .shot-grid {{ grid-template-columns: 1fr; }} img {{ height: auto; }} }}
    </style>
  </head>
  <body>
    <header>
      <h1>{_h(title)} Saliency Review</h1>
      <p class="meta">Study {_h(str(study.get("id") or ""))}. <span class="engine">{_h(engine_label)}</span></p>
      {_warning_html(warning)}
    </header>
    <main>
      <section class="grid">
        {cards}
      </section>
    </main>
  </body>
</html>
"""


def _render_card(item: dict[str, Any], base_dir: Path) -> str:
    screenshot = item.get("screenshot")
    overlay = item.get("overlay")
    engine = str(item.get("engine") or "")
    overlay_label = "Saliency overlay"
    note = str(item.get("note") or "")
    return f"""<article>
  <div class="shot-grid">
    {_figure(screenshot, "Screenshot", base_dir)}
    {_figure(overlay, overlay_label, base_dir)}
  </div>
  <div class="body">
    <h2>{_h(str(item.get("persona") or "persona"))} step {_h(str(item.get("step") or ""))}</h2>
    <p class="muted"><code>{_h(str(item.get("run_id") or ""))}</code> | {_h(str(item.get("selection_reason") or ""))} | {_h(ENGINE_LABELS.get(engine, engine))}</p>
    {_note_html(note)}
    <p><strong>Action:</strong> {_h(str(item.get("synthetic_action") or ""))}</p>
    <p><strong>Thinking:</strong> {_h(str(item.get("synthetic_thinking") or ""))}</p>
  </div>
</article>"""


def _figure(path_value: Any, label: str, base_dir: Path) -> str:
    if not path_value:
        return f"<figure><figcaption>{_h(label)} unavailable</figcaption></figure>"
    return f"""<figure>
  <img src="{_h(str(path_value))}" alt="{_h(label)}" />
  <figcaption>{_h(label)}</figcaption>
</figure>"""


def _warning_html(warning: str) -> str:
    if not warning:
        return ""
    return f'<p class="warning">{_h(warning)}</p>'


def _note_html(note: str) -> str:
    if not note:
        return ""
    return f'<p class="muted"><strong>Note:</strong> {_h(note)}</p>'


def _scenario_prefix(scenario: ScreenshotScenario) -> str:
    step = str(scenario.step).replace("/", "-")
    return f"{scenario.scenario_id}-{scenario.run_id}-step-{step}"


def _latest_image(directory: Path) -> Path | None:
    images = [path for path in directory.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg"} and path.is_file()]
    if not images:
        return None
    return max(images, key=lambda path: path.stat().st_mtime)


def _rel(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    return os.path.relpath(path.resolve(), base.resolve()).replace(os.sep, "/")


def _h(value: str) -> str:
    return html.escape(value, quote=True)
