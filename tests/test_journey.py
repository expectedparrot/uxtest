from __future__ import annotations

import json

from uxtest.journey import generate_journey_tree
from uxtest.store import Store


def test_journey_tree_merges_shared_prefix_and_branches(tmp_path):
    store = Store.init(tmp_path)
    study_dir = store.create_study("Navigation", task="Explore.", url="https://example.test")
    for run_id, second_action in (("run-a", "Docs"), ("run-b", "Pricing")):
        run_dir = study_dir / "runs" / run_id
        screenshots = run_dir / "screenshots"
        screenshots.mkdir(parents=True)
        (screenshots / "step-001.png").write_bytes(b"one")
        (screenshots / "step-002.png").write_bytes(b"two")
        events = [
            _event(1, "View examples", "screenshots/step-001.png", "/", "/examples"),
            _event(2, second_action, "screenshots/step-002.png", "/examples", f"/{second_action.lower()}"),
        ]
        (run_dir / "trace.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

    output = generate_journey_tree(store, study_dir.name)
    text = output.read_text(encoding="utf-8")

    assert text.count("View examples") == 1
    assert "Docs" in text and "Pricing" in text
    assert "run-a, run-b" in text
    assert text.startswith("<svg")
    assert "data:image/png;base64," in text
    assert (output.parent / "index.html").is_file()


def _event(step, text, screenshot, url, final_url):
    return {
        "event_type": "step",
        "step": step,
        "url": f"https://example.test{url}",
        "action": {"type": "click", "text": text, "ref": f"e{step}"},
        "observation": {"screenshot": screenshot},
        "result": {"action_outcome": "url_navigation", "final_url": f"https://example.test{final_url}"},
    }
