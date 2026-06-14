from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .analyze import analyze_study
from .animate import animate_study
from .comparison import write_comparison_report
from .eval import evaluate_study
from .retention import prune_study_runs
from .runner import run_study
from .store import Store, StoreError, read_yaml


DEVICE_PROFILES: dict[str, dict[str, Any]] = {
    "desktop": {
        "viewport": {"width": 1280, "height": 800},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
    },
    "iphone": {
        "viewport": {"width": 390, "height": 844},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 3,
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    },
    "pixel": {
        "viewport": {"width": 412, "height": 915},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 2.625,
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    },
}


BUILTIN_PERSONAS: dict[str, dict[str, Any]] = {
    "seniors": {
        "schema_version": 1,
        "name": "seniors",
        "description": "Desktop shopper with moderate web familiarity",
        "attributes": {
            "age_range": [35, 55],
            "tech_literacy": "medium",
            "reading_style": "skims",
            "patience": "medium",
            "device_familiarity": "desktop",
        },
        "accessibility": {},
        "goals_bias": "Prefers clear labels, predictable checkout steps, and helpful error messages.",
        "frustration": {"threshold": 7, "per_step_decay": 1},
    },
    "low-confidence": {
        "schema_version": 1,
        "name": "low-confidence",
        "description": "Cautious shopper who hesitates when labels or errors are unclear",
        "attributes": {
            "age_range": [45, 70],
            "tech_literacy": "low",
            "reading_style": "reads carefully",
            "patience": "low",
            "device_familiarity": "desktop",
        },
        "accessibility": {"prefers_large_targets": True},
        "goals_bias": "Needs plain labels, visible reassurance, and clear recovery from mistakes.",
        "frustration": {"threshold": 5, "per_step_decay": 1},
    },
    "mobile-first": {
        "schema_version": 1,
        "name": "mobile-first",
        "description": "Phone-first user who expects compact, direct flows",
        "attributes": {
            "age_range": [20, 40],
            "tech_literacy": "high",
            "reading_style": "scans headings",
            "patience": "medium",
            "device_familiarity": "mobile",
        },
        "accessibility": {},
        "goals_bias": "Looks for visible primary actions, direct navigation, and minimal friction.",
        "frustration": {"threshold": 6, "per_step_decay": 1},
    },
    "price-sensitive": {
        "schema_version": 1,
        "name": "price-sensitive",
        "description": "Skimming shopper who checks totals and fees before committing",
        "attributes": {
            "age_range": [25, 60],
            "tech_literacy": "medium",
            "reading_style": "skims prices",
            "patience": "medium",
            "device_familiarity": "desktop",
        },
        "accessibility": {},
        "goals_bias": "Focuses on total cost, fees, trust signals, and whether the final order action is safe.",
        "frustration": {"threshold": 6, "per_step_decay": 1},
    },
}


