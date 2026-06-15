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


class FigmaRateLimitError(StoreError):
    def __init__(
        self,
        detail: str,
        *,
        retry_after: int | None = None,
        plan_tier: str | None = None,
        rate_limit_type: str | None = None,
        upgrade_link: str | None = None,
    ):
        self.retry_after = retry_after
        self.plan_tier = plan_tier
        self.rate_limit_type = rate_limit_type
        self.upgrade_link = upgrade_link
        parts = [detail]
        if retry_after is not None:
            parts.append(f"retry after {retry_after}s")
        if plan_tier:
            parts.append(f"plan tier {plan_tier}")
        if rate_limit_type:
            parts.append(f"rate limit type {rate_limit_type}")
        super().__init__("; ".join(parts), exit_code=1)


@dataclass(frozen=True)
class FigmaLocation:
    file_key: str
    node_id: str | None
    kind: str = "design"
    page_id: str | None = None
    starting_point_node_id: str | None = None


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
            if exc.code == 429:
                raise FigmaRateLimitError(
                    f"Figma API request failed with HTTP 429: {detail}",
                    retry_after=_parse_retry_after(exc.headers.get("Retry-After")),
                    plan_tier=exc.headers.get("X-Figma-Plan-Tier"),
                    rate_limit_type=exc.headers.get("X-Figma-Rate-Limit-Type"),
                    upgrade_link=exc.headers.get("X-Figma-Upgrade-Link"),
                ) from exc
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
    kind = "design"
    for marker in ("file", "design", "proto"):
        if marker in parts:
            index = parts.index(marker)
            if len(parts) > index + 1:
                file_key = parts[index + 1]
                kind = marker
                break
    if not file_key:
        raise StoreError("Could not find a Figma file key in the URL. Expected /file/<key>, /design/<key>, or /proto/<key>.", exit_code=2)
    query = urllib.parse.parse_qs(parsed.query)
    node_id = _normalize_node_id((query.get("node-id") or query.get("node_id") or [None])[0])
    page_id = _normalize_node_id((query.get("page-id") or query.get("page_id") or [None])[0])
    starting_point = _normalize_node_id((query.get("starting-point-node-id") or query.get("starting_point_node_id") or [None])[0])
    return FigmaLocation(file_key=file_key, node_id=node_id, kind=kind, page_id=page_id, starting_point_node_id=starting_point)


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


def write_figma_prototype_script(
    store: Store,
    figma_url: str,
    *,
    task: str,
    model: str = "gpt-4o",
    max_steps: int = 8,
    output: Path | None = None,
) -> tuple[Path, Path]:
    location = parse_figma_url(figma_url)
    if location.kind != "proto":
        raise StoreError("`uxtest figma prototype` expects a Figma /proto/ URL.", exit_code=2)
    import_id = f"prototype-{_safe_node_id(location.file_key)[:12]}-{_safe_node_id(location.node_id or location.starting_point_node_id or 'start')[:12]}"
    prototype_dir = store.path / "figma" / import_id
    prototype_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = prototype_dir / "manifest.json"
    previous_manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    manifest = {
        "schema_version": 1,
        "kind": "figma_prototype",
        "import_id": import_id,
        "created_at": utc_now(),
        "source_url": figma_url,
        "file_key": location.file_key,
        "node_id": location.node_id,
        "page_id": location.page_id,
        "starting_point_node_id": location.starting_point_node_id,
        "task": task,
        "model": model,
        "max_steps": max_steps,
    }
    token = os.environ.get("FIGMA_ACCESS_TOKEN", "")
    if token and location.node_id:
        try:
            document, cache_meta = _cached_figma_node_document(store, location, token=token, refresh=False)
            manifest["prototype_targets"] = _prototype_targets(document, viewport_height=1000)
            manifest["prototype_interactions"] = _prototype_interactions(document, viewport_height=1000)
            manifest["prototype_metadata_cache"] = cache_meta
        except StoreError as exc:
            manifest["prototype_target_error"] = str(exc)
            for key in ("prototype_targets", "prototype_interactions"):
                if previous_manifest.get(key):
                    manifest[key] = previous_manifest[key]
    atomic_write_json(manifest_path, manifest)
    output_path = output or prototype_dir / "figma_prototype_runner.py"
    if not output_path.is_absolute():
        output_path = (store.root / output_path).resolve()
    script = render_figma_prototype_script(manifest=manifest, script_dir=output_path.parent)
    atomic_write_text(output_path, script)
    return output_path, manifest_path


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


