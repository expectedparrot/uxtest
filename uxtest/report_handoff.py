from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import Store
from .trace import study_bundle


def report_guidance(store: Store, study_id: str) -> dict[str, Any]:
    bundle = study_bundle(store, study_id)
    study_dir = store.study_dir(study_id)
    analysis_dir = study_dir / "analysis"
    runs = bundle["runs"]

    def artifact(path: Path, purpose: str) -> dict[str, Any]:
        return {
            "path": str(path.relative_to(store.root)),
            "available": path.exists(),
            "purpose": purpose,
        }

    evidence = [
        artifact(study_dir / "study.yaml", "Study question, task, target, personas, and success criteria."),
        artifact(analysis_dir / "findings.json", "Normalized findings and evidence references."),
        artifact(analysis_dir / "scores.json", "Run counts, outcomes, frustration, and stop-quality summaries."),
        artifact(analysis_dir / "report.html", "Deterministic evidence dashboard; not the final narrative report."),
        artifact(analysis_dir / "log.html", "Step-level technical audit with browser and model details."),
        artifact(analysis_dir / "journey" / "journey.svg", "Screenshot-backed navigation tree."),
        artifact(analysis_dir / "image_review" / "findings.json", "EDSL visual-review findings, when image review was run."),
    ]
    for run in runs:
        run_dir = run["run_dir"]
        evidence.extend(
            [
                artifact(run_dir / "meta.json", f"Run metadata for {run_dir.name}."),
                artifact(run_dir / "trace.jsonl", f"Action, reasoning, outcome, and screenshot references for {run_dir.name}."),
            ]
        )
    return {
        "purpose": "Structured evidence handoff for the coding agent that writes the final report.",
        "uxtest_role": (
            "uxtest records browser evidence, model decisions, screenshots, deterministic summaries, and technical views. "
            "It does not write the final stakeholder narrative."
        ),
        "study_id": study_id,
        "study_title": bundle["study"].get("title") or study_id,
        "target_file": "writeup/report.md",
        "available_evidence": evidence,
        "recommended_sections": [
            "Summary",
            "Decision context",
            "Study question and scope",
            "Method in brief",
            "What happened",
            "Findings",
            "Recommendations",
            "Limitations and validation plan",
            "Appendix: evidence index",
        ],
        "writing_rules": [
            "Write for a reader with no prior exposure to the study or uxtest.",
            "State the decision this work informs before describing commands or artifacts.",
            "Distinguish captured page content from uxtest annotations and model reasoning.",
            "Support every material finding with a run, step, screenshot, trace field, or image-review finding.",
            "Describe browser-agent runs and synthetic personas precisely; do not relabel them as human participants.",
            "Treat no_visible_change, max_steps, and model frustration as evidence requiring interpretation, not automatic product failure.",
            "Separate observed behavior, interpretation, and recommendation.",
            "Report missing captures, incomplete inference, runner defects, and other evidence limitations.",
            "Use study and run IDs as audit references, not as the main narrative.",
        ],
        "next_command": f"uxtest report template {study_id}",
    }


def report_template(store: Store, study_id: str) -> dict[str, Any]:
    bundle = study_bundle(store, study_id)
    study = bundle["study"]
    scores = bundle["scores"]
    run_ids = [run["run_dir"].name for run in bundle["runs"]]
    title = study.get("title") or study_id
    template = f'''---
title: "{title}"
date: [YYYY-MM-DD]
---

# Summary

[State the most important finding, the decision it informs, and the recommended next action.]

## Decision context

[Explain why this study was run and who needs to act on it.]

## Study question and scope

- Target: {study.get('url') or '[target]'}
- Task: {study.get('task') or '[task]'}
- Success criteria: {study.get('success_criteria') or '[success criteria]'}
- Runs available: {scores.get('runs_analyzed', len(run_ids))}
- Audit references: {', '.join(run_ids) or '[no completed runs]'}

## Method in brief

[Explain the synthetic personas, Playwright capture, EDSL inference or visual evaluation used, devices, and study date.]

## What happened

[Describe the important paths through the interface. Link the journey SVG and representative screenshots.]

## Findings

### 1. [Finding stated as a concrete claim]

- Observed evidence: [run, step, screenshot, trace field, or image-review finding]
- Interpretation: [what the evidence means]
- Product implication: [why it matters]
- Confidence and caveat: [scope and uncertainty]

## Recommendations

1. [Action tied directly to a finding.]

## Limitations and validation plan

[State synthetic-study limits, instrumentation gaps, and the next validation step.]

## Appendix: evidence index

[List the exact study, run, trace, screenshot, journey, and analysis paths used.]
'''
    return {
        "purpose": "Study-specific scaffold for the coding agent; no report file was written.",
        "study_id": study_id,
        "target_file": "writeup/report.md",
        "template": template,
        "next_step": "Draft the report in the calling agent's writeup directory using only the listed evidence.",
    }
