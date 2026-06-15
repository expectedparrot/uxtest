from __future__ import annotations

import json
import py_compile

from uxtest.figma import import_figma_frames, parse_figma_url, write_figma_report, write_figma_study_script
from uxtest.store import Store


def test_parse_figma_url_extracts_file_key_and_node_id():
    location = parse_figma_url("https://www.figma.com/design/abc123/My-File?node-id=1-24&t=xyz")

    assert location.file_key == "abc123"
    assert location.node_id == "1:24"


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