def render_figma_prototype_script(*, manifest: dict[str, Any], script_dir: Path) -> str:
    lines = [
        "from __future__ import annotations",
        "",
        "import argparse",
        "import json",
        "from pathlib import Path",
        "from typing import Literal",
        "",
        "from edsl import Agent, FileStore, Model, QuestionFreeText, Scenario",
        "from PIL import Image, ImageDraw, ImageEnhance, ImageFont",
        "from pydantic import BaseModel, Field",
        "from playwright.sync_api import sync_playwright",
        "",
        "BASE_DIR = Path(__file__).resolve().parent",
        f"PROTOTYPE_ID = {str(manifest.get('import_id') or '').__repr__()}",
        f"SOURCE_URL = {str(manifest.get('source_url') or '').__repr__()}",
        f"TASK = {str(manifest.get('task') or '').__repr__()}",
        f"DEFAULT_MODEL = {str(manifest.get('model') or 'gpt-4o').__repr__()}",
        f"DEFAULT_MAX_STEPS = {int(manifest.get('max_steps') or 8)}",
        f"PROTOTYPE_TARGETS = {json.dumps(manifest.get('prototype_targets') or [], sort_keys=True)}",
        f"PROTOTYPE_INTERACTION_TARGETS = {json.dumps(manifest.get('prototype_interactions') or [], sort_keys=True)}",
        "VIEWPORT_WIDTH = 1440",
        "VIEWPORT_HEIGHT = 1000",
        "BOTTOM_FIGMA_CONTROL_Y = 940",
        "",
        "",
        "class PrototypeDecision(BaseModel):",
        "    status: Literal['continue', 'done', 'gave_up'] = Field(description='Whether the task is complete, blocked, or should continue.')",
        "    x: int | None = Field(default=None, description='Viewport x coordinate to click next, in screenshot pixels.')",
        "    y: int | None = Field(default=None, description='Viewport y coordinate to click next, in screenshot pixels.')",
        "    target: str = Field(default='', description='Short label for the intended target.')",
        "    thinking: str = Field(description='Brief rationale, including what changed or why the flow is blocked.')",
        "    confusion: str = Field(default='', description='Anything confusing or missing on this step.')",
        "",
        "",
        "def annotate_screenshot(source_path: Path) -> Path:",
        "    annotated_path = source_path.with_name(source_path.stem + '-grid.png')",
        "    image = Image.open(source_path).convert('RGBA')",
        "    image = ImageEnhance.Brightness(image).enhance(1.35)",
        "    image = ImageEnhance.Contrast(image).enhance(1.2)",
        "    overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))",
        "    draw = ImageDraw.Draw(overlay)",
        "    font = ImageFont.load_default()",
        "    width, height = image.size",
        "    for x in range(0, width, 100):",
        "        draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 72), width=1)",
        "        draw.text((x + 4, 6), str(x), fill=(255, 255, 0, 230), font=font)",
        "    for y in range(0, height, 100):",
        "        draw.line([(0, y), (width, y)], fill=(255, 255, 255, 72), width=1)",
        "        draw.text((6, y + 4), str(y), fill=(255, 255, 0, 230), font=font)",
        "    draw.rectangle([(0, BOTTOM_FIGMA_CONTROL_Y), (width, height)], outline=(255, 80, 80, 220), width=3)",
        "    draw.text((12, BOTTOM_FIGMA_CONTROL_Y + 8), 'avoid Figma controls', fill=(255, 80, 80, 240), font=font)",
        "    Image.alpha_composite(image, overlay).convert('RGB').save(annotated_path)",
        "    return annotated_path",
        "",
        "",
        "def screenshot_looks_ready(path: Path) -> bool:",
        "    if not path.exists() or path.stat().st_size < 50_000:",
        "        return False",
        "    image = Image.open(path).convert('RGB')",
        "    width, height = image.size",
        "    sample_points = [(x, y) for x in range(0, width, 80) for y in range(0, height, 80)]",
        "    if not sample_points:",
        "        return False",
        "    non_dark = 0",
        "    for x, y in sample_points:",
        "        r, g, b = image.getpixel((x, y))",
        "        if max(r, g, b) > 35:",
        "            non_dark += 1",
        "    return non_dark / len(sample_points) > 0.08",
        "",
        "",
        "def capture_ready_screenshot(page, path: Path, *, timeout_ms: int = 25000) -> bool:",
        "    elapsed = 0",
        "    reloaded = False",
        "    while elapsed <= timeout_ms:",
        "        page.screenshot(path=str(path), full_page=False)",
        "        if screenshot_looks_ready(path):",
        "            return True",
        "        if not reloaded and elapsed >= 8000:",
        "            try:",
        "                page.reload(wait_until='domcontentloaded', timeout=45000)",
        "            except Exception:",
        "                pass",
        "            reloaded = True",
        "        page.wait_for_timeout(1000)",
        "        elapsed += 1000",
        "    return False",
        "",
        "",
        "def dismiss_figma_overlays(page) -> None:",
        "    for _ in range(3):",
        "        dismiss = page.locator('button[aria-label=\"Dismiss\"]')",
        "        if not dismiss.count():",
        "            break",
        "        try:",
        "            dismiss.first.click(timeout=750)",
        "            page.wait_for_timeout(250)",
        "        except Exception:",
        "            break",
        "    page.evaluate(",
        "        \"\"\"",
        "        () => {",
        "          for (const el of document.querySelectorAll('button')) {",
        "            const rect = el.getBoundingClientRect();",
        "            const label = el.getAttribute('aria-label') || el.innerText || '';",
        "            const isFigmaChrome = rect.top < 56 || rect.top > 930 ||",
        "              /Open flows list|Comment|Options|full screen|Previous frame|Next frame|Restart|Continue with Google/i.test(label);",
        "            if (isFigmaChrome) {",
        "              el.style.pointerEvents = 'none';",
        "              el.style.opacity = '0';",
        "            }",
        "          }",
        "          for (const el of document.querySelectorAll('div, span')) {",
        "            const text = el.innerText || el.textContent || '';",
        "            const rect = el.getBoundingClientRect();",
        "            if (/Improve performance|Log in or create account|Continue with Google|Homepage v3|Restart/i.test(text) && (rect.top < 70 || rect.top > 880)) {",
        "              el.style.opacity = '0';",
        "              el.style.pointerEvents = 'none';",
        "            }",
        "          }",
        "        }",
        "        \"\"\"",
        "    )",
        "",
        "",
        "def repeated_static_target(recent_events: list[dict], event: dict) -> bool:",
        "    target = str((event.get('decision') or {}).get('target') or '').strip().lower()",
        "    if not target:",
        "        return False",
        "    matches = 0",
        "    for prior in reversed(recent_events):",
        "        prior_decision = prior.get('decision') or {}",
        "        prior_target = str(prior_decision.get('target') or '').strip().lower()",
        "        if prior_target != target:",
        "            break",
        "        if prior.get('url') == prior.get('after_url') == event.get('url') == event.get('after_url'):",
        "            matches += 1",
        "    return matches >= 2",
        "",
        "",
        "def normalize_label(value: str) -> str:",
        "    return ''.join(ch for ch in value.casefold() if ch.isalnum())",
        "",
        "",
        "def visible_candidate_targets() -> list[dict]:",
        "    output = []",
        "    candidates = PROTOTYPE_INTERACTION_TARGETS or PROTOTYPE_TARGETS",
        "    for target in candidates:",
        "        try:",
        "            x = int(target.get('center_x'))",
        "            y = int(target.get('center_y'))",
        "        except (TypeError, ValueError):",
        "            continue",
        "        if 0 <= x < VIEWPORT_WIDTH and 0 <= y < BOTTOM_FIGMA_CONTROL_Y:",
        "            output.append(target)",
        "    return output[:80]",
        "",
        "",
        "def visible_text_targets() -> list[dict]:",
        "    output = []",
        "    for target in PROTOTYPE_TARGETS:",
        "        try:",
        "            x = int(target.get('center_x'))",
        "            y = int(target.get('center_y'))",
        "        except (TypeError, ValueError):",
        "            continue",
        "        if 0 <= x < VIEWPORT_WIDTH and 0 <= y < BOTTOM_FIGMA_CONTROL_Y:",
        "            output.append(target)",
        "    return output[:120]",
        "",
        "",
        "def matching_candidate_from(candidates: list[dict], label: str) -> dict | None:",
        "    normalized = normalize_label(label)",
        "    if len(normalized) < 4:",
        "        return None",
        "    matches = []",
        "    for target in candidates:",
        "        candidate_label = normalize_label(str(target.get('label') or ''))",
        "        if not candidate_label:",
        "            continue",
        "        if normalized == candidate_label or (len(normalized) >= 8 and normalized in candidate_label) or (len(candidate_label) >= 8 and candidate_label in normalized):",
        "            matches.append(target)",
        "    if not matches:",
        "        return None",
        "    return sorted(matches, key=lambda item: (int(item.get('center_y') or 9999), int(item.get('center_x') or 9999)))[0]",
        "",
        "",
        "def matching_candidate(label: str) -> dict | None:",
        "    return matching_candidate_from(visible_candidate_targets(), label)",
        "",
        "",
        "def unwired_visible_target(label: str) -> dict | None:",
        "    if matching_candidate(label):",
        "        return None",
        "    return matching_candidate_from(visible_text_targets(), label)",
        "",
        "",
        "def snap_decision_to_candidate(decision: PrototypeDecision) -> dict | None:",
        "    candidate = matching_candidate(decision.target)",
        "    if not candidate:",
        "        return None",
        "    original = {'x': decision.x, 'y': decision.y, 'target': decision.target}",
        "    decision.x = int(candidate['center_x'])",
        "    decision.y = int(candidate['center_y'])",
        "    return {'original': original, 'candidate': candidate}",
        "",
        "",
        "def element_at_point(page, x: int, y: int) -> dict:",
        "    return page.evaluate(",
        "        \"\"\"",
        "        ([x, y]) => {",
        "          const el = document.elementFromPoint(x, y);",
        "          if (!el) return {};",
        "          const rect = el.getBoundingClientRect();",
        "          return {",
        "            tag: el.tagName,",
        "            aria_label: el.getAttribute('aria-label') || '',",
        "            text: (el.innerText || el.textContent || '').slice(0, 120),",
        "            class_name: String(el.className || '').slice(0, 120),",
        "            rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},",
        "          };",
        "        }",
        "        \"\"\",",
        "        [x, y],",
        "    )",
        "",
        "",
        "def ask_next_action(*, screenshot_path: Path, url: str, step: int, recent_events: list[dict], model_name: str) -> PrototypeDecision:",
        "    annotated_path = annotate_screenshot(screenshot_path)",
        "    scenario = Scenario({",
        "        'task': TASK,",
        "        'step': step,",
        "        'current_url': url,",
        "        'recent_events': recent_events[-5:],",
        "        'screenshot': FileStore(str(annotated_path)),",
        "        'screenshot_dimensions': {'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT},",
        "        'valid_click_area': {'x_min': 0, 'y_min': 0, 'x_max': VIEWPORT_WIDTH - 1, 'y_max': BOTTOM_FIGMA_CONTROL_Y - 1},",
        "        'candidate_targets': visible_candidate_targets()[:40],",
        "    })",
        "    agent = Agent(",
        "        name='figma-prototype-reviewer',",
        "        traits={",
        "            'role': 'synthetic UX research participant',",
        "            'task_focus': 'understand the prototype, choose the next click, and stop when the path is clear or blocked',",
        "        },",
        "    )",
        "    question = QuestionFreeText(",
        "        question_name='prototype_decision',",
        "        question_text=(",
        "            'You are using a clickable Figma prototype.\\n'",
        "            'Task: {{ scenario.task }}\\n'",
        "            'Step: {{ scenario.step }}\\n'",
        "            'Current URL: {{ scenario.current_url }}\\n'",
        "            'Recent events: {{ scenario.recent_events }}\\n'",
        "            'Screenshot dimensions: {{ scenario.screenshot_dimensions }}\\n'",
        "            'Valid click area: {{ scenario.valid_click_area }}\\n'",
        "            'Candidate Figma interaction targets with exact centers, when available: {{ scenario.candidate_targets }}\\n'",
        "            'Screenshot: {{ scenario.screenshot }}\\n\\n'",
        "            'If you can answer the task or the flow is blocked, set status=done and leave x/y null. '",
        "            'This prototype may use a dark visual design; if you can see text, buttons, logos, or navigation, the screen is not blank. '",
        "            'Otherwise choose exactly one next click coordinate visible in the screenshot. Prefer candidate Figma interaction targets over raw coordinate guesses. '",
        "            'Use the yellow coordinate grid only as a ruler; do not snap to grid intersections or grid lines. '",
        "            'Choose the center of the actual visible text, button, icon, or control you intend to click. '",
        "            'Top navigation labels may have y coordinates around 20-45, not 100. '",
        "            'If a candidate interaction target matches your intended target, use that candidate center exactly. '",
        "            'If a visible item is not represented by any candidate interaction target and previous clicks did not work, treat it as possibly unwired. '",
        "            'Coordinates must be viewport pixel coordinates, with origin at the top-left of the screenshot. '",
        "            'Do not click in the red bottom Figma control area. If recent events show the same target did not work, choose a different target or stop as blocked.\\n'",
        "            'Return only compact JSON with keys: status, x, y, target, thinking, confusion.'",
        "        ),",
        "    )",
        "    results = question.by(scenario).by(agent).by(Model(model_name)).run(remote=True)",
        "    answer = results.to_dict()['data'][0]['answer']['prototype_decision']",
        "    if isinstance(answer, str):",
        "        answer = answer.strip()",
        "        if answer.startswith('```'):",
        "            answer = answer.strip('`')",
        "            answer = answer.replace('json\\n', '', 1).replace('JSON\\n', '', 1).strip()",
        "        answer = json.loads(answer)",
        "    if isinstance(answer, dict):",
        "        status = str(answer.get('status') or '').strip().lower().replace('-', '_').replace(' ', '_')",
        "        status_map = {'incomplete': 'continue', 'next': 'continue', 'click': 'continue', 'complete': 'done', 'completed': 'done', 'blocked': 'done', 'stop': 'done', 'give_up': 'gave_up', 'gaveup': 'gave_up'}",
        "        if status in status_map:",
        "            answer['status'] = status_map[status]",
        "        for key in ('target', 'thinking', 'confusion'):",
        "            if answer.get(key) is None:",
        "                answer[key] = ''",
        "    return PrototypeDecision.model_validate(answer)",
        "",
        "",
        "def run(max_steps: int, model_name: str, headed: bool) -> Path:",
        "    run_dir = BASE_DIR / 'prototype_runs'",
        "    run_dir.mkdir(parents=True, exist_ok=True)",
        "    trace_path = run_dir / 'trace.jsonl'",
        "    if trace_path.exists():",
        "        trace_path.unlink()",
        "    recent_events: list[dict] = []",
        "    with sync_playwright() as p:",
        "        browser = p.chromium.launch(headless=not headed)",
        "        page = browser.new_page(viewport={'width': 1440, 'height': 1000})",
        "        page.goto(SOURCE_URL, wait_until='domcontentloaded', timeout=45000)",
        "        page.wait_for_timeout(2500)",
        "        dismiss_figma_overlays(page)",
        "        for step in range(1, max_steps + 1):",
        "            screenshot_path = run_dir / f'step-{step:03d}.png'",
        "            if not capture_ready_screenshot(page, screenshot_path):",
        "                event = {'step': step, 'url': page.url, 'screenshot': str(screenshot_path), 'decision': {'status': 'gave_up', 'target': '', 'thinking': 'Figma prototype did not finish loading before screenshot timeout.', 'confusion': 'Loading screen remained visible.', 'x': None, 'y': None}, 'failure_type': 'loading_timeout', 'error': 'prototype screenshot did not become ready'}",
        "                recent_events.append(event)",
        "                trace_path.open('a', encoding='utf-8').write(json.dumps(event, sort_keys=True) + '\\n')",
        "                break",
        "            decision = ask_next_action(screenshot_path=screenshot_path, url=page.url, step=step, recent_events=recent_events, model_name=model_name)",
        "            event = {'step': step, 'url': page.url, 'screenshot': str(screenshot_path), 'decision': decision.model_dump()}",
        "            if decision.status == 'continue':",
        "                if decision.x is None or decision.y is None:",
        "                    event['error'] = 'continue decision omitted x/y coordinates'",
        "                    event['failure_type'] = 'agent_invalid_decision'",
        "                    event['decision']['status'] = 'gave_up'",
        "                    recent_events.append(event)",
        "                    trace_path.open('a', encoding='utf-8').write(json.dumps(event, sort_keys=True) + '\\n')",
        "                    break",
        "                unwired = unwired_visible_target(decision.target)",
        "                if unwired:",
        "                    event['unwired_visible_target'] = unwired",
        "                    event['error'] = 'visible target has no Figma prototype interaction'",
        "                    event['failure_type'] = 'unwired_visible_affordance'",
        "                    event['decision']['status'] = 'gave_up'",
        "                    recent_events.append(event)",
        "                    trace_path.open('a', encoding='utf-8').write(json.dumps(event, sort_keys=True) + '\\n')",
        "                    break",
        "                snapped = snap_decision_to_candidate(decision)",
        "                if snapped:",
        "                    event['candidate_snap'] = snapped",
        "                    event['decision'] = decision.model_dump()",
        "                if not (0 <= decision.x < VIEWPORT_WIDTH and 0 <= decision.y < BOTTOM_FIGMA_CONTROL_Y):",
        "                    event['error'] = f'click coordinate outside valid area: ({decision.x}, {decision.y})'",
        "                    event['failure_type'] = 'coordinate_miss'",
        "                    event['decision']['status'] = 'gave_up'",
        "                    recent_events.append(event)",
        "                    trace_path.open('a', encoding='utf-8').write(json.dumps(event, sort_keys=True) + '\\n')",
        "                    break",
        "                event['element_before_click'] = element_at_point(page, decision.x, decision.y)",
        "                page.mouse.click(decision.x, decision.y)",
        "                page.wait_for_timeout(1500)",
        "                dismiss_figma_overlays(page)",
        "                event['after_url'] = page.url",
        "                if repeated_static_target(recent_events, event):",
        "                    event['error'] = 'same target clicked repeatedly without URL change'",
        "                    event['failure_type'] = 'repeated_no_op'",
        "                    event['decision']['status'] = 'gave_up'",
        "                    recent_events.append(event)",
        "                    trace_path.open('a', encoding='utf-8').write(json.dumps(event, sort_keys=True) + '\\n')",
        "                    break",
        "            if decision.status != 'continue':",
        "                event.setdefault('outcome', 'task_completed_or_blocked')",
        "            recent_events.append(event)",
        "            trace_path.open('a', encoding='utf-8').write(json.dumps(event, sort_keys=True) + '\\n')",
        "            if decision.status != 'continue':",
        "                break",
        "        browser.close()",
        "    return trace_path",
        "",
        "",
        "def main() -> None:",
        "    parser = argparse.ArgumentParser(description='Drive a Figma prototype with screenshot-based EDSL coordinate clicks.')",
        "    parser.add_argument('--launch', action='store_true', help='Actually run the prototype. Without this, print configuration only.')",
        "    parser.add_argument('--headed', action='store_true', help='Show the browser while running.')",
        "    parser.add_argument('--model', default=DEFAULT_MODEL)",
        "    parser.add_argument('--max-steps', type=int, default=DEFAULT_MAX_STEPS)",
        "    args = parser.parse_args()",
        "    print(f'Figma prototype: {PROTOTYPE_ID}')",
        "    print(f'Source: {SOURCE_URL}')",
        "    print(f'Task: {TASK}')",
        "    print(f'Model: {args.model}')",
        "    print(f'Max steps: {args.max_steps}')",
        "    if not args.launch:",
        "        print('Dry run only. Re-run with --launch to open Playwright and call EDSL remote inference.')",
        "        return",
        "    trace_path = run(max_steps=args.max_steps, model_name=args.model, headed=args.headed)",
        "    print(trace_path)",
        "",
        "",
        "if __name__ == '__main__':",
        "    main()",
        "",
    ]
    return "\n".join(lines)


