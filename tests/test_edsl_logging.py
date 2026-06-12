from __future__ import annotations

from pathlib import Path

from uxtest.log_report import render_log_report
from uxtest.runner import PYDANTIC_ANSWERING_INSTRUCTIONS


def test_pydantic_instructions_avoid_edsl_answer_wrapper():
    assert "Do not wrap it in an answer key" in PYDANTIC_ANSWERING_INSTRUCTIONS
    assert "minified JSON object" in PYDANTIC_ANSWERING_INSTRUCTIONS


def test_log_report_renders_question_attempts():
    html = render_log_report(
        study={"id": "study-1", "title": "Checkout", "personas": ["seniors"]},
        study_dir=Path("/tmp/study-1"),
        runs=[
            {
                "meta": {
                    "run_id": "run-001-seniors-abcd",
                    "outcome": "done",
                    "steps_taken": 1,
                    "persona_instance": {"name": "seniors"},
                },
                "trace": [
                    {
                        "step": 1,
                        "url": "http://example.test",
                        "page_title": "Checkout",
                        "status": "continue",
                        "frustration": 0,
                        "observation": {"interactive_elements_sample": [], "visible_text_preview": "Checkout"},
                        "action": {"type": "click", "ref": "e1"},
                        "result": {"ok": True},
                        "thinking": "Click checkout.",
                        "model_decision": {
                            "driver": "edsl",
                            "edsl": {
                                "question_type": "free_text_fallback",
                                "attempt": 1,
                                "raw_response": '{"action_type":"click"}',
                                "job": {
                                    "job_uuid": "fallback-job",
                                    "progress_url": "https://example.test/fallback",
                                },
                                "pydantic_fallback": {
                                    "last_error": "validation failed",
                                    "attempts": [
                                        {
                                            "attempt": 1,
                                            "ok": False,
                                            "error": "answer was None",
                                            "job": {
                                                "job_uuid": "pydantic-job",
                                                "progress_url": "https://example.test/pydantic",
                                            },
                                        }
                                    ],
                                },
                            },
                        },
                    }
                ],
            }
        ],
    )

    assert "Question Attempts" in html
    assert "pydantic-job" in html
    assert "fallback-job" in html
    assert "QuestionFreeText fallback" in html
