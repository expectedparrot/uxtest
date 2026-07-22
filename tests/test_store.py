from __future__ import annotations

import json

import pytest

from uxtest.analyze import analyze_study
from uxtest.eval import evaluate_checks, evaluate_study
from uxtest.fixtures import _ensure_personas, _ensure_fixture_study, _fixture_eval_failures, _prune_fixture_runs
from uxtest.retention import prune_study_runs
from uxtest.runner import BrowserAction, _recover_static_text_action, _scripted_decision
from uxtest.store import Store, StoreError, find_store, read_yaml


def test_init_creates_store(tmp_path):
    store = Store.init(tmp_path, project_name="Acme Checkout")

    assert store.path.name == "uxtest_store"
    assert store.config_path.exists()
    assert (store.personas_path / "seniors.yaml").exists()
    assert (store.path / ".gitignore").exists()

    config = read_yaml(store.config_path)
    assert config["project_name"] == "acme-checkout"
    assert config["defaults"]["screenshot_format"] == "png"


def test_find_store_walks_up(tmp_path, monkeypatch):
    store = Store.init(tmp_path)
    child = tmp_path / "app" / "nested"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)

    assert find_store().path == store.path


def test_create_persona_and_study(tmp_path):
    store = Store.init(tmp_path)
    store.create_persona("power-users", description="Confident shoppers")
    study_dir = store.create_study(
        "Checkout Flow",
        task="Buy the breakfast bundle as a guest.",
        url="http://127.0.0.1:8765/?variant=confusing",
        success_criteria="Order confirmation page is visible.",
        personas=["seniors", "power-users"],
        runs_per_persona=2,
    )

    study = read_yaml(study_dir / "study.yaml")
    assert study["id"].endswith("checkout-flow")
    assert study["status"] == "draft"
    assert study["personas"] == ["seniors", "power-users"]
    assert (study_dir / "runs").is_dir()
    assert (study_dir / "analysis").is_dir()


def test_create_study_rejects_missing_persona(tmp_path):
    store = Store.init(tmp_path)

    with pytest.raises(StoreError) as exc:
        store.create_study(
            "Checkout",
            task="Buy something.",
            url="http://example.test",
            personas=["missing"],
        )

    assert exc.value.exit_code == 2


def test_status_counts_runs(tmp_path):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Checkout",
        task="Buy something.",
        url="http://example.test",
    )
    run_dir = study_dir / "runs" / "run-001-seniors-abcd"
    run_dir.mkdir()
    (run_dir / "meta.json").write_text(json.dumps({"outcome": None}), encoding="utf-8")

    status = store.status()

    assert status["studies"] == 1
    assert status["runs"] == 1
    assert status["incomplete_runs"] == 0
    recovered = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert recovered["outcome"] == "interrupted"


def test_study_lock_blocks_second_writer(tmp_path):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Checkout",
        task="Buy something.",
        url="http://example.test",
    )
    study_id = study_dir.name

    with store.study_lock(study_id):
        with pytest.raises(StoreError) as exc:
            with store.study_lock(study_id, break_stale=False):
                pass

    assert exc.value.exit_code == 4


