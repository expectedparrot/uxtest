from __future__ import annotations

import json
import py_compile
from pathlib import Path

from uxtest.agent_export import export_agent_list, export_interview_script
from uxtest.cli import main
from uxtest.store import Store


def test_export_agent_list_writes_rich_edsl_agents(tmp_path):
    store, study_id = _store_with_trace_screenshots(tmp_path)

    script_path, manifest_path = export_agent_list(store, study_id)

    py_compile.compile(str(script_path), doraise=True)
    script = script_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "AgentList" in script
    assert "FileStore" in script
    assert "screenshot_files" in script
    assert "The demo CTA is visible." in script
    assert "journey" in script
    assert manifest["agent_count"] == 1
    assert manifest["agents"][0]["screenshot_count"] == 2


def test_export_interview_script_uses_rich_agents_and_remote_edsl(tmp_path):
    store, study_id = _store_with_trace_screenshots(tmp_path)

    script_path, manifest_path = export_interview_script(
        store,
        study_id,
        model="test-model",
        questions=["What confused you?"],
    )

    py_compile.compile(str(script_path), doraise=True)
    script = script_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "QuestionFreeText" in script
    assert "survey.by(agents).by(Model(args.model)).run(remote=True)" in script
    assert "Dry run only" in script
    assert "What confused you?" in script
    assert manifest["model"] == "test-model"
    assert manifest["questions"] == ["What confused you?"]


def test_agent_export_cli_commands(tmp_path, capsys):
    store, study_id = _store_with_trace_screenshots(tmp_path)

    main(["--store", str(store.root), "agents", "export", study_id])
    agent_output = capsys.readouterr().out
    assert "agent_list.py" in agent_output
    assert "agent_list.manifest.json" in agent_output

    main(["--store", str(store.root), "interview", study_id, "--question", "What happened?"])
    interview_output = capsys.readouterr().out
    assert "agent_interview.py" in interview_output
    assert "agent_interview.manifest.json" in interview_output


def _store_with_trace_screenshots(tmp_path: Path) -> tuple[Store, str]:
    store = Store.init(tmp_path)
    store.create_persona("enterprise-buyer", description="Evaluates procurement risk")
    study_dir = store.create_study(
        "Demo path",
        task="Find the demo path.",
        url="http://example.test",
        success_criteria="Reach the demo form.",
        personas=["enterprise-buyer"],
    )
    study_id = study_dir.name
    run_dir = study_dir / "runs" / "run-001-enterprise-buyer-abcd"
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
                "outcome": "done",
                "steps_taken": 2,
                "final_url": "http://example.test/demo",
                "persona_instance": {
                    "name": "enterprise-buyer",
                    "resolved": {"company_size": "enterprise"},
                    "snapshot": {
                        "goals_bias": "Looks for proof that the company is credible and sales-ready.",
                    },
                },
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
                "headings": ["Welcome"],
                "interactive_elements_sample": [
                    {"ref": "e1", "role": "button", "text": "Get a demo"},
                    {"ref": "e2", "role": "link", "text": "Docs"},
                ],
            },
            "action": {"type": "click", "text": "Get a demo"},
            "result": {"ok": True, "navigation": "http://example.test/demo"},
            "thinking": "The demo CTA is visible.",
        },
        {
            "schema_version": 1,
            "event_type": "step",
            "step": 2,
            "url": "http://example.test/demo",
            "page_title": "Demo",
            "frustration": 4,
            "status": "done",
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
