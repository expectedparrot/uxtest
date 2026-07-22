from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_json


QUESTION_NAME = "visual_findings"
QUESTION_TEXT = """Inspect this browser screenshot as a visual UX reviewer.

Screenshot: {{ scenario.screenshot }}
Page URL: {{ scenario.url }}
Viewport: {{ scenario.viewport }}
Task: {{ scenario.task }}

Look at the pixels in the screenshot. Identify visible interface defects such as clipped or
truncated text, overflow, overlap, elements outside their containers, unreadable contrast,
missing content, or broken responsive layout. Do not assume that text present in the DOM is
visible in the screenshot.

Return only JSON with this shape:
{"issues":[{"title":"short name","description":"what is visibly wrong and where","severity":"low|medium|high"}]}
Return {"issues":[]} only when the screenshot has no visible interface defect.
"""


def latest_image_review_target(store: Store) -> tuple[str, str]:
    captures = list_image_captures(store)
    if not captures:
        raise StoreError("No captured runs with PNG screenshots were found.", exit_code=2)
    capture = captures[0]
    return str(capture["study_id"]), str(capture["run_id"])


def list_image_captures(store: Store) -> list[dict[str, Any]]:
    captures: list[dict[str, Any]] = []
    for study in store.list_studies():
        study_id = str(study.get("id") or "")
        if not study_id:
            continue
        for run_dir in store.list_runs(study_id):
            screenshots = sorted((run_dir / "screenshots").glob("*.png"))
            if screenshots:
                screenshot = screenshots[-1]
                captures.append(
                    {
                        "capture_id": _capture_id(study_id, run_dir.name, screenshot),
                        "study_id": study_id,
                        "run_id": run_dir.name,
                        "screenshot": str(screenshot),
                        "captured_at_ns": screenshot.stat().st_mtime_ns,
                    }
                )
    return sorted(captures, key=lambda item: int(item["captured_at_ns"]), reverse=True)


def resolve_image_capture(store: Store, reference: str) -> tuple[str, str]:
    if len(reference) < 7:
        raise StoreError("Capture references must contain at least 7 hash characters.", exit_code=2)
    matches = [item for item in list_image_captures(store) if str(item["capture_id"]).startswith(reference.lower())]
    if not matches:
        raise StoreError(f"No image capture matches {reference!r}.", exit_code=2)
    if len(matches) > 1:
        raise StoreError(f"Image capture reference {reference!r} is ambiguous; provide more hash characters.", exit_code=2)
    return str(matches[0]["study_id"]), str(matches[0]["run_id"])


