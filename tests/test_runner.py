from __future__ import annotations

from pathlib import Path

from uxtest import runner
from uxtest.cli import _doc_resource, _example_resource, _parse_viewport, _resource_files
from uxtest.fixtures import _fixture_run_overrides
from uxtest.runner import (
    _classify_action_outcome,
    _decision_has_enough_evidence,
    _is_exploratory_study,
    _normalize_stop_decision,
    _redact_text,
    _redacted_setup_action,
    _setup_step_value,
    _should_stop_after_action,
    _should_auto_stop_with_evidence,
)
from uxtest.models import BrowserAction, BrowserDecision
from uxtest.store import Store, read_yaml
from uxtest.stop_quality import classify_run_stop_quality


def test_run_study_preallocates_unique_run_ids(tmp_path, monkeypatch):
    store = Store.init(tmp_path)
    store.create_persona("power-users")
    study_dir = store.create_study(
        "Checkout",
        task="Buy something.",
        url="http://example.test",
        personas=["seniors", "power-users"],
        runs_per_persona=2,
    )

    def fake_run_once(store, study, config, persona_doc, *, run_id=None, **kwargs):
        assert run_id is not None
        run_dir = store.study_dir(study["id"]) / "runs" / run_id
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(runner, "_run_once", fake_run_once)

    run_dirs = runner.run_study(
        store,
        study_dir.name,
        driver="heuristic",
        max_concurrent_runs=3,
    )

    names = sorted(path.name for path in run_dirs)
    assert len(names) == 4
    assert len(set(names)) == 4
    assert names[0].startswith("run-001-")
    assert names[-1].startswith("run-004-")


def test_run_study_continue_on_error_records_complete_with_errors(tmp_path, monkeypatch):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Checkout",
        task="Buy something.",
        url="http://example.test",
        runs_per_persona=2,
    )

    def fake_run_once(store, study, config, persona_doc, *, run_id=None, **kwargs):
        run_dir = store.study_dir(study["id"]) / "runs" / str(run_id)
        run_dir.mkdir(parents=True)
        if str(run_id).startswith("run-001-"):
            raise RuntimeError("remote inference failed")
        return run_dir

    monkeypatch.setattr(runner, "_run_once", fake_run_once)

    run_dirs = runner.run_study(
        store,
        study_dir.name,
        driver="heuristic",
        max_concurrent_runs=2,
        continue_on_error=True,
    )

    study = read_yaml(Path(study_dir) / "study.yaml")
    assert len(run_dirs) == 2
    assert study["status"] == "complete_with_errors"


def test_run_study_applies_transient_run_overrides(tmp_path, monkeypatch):
    store = Store.init(tmp_path)
    study_dir = store.create_study(
        "Checkout",
        task="Buy something.",
        url="http://example.test",
    )

    seen = {}

    def fake_run_once(store, study, config, persona_doc, *, run_id=None, **kwargs):
        seen["overrides"] = study.get("overrides")
        run_dir = store.study_dir(study["id"]) / "runs" / str(run_id)
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(runner, "_run_once", fake_run_once)

    runner.run_study(
        store,
        study_dir.name,
        driver="heuristic",
        run_overrides={"viewport": {"width": 390, "height": 844}, "is_mobile": True},
    )

    assert seen["overrides"]["viewport"] == {"width": 390, "height": 844}
    assert seen["overrides"]["is_mobile"] is True
    study = read_yaml(Path(study_dir) / "study.yaml")
    assert "overrides" not in study


def test_parse_viewport():
    assert _parse_viewport("390x844") == {"width": 390, "height": 844}


def test_fixture_run_overrides_include_auth_setup_fields():
    overrides = _fixture_run_overrides(
        {
            "device": "desktop",
            "setup_steps": [{"type": "type", "name": "email", "env": "TEST_EMAIL"}],
            "auth_state": {"save": ".uxtest/auth/example.json"},
            "redact_patterns": ["secret-[0-9]+"],
        },
        {"name": "default"},
    )

    assert overrides["setup_steps"][0]["env"] == "TEST_EMAIL"
    assert overrides["auth_state"]["save"] == ".uxtest/auth/example.json"
    assert overrides["redact_patterns"] == ["secret-[0-9]+"]
    assert overrides["viewport"] == {"width": 1280, "height": 800}


