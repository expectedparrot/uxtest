from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from uxtest.cli import main
from uxtest.saliency import run_saliency
from uxtest.store import Store, StoreError


def test_run_saliency_command_writes_overlay_manifest_and_index(tmp_path):
    store, study_id = _store_with_png_screenshot(tmp_path)
    command = _copy_image_command(tmp_path)

    root, manifest_path, html_path = run_saliency(
        store,
        study_id,
        engine="command",
        command_template=f"{command} {{input}} {{output}}",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert root.name == "saliency"
    assert html_path.exists()
    assert manifest["engine"] == "command"
    assert manifest["item_count"] == 1
    item = manifest["items"][0]
    assert item["overlay"].endswith("-overlay.png")
    assert (root / item["overlay"]).exists()
    assert item["returncode"] == 0
    assert "External saliency command" in html_path.read_text(encoding="utf-8")
    assert "Saliency Review" in html_path.read_text(encoding="utf-8")


def test_saliency_cli_run_command(tmp_path, capsys):
    store, study_id = _store_with_png_screenshot(tmp_path)
    command = _copy_image_command(tmp_path)

    main(
        [
            "--store",
            str(store.root),
            "saliency",
            "run",
            study_id,
            "--max-screenshots",
            "1",
            "--command-template",
            f"{command} {{input}} {{output}}",
        ]
    )

    output = capsys.readouterr().out
    assert "analysis/saliency" in output
    assert "manifest.json" in output
    assert "index.html" in output


def test_saliency_command_engine_requires_template(tmp_path, monkeypatch):
    monkeypatch.delenv("UXTEST_SALIENCY_COMMAND", raising=False)
    store, study_id = _store_with_png_screenshot(tmp_path)

    with pytest.raises(StoreError) as exc:
        run_saliency(store, study_id)

    assert exc.value.exit_code == 2
    assert "requires a real external model command" in str(exc.value)


def _store_with_png_screenshot(tmp_path: Path) -> tuple[Store, str]:
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Visual Attention",
        task="Find the primary CTA.",
        url="http://example.test",
    )
    study_id = study_dir.name
    run_dir = study_dir / "runs" / "run-001-seniors-abcd"
    screenshots_dir = run_dir / "screenshots"
    screenshots_dir.mkdir(parents=True)
    Image.new("RGB", (80, 60), color=(245, 245, 245)).save(screenshots_dir / "step-001.png")
    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_dir.name,
                "study_id": study_id,
                "outcome": "done",
                "steps_taken": 1,
                "persona_instance": {"name": "seniors"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event_type": "step",
                "step": 1,
                "url": "http://example.test",
                "page_title": "Home",
                "status": "continue",
                "frustration": 2,
                "observation": {
                    "screenshot": "screenshots/step-001.png",
                    "visible_text_preview": "Welcome. Get started.",
                },
                "action": {"type": "click", "text": "Get started"},
                "thinking": "The primary CTA is the likely next step.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return store, study_id


def _copy_image_command(tmp_path: Path) -> Path:
    script = tmp_path / "copy_saliency.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import shutil\n"
        "import sys\n"
        "shutil.copyfile(sys.argv[1], sys.argv[2])\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script