def _capture_id(study_id: str, run_id: str, screenshot: Path) -> str:
    screenshot_sha = hashlib.sha256(screenshot.read_bytes()).hexdigest()
    identity = json.dumps(
        {"run_id": run_id, "screenshot": screenshot.name, "screenshot_sha256": screenshot_sha, "study_id": study_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def prepare_image_review(
    store: Store,
    study_id: str,
    *,
    run_id: str | None = None,
    model: str = "gpt-4o",
) -> dict[str, Any]:
    study = store.load_study(study_id)
    runs = _selected_runs(store, study_id, run_id)
    scenarios: list[Any] = []
    manifest_runs: list[dict[str, str]] = []
    try:
        from edsl import Agent, FileStore, Model, QuestionFreeText, Scenario, ScenarioList
    except Exception as exc:
        raise StoreError(f"Unable to import EDSL image-review dependencies: {exc}", exit_code=1) from exc

    for run_dir in runs:
        screenshot = _last_screenshot(run_dir)
        meta = _read_json(run_dir / "meta.json")
        scenarios.append(
            Scenario(
                {
                    "screenshot": FileStore(str(screenshot)),
                    "study_id": study_id,
                    "run_id": run_dir.name,
                    "screenshot_path": str(screenshot),
                    "url": str(meta.get("final_url") or study.get("url") or ""),
                    "viewport": (meta.get("resolved_config") or {}).get("viewport", {}),
                    "task": str(study.get("task") or ""),
                }
            )
        )
        manifest_runs.append(
            {
                "capture_id": _capture_id(study_id, run_dir.name, screenshot),
                "run_id": run_dir.name,
                "screenshot": str(screenshot),
            }
        )

    question = QuestionFreeText(question_name=QUESTION_NAME, question_text=QUESTION_TEXT)
    reviewer = Agent(name="visual-ux-reviewer", traits={"role": "visual UX reviewer"})
    jobs = question.by(ScenarioList(scenarios)).by(reviewer).by(Model(model))
    output_dir = store.study_dir(study_id) / "analysis" / "image_review"
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs_path = output_dir / "jobs.ep"
    git = getattr(jobs, "git", None)
    if git is None:
        raise StoreError(
            "Installed EDSL does not support .ep Jobs packages. Install the EDSL version that provides `Jobs.git.save()` and the `ep` CLI.",
            exit_code=1,
        )
    git.save(jobs_path, message=f"Prepare uxtest image review for {study_id}")
    results_path = output_dir / "results.ep"
    manifest = {
        "schema_version": 1,
        "study_id": study_id,
        "model": model,
        "jobs": str(jobs_path),
        "results": str(results_path),
        "runs": manifest_runs,
        "next_command": f"ep run {jobs_path} --output {results_path}",
    }
    atomic_write_json(output_dir / "manifest.json", manifest)
    return manifest


def ingest_image_review(store: Store, study_id: str, results_path: Path | None = None) -> dict[str, Any]:
    output_dir = store.study_dir(study_id) / "analysis" / "image_review"
    source = (results_path or output_dir / "results.ep").expanduser().resolve()
    if not source.exists():
        raise StoreError(f"EDSL results package does not exist: {source}", exit_code=2)
    try:
        from edsl import Results

        results = Results.git.load(source)
    except Exception as exc:
        raise StoreError(f"Unable to load EDSL Results package {source}: {exc}", exit_code=1) from exc
    data = results.to_dict()
    findings: list[dict[str, Any]] = []
    for row in data.get("data", []):
        answer = (row.get("answer") or {}).get(QUESTION_NAME)
        parsed = _parse_answer(answer)
        scenario = row.get("scenario") or {}
        for issue in parsed.get("issues", []):
            if not isinstance(issue, dict):
                continue
            findings.append(
                {
                    "title": str(issue.get("title") or "Visual issue"),
                    "description": str(issue.get("description") or ""),
                    "severity": str(issue.get("severity") or "medium"),
                    "run_id": scenario.get("run_id"),
                    "screenshot": scenario.get("screenshot_path"),
                }
            )
    payload = {"schema_version": 1, "study_id": study_id, "findings": findings, "results": str(source)}
    atomic_write_json(output_dir / "findings.json", payload)
    return payload


def run_image_review(store: Store, capture_reference: str, *, model: str = "gpt-4o") -> dict[str, Any]:
    study_id, run_id = resolve_image_capture(store, capture_reference)
    prepared = prepare_image_review(store, study_id, run_id=run_id, model=model)
    ep = shutil.which("ep")
    if not ep:
        raise StoreError("The EDSL `ep` command is not available on PATH.", exit_code=1)
    command = [ep, "run", str(prepared["jobs"]), "--output", str(prepared["results"])]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise StoreError(f"EDSL image-review job failed: {detail}", exit_code=1)
    try:
        ep_response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise StoreError("EDSL `ep run` did not return its expected JSON envelope.", exit_code=1) from exc
    if ep_response.get("status") != "ok":
        raise StoreError(f"EDSL image-review job failed: {ep_response.get('error') or ep_response}", exit_code=1)
    ingested = ingest_image_review(store, study_id, Path(str(prepared["results"])))
    capture_id = str(prepared["runs"][0]["capture_id"])
    return {
        "capture_id": capture_id,
        "study_id": study_id,
        "run_id": run_id,
        "jobs": prepared["jobs"],
        "results": prepared["results"],
        "findings": ingested["findings"],
        "ep": ep_response,
    }


def _selected_runs(store: Store, study_id: str, run_id: str | None) -> list[Path]:
    runs = store.list_runs(study_id)
    if run_id:
        runs = [path for path in runs if path.name == run_id]
        if not runs:
            raise StoreError(f"Run {run_id!r} does not exist in study {study_id!r}.", exit_code=2)
    if not runs:
        raise StoreError(f"Study {study_id!r} has no runs to review.", exit_code=2)
    return runs


def _last_screenshot(run_dir: Path) -> Path:
    screenshots = sorted((run_dir / "screenshots").glob("*.png"))
    if not screenshots:
        raise StoreError(f"Run {run_dir.name!r} has no PNG screenshots.", exit_code=2)
    return screenshots[-1]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _parse_answer(answer: Any) -> dict[str, Any]:
    if isinstance(answer, dict):
        return answer
    text = str(answer or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StoreError(f"EDSL image-review answer is not valid JSON: {text[:200]}", exit_code=1) from exc
    if not isinstance(value, dict) or not isinstance(value.get("issues"), list):
        raise StoreError("EDSL image-review answer must be an object containing an issues list.", exit_code=1)
    return value
