from __future__ import annotations

import json

import pytest

from uxtest.cli import _doc_resource, main
from uxtest.store import Store


def test_docs_without_subcommand_lists_docs(capsys):
    main(["docs"])

    output = capsys.readouterr().out
    assert "README.md" in output
    assert "report_writer_agent.md" in output
    assert "study_types/task_discovery/README.md" in output


def test_doc_resource_accepts_short_readme_path():
    assert _doc_resource("feature_findability/README.md").is_file()


def test_report_writer_agent_doc_is_discoverable(capsys):
    assert _doc_resource("report-writer-agent").is_file()

    main(["docs", "show", "report-writer-agent"])
    output = capsys.readouterr().out
    assert "Report Writer Agent Guide" in output
    assert "action_outcome" in output
    assert "stop_quality" in output


def test_persona_list_show_and_path(tmp_path, capsys):
    store = Store.init(tmp_path)
    store.create_persona("enterprise-buyer", description="Evaluates procurement risk")

    main(["--store", str(store.root), "persona", "list"])
    assert "enterprise-buyer" in capsys.readouterr().out

    main(["--store", str(store.root), "persona", "show", "enterprise-buyer"])
    assert "Evaluates procurement risk" in capsys.readouterr().out

    main(["--store", str(store.root), "persona", "path", "enterprise-buyer"])
    assert "uxtest_store/personas/enterprise-buyer.yaml" in capsys.readouterr().out


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
    assert "uxtest_store/studies/" in output
    report = store.study_dir(study_id) / "analysis" / "narrative_report.md"
    text = report.read_text(encoding="utf-8")
    assert "# Founder Findability" in text
    assert "## Context" in text
    assert "## Trust And Seriousness Signals" in text
    assert "company substance cue" in text
    assert "About likely contains team information." in text
    assert "../runs/run-001-seniors-abcd/screenshots/step-001.png" in text


def test_batch_report_dedupes_findings_and_flags_reliability(tmp_path, capsys):
    store, first = _store_with_batch_study(
        tmp_path,
        title="Demo Path",
        outcome="max_steps",
        finding_title="Product-learning action led to login",
        final_url="https://example.test/login",
    )
    _, second = _store_with_batch_study(
        tmp_path,
        title="Enterprise Demo",
        outcome="max_steps",
        finding_title="Product-learning action led to login",
        final_url="https://example.test/login",
    )

    main(
        [
            "--store",
            str(store.root),
            "batch",
            "report",
            "acme-cross-study",
            "--title",
            "Acme Cross Study",
            "--study",
            first,
            "--study",
            second,
        ]
    )

    output = capsys.readouterr().out
    assert "uxtest_store/comparisons/acme-cross-study.md" in output
    report = store.path / "comparisons" / "acme-cross-study.md"
    text = report.read_text(encoding="utf-8")
    assert "# Acme Cross Study" in text
    assert "Product-learning action led to login" in text
    assert "2 studies" in text
    assert "Runs ending at `max_steps`: 2" in text
    assert "Click actions with no visible advance: 2" in text
    assert "## Run Resolution" in text
    assert "blocked_by_auth=2" in text
    assert "Unresolved path at max steps" in text
    assert "acme-cross-study.manifest.json" in {path.name for path in (store.path / "comparisons").iterdir()}


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


def _store_with_batch_study(tmp_path, *, title, outcome, finding_title, final_url):
    store = Store.init(tmp_path) if not (tmp_path / "uxtest_store").exists() else Store(tmp_path / "uxtest_store")
    study_dir = store.create_study(
        title,
        task="Find a buying path.",
        url="https://example.test",
        success_criteria="A next step is found.",
    )
    run_dir = study_dir / "runs" / f"run-001-seniors-{study_dir.name[-4:]}"
    screenshots = run_dir / "screenshots"
    screenshots.mkdir(parents=True)
    (screenshots / "step-001.png").write_bytes(b"fake png")
    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "study_id": study_dir.name,
                "outcome": outcome,
                "steps_taken": 1,
                "final_url": final_url,
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
                "status": "continue",
                "thinking": "The Get started CTA may lead to a buying path.",
                "frustration": 6,
                "action": {"type": "click", "ref": "e1", "text": "Get started"},
                "result": {"ok": True, "navigation": False, "final_url": final_url},
                "observation": {"screenshot": "screenshots/step-001.png"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    analysis_dir = study_dir / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    (analysis_dir / "scores.json").write_text(
        json.dumps(
            {
                "study_id": study_dir.name,
                "runs_analyzed": 1,
                "outcomes": {outcome: 1},
                "mean_steps": 1,
                "task_completion_rate": 0,
            }
        ),
        encoding="utf-8",
    )
    (analysis_dir / "findings.json").write_text(
        json.dumps(
            {
                "study_id": study_dir.name,
                "runs_analyzed": 1,
                "findings": [
                    {
                        "title": finding_title,
                        "severity": "high",
                        "summary": "Exploratory action led to login before enough evidence.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (analysis_dir / "report.html").write_text("<!doctype html><title>Report</title>", encoding="utf-8")
    (analysis_dir / "log.html").write_text("<!doctype html><title>Log</title>", encoding="utf-8")
    return store, study_dir.name