def run_fixture(
    store: Store,
    fixture_path: Path,
    *,
    open_report: bool = False,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixture_path = fixture_path.expanduser().resolve()
    fixture = _merge_dict(read_yaml(fixture_path), overrides or {})
    base_dir = fixture_path.parent
    server_process = _ensure_fixture_server(fixture, base_dir=base_dir)
    try:
        personas = [str(item) for item in fixture.get("personas") or ["seniors"]]
        _ensure_personas(store, personas)
        study_ids: list[str] = []
        eval_results: dict[str, dict[str, Any]] = {}
        artifacts: list[Path] = []
        pruned_runs: list[Path] = []
        variants = fixture.get("variants") or []
        if not isinstance(variants, list) or not variants:
            raise StoreError(f"Fixture must define a non-empty variants list: {fixture_path}", exit_code=2)

        for variant_spec in variants:
            if not isinstance(variant_spec, dict) or not variant_spec.get("name"):
                raise StoreError(f"Each fixture variant must be a mapping with name: {fixture_path}", exit_code=2)
            variant = str(variant_spec["name"])
            study_id = _ensure_fixture_study(store, fixture, variant_spec)
            study_ids.append(study_id)
            run_dirs = run_study(
                store,
                study_id,
                max_steps=int(variant_spec.get("max_steps") or fixture.get("max_steps") or 12),
                driver=str(variant_spec.get("driver") or fixture.get("driver") or "edsl"),  # type: ignore[arg-type]
                max_concurrent_runs=int(variant_spec.get("max_concurrent_runs") or fixture.get("max_concurrent_runs") or 1),
                continue_on_error=True,
                run_overrides=_fixture_run_overrides(fixture, variant_spec),
            )
            pruned = _prune_fixture_runs(store, fixture, variant_spec, study_id)
            findings_path, scores_path, report_path, log_path = analyze_study(
                store,
                study_id,
                include_interrupted=True,
                driver=str(variant_spec.get("analysis_driver") or fixture.get("analysis_driver") or "local"),
            )
            animation_path = animate_study(
                store,
                study_id,
                delay_cs=int(variant_spec.get("animation_delay") or fixture.get("animation_delay") or 250),
                max_width=int(variant_spec.get("animation_max_width") or fixture.get("animation_max_width") or 520),
            )
            expected_path = _fixture_expected_path(fixture, base_dir)
            eval_json_path, eval_html_path = evaluate_study(
                store,
                study_id,
                expect_path=expected_path,
                variant=variant,
                policy=str(fixture.get("eval_policy") or "strict"),
                minimum_recovered_expected=int(fixture.get("minimum_recovered_expected") or 1),
            )
            eval_results[variant] = json.loads(eval_json_path.read_text(encoding="utf-8"))
            artifacts.extend([*run_dirs, findings_path, scores_path, report_path, log_path, animation_path, eval_json_path, eval_html_path])
            pruned_runs.extend(pruned)

        comparison_path = write_comparison_report(
            store,
            title=str(fixture.get("comparison_title") or fixture.get("name") or "uxtest fixture"),
            study_ids=study_ids,
            output_name=str(fixture.get("comparison_output") or f"{fixture_path.stem}.html"),
        )
        artifacts.append(comparison_path)
        failures = _fixture_eval_failures(fixture, eval_results)
        if open_report:
            subprocess.run(["open", str(comparison_path)], check=False)
        if failures:
            raise StoreError(f"Fixture regression failed for {fixture_path.name}: " + "; ".join(failures), exit_code=1)
        return {
            "fixture": str(fixture_path),
            "study_ids": study_ids,
            "eval_results": eval_results,
            "comparison": comparison_path,
            "artifacts": artifacts,
            "pruned_runs": pruned_runs,
        }
    finally:
        if server_process is not None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()


def _ensure_fixture_study(store: Store, fixture: dict[str, Any], variant_spec: dict[str, Any]) -> str:
    variant = str(variant_spec["name"])
    context = _fixture_context(fixture, variant_spec)
    title_template = str(variant_spec.get("title") or fixture.get("study_title") or f"{fixture.get('name', 'Fixture')} ({variant})")
    title = title_template.format(**context)
    url = _format_fixture_url(str(variant_spec.get("url") or fixture.get("url_template") or ""), variant=variant, fixture=fixture)
    if not url:
        raise StoreError("Fixture must define url_template or per-variant url.", exit_code=2)
    task = str(variant_spec.get("task") or fixture.get("task") or "")
    success_criteria = str(variant_spec.get("success_criteria") or fixture.get("success_criteria") or "")
    personas = [str(item) for item in variant_spec.get("personas") or fixture.get("personas") or ["seniors"]]
    runs_per_persona = int(variant_spec.get("runs_per_persona") or fixture.get("runs_per_persona") or 1)
    tags = {
        "uxtest-fixture",
        f"fixture-{fixture.get('id') or fixture.get('name') or 'unnamed'}",
        f"variant-{variant}",
        f"driver-{context['driver']}",
        f"device-{context['device']}",
    }
    if context.get("mode"):
        tags.add(f"mode-{context['mode']}")
    for study in store.list_studies():
        if study.get("title") == title and "uxtest-fixture" in (study.get("tags") or []):
            study["url"] = url
            study["task"] = task
            study["success_criteria"] = success_criteria
            study["personas"] = personas
            study["runs_per_persona"] = runs_per_persona
            study["tags"] = sorted(tags.union(set(study.get("tags") or [])))
            store.write_study(study)
            return str(study["id"])
    study_dir = store.create_study(
        title,
        task=task,
        url=url,
        success_criteria=success_criteria,
        personas=personas,
        runs_per_persona=runs_per_persona,
        tags=sorted(tags),
    )
    return study_dir.name


def _fixture_run_overrides(fixture: dict[str, Any], variant_spec: dict[str, Any]) -> dict[str, Any] | None:
    overrides: dict[str, Any] = {}
    device = variant_spec.get("device") or fixture.get("device")
    if device:
        if str(device) not in DEVICE_PROFILES:
            raise StoreError(f"Unknown fixture device {device!r}.", exit_code=2)
        overrides.update(DEVICE_PROFILES[str(device)])
    for source in (fixture.get("overrides"), variant_spec.get("overrides")):
        if isinstance(source, dict):
            overrides.update(source)
    for key in ("setup_steps", "auth_state", "env_file", "redact_patterns", "secrets"):
        if key in fixture:
            overrides[key] = fixture[key]
        if key in variant_spec:
            overrides[key] = variant_spec[key]
    return overrides or None


def _fixture_context(fixture: dict[str, Any], variant_spec: dict[str, Any]) -> dict[str, str]:
    return {
        "variant": str(variant_spec.get("name") or ""),
        "driver": str(variant_spec.get("driver") or fixture.get("driver") or "edsl"),
        "device": str(variant_spec.get("device") or fixture.get("device") or "default"),
        "mode": str(variant_spec.get("mode") or fixture.get("mode") or ""),
    }


def _prune_fixture_runs(store: Store, fixture: dict[str, Any], variant_spec: dict[str, Any], study_id: str) -> list[Path]:
    keep = variant_spec.get("keep_runs") or fixture.get("keep_runs")
    if keep is None:
        return []
    personas = variant_spec.get("personas") or fixture.get("personas") or ["seniors"]
    runs_per_persona = int(variant_spec.get("runs_per_persona") or fixture.get("runs_per_persona") or 1)
    minimum_keep = len(personas) * runs_per_persona if isinstance(personas, list) else runs_per_persona
    return prune_study_runs(store, study_id, keep=max(int(keep), minimum_keep))


def _fixture_eval_failures(fixture: dict[str, Any], eval_results: dict[str, dict[str, Any]]) -> list[str]:
    return [
        f"{variant}: missed={result['summary'].get('missed_expected')}, forbidden={result['summary'].get('forbidden_recovered')}"
        for variant, result in eval_results.items()
        if not result.get("summary", {}).get("passed")
    ]


def _fixture_expected_path(fixture: dict[str, Any], base_dir: Path) -> Path | None:
    expected = fixture.get("expected_flaws")
    if not expected:
        return None
    path = Path(str(expected)).expanduser()
    return path if path.is_absolute() else base_dir / path


def _format_fixture_url(template: str, *, variant: str, fixture: dict[str, Any]) -> str:
    server = fixture.get("server") if isinstance(fixture.get("server"), dict) else {}
    return template.format(
        variant=variant,
        host=server.get("host", "127.0.0.1"),
        port=server.get("port", ""),
    )


def _ensure_fixture_server(fixture: dict[str, Any], *, base_dir: Path) -> subprocess.Popen | None:
    server = fixture.get("server")
    if not isinstance(server, dict):
        return None
    host = str(server.get("host") or "127.0.0.1")
    port = int(server.get("port") or 0)
    if port and _port_is_open(host, port):
        return None
    command = server.get("command")
    if not isinstance(command, list) or not command:
        return None
    argv = [_format_server_arg(str(item), server=server, base_dir=base_dir) for item in command]
    if argv[0] == "python":
        argv[0] = sys.executable
    process = subprocess.Popen(argv, cwd=str(base_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not port:
        return process
    deadline = time.time() + float(server.get("startup_timeout") or 5)
    while time.time() < deadline:
        if _port_is_open(host, port):
            return process
        time.sleep(0.1)
    process.terminate()
    raise StoreError(f"Fixture server did not start on {host}:{port}.", exit_code=1)


def _format_server_arg(value: str, *, server: dict[str, Any], base_dir: Path) -> str:
    formatted = value.format(host=server.get("host", "127.0.0.1"), port=server.get("port", ""))
    if formatted.startswith("./"):
        return str(base_dir / formatted)
    return formatted


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _ensure_personas(store: Store, personas: list[str]) -> None:
    for persona in personas:
        if (store.personas_path / f"{persona}.yaml").exists():
            continue
        if persona not in BUILTIN_PERSONAS:
            raise StoreError(f"Persona {persona!r} does not exist.", exit_code=2)
        store.write_persona(BUILTIN_PERSONAS[persona])


def _merge_dict(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
            continue
        merged[key] = value
    return merged