def test_setup_step_value_reads_env_and_redacts(monkeypatch):
    monkeypatch.setenv("UXTEST_PASSWORD", "super-secret")
    step = {"type": "type", "name": "password", "env": "UXTEST_PASSWORD", "sensitive": True}

    value = _setup_step_value(step)
    action = _redacted_setup_action(step, action_type="type", value=value, sensitive=True, config={})

    assert value == "super-secret"
    assert action["value"] == "[REDACTED]"
    assert action["text"] == "[REDACTED]"
    assert action["env"] == "UXTEST_PASSWORD"


def test_redact_text_applies_patterns():
    assert _redact_text("token=abc123", {"redact_patterns": ["abc[0-9]+"]}) == "token=[REDACTED]"


def test_action_outcome_classifier_distinguishes_url_hash_and_tabs():
    before = {"url": "https://example.com/page", "open_pages": 1}

    nav = _classify_action_outcome("click", before, {"url": "https://example.com/other", "open_pages": 1}, ok=True)
    hash_change = _classify_action_outcome("click", before, {"url": "https://example.com/page#details", "open_pages": 1}, ok=True)
    new_tab = _classify_action_outcome("click", before, {"url": "https://example.com/page", "open_pages": 2}, ok=True)

    assert nav["action_outcome"] == "url_navigation"
    assert nav["url_change_type"] == "path"
    assert hash_change["action_outcome"] == "hash_change"
    assert hash_change["url_change_type"] == "hash"
    assert new_tab["action_outcome"] == "new_tab"
    assert new_tab["open_pages_delta"] == 1


def test_action_outcome_classifier_distinguishes_menu_state_and_noop():
    before = {
        "url": "https://example.com/page",
        "open_pages": 1,
        "text_hash": "a",
        "interactive_hash": "a",
        "expanded_count": 0,
        "menu_like_count": 0,
    }
    menu = dict(before, expanded_count=1, menu_like_count=2)
    state = dict(before, text_hash="b")

    assert _classify_action_outcome("click", before, menu, ok=True)["action_outcome"] == "menu_opened"
    assert _classify_action_outcome("click", before, state, ok=True)["action_outcome"] == "same_page_state_change"
    assert _classify_action_outcome("click", before, before, ok=True)["action_outcome"] == "no_visible_change"


def test_action_outcome_classifier_treats_missing_find_as_observed_result():
    before = {"url": "https://example.com/page", "open_pages": 1}

    result = _classify_action_outcome("find", before, before, ok=True, found=False)

    assert result["action_outcome"] == "find_not_found"
    assert result["state_change"] is False


def test_stop_quality_classifier_detects_enough_evidence_before_max_steps():
    meta = {"outcome": "max_steps", "final_url": "https://example.test/company"}
    trace = [
        {
            "step": 1,
            "url": "https://example.test",
            "thinking": "I understand the site is for AI simulation research. My next step would be Products.",
            "result": {"action_outcome": "url_navigation"},
        },
        {
            "step": 2,
            "url": "https://example.test/company",
            "thinking": "I will keep exploring.",
            "result": {"action_outcome": "menu_opened"},
        },
    ]

    quality = classify_run_stop_quality(meta, trace)

    assert quality["class"] == "enough_evidence_but_continued"
    assert quality["step"] == 1