def audit_figma_prototype(
    store: Store,
    figma_url: str,
    *,
    token: str | None = None,
    refresh: bool = False,
    viewport_height: int = 1000,
    client: FigmaClient | None = None,
) -> tuple[Path, Path, Path]:
    location = parse_figma_url(figma_url)
    if not location.node_id:
        raise StoreError("Figma audit requires a URL with node-id.", exit_code=2)
    audit_id = f"audit-{_safe_node_id(location.file_key)[:12]}-{_safe_node_id(location.node_id)[:12]}"
    audit_dir = store.path / "figma" / audit_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    document, cache_meta = _cached_figma_node_document(store, location, token=token, refresh=refresh, client=client)
    visible_targets = _prototype_targets(document, viewport_height=viewport_height)
    interactions = _prototype_interactions(document, viewport_height=viewport_height)
    audit = build_figma_audit(
        source_url=figma_url,
        location=location,
        visible_targets=visible_targets,
        interactions=interactions,
        cache_meta=cache_meta,
    )
    audit_path = audit_dir / "audit.json"
    report_path = audit_dir / "audit.md"
    atomic_write_json(audit_path, audit)
    atomic_write_text(report_path, render_figma_audit_report(audit))
    return audit_dir, audit_path, report_path


def build_figma_audit(
    *,
    source_url: str,
    location: FigmaLocation,
    visible_targets: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
    cache_meta: dict[str, Any],
) -> dict[str, Any]:
    wired_labels = [_clean_label(str(item.get("label") or item.get("name") or "")) for item in interactions]
    visible_unwired = []
    for target in visible_targets:
        label = _clean_label(str(target.get("label") or ""))
        if not label:
            continue
        if not _has_label_match(label, wired_labels):
            visible_unwired.append(target)
    vague_interactions = [
        item
        for item in interactions
        if _is_vague_interaction_label(str(item.get("label") or item.get("name") or ""))
    ]
    likely_dead_ends = [
        item
        for item in visible_unwired
        if _looks_actionable_label(str(item.get("label") or ""))
    ]
    return {
        "schema_version": 1,
        "kind": "figma_audit",
        "created_at": utc_now(),
        "source_url": source_url,
        "file_key": location.file_key,
        "node_id": location.node_id,
        "cache": cache_meta,
        "summary": {
            "visible_target_count": len(visible_targets),
            "interaction_target_count": len(interactions),
            "visible_unwired_count": len(visible_unwired),
            "vague_interaction_count": len(vague_interactions),
            "likely_dead_end_count": len(likely_dead_ends),
        },
        "visible_targets": visible_targets,
        "interaction_targets": interactions,
        "visible_unwired_targets": visible_unwired,
        "vague_interaction_targets": vague_interactions,
        "likely_dead_end_targets": likely_dead_ends,
    }


