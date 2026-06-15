from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_json, atomic_write_text, slugify, utc_now


FIGMA_API_BASE = "https://api.figma.com/v1"


@dataclass(frozen=True)
class FigmaLocation:
    file_key: str
    node_id: str | None


@dataclass(frozen=True)
class FigmaFrame:
    node_id: str
    name: str
    type: str
    image_path: Path
    image_relative_path: str
    bounds: dict[str, Any]
    text_preview: str
    layer_names: list[str]

    def to_manifest(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "type": self.type,
            "image": self.image_relative_path,
            "bounds": self.bounds,
            "text_preview": self.text_preview,
            "layer_names": self.layer_names,
        }


class FigmaClient:
    def __init__(self, token: str, *, api_base: str = FIGMA_API_BASE):
        if not token.strip():
            raise StoreError("FIGMA_ACCESS_TOKEN is required for Figma import.", exit_code=2)
        self.token = token
        self.api_base = api_base.rstrip("/")

    def get_file(self, file_key: str) -> dict[str, Any]:
        return self._get_json(f"/files/{file_key}")

    def get_nodes(self, file_key: str, node_ids: list[str]) -> dict[str, Any]:
        query = urllib.parse.urlencode({"ids": ",".join(node_ids)})
        return self._get_json(f"/files/{file_key}/nodes?{query}")

    def get_image_urls(self, file_key: str, node_ids: list[str], *, scale: float = 2.0, fmt: str = "png") -> dict[str, str]:
        query = urllib.parse.urlencode({"ids": ",".join(node_ids), "scale": scale, "format": fmt})
        payload = self._get_json(f"/images/{file_key}?{query}")
        images = payload.get("images")
        if not isinstance(images, dict):
            raise StoreError("Figma image export response did not include an images mapping.", exit_code=1)
        return {str(key): str(value) for key, value in images.items() if value}

    def download(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "uxtest/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise StoreError(f"Figma image download failed with HTTP {exc.code}: {url}", exit_code=1) from exc
        except urllib.error.URLError as exc:
            raise StoreError(f"Figma image download failed: {exc.reason}", exit_code=1) from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            headers={"X-Figma-Token": self.token, "User-Agent": "uxtest/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise StoreError(f"Figma API request failed with HTTP {exc.code}: {detail}", exit_code=1) from exc
        except urllib.error.URLError as exc:
            raise StoreError(f"Figma API request failed: {exc.reason}", exit_code=1) from exc
        if not isinstance(data, dict):
            raise StoreError("Figma API returned a non-object response.", exit_code=1)
        return data


def parse_figma_url(value: str) -> FigmaLocation:
    parsed = urllib.parse.urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    file_key: str | None = None
    for marker in ("file", "design", "proto"):
        if marker in parts:
            index = parts.index(marker)
            if len(parts) > index + 1:
                file_key = parts[index + 1]
                break
    if not file_key:
        raise StoreError("Could not find a Figma file key in the URL. Expected /file/<key>, /design/<key>, or /proto/<key>.", exit_code=2)
    query = urllib.parse.parse_qs(parsed.query)
    node_id = _normalize_node_id((query.get("node-id") or query.get("node_id") or [None])[0])
    return FigmaLocation(file_key=file_key, node_id=node_id)


def import_figma_frames(
    store: Store,
    figma_url: str,
    *,
    frames: str = "selected",
    limit: int = 20,
    scale: float = 2.0,
    token: str | None = None,
    client: FigmaClient | None = None,
) -> tuple[Path, Path]:
    if limit < 1:
        raise StoreError("--limit must be at least 1.", exit_code=2)
    location = parse_figma_url(figma_url)
    client = client or FigmaClient(token or os.environ.get("FIGMA_ACCESS_TOKEN", ""))

    nodes = _nodes_for_import(client, location, frames=frames, limit=limit)
    if not nodes:
        raise StoreError("No Figma frames were found to import.", exit_code=2)

    image_urls = client.get_image_urls(location.file_key, [node["id"] for node in nodes], scale=scale)
    import_id = _import_id(location, nodes)
    import_dir = store.path / "figma" / import_id
    frames_dir = import_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    imported: list[FigmaFrame] = []
    for index, node in enumerate(nodes, start=1):
        node_id = str(node["id"])
        image_url = image_urls.get(node_id)
        if not image_url:
            continue
        filename = f"{index:03d}-{slugify(str(node.get('name') or 'frame'), max_len=48)}-{_safe_node_id(node_id)}.png"
        image_path = frames_dir / filename
        image_path.write_bytes(client.download(image_url))
        imported.append(
            FigmaFrame(
                node_id=node_id,
                name=str(node.get("name") or node_id),
                type=str(node.get("type") or ""),
                image_path=image_path,
                image_relative_path=str(image_path.relative_to(import_dir)),
                bounds=node.get("absoluteBoundingBox") if isinstance(node.get("absoluteBoundingBox"), dict) else {},
                text_preview=_text_preview(node),
                layer_names=_layer_names(node),
            )
        )

    if not imported:
        raise StoreError("Figma did not return image exports for the selected frames.", exit_code=1)

    manifest_path = import_dir / "manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": 1,
            "kind": "figma_import",
            "import_id": import_id,
            "created_at": utc_now(),
            "source_url": figma_url,
            "file_key": location.file_key,
            "node_id": location.node_id,
            "frames_mode": frames,
            "scale": scale,
            "frame_count": len(imported),
            "frames": [frame.to_manifest() for frame in imported],
        },
    )
    return import_dir, manifest_path


