from __future__ import annotations

import json
import py_compile

from uxtest.figma import (
    audit_figma_prototype,
    FigmaRateLimitError,
    import_figma_frames,
    parse_figma_url,
    _prototype_interactions,
    _prototype_targets,
    write_figma_prototype_script,
    write_figma_report,
    write_figma_study_script,
)
from uxtest.store import Store


def test_parse_figma_url_extracts_file_key_and_node_id():
    location = parse_figma_url("https://www.figma.com/design/abc123/My-File?node-id=1-24&t=xyz")

    assert location.file_key == "abc123"
    assert location.node_id == "1:24"
    assert location.kind == "design"


def test_parse_figma_proto_url_extracts_prototype_context():
    location = parse_figma_url(
        "https://www.figma.com/proto/GQbpvEGImEtoQzKvM8Imv5/Homepage-v3?"
        "node-id=7456-94184&starting-point-node-id=7456%3A94184&page-id=7456%3A87150"
    )

    assert location.file_key == "GQbpvEGImEtoQzKvM8Imv5"
    assert location.kind == "proto"
    assert location.node_id == "7456:94184"
    assert location.starting_point_node_id == "7456:94184"
    assert location.page_id == "7456:87150"


def test_import_figma_selected_frame(tmp_path):
    store = Store.init(tmp_path)

    import_dir, manifest_path = import_figma_frames(
        store,
        "https://www.figma.com/design/file123/My-File?node-id=1-24",
        client=FakeFigmaClient(),
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["file_key"] == "file123"
    assert manifest["frame_count"] == 1
    assert manifest["frames"][0]["node_id"] == "1:24"
    assert "Get started" in manifest["frames"][0]["text_preview"]
    image_path = import_dir / manifest["frames"][0]["image"]
    assert image_path.read_bytes() == b"fake-png"


def test_figma_study_script_and_report(tmp_path):
    store = Store.init(tmp_path)
    import_dir, _manifest_path = import_figma_frames(
        store,
        "https://www.figma.com/design/file123/My-File?node-id=1-24",
        client=FakeFigmaClient(),
    )

    script_path, study_manifest_path = write_figma_study_script(
        store,
        import_dir.name,
        task="Figure out what to click next.",
    )
    py_compile.compile(str(script_path), doraise=True)
    script = script_path.read_text(encoding="utf-8")
    assert "QuestionMultipleChoice" in script
    assert "Dry run only" in script
    assert json.loads(study_manifest_path.read_text(encoding="utf-8"))["task"] == "Figure out what to click next."

    report_path = write_figma_report(store, import_dir.name)
    report = report_path.read_text(encoding="utf-8")
    assert "# Figma Import:" in report
    assert "Homepage" in report
    assert "frames/" in report


def test_figma_prototype_script_generation(tmp_path):
    store = Store.init(tmp_path)

    script_path, manifest_path = write_figma_prototype_script(
        store,
        "https://www.figma.com/proto/GQbpvEGImEtoQzKvM8Imv5/Homepage-v3?node-id=7456-94184",
        task="Find the enterprise demo path.",
        max_steps=4,
    )

    py_compile.compile(str(script_path), doraise=True)
    script = script_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "sync_playwright" in script
    assert "PrototypeDecision" in script
    assert "coordinate" in script.lower()
    assert "'incomplete': 'continue'" in script
    assert "annotate_screenshot" in script
    assert "dismiss_figma_overlays" in script
    assert "element_before_click" in script
    assert "repeated_static_target" in script
    assert "candidate_snap" in script
    assert "PROTOTYPE_TARGETS" in script
    assert "PROTOTYPE_INTERACTION_TARGETS" in script
    assert "unwired_visible_target" in script
    assert "domcontentloaded" in script
    assert "failure_type" in script
    assert "unwired_visible_affordance" in script
    assert "repeated_no_op" in script
    assert "capture_ready_screenshot" in script
    assert "loading_timeout" in script
    assert "page.reload" in script
    assert "ImageEnhance" in script
    assert "screen is not blank" in script
    assert manifest["kind"] == "figma_prototype"
    assert manifest["max_steps"] == 4


def test_prototype_targets_use_frame_relative_centers():
    node = {
        "id": "1:1",
        "absoluteBoundingBox": {"x": -100, "y": -200, "width": 1440, "height": 900},
        "children": [
            {
                "id": "2:1",
                "type": "TEXT",
                "characters": "Enterprise",
                "absoluteBoundingBox": {"x": 685, "y": -180, "width": 90, "height": 24},
            },
            {
                "id": "2:2",
                "type": "TEXT",
                "characters": "Footer",
                "absoluteBoundingBox": {"x": 0, "y": 2000, "width": 90, "height": 24},
            },
        ],
    }

    targets = _prototype_targets(node, viewport_height=1000)

    assert targets == [
        {
            "label": "Enterprise",
            "node_id": "2:1",
            "center_x": 830,
            "center_y": 32,
            "x": 785,
            "y": 20,
            "width": 90,
            "height": 24,
        }
    ]


def test_prototype_interactions_use_descendant_text_labels():
    node = {
        "id": "1:1",
        "absoluteBoundingBox": {"x": -100, "y": -200, "width": 1440, "height": 900},
        "children": [
            {
                "id": "2:1",
                "name": "Button",
                "type": "INSTANCE",
                "transitionNodeID": "3:1",
                "absoluteBoundingBox": {"x": 1200, "y": -188, "width": 81, "height": 40},
                "children": [
                    {
                        "id": "2:2",
                        "type": "TEXT",
                        "characters": "Sign up",
                        "absoluteBoundingBox": {"x": 1225, "y": -179, "width": 49, "height": 22},
                    }
                ],
            }
        ],
    }

    interactions = _prototype_interactions(node, viewport_height=1000)

    assert interactions == [
        {
            "label": "Sign up",
            "name": "Button",
            "node_id": "2:1",
            "transition_node_id": "3:1",
            "center_x": 1340,
            "center_y": 32,
            "x": 1300,
            "y": 12,
            "width": 81,
            "height": 40,
        }
    ]


def test_figma_audit_flags_visible_unwired_affordance(tmp_path):
    store = Store.init(tmp_path)

    _audit_dir, audit_path, report_path = audit_figma_prototype(
        store,
        "https://www.figma.com/proto/file123/My-File?node-id=1-1",
        client=FakePrototypeClient(),
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    assert audit["summary"]["visible_target_count"] == 2
    assert audit["summary"]["interaction_target_count"] == 1
    assert [item["label"] for item in audit["likely_dead_end_targets"]] == ["Enterprise"]
    assert "Likely Dead-End Affordances" in report
    assert "Enterprise" in report


def test_figma_audit_uses_stale_cache_after_rate_limit(tmp_path):
    store = Store.init(tmp_path)
    url = "https://www.figma.com/proto/file123/My-File?node-id=1-1"

    audit_figma_prototype(store, url, client=FakePrototypeClient())
    _audit_dir, audit_path, _report_path = audit_figma_prototype(store, url, refresh=True, client=RateLimitedPrototypeClient())

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["cache"]["status"] == "stale_after_rate_limit"
    assert audit["cache"]["retry_after"] == 30
    assert [item["label"] for item in audit["likely_dead_end_targets"]] == ["Enterprise"]


def test_figma_report_handles_prototype_trace(tmp_path):
    store = Store.init(tmp_path)
    script_path, manifest_path = write_figma_prototype_script(
        store,
        "https://www.figma.com/proto/GQbpvEGImEtoQzKvM8Imv5/Homepage-v3?node-id=7456-94184",
        task="Find the enterprise demo path.",
        max_steps=4,
    )
    run_dir = script_path.parent / "prototype_runs"
    run_dir.mkdir()
    screenshot = run_dir / "step-001.png"
    screenshot.write_bytes(b"fake")
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "step": 1,
                "url": "https://figma.example/proto",
                "after_url": "https://figma.example/proto",
                "screenshot": str(screenshot),
                "decision": {
                    "status": "gave_up",
                    "target": "Enterprise",
                    "thinking": "This looks like the right enterprise path.",
                    "x": 820,
                    "y": 33,
                },
                "failure_type": "unwired_visible_affordance",
                "error": "visible target has no Figma prototype interaction",
            }
        )
        + "\n"
        + json.dumps(
            {
                "step": 2,
                "url": "https://figma.example/proto",
                "screenshot": str(screenshot),
                "decision": {
                    "status": "done",
                    "target": "Enterprise",
                    "thinking": "The path is blocked.",
                    "x": None,
                    "y": None,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report_path = write_figma_report(store, manifest_path.parent.name)
    report = report_path.read_text(encoding="utf-8")

    assert "Figma Prototype Study" in report
    assert "unwired_visible_affordance" in report
    assert "prototype_runs/step-001.png" in report
    assert "URL changed: not applicable; no click was executed" in report


class FakeFigmaClient:
    def get_nodes(self, file_key, node_ids):
        assert file_key == "file123"
        assert node_ids == ["1:24"]
        return {
            "nodes": {
                "1:24": {
                    "document": {
                        "id": "1:24",
                        "name": "Homepage",
                        "type": "FRAME",
                        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 900},
                        "children": [
                            {"id": "2:1", "name": "Hero headline", "type": "TEXT", "characters": "Research faster"},
                            {"id": "2:2", "name": "Get started", "type": "TEXT", "characters": "Get started"},
                        ],
                    }
                }
            }
        }

    def get_file(self, file_key):
        raise AssertionError("selected import should not fetch the full file")

    def get_image_urls(self, file_key, node_ids, *, scale=2.0, fmt="png"):
        assert node_ids == ["1:24"]
        return {"1:24": "https://figma.example/image.png"}

    def download(self, url):
        assert url == "https://figma.example/image.png"
        return b"fake-png"


class FakePrototypeClient:
    def get_nodes(self, file_key, node_ids):
        assert file_key == "file123"
        assert node_ids == ["1:1"]
        return {
            "nodes": {
                "1:1": {
                    "document": {
                        "id": "1:1",
                        "name": "Prototype frame",
                        "type": "FRAME",
                        "absoluteBoundingBox": {"x": -100, "y": -200, "width": 1440, "height": 900},
                        "children": [
                            {
                                "id": "2:1",
                                "name": "Title",
                                "type": "TEXT",
                                "characters": "Enterprise",
                                "absoluteBoundingBox": {"x": 685, "y": -180, "width": 90, "height": 24},
                            },
                            {
                                "id": "2:2",
                                "name": "Button",
                                "type": "INSTANCE",
                                "transitionNodeID": "3:1",
                                "absoluteBoundingBox": {"x": 1200, "y": -188, "width": 81, "height": 40},
                                "children": [
                                    {
                                        "id": "2:3",
                                        "type": "TEXT",
                                        "characters": "Sign up",
                                        "absoluteBoundingBox": {"x": 1225, "y": -179, "width": 49, "height": 22},
                                    }
                                ],
                            },
                        ],
                    }
                }
            }
        }


class RateLimitedPrototypeClient:
    def get_nodes(self, file_key, node_ids):
        raise FigmaRateLimitError(
            "Figma API request failed with HTTP 429: rate limited",
            retry_after=30,
            plan_tier="starter",
            rate_limit_type="low",
        )