def render_figma_audit_report(audit: dict[str, Any]) -> str:
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    lines = [
        f"# Figma Prototype Audit: {audit.get('node_id')}",
        "",
        f"Source: {audit.get('source_url')}",
        "",
        "## Summary",
        "",
        f"- Visible text targets: {summary.get('visible_target_count', 0)}",
        f"- Wired interaction targets: {summary.get('interaction_target_count', 0)}",
        f"- Visible targets without matching interaction: {summary.get('visible_unwired_count', 0)}",
        f"- Vague interaction labels: {summary.get('vague_interaction_count', 0)}",
        f"- Likely dead-end affordances: {summary.get('likely_dead_end_count', 0)}",
        "",
    ]
    cache = audit.get("cache") if isinstance(audit.get("cache"), dict) else {}
    if cache:
        lines.extend(
            [
                "## Metadata",
                "",
                f"- Cache status: {cache.get('status', 'unknown')}",
                f"- Cache path: `{cache.get('path', '')}`",
                "",
            ]
        )
        if cache.get("warning"):
            lines.extend([f"Warning: {cache['warning']}", ""])
    _append_audit_table(lines, "Likely Dead-End Affordances", audit.get("likely_dead_end_targets") or [])
    _append_audit_table(lines, "Visible But Unwired Targets", audit.get("visible_unwired_targets") or [])
    _append_audit_table(lines, "Wired Interaction Targets", audit.get("interaction_targets") or [], limit=40)
    if not audit.get("likely_dead_end_targets"):
        lines.extend(["## Product Finding", "", "No high-confidence dead-end affordances were detected from metadata alone.", ""])
    else:
        lines.extend(
            [
                "## Product Finding",
                "",
                "The likely dead-end targets are visible labels that look like things a user might click, but no matching Figma prototype interaction was found. These should be reviewed before running synthetic navigation, because agents and users may reasonably choose them and then get stuck.",
                "",
            ]
        )
    return "\n".join(lines)