def write_figma_study_script(
    store: Store,
    import_id: str,
    *,
    task: str,
    model: str = "gpt-4o",
    output: Path | None = None,
) -> tuple[Path, Path]:
    manifest_path = store.path / "figma" / import_id / "manifest.json"
    if not manifest_path.exists():
        raise StoreError(f"Figma import {import_id!r} does not exist. Run `uxtest figma import` first.", exit_code=2)
    manifest = _read_json(manifest_path)
    output_path = output or manifest_path.parent / "figma_vision_study.py"
    if not output_path.is_absolute():
        output_path = (store.root / output_path).resolve()
    script = render_figma_study_script(manifest=manifest, task=task, model=model, script_dir=output_path.parent)
    atomic_write_text(output_path, script)
    study_manifest_path = output_path.with_suffix(".manifest.json")
    study_manifest = dict(manifest)
    study_manifest.update({"task": task, "model": model, "script": str(output_path)})
    atomic_write_json(study_manifest_path, study_manifest)
    return output_path, study_manifest_path


def render_figma_study_script(*, manifest: dict[str, Any], task: str, model: str, script_dir: Path) -> str:
    import_dir = Path(str(manifest.get("_manifest_path", ""))).parent if manifest.get("_manifest_path") else script_dir
    rows = []
    for frame in manifest.get("frames") or []:
        if not isinstance(frame, dict):
            continue
        image = Path(str(frame.get("image") or ""))
        image_path = image if image.is_absolute() else import_dir / image
        rows.append(
            {
                "node_id": frame.get("node_id"),
                "name": frame.get("name"),
                "type": frame.get("type"),
                "image": os.path.relpath(image_path.resolve(), script_dir.resolve()).replace(os.sep, "/"),
                "text_preview": frame.get("text_preview") or "",
                "layer_names": frame.get("layer_names") or [],
                "choice_options": _choice_options(frame),
            }
        )
    lines = [
        "from __future__ import annotations",
        "",
        "import argparse",
        "from pathlib import Path",
        "",
        "from edsl import FileStore, Model, Scenario, ScenarioList, Survey",
        "from edsl.questions import QuestionFreeText, QuestionLinearScale, QuestionMultipleChoice",
        "",
        "BASE_DIR = Path(__file__).resolve().parent",
        f"FIGMA_IMPORT_ID = {str(manifest.get('import_id') or '').__repr__()}",
        f"SOURCE_URL = {str(manifest.get('source_url') or '').__repr__()}",
        f"DEFAULT_MODEL = {model.__repr__()}",
        f"TASK = {task.__repr__()}",
        f"SCENARIO_ROWS = {json.dumps(rows, indent=2)}",
        "",
        "",
        "def build_scenarios() -> ScenarioList:",
        "    scenarios = []",
        "    for row in SCENARIO_ROWS:",
        "        data = dict(row)",
        "        data['task'] = TASK",
        "        data['screenshot'] = FileStore(str(BASE_DIR / row['image']))",
        "        scenarios.append(Scenario(data))",
        "    return ScenarioList(scenarios)",
        "",
        "",
        "def build_survey() -> Survey:",
        "    return Survey([",
        "        QuestionFreeText(",
        "            question_name='interpretation',",
        "            question_text='Task: {{ scenario.task }}\\nFrame: {{ scenario.name }}\\nScreenshot: {{ scenario.screenshot }}\\n\\nWhat do you think this screen is for, and what is unclear?',",
        "        ),",
        "        QuestionMultipleChoice(",
        "            question_name='next_click',",
        "            question_text='Task: {{ scenario.task }}\\nFrame: {{ scenario.name }}\\nScreenshot: {{ scenario.screenshot }}\\n\\nWhat would you click or inspect next? Choose the closest option.',",
        "            question_options='{{ scenario.choice_options }}',",
        "        ),",
        "        QuestionFreeText(",
        "            question_name='next_click_reason',",
        "            question_text='Task: {{ scenario.task }}\\nFrame: {{ scenario.name }}\\nScreenshot: {{ scenario.screenshot }}\\n\\nWhy would you take that next action?',",
        "        ),",
        "        QuestionLinearScale(",
        "            question_name='confidence',",
        "            question_text='Task: {{ scenario.task }}\\nFrame: {{ scenario.name }}\\nScreenshot: {{ scenario.screenshot }}\\n\\nHow confident are you that you know what to do next?',",
        "            question_options=[1, 2, 3, 4, 5],",
        "            option_labels={1: 'Not confident', 5: 'Very confident'},",
        "        ),",
        "    ])",
        "",
        "",
        "def main() -> None:",
        "    parser = argparse.ArgumentParser(description='Run an EDSL vision study over imported Figma frames.')",
        "    parser.add_argument('--launch', action='store_true', help='Run the EDSL survey remotely.')",
        "    parser.add_argument('--model', default=DEFAULT_MODEL)",
        "    args = parser.parse_args()",
        "",
        "    scenarios = build_scenarios()",
        "    survey = build_survey()",
        "    print(f'Figma import: {FIGMA_IMPORT_ID}')",
        "    print(f'Source: {SOURCE_URL}')",
        "    print(f'Frames: {len(scenarios)}')",
        "    print(f'Model: {args.model}')",
        "    if not args.launch:",
        "        print('Dry run only. Re-run with --launch to call EDSL remote inference.')",
        "        return",
        "    results = survey.by(scenarios).by(Model(args.model)).run(remote=True)",
        "    print(results)",
        "",
        "",
        "if __name__ == '__main__':",
        "    main()",
        "",
    ]
    return "\n".join(lines)


