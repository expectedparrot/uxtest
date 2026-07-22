from __future__ import annotations

import html
import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_text


@dataclass
class JourneyNode:
    event: dict[str, Any] | None = None
    run_ids: set[str] = field(default_factory=set)
    children: dict[str, "JourneyNode"] = field(default_factory=dict)


def generate_journey_tree(store: Store, study_id: str) -> Path:
    study = store.load_study(study_id)
    root = JourneyNode()
    run_count = 0
    for run_dir in store.list_runs(study_id):
        events = _trace_events(run_dir / "trace.jsonl")
        if not events:
            continue
        run_count += 1
        node = root
        for event in events:
            key = _event_key(event)
            child = node.children.setdefault(key, JourneyNode(event=event))
            child.run_ids.add(run_dir.name)
            child.event = dict(child.event or event)
            child.event["_run_id"] = str(child.event.get("_run_id") or run_dir.name)
            node = child
    if not root.children:
        raise StoreError(f"Study {study_id!r} has no trace events to map.", exit_code=2)
    output_dir = store.study_dir(study_id) / "analysis" / "journey"
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / "journey.svg"
    atomic_write_text(svg_path, _render_svg(study, root, run_count, store.study_dir(study_id)))
    atomic_write_text(output_dir / "index.html", _render(study, root, run_count))
    return svg_path


def _trace_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict) and value.get("step") is not None and value.get("event_type", "step") == "step":
            events.append(value)
    return events


def _event_key(event: dict[str, Any]) -> str:
    action = event.get("action") or {}
    result = event.get("result") or {}
    return json.dumps(
        {
            "step": event.get("step"),
            "url": event.get("url"),
            "action": {"type": action.get("type"), "text": action.get("text"), "ref": action.get("ref")},
            "final_url": result.get("final_url"),
            "outcome": result.get("action_outcome"),
        },
        sort_keys=True,
    )


def _render(study: dict[str, Any], root: JourneyNode, run_count: int) -> str:
    title = html.escape(str(study.get("title") or study.get("id") or "Journey tree"))
    tree = "".join(_render_node(node) for node in root.children.values())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Journey tree</title><style>
