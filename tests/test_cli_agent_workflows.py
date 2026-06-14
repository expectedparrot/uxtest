from __future__ import annotations

import json

import pytest

from uxtest.cli import _doc_resource, main
from uxtest.store import Store


def test_docs_without_subcommand_lists_docs(capsys):
    main(["docs"])

    output = capsys.readouterr().out
    assert "README.md" in output
    assert "study_types/task_discovery/README.md" in output


def test_doc_resource_accepts_short_readme_path():
    assert _doc_resource("feature_findability/README.md").is_file()


def test_persona_list_show_and_path(tmp_path, capsys):
    store = Store.init(tmp_path)
    store.create_persona("enterprise-buyer", description="Evaluates procurement risk")

    main(["--store", str(store.root), "persona", "list"])
    assert "enterprise-buyer" in capsys.readouterr().out

    main(["--store", str(store.root), "persona", "show", "enterprise-buyer"])
    assert "Evaluates procurement risk" in capsys.readouterr().out

    main(["--store", str(store.root), "persona", "path", "enterprise-buyer"])
    assert ".uxtest/personas/enterprise-buyer.yaml" in capsys.readouterr().out


def test_trace_summary_and_edsl_jobs(tmp_path, capsys):
    store, study_id = _store_with_edsl_trace(tmp_path)

    main(["--store", str(store.root), "trace", study_id])
    summary = capsys.readouterr().out
    assert "Run: run-001-seniors-abcd" in summary
    assert "thinking: About likely contains team information." in summary

    main(["--store", str(store.root), "trace", study_id, "--edsl-jobs", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["edsl_jobs"][0]["results_url"] == "https://www.expectedparrot.com/content/result-1"
    assert data["edsl_jobs"][0]["question_type"] == "pydantic"


def test_report_writes_narrative_markdown(tmp_path, capsys):
    store, study_id = _store_with_edsl_trace(tmp_path)

    main(["--store", str(store.root), "report", study_id])

    output = capsys.readouterr().out
    assert ".uxtest/studies/" in output
    report = store.study_dir(study_id) / "analysis" / "narrative_report.md"
    text = report.read_text(encoding="utf-8")
    assert "# Founder Findability" in text
    assert "## Context" in text
    assert "About likely contains team information." in text
    assert "../runs/run-001-seniors-abcd/screenshots/step-001.png" in text


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
    assert "uxtest " in capsys.readouterr().out


def _store_with_edsl_trace(tmp_path):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Founder Findability",
        task="Find who founded the company.",
        url="https://example.test",
        success_criteria="Founder names are found.",
    )
    run_dir = study_dir / "runs" / "run-001-seniors-abcd"
    screenshots = run_dir / "screenshots"
    screenshots.mkdir(parents=True)
    (screenshots / "step-001.png").write_bytes(b"fake png")
    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "run_id": "run-001-seniors-abcd",
                "study_id": study_dir.name,
                "outcome": "done",
                "steps_taken": 1,
                "final_url": "https://example.test/about",
                "persona_instance": {"name": "seniors"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "step": 1,
                "url": "https://example.test",
                "page_title": "Example",
                "status": "continue",
                "thinking": "About likely contains team information.",
                "frustration": 1,
                "action": {"type": "click", "ref": "e4", "text": "About"},
                "observation": {"screenshot": "screenshots/step-001.png"},
                "model_decision": {
                    "edsl": {
                        "question_type": "pydantic",
                        "question_name": "browser_decision",
                        "model": "gpt-4o",
                        "job": {
                            "job_uuid": "job-1",
                            "progress_url": "https://www.expectedparrot.com/home/remote-job-progress/job-1",
                            "results_url": "https://www.expectedparrot.com/content/result-1",
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return store, study_dir.name
