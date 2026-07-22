from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from uxtest import image_review
from uxtest.image_review import _parse_answer, latest_image_review_target, list_image_captures, resolve_image_capture
from uxtest.store import Store, StoreError


def test_parse_image_review_answer_accepts_json_and_fences():
    expected = {"issues": [{"title": "Clipped text", "description": "Status is cut off.", "severity": "high"}]}
    assert _parse_answer(expected) == expected
    assert _parse_answer('```json\n{"issues": []}\n```') == {"issues": []}


def test_parse_image_review_answer_rejects_unstructured_prose():
    with pytest.raises(StoreError, match="not valid JSON"):
        _parse_answer("The page looks broken.")


def test_latest_image_review_target_selects_newest_screenshot(tmp_path):
    store = Store.init(tmp_path)
    first = store.create_study("First", task="Review.", url="https://first.test")
    second = store.create_study("Second", task="Review.", url="https://second.test")
    first_shot = first / "runs" / "run-001" / "screenshots" / "step-001.png"
    second_shot = second / "runs" / "run-002" / "screenshots" / "step-001.png"
    first_shot.parent.mkdir(parents=True)
    second_shot.parent.mkdir(parents=True)
    first_shot.write_bytes(b"first")
    second_shot.write_bytes(b"second")
    os.utime(second_shot, ns=(1, 1))
    os.utime(first_shot, ns=(2, 2))

    assert latest_image_review_target(store) == (first.name, "run-001")
    captures = list_image_captures(store)
    assert len(captures[0]["capture_id"]) == 64
    assert resolve_image_capture(store, captures[0]["capture_id"][:8]) == (first.name, "run-001")


def test_capture_reference_rejects_short_or_missing_hash(tmp_path):
    store = Store.init(tmp_path)
    with pytest.raises(StoreError, match="at least 7"):
        resolve_image_capture(store, "abc")
    with pytest.raises(StoreError, match="No image capture matches"):
        resolve_image_capture(store, "abcdef0")


def test_run_image_review_orchestrates_ep_without_exposing_path_work(monkeypatch, tmp_path):
    store = Store.init(tmp_path)
    capture_id = "a" * 64
    monkeypatch.setattr(image_review, "resolve_image_capture", lambda store, ref: ("study-one", "run-one"))
    monkeypatch.setattr(
        image_review,
        "prepare_image_review",
        lambda store, study_id, run_id, model: {
            "jobs": "/store/jobs.ep",
            "results": "/store/results.ep",
            "runs": [{"capture_id": capture_id}],
        },
    )
    monkeypatch.setattr(image_review.shutil, "which", lambda command: "/bin/ep")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"status":"ok","data":{}}', stderr="")

    monkeypatch.setattr(image_review.subprocess, "run", fake_run)
    monkeypatch.setattr(
        image_review,
        "ingest_image_review",
        lambda store, study_id, results: {"findings": [{"title": "Clipped text"}]},
    )

    result = image_review.run_image_review(store, "aaaaaaa")

    assert calls == [["/bin/ep", "run", "/store/jobs.ep", "--output", "/store/results.ep"]]
    assert result["capture_id"] == capture_id
    assert result["findings"] == [{"title": "Clipped text"}]