def _append_audit_table(lines: list[str], title: str, rows: list[Any], *, limit: int = 25) -> None:
    lines.extend([f"## {title}", ""])
    items = [row for row in rows if isinstance(row, dict)][:limit]
    if not items:
        lines.extend(["None detected.", ""])
        return
    lines.extend(["| Label | Center | Size | Node |", "|---|---:|---:|---|"])
    for item in items:
        label = str(item.get("label") or item.get("name") or "").replace("|", "\\|")
        center = f"({item.get('center_x')}, {item.get('center_y')})"
        size = f"{item.get('width')}x{item.get('height')}"
        node_id = str(item.get("node_id") or "")
        lines.append(f"| {label} | {center} | {size} | `{node_id}` |")
    if len(rows) > limit:
        lines.append(f"| ...and {len(rows) - limit} more |  |  |  |")
    lines.append("")


def render_figma_report(store: Store, import_id: str) -> str:
    manifest_path = store.path / "figma" / import_id / "manifest.json"
    if not manifest_path.exists():
        raise StoreError(f"Figma import {import_id!r} does not exist.", exit_code=2)
    manifest = _read_json(manifest_path)
    if manifest.get("kind") == "figma_prototype":
        return render_figma_prototype_report(manifest_path, manifest)
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


def render_figma_prototype_report(manifest_path: Path, manifest: dict[str, Any]) -> str:
    trace_path = manifest_path.parent / "prototype_runs" / "trace.jsonl"
    events = _read_jsonl(trace_path) if trace_path.exists() else []
    title = f"Figma Prototype Study: {manifest.get('import_id')}"
    lines = [
        f"# {title}",
        "",
        f"Source: {manifest.get('source_url')}",
        "",
        f"Task: {manifest.get('task')}",
        "",
        "## Context",
        "",
        "This report summarizes a screenshot-driven prototype run. The runner opens the Figma prototype with Playwright, sends screenshots to EDSL remote vision inference, executes the selected click, and records what happened after each step.",
        "",
    ]
    if manifest.get("prototype_target_error"):
        lines.extend(["Metadata warning:", "", f"`{manifest['prototype_target_error']}`", ""])
    if not events:
        lines.extend(["## Result", "", "No trace events were found. Run the generated prototype runner with `--launch` before writing a prototype report.", ""])
        return "\n".join(lines)

    final = events[-1]
    failure_type = final.get("failure_type")
    if failure_type:
        result = f"The run stopped with `{failure_type}`."
    else:
        result = "The run completed or stopped without a classified failure."
    lines.extend(["## Result", "", result, ""])

    lines.extend(["## Journey", ""])
    for event in events:
        if not isinstance(event, dict):
            continue
        decision = event.get("decision") if isinstance(event.get("decision"), dict) else {}
        step = event.get("step")
        target = decision.get("target") or "(no target)"
        status = decision.get("status") or ""
        coord = ""
        if decision.get("x") is not None and decision.get("y") is not None:
            coord = f" at `({decision.get('x')}, {decision.get('y')})`"
        lines.extend(
            [
                f"### Step {step}",
                "",
                f"- Decision: `{status}` on `{target}`{coord}",
                f"- Rationale: {decision.get('thinking') or ''}",
            ]
        )
        if "after_url" in event:
            lines.append(f"- URL changed: {'yes' if event.get('url') != event.get('after_url') else 'no'}")
        else:
            lines.append("- URL changed: not applicable; no click was executed")
        if event.get("candidate_snap"):
            candidate = (event["candidate_snap"] or {}).get("candidate") or {}
            lines.append(f"- Snapped to Figma interaction: `{candidate.get('label') or candidate.get('name')}`")
        if event.get("failure_type"):
            lines.append(f"- Failure type: `{event['failure_type']}`")
        if event.get("error"):
            lines.append(f"- Error: {event['error']}")
        screenshot = event.get("screenshot")
        if screenshot:
            path = Path(str(screenshot))
            rel = os.path.relpath(path, manifest_path.parent).replace(os.sep, "/") if path.is_absolute() else str(path)
            lines.extend(["", f"![Step {step}]({rel})"])
        lines.append("")

    lines.extend(["## Follow-On Steps", ""])
    if failure_type == "unwired_visible_affordance":
        lines.append("- Review the visible target identified in the trace and wire it to a prototype destination or remove/de-emphasize it.")
    elif failure_type == "repeated_no_op":
        lines.append("- Review whether the repeated target is actually wired. Run `uxtest figma audit` to compare visible labels with Figma interaction targets.")
    elif failure_type == "coordinate_miss":
        lines.append("- Prefer Figma interaction metadata or rerun after auditing the prototype; raw coordinate guessing was unreliable for this step.")
    else:
        lines.append("- Review the step trace and screenshots, then compare intended design paths with the recorded clicks.")
    lines.append("")
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