def render_figma_report(store: Store, import_id: str) -> str:
    manifest_path = store.path / "figma" / import_id / "manifest.json"
    if not manifest_path.exists():
        raise StoreError(f"Figma import {import_id!r} does not exist.", exit_code=2)
    manifest = _read_json(manifest_path)
    title = f"Figma Import: {manifest.get('import_id')}"
    lines = [
        f"# {title}",
        "",
        f"Source: {manifest.get('source_url')}",
        "",
        f"Frames imported: {manifest.get('frame_count')}",
        "",
    ]
    for frame in manifest.get("frames") or []:
        if not isinstance(frame, dict):
            continue
        lines.extend(
            [
                f"## {frame.get('name')}",
                "",
                f"- Node: `{frame.get('node_id')}`",
                f"- Type: `{frame.get('type')}`",
                "",
                f"![{frame.get('name')}]({frame.get('image')})",
                "",
            ]
        )
        if frame.get("text_preview"):
            lines.extend(["Text preview:", "", str(frame["text_preview"]), ""])
    return "\n".join(lines)


def write_figma_report(store: Store, import_id: str) -> Path:
    report_path = store.path / "figma" / import_id / "report.md"
    atomic_write_text(report_path, render_figma_report(store, import_id))
    return report_path


def figma_doctor() -> list[dict[str, Any]]:
    token = os.environ.get("FIGMA_ACCESS_TOKEN")
    return [
        {
            "name": "FIGMA_ACCESS_TOKEN",
            "ok": bool(token),
            "detail": "set" if token else "not set",
            "fix": "Create a Figma access token and export FIGMA_ACCESS_TOKEN.",
        }
    ]