def test_live_auto_stop_uses_decision_evidence_for_exploratory_tasks():
    study = {
        "mode": "live-site-task-discovery",
        "task": "Figure out what this product is for and what you would click next.",
        "success_criteria": "The visitor can explain the purpose and next action.",
    }
    decision = BrowserDecision(
        action=BrowserAction(type="click", ref="e1", text="Products"),
        thinking="I understand this site is for AI simulation and survey research. My next step would be Products.",
        frustration=1,
        status="continue",
        driver="edsl",
    )

    assert _is_exploratory_study(study)
    assert _decision_has_enough_evidence(decision)
    assert _should_auto_stop_with_evidence(study, {}, decision)


def test_live_auto_stop_does_not_apply_to_transactional_or_heuristic_runs():
    transactional = {
        "mode": "checkout",
        "task": "Complete checkout and place order.",
        "success_criteria": "The order confirmation page is shown.",
    }
    exploratory = {
        "task": "Figure out what this product is for and explain what you would click next.",
        "success_criteria": "The visitor can explain purpose and next action.",
    }
    heuristic_decision = BrowserDecision(
        action=BrowserAction(type="click", ref="e1", text="Products"),
        thinking="I understand this site is for AI simulation and survey research. My next step would be Products.",
        frustration=1,
        status="continue",
        driver="heuristic",
    )

    assert not _is_exploratory_study(transactional)
    assert not _should_auto_stop_with_evidence(transactional, {}, heuristic_decision.model_copy(update={"driver": "edsl"}))
    assert not _should_auto_stop_with_evidence(exploratory, {}, heuristic_decision)
    assert not _should_auto_stop_with_evidence(exploratory, {"auto_stop_on_enough_evidence": False}, heuristic_decision.model_copy(update={"driver": "edsl"}))


def test_done_decision_does_not_execute_a_browser_action():
    study = {
        "mode": "live-site-task-discovery",
        "task": "Figure out what this product is for.",
        "success_criteria": "The visitor can explain the purpose.",
    }
    decision = BrowserDecision(
        action=BrowserAction(type="click", ref="e1", text="Get started"),
        thinking="The site appears to be for stakeholder simulation. Get started is the likely next action.",
        frustration=1,
        status="done",
        driver="edsl",
    )

    normalized = _normalize_stop_decision(study, {}, decision)

    assert normalized.status == "done"
    assert normalized.action.type == "none"
    assert "not executed" in normalized.thinking


def test_auth_next_step_stops_conversion_path_after_action():
    study = {
        "mode": "live-site-conversion",
        "task": "Find the path to schedule a demo, request access, contact sales, or explain why blocked.",
        "success_criteria": "The visitor reaches a demo, contact, sales, signup, dashboard, or equivalent next-step path.",
    }
    decision = BrowserDecision(
        action=BrowserAction(type="click", ref="e1", text="Get started"),
        thinking="Get started is likely the enterprise buying next step.",
        frustration=2,
        status="continue",
        driver="edsl",
    )

    assert _should_stop_after_action(study, decision, {"final_url": "https://example.test/login", "action_outcome": "url_navigation"})


def test_stop_quality_classifier_detects_auth_and_no_visible_advance():
    auth = classify_run_stop_quality(
        {"outcome": "max_steps", "final_url": "https://example.test/login"},
        [{"step": 1, "url": "https://example.test", "result": {"final_url": "https://example.test/login"}}],
    )
    no_advance = classify_run_stop_quality(
        {"outcome": "max_steps", "final_url": "https://example.test"},
        [{"step": 1, "url": "https://example.test", "result": {"action_outcome": "no_visible_change"}}],
    )

    assert auth["class"] == "blocked_by_auth"
    assert no_advance["class"] == "blocked_by_no_visible_advance"


def test_bundled_docs_and_examples_are_discoverable():
    docs = _resource_files("docs", suffixes=(".md",))
    examples = _resource_files("examples")

    assert "README.md" in docs
    assert "study_types/task_discovery/README.md" in docs
    assert "expectedparrot_site/enterprise-demo.yaml" in examples
    assert _doc_resource("task-discovery").is_file()
    assert _doc_resource("conversion-path-testing").is_file()
    assert _example_resource("expectedparrot-enterprise-demo").is_file()