def _cached_figma_node_document(
    store: Store,
    location: FigmaLocation,
    *,
    token: str | None,
    refresh: bool = False,
    client: FigmaClient | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not location.node_id:
        raise StoreError("Figma node metadata requires node-id.", exit_code=2)
    cache_path = _figma_node_cache_path(store, location)
    if cache_path.exists() and not refresh:
        payload = _read_json(cache_path)
        document = _document_from_nodes_payload(payload, location.node_id)
        return document, {"status": "hit", "path": str(cache_path)}

    figma_client = client or FigmaClient(token or os.environ.get("FIGMA_ACCESS_TOKEN", ""))
    try:
        payload = figma_client.get_nodes(location.file_key, [location.node_id])
    except FigmaRateLimitError as exc:
        if cache_path.exists():
            payload = _read_json(cache_path)
            document = _document_from_nodes_payload(payload, location.node_id)
            return document, {
                "status": "stale_after_rate_limit",
                "path": str(cache_path),
                "warning": str(exc),
                "retry_after": exc.retry_after,
                "plan_tier": exc.plan_tier,
                "rate_limit_type": exc.rate_limit_type,
                "upgrade_link": exc.upgrade_link,
            }
        raise

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(cache_path, payload)
    document = _document_from_nodes_payload(payload, location.node_id)
    return document, {"status": "refreshed", "path": str(cache_path)}


def _figma_node_cache_path(store: Store, location: FigmaLocation) -> Path:
    node = _safe_node_id(location.node_id or "node")
    return store.path / "figma" / "cache" / "nodes" / f"{_safe_node_id(location.file_key)}-{node}.json"


def _document_from_nodes_payload(payload: dict[str, Any], node_id: str) -> dict[str, Any]:
    node_entry = ((payload.get("nodes") or {}).get(node_id) or {}) if isinstance(payload.get("nodes"), dict) else {}
    document = node_entry.get("document")
    if not isinstance(document, dict):
        raise StoreError(f"Figma did not return node {node_id!r}.", exit_code=1)
    return document


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


def _prototype_targets(node: dict[str, Any], *, viewport_height: int) -> list[dict[str, Any]]:
    frame_bounds = node.get("absoluteBoundingBox") if isinstance(node.get("absoluteBoundingBox"), dict) else {}
    frame_x = float(frame_bounds.get("x") or 0)
    frame_y = float(frame_bounds.get("y") or 0)
    frame_width = float(frame_bounds.get("width") or 0)
    targets: list[dict[str, Any]] = []
    _collect_prototype_targets(node, targets, frame_x=frame_x, frame_y=frame_y, frame_width=frame_width, viewport_height=viewport_height)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for target in sorted(targets, key=lambda item: (item["center_y"], item["center_x"])):
        key = (str(target["label"]).casefold(), int(target["center_x"]), int(target["center_y"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped[:120]


def _prototype_interactions(node: dict[str, Any], *, viewport_height: int) -> list[dict[str, Any]]:
    frame_bounds = node.get("absoluteBoundingBox") if isinstance(node.get("absoluteBoundingBox"), dict) else {}
    frame_x = float(frame_bounds.get("x") or 0)
    frame_y = float(frame_bounds.get("y") or 0)
    frame_width = float(frame_bounds.get("width") or 0)
    interactions: list[dict[str, Any]] = []
    _collect_prototype_interactions(
        node,
        interactions,
        frame_x=frame_x,
        frame_y=frame_y,
        frame_width=frame_width,
        viewport_height=viewport_height,
    )
    return sorted(interactions, key=lambda item: (item["center_y"], item["center_x"]))[:160]


def _collect_prototype_interactions(
    node: dict[str, Any],
    interactions: list[dict[str, Any]],
    *,
    frame_x: float,
    frame_y: float,
    frame_width: float,
    viewport_height: int,
) -> None:
    bounds = node.get("absoluteBoundingBox") if isinstance(node.get("absoluteBoundingBox"), dict) else {}
    has_interaction = bool(node.get("transitionNodeID") or node.get("reactions"))
    if has_interaction and bounds:
        x = float(bounds.get("x") or 0) - frame_x
        y = float(bounds.get("y") or 0) - frame_y
        width = float(bounds.get("width") or 0)
        height = float(bounds.get("height") or 0)
        if width > 0 and height > 0 and -height <= y <= viewport_height and x <= max(frame_width, 1) and x + width >= 0:
            label = _text_preview(node).replace("\n", " | ")
            interactions.append(
                {
                    "label": label[:180] or str(node.get("name") or ""),
                    "name": str(node.get("name") or ""),
                    "node_id": str(node.get("id") or ""),
                    "transition_node_id": str(node.get("transitionNodeID") or ""),
                    "center_x": round(x + width / 2),
                    "center_y": round(y + height / 2),
                    "x": round(x),
                    "y": round(y),
                    "width": round(width),
                    "height": round(height),
                }
            )
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _collect_prototype_interactions(
                child,
                interactions,
                frame_x=frame_x,
                frame_y=frame_y,
                frame_width=frame_width,
                viewport_height=viewport_height,
            )


def _collect_prototype_targets(
    node: dict[str, Any],
    targets: list[dict[str, Any]],
    *,
    frame_x: float,
    frame_y: float,
    frame_width: float,
    viewport_height: int,
) -> None:
    characters = node.get("characters")
    bounds = node.get("absoluteBoundingBox") if isinstance(node.get("absoluteBoundingBox"), dict) else {}
    if isinstance(characters, str) and characters.strip() and bounds:
        x = float(bounds.get("x") or 0) - frame_x
        y = float(bounds.get("y") or 0) - frame_y
        width = float(bounds.get("width") or 0)
        height = float(bounds.get("height") or 0)
        if width > 0 and height > 0 and -height <= y <= viewport_height and 0 <= x <= max(frame_width, 1):
            targets.append(
                {
                    "label": characters.strip()[:120],
                    "node_id": str(node.get("id") or ""),
                    "center_x": round(x + width / 2),
                    "center_y": round(y + height / 2),
                    "x": round(x),
                    "y": round(y),
                    "width": round(width),
                    "height": round(height),
                }
            )
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _collect_prototype_targets(
                child,
                targets,
                frame_x=frame_x,
                frame_y=frame_y,
                frame_width=frame_width,
                viewport_height=viewport_height,
            )


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


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _clean_label(value: str) -> str:
    return " ".join(value.replace("\n", " | ").split()).strip()


def _normalize_label(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _has_label_match(label: str, candidate_labels: list[str]) -> bool:
    normalized = _normalize_label(label)
    if len(normalized) < 3:
        return False
    for candidate in candidate_labels:
        candidate_normalized = _normalize_label(candidate)
        if not candidate_normalized:
            continue
        if normalized == candidate_normalized:
            return True
        if len(normalized) >= 8 and normalized in candidate_normalized:
            return True
    return False


def _is_vague_interaction_label(label: str) -> bool:
    normalized = _normalize_label(label)
    if not normalized:
        return True
    vague = {"headline", "description", "xx", "xxxx", "button", "navprimary", "navsecondary", "navdetail"}
    if normalized in vague:
        return True
    words = [word.strip().casefold() for word in re.split(r"[^A-Za-z0-9]+", label) if word.strip()]
    if words and all(word in {"headline", "description", "xx", "button"} for word in words):
        return True
    return False


def _looks_actionable_label(label: str) -> bool:
    normalized = _normalize_label(label)
    if len(normalized) < 4:
        return False
    action_terms = [
        "start",
        "signup",
        "login",
        "demo",
        "enterprise",
        "pricing",
        "contact",
        "learnmore",
        "getstarted",
        "findtalent",
        "docs",
        "examples",
        "download",
    ]
    return any(term in normalized for term in action_terms)


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