def _nodes_for_import(client: FigmaClient, location: FigmaLocation, *, frames: str, limit: int) -> list[dict[str, Any]]:
    if frames == "selected":
        if not location.node_id:
            raise StoreError("The Figma URL has no node-id. Use --frames top-level or copy a link to a selected frame.", exit_code=2)
        payload = client.get_nodes(location.file_key, [location.node_id])
        node_entry = ((payload.get("nodes") or {}).get(location.node_id) or {}) if isinstance(payload.get("nodes"), dict) else {}
        document = node_entry.get("document")
        if not isinstance(document, dict):
            raise StoreError(f"Figma did not return node {location.node_id!r}.", exit_code=1)
        return [_frame_like_node(document)]

    file_payload = client.get_file(location.file_key)
    document = file_payload.get("document")
    if not isinstance(document, dict):
        raise StoreError("Figma file response did not include a document.", exit_code=1)
    if frames == "top-level":
        pages = [child for child in document.get("children") or [] if isinstance(child, dict)]
        top_level = []
        for page in pages:
            top_level.extend(child for child in page.get("children") or [] if isinstance(child, dict) and _is_frame_like(child))
        return [_frame_like_node(node) for node in top_level[:limit]]
    if frames == "all":
        output: list[dict[str, Any]] = []
        _walk_frames(document, output)
        return [_frame_like_node(node) for node in output[:limit]]
    raise StoreError(f"Unsupported Figma frame mode {frames!r}.", exit_code=2)


def _frame_like_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(node.get("id") or ""),
        "name": str(node.get("name") or "Frame"),
        "type": str(node.get("type") or ""),
        "absoluteBoundingBox": node.get("absoluteBoundingBox") if isinstance(node.get("absoluteBoundingBox"), dict) else {},
        "children": node.get("children") if isinstance(node.get("children"), list) else [],
        "characters": node.get("characters"),
    }


def _walk_frames(node: dict[str, Any], output: list[dict[str, Any]]) -> None:
    if _is_frame_like(node):
        output.append(node)
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _walk_frames(child, output)


def _is_frame_like(node: dict[str, Any]) -> bool:
    return str(node.get("type") or "").upper() in {"FRAME", "COMPONENT", "INSTANCE", "SECTION"}


def _text_preview(node: dict[str, Any]) -> str:
    chunks: list[str] = []
    _collect_text(node, chunks)
    text = "\n".join(chunks)
    return text[:1200]


def _collect_text(node: dict[str, Any], chunks: list[str]) -> None:
    characters = node.get("characters")
    if isinstance(characters, str) and characters.strip():
        chunks.append(characters.strip())
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _collect_text(child, chunks)


def _layer_names(node: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for child in node.get("children") or []:
        if isinstance(child, dict) and child.get("name"):
            names.append(str(child["name"]))
        if len(names) >= 20:
            break
    return names


def _choice_options(frame: dict[str, Any]) -> list[str]:
    options = []
    for name in frame.get("layer_names") or []:
        text = str(name).strip()
        if text and text not in options:
            options.append(text)
        if len(options) >= 6:
            break
    for fallback in ["Primary call to action", "Navigation/menu", "Back or close", "I would not click yet", "Other visible element"]:
        if fallback not in options:
            options.append(fallback)
    return options[:10]


def _import_id(location: FigmaLocation, nodes: list[dict[str, Any]]) -> str:
    label = nodes[0].get("name") if nodes else location.file_key
    return f"{slugify(str(label or 'figma'), max_len=28)}-{_safe_node_id(location.node_id or location.file_key)[:12]}"


def _safe_node_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "node"


def _normalize_node_id(value: str | None) -> str | None:
    if not value:
        return None
    decoded = urllib.parse.unquote(value)
    if ":" in decoded:
        return decoded
    if re.match(r"^\d+-\d+$", decoded):
        return decoded.replace("-", ":", 1)
    return decoded


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise StoreError(f"Expected JSON object in {path}.")
    data["_manifest_path"] = str(path)
    return data