def test_analyze_writes_findings_and_scores(tmp_path):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Checkout",
        task="Buy something.",
        url="http://example.test",
    )
    run_dir = study_dir / "runs" / "run-001-seniors-abcd"
    run_dir.mkdir()
    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "run-001-seniors-abcd",
                "study_id": study_dir.name,
                "outcome": "max_steps",
                "outcome_detail": "Reached max_steps=2",
                "steps_taken": 2,
                "final_url": "http://example.test/cart",
                "persona_instance": {"name": "seniors"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "step": 1,
                "url": "http://example.test/cart",
                "page_title": "Cart",
                "frustration": 7,
                "observation": {"screenshot": "screenshots/step-001.png"},
                "result": {"ok": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    screenshots = run_dir / "screenshots"
    screenshots.mkdir()
    (screenshots / "step-001.png").write_bytes(b"evidence")

    findings_path, scores_path, report_path, log_path = analyze_study(store, study_dir.name)

    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    scores = json.loads(scores_path.read_text(encoding="utf-8"))
    analysis_dir = study_dir / "analysis"
    assert findings["runs_analyzed"] == 1
    assert findings["findings"]
    assert findings["findings"][0]["evidence"][0]["evidence_id"] == "f-001-e01"
    assert scores["task_completion_rate"] == 0
    assert scores["max_frustration"] == 7
    report_text = report_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in report_text
    assert "Run ended with max_steps" in report_text
    assert "f-001-e01" in report_text
    assert "../runs/run-001-seniors-abcd/screenshots/step-001.png" in report_text
    assert "data:image" not in report_text
    assert "<!doctype html>" in log_path.read_text(encoding="utf-8")
    assert "Developer Log" in log_path.read_text(encoding="utf-8")
    assert "Study Plan" in (analysis_dir / "study_plan.md").read_text(encoding="utf-8")
    assert "Stakeholder report" in (analysis_dir / "uxr_report.html").read_text(encoding="utf-8")
    assert "Human Test Protocol" in (analysis_dir / "human_test_protocol.md").read_text(encoding="utf-8")


def test_static_heading_action_recovers_to_find():
    action = BrowserAction(type="none", text="Click on the Research section")
    state = {
        "headings": [{"text": "Research", "level": "h2"}],
        "visible_text": "Bio\nResearch\nWorking papers",
    }

    recovered = _recover_static_text_action(action, state)

    assert recovered is not None
    assert recovered.type == "find"
    assert recovered.text == "Research"


def test_eval_recovers_expected_trace_patterns(tmp_path):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "SaaS Discovery",
        task="Understand product.",
        url="http://example.test",
    )
    run_dir = study_dir / "runs" / "run-001-seniors-abcd"
    run_dir.mkdir()
    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "run-001-seniors-abcd",
                "study_id": study_dir.name,
                "outcome": "max_steps",
                "steps_taken": 3,
                "final_url": "http://example.test/login",
                "persona_instance": {"name": "seniors"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "trace.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "step": 1,
                        "url": "http://example.test/examples",
                        "action": {"type": "click", "ref": "e4", "text": "Open example"},
                        "result": {"ok": True, "navigation": True, "final_url": "http://example.test/login"},
                    }
                ),
                json.dumps(
                    {
                        "step": 2,
                        "url": "http://example.test/login",
                        "action": {"type": "click", "ref": "e8", "text": "View Docs"},
                        "result": {"ok": True, "navigation": False, "final_url": "http://example.test/login"},
                    }
                ),
                json.dumps(
                    {
                        "step": 3,
                        "url": "http://example.test/login",
                        "action": {"type": "click", "ref": "e8", "text": "View Docs"},
                        "result": {"ok": True, "navigation": False, "final_url": "http://example.test/login"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    expected_path = tmp_path / "expected.yaml"
    expected_path.write_text(
        "flaws:\n"
        "  - id: login_detour\n"
        "    expected_in: flawed\n"
        "    absent_in: clear\n"
        "  - id: dead_docs_link\n"
        "    expected_in: flawed\n"
        "    absent_in: clear\n"
        "  - id: generic_cta_confusion\n"
        "    expected_in: flawed\n"
        "    absent_in: clear\n"
        "  - id: repeated_non_navigation\n"
        "    expected_in: flawed\n"
        "    absent_in: clear\n",
        encoding="utf-8",
    )

    json_path, html_path = evaluate_study(store, study_dir.name, expect_path=expected_path, variant="flawed")

    result = json.loads(json_path.read_text(encoding="utf-8"))
    assert result["summary"]["missed_expected"] == []
    assert result["summary"]["recovered_expected_count"] == 4
    assert result["summary"]["passed"] is True
    assert "login_detour" in html_path.read_text(encoding="utf-8")

    clear_json_path, _ = evaluate_study(store, study_dir.name, expect_path=expected_path, variant="clear")
    clear_result = json.loads(clear_json_path.read_text(encoding="utf-8"))
    assert clear_result["summary"]["forbidden_recovered"] == [
        "login_detour",
        "dead_docs_link",
        "generic_cta_confusion",
        "repeated_non_navigation",
    ]
    assert clear_result["summary"]["passed"] is False


def test_eval_first_click_check():
    runs = [
        {
            "meta": {"run_id": "run-001"},
            "trace": [
                {
                    "step": 1,
                    "action": {"type": "click", "text": "Explore products"},
                    "result": {"final_url": "http://example.test/designer"},
                }
            ],
        }
    ]

    results = evaluate_checks(
        runs,
        [
            {
                "id": "first_click_clear_explores_products",
                "type": "first_click",
                "expected_in": "clear",
                "action_contains": "explore products",
                "final_url_contains": "/designer",
            }
        ],
        variant="clear",
    )

    assert results[0]["passed"] is True


def test_scripted_saas_driver_prefers_variant_paths():
    state = {
        "url": "http://127.0.0.1:8776/?variant=clear",
        "visible_text": "Northstar Research Agent AI Interviewer",
        "interactive_elements": [
            {"ref": "e1", "label": "View examples"},
            {"ref": "e2", "label": "Explore products"},
        ],
    }

    clear_decision = _scripted_decision({"url": "http://127.0.0.1:8776/?variant=clear"}, state, [])
    assert clear_decision.driver == "scripted"
    assert clear_decision.action.ref == "e2"

    flawed_decision = _scripted_decision({"url": "http://127.0.0.1:8776/?variant=flawed"}, state, [])
    assert flawed_decision.driver == "scripted"
    assert flawed_decision.action.ref == "e1"


def test_prune_study_runs_keeps_newest(tmp_path):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Retention",
        task="Check cleanup.",
        url="http://example.test",
    )
    for index in range(1, 5):
        run_dir = study_dir / "runs" / f"run-{index:03d}-seniors-abcd"
        run_dir.mkdir()
        (run_dir / "meta.json").write_text(
            json.dumps({"run_id": run_dir.name, "started_at": f"2026-06-12T00:0{index}:00Z"}),
            encoding="utf-8",
        )

    dry_run = prune_study_runs(store, study_dir.name, keep=2, dry_run=True)
    assert [path.name for path in dry_run] == ["run-001-seniors-abcd", "run-002-seniors-abcd"]
    assert (study_dir / "runs" / "run-001-seniors-abcd").exists()

    pruned = prune_study_runs(store, study_dir.name, keep=2)

    assert [path.name for path in pruned] == ["run-001-seniors-abcd", "run-002-seniors-abcd"]
    assert [path.name for path in store.list_runs(study_dir.name)] == ["run-003-seniors-abcd", "run-004-seniors-abcd"]


def test_fixture_study_labels_driver_and_device(tmp_path):
    store = Store.init(tmp_path)
    _ensure_personas(store, ["mobile-first"])
    fixture = {
        "id": "northstar-saas-edsl",
        "mode": "edsl-personas",
        "study_title": "Northstar SaaS {driver} {device} ({variant})",
        "url_template": "http://127.0.0.1:8776/?variant={variant}",
        "task": "Inspect product.",
        "personas": ["mobile-first"],
        "driver": "edsl",
        "device": "iphone",
    }

    study_id = _ensure_fixture_study(store, fixture, {"name": "flawed"})
    study = store.load_study(study_id)

    assert study["title"] == "Northstar SaaS edsl iphone (flawed)"
    assert "driver-edsl" in study["tags"]
    assert "device-iphone" in study["tags"]
    assert "mode-edsl-personas" in study["tags"]


def test_fixture_threshold_eval_policy():
    assert _fixture_eval_failures(
        {},
        {
            "flawed": {"summary": {"passed": True}},
            "clear": {"summary": {"passed": True}},
        },
    ) == []
    assert _fixture_eval_failures(
        {},
        {
            "flawed": {"summary": {"passed": False, "missed_expected": ["dead_docs_link"], "forbidden_recovered": []}},
            "clear": {"summary": {"passed": False, "missed_expected": [], "forbidden_recovered": ["login_detour"]}},
        },
    ) == [
        "flawed: missed=['dead_docs_link'], forbidden=[]",
        "clear: missed=[], forbidden=['login_detour']",
    ]


def test_fixture_prune_keeps_at_least_one_invocation(tmp_path):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Fixture Retention",
        task="Check cleanup.",
        url="http://example.test",
    )
    for index in range(1, 5):
        run_dir = study_dir / "runs" / f"run-{index:03d}-seniors-abcd"
        run_dir.mkdir()
        (run_dir / "meta.json").write_text(
            json.dumps({"run_id": run_dir.name, "started_at": f"2026-06-12T00:0{index}:00Z"}),
            encoding="utf-8",
        )

    pruned = _prune_fixture_runs(
        store,
        {"keep_runs": 1, "personas": ["a", "b", "c"], "runs_per_persona": 1},
        {"name": "flawed"},
        study_dir.name,
    )

    assert [path.name for path in pruned] == ["run-001-seniors-abcd"]
    assert len(store.list_runs(study_dir.name)) == 3
