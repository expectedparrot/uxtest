from __future__ import annotations

import json
from pathlib import Path

from uxtest.humanize_export import collect_screenshot_scenarios, export_humanize_survey
from uxtest.store import Store


def test_humanize_export_writes_script_and_manifest(tmp_path):
    store, study_id = _store_with_trace_screenshots(tmp_path)

    script_path, manifest_path = export_humanize_survey(
        store,
        study_id,
        template="conversion",
        screenshots="representative",
        max_screenshots=2,
    )

    script = script_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "survey.by(scenarios).humanize" in script
    assert "scenario_list_method='ordered'" in script
    assert "QuestionMultipleChoice" in script
    assert "question_name='target_path'" in script
    assert "question_options='{{ scenario.choice_options }}'" in script
    assert "QuestionLinearScale" in script
    assert "HUMANIZE_SCHEMA" in script
    assert "max-width: min(100%, 760px)" in script
    assert "humanize_schema=HUMANIZE_SCHEMA" in script
    assert "Dry run only" in script
    assert manifest["template"] == "conversion"
    assert manifest["scenario_count"] == 2
    assert manifest["scenarios"][0]["screenshot"].endswith("step-001.png")
    assert "Get a demo (button)" in manifest["scenarios"][0]["choice_options"]


def test_collect_screenshot_scenarios_supports_first_last(tmp_path):
    store, study_id = _store_with_trace_screenshots(tmp_path)

    scenarios = collect_screenshot_scenarios(
        store,
        study_id,
        selection="first-last",
        max_screenshots=10,
        script_dir=tmp_path,
    )

    assert [scenario.selection_reason for scenario in scenarios] == ["first", "last"]
    assert [scenario.step for scenario in scenarios] == [1, 2]


def _store_with_trace_screenshots(tmp_path: Path) -> tuple[Store, str]:
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Demo path",
        task="Find the demo path.",
        url="http://example.test",
        personas=["seniors"],
    )
    study_id = study_dir.name
    run_dir = study_dir / "runs" / "run-001-seniors-abcd"
    screenshots_dir = run_dir / "screenshots"
    screenshots_dir.mkdir(parents=True)
    (screenshots_dir / "step-001.png").write_bytes(b"fake-png-1")
    (screenshots_dir / "step-002.png").write_bytes(b"fake-png-2")
    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_dir.name,
                "study_id": study_id,
                "outcome": "max_steps",
                "steps_taken": 2,
                "persona_instance": {"name": "seniors"},
            }
        ),
        encoding="utf-8",
    )
    events = [
        {
            "schema_version": 1,
            "event_type": "step",
            "step": 1,
            "url": "http://example.test",
            "page_title": "Home",
            "frustration": 1,
            "status": "continue",
            "observation": {
                "screenshot": "screenshots/step-001.png",
                "visible_text_preview": "Welcome. Get a demo.",
                "interactive_elements_sample": [
                    {"ref": "e1", "role": "button", "text": "Get a demo"},
                    {"ref": "e2", "role": "link", "text": "Docs"},
                ],
            },
            "action": {"type": "click", "text": "Get a demo"},
            "result": {"ok": True},
            "thinking": "The demo CTA is visible.",
        },
        {
            "schema_version": 1,
            "event_type": "step",
            "step": 2,
            "url": "http://example.test/demo",
            "page_title": "Demo",
            "frustration": 4,
            "status": "continue",
            "observation": {
                "screenshot": "screenshots/step-002.png",
                "visible_text_preview": "Demo form.",
                "interactive_elements_sample": [
                    {"ref": "e1", "role": "textbox", "placeholder": "Work email"},
                    {"ref": "e2", "role": "button", "text": "Submit"},
                ],
            },
            "action": {"type": "none"},
            "result": {"ok": True},
            "thinking": "The form asks for contact details.",
        },
    ]
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    return store, study_id