:root{{--green:#428a5f;--forest:#193f2a;--ink:#18201b;--muted:#657069;--paper:#f3f5f3;--rule:#dce4de}}
*{{box-sizing:border-box}}body{{margin:0;padding:38px;color:var(--ink);background:var(--paper);font:14px/1.45 system-ui,sans-serif}}
header{{max-width:900px;margin:0 0 34px}}h1{{margin:5px 0;font:600 38px/1.2 Georgia,serif}}header p{{color:var(--muted)}}
.tree,.tree ul{{list-style:none;margin:0;padding-left:34px;position:relative}}.tree{{padding-left:0}}.tree ul:before{{position:absolute;left:11px;top:0;bottom:22px;border-left:2px solid #b8cdbf;content:""}}
.tree li{{position:relative;margin:0 0 28px}}.tree li:before{{position:absolute;left:-23px;top:25px;width:23px;border-top:2px solid #b8cdbf;content:""}}.tree>li:before{{display:none}}
.node{{display:grid;grid-template-columns:220px minmax(250px,480px);gap:18px;width:max-content;max-width:760px;padding:14px;background:white;border:1px solid var(--rule);border-radius:12px;box-shadow:0 5px 18px #193f2a12}}
.node img{{display:block;width:220px;height:390px;object-fit:cover;object-position:top;border:1px solid var(--rule)}}.step{{color:var(--green);font-size:11px;font-weight:850;letter-spacing:.1em;text-transform:uppercase}}
h2{{margin:7px 0 8px;color:var(--forest);font-size:20px}}.meta{{color:var(--muted);font:12px/1.5 ui-monospace,monospace;overflow-wrap:anywhere}}.runs{{margin-top:13px;color:var(--muted);font-size:12px}}.outcome{{display:inline-block;margin-top:12px;padding:5px 8px;color:var(--forest);background:#eef7f1;border-radius:5px;font-weight:700}}
@media(max-width:700px){{body{{padding:20px}}.node{{grid-template-columns:150px minmax(180px,1fr);width:auto}}.node img{{width:150px;height:266px}}}}
</style></head><body><header><div class="step">uxtest journey tree</div><h1>{title}</h1><p>{run_count} run(s). Each node shows the screenshot captured before an action; branches indicate paths that diverged across runs.</p></header><ul class="tree">{tree}</ul></body></html>"""


def _render_node(node: JourneyNode) -> str:
    event = node.event or {}
    action = event.get("action") or {}
    result = event.get("result") or {}
    action_label = " ".join(str(value) for value in (action.get("type"), action.get("text") or action.get("ref")) if value) or "No action"
    run_id = str(event.get("_run_id") or sorted(node.run_ids)[0])
    screenshot = str((event.get("observation") or {}).get("screenshot") or "")
    image_path = f"../../runs/{run_id}/{screenshot}" if screenshot else ""
    image = f'<img src="{html.escape(image_path, quote=True)}" alt="Step {html.escape(str(event.get("step") or ""))} browser capture">' if image_path else ""
    children = ""
    if node.children:
        children = "<ul>" + "".join(_render_node(child) for child in node.children.values()) + "</ul>"
    runs = ", ".join(sorted(node.run_ids))
    return f"""<li><article class="node">{image}<div><div class="step">Step {html.escape(str(event.get('step') or ''))}</div><h2>{html.escape(action_label)}</h2><div class="meta">From: {html.escape(str(event.get('url') or ''))}<br>To: {html.escape(str(result.get('final_url') or event.get('url') or ''))}</div><span class="outcome">{html.escape(str(result.get('action_outcome') or event.get('status') or 'recorded'))}</span><div class="runs">Runs: {html.escape(runs)}</div></div></article>{children}</li>"""


def _render_svg(study: dict[str, Any], root: JourneyNode, run_count: int, study_dir: Path) -> str:
    positions: dict[int, tuple[float, int]] = {}
    cursor = [0]

    def place(node: JourneyNode, depth: int) -> float:
        if node.children:
            child_x = [place(child, depth + 1) for child in node.children.values()]
            x = sum(child_x) / len(child_x)
        else:
            x = 190 + cursor[0] * 350
            cursor[0] += 1
        positions[id(node)] = (x, depth)
        return x

    for child in root.children.values():
        place(child, 0)
    nodes = list(_walk_nodes(root))
    leaf_count = max(1, cursor[0])
    max_depth = max(depth for _, depth in (positions[id(node)] for node in nodes))
    width = max(760, leaf_count * 350 + 30)
    if leaf_count == 1:
        for node in nodes:
            _, depth = positions[id(node)]
            positions[id(node)] = (width / 2, depth)
    card_w, card_h, level_gap = 300, 466, 536
    height = 90 + (max_depth + 1) * level_gap
    edges: list[str] = []
    cards: list[str] = []
    for node in nodes:
        x, depth = positions[id(node)]
        y = 55 + depth * level_gap
        for child in node.children.values():
            child_x, child_depth = positions[id(child)]
            child_y = 55 + child_depth * level_gap
            edges.append(f'<path d="M {x} {y + card_h} C {x} {y + card_h + 36}, {child_x} {child_y - 36}, {child_x} {child_y}" fill="none" stroke="#8fb39b" stroke-width="4" marker-end="url(#arrow)"/>')
        cards.append(_svg_card(node, x - card_w / 2, y, card_w, card_h, study_dir, len(cards)))
    title = html.escape(str(study.get("title") or study.get("id") or "Journey tree"))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{title} journey tree</title><desc id="desc">Screenshot-backed browser paths across {run_count} runs.</desc>
<defs><filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="5" stdDeviation="7" flood-color="#193f2a" flood-opacity=".14"/></filter><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#428a5f"/></marker></defs>
<rect width="100%" height="100%" fill="#f3f5f3"/>{''.join(edges)}{''.join(cards)}</svg>'''


def _walk_nodes(root: JourneyNode):
    for child in root.children.values():
        yield child
        yield from _walk_nodes(child)


def _svg_card(node: JourneyNode, x: float, y: float, width: int, height: int, study_dir: Path, index: int) -> str:
    event = node.event or {}
    action = event.get("action") or {}
    result = event.get("result") or {}
    action_label = " ".join(str(value) for value in (action.get("type"), action.get("text") or action.get("ref")) if value) or "No action"
    run_id = str(event.get("_run_id") or sorted(node.run_ids)[0])
    screenshot = str((event.get("observation") or {}).get("screenshot") or "")
    image_file = study_dir / "runs" / run_id / screenshot
    image = ""
    if image_file.is_file():
        encoded = base64.b64encode(image_file.read_bytes()).decode("ascii")
        image = f'<image href="data:image/png;base64,{encoded}" x="{x + 16}" y="{y + 62}" width="{width - 32}" height="276" preserveAspectRatio="xMidYMin slice" clip-path="url(#clip{index})"/>'
    runs = ", ".join(sorted(node.run_ids))
    outcome = str(result.get("action_outcome") or event.get("status") or "recorded")
    url = str(event.get("url") or "")
    if len(url) > 44:
        url = "…" + url[-43:]
    return f'''<defs><clipPath id="clip{index}"><rect x="{x + 16}" y="{y + 62}" width="{width - 32}" height="276" rx="3"/></clipPath></defs>
<g filter="url(#shadow)"><rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#fff" stroke="#9eb0a4" stroke-width="2"/>
<path d="M {x + 12} {y} H {x + width - 12} Q {x + width} {y} {x + width} {y + 12} V {y + 48} H {x} V {y + 12} Q {x} {y} {x + 12} {y}" fill="#193f2a"/>
<text x="{x + 16}" y="{y + 30}" fill="#fff" font-family="system-ui,sans-serif" font-size="13" font-weight="800">CAPTURED PAGE · STEP {html.escape(str(event.get('step') or ''))}</text>{image}
<rect x="{x}" y="{y + 350}" width="{width}" height="{height - 350}" fill="#eef7f1"/>
<line x1="{x}" y1="{y + 350}" x2="{x + width}" y2="{y + 350}" stroke="#428a5f" stroke-width="3"/>
<text x="{x + 16}" y="{y + 376}" fill="#428a5f" font-family="system-ui,sans-serif" font-size="11" font-weight="850" letter-spacing="1">RECORDED NAVIGATION</text>
<text x="{x + 16}" y="{y + 404}" fill="#193f2a" font-family="system-ui,sans-serif" font-size="19" font-weight="750">{html.escape(action_label[:34])}</text>
<text x="{x + 16}" y="{y + 429}" fill="#657069" font-family="ui-monospace,monospace" font-size="11">{html.escape(url)}</text>
<text x="{x + 16}" y="{y + 453}" fill="#428a5f" font-family="system-ui,sans-serif" font-size="12" font-weight="700">{html.escape(outcome)} · {html.escape(runs[:26])}</text></g>'''
