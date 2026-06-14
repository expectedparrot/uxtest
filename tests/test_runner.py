from __future__ import annotations

from pathlib import Path

from uxtest import runner
from uxtest.cli import _parse_viewport
from uxtest.fixtures import _fixture_run_overrides
from uxtest.runner import _redact_text, _redacted_setup_action, _setup_step_value
from uxtest.store import Store, read_yaml


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
