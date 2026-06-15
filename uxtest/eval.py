from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import yaml

from .store import Store, StoreError, atomic_write_json, atomic_write_text, read_json, utc_now


RULES: dict[str, dict[str, str]] = {
    "login_detour": {
        "title": "Product-learning action led to login",
        "severity": "high",
        "category": "navigation",
    },
    "dead_docs_link": {
        "title": "Docs or pricing action acknowledged without navigation",
        "severity": "high",
        "category": "navigation",
    },
    "generic_cta_confusion": {
        "title": "Generic CTA caused a detour",
        "severity": "medium",
        "category": "content",
    },
    "repeated_non_navigation": {
        "title": "Repeated action did not advance page state",
        "severity": "medium",
        "category": "navigation",
    },
}


def evaluate_study(
    store: Store,
    study_id: str,
    *,
    expect_path: Path | None = None,
    variant: str | None = None,
    policy: str = "strict",
    minimum_recovered_expected: int = 1,
) -> tuple[Path, Path]:
    study_dir = store.study_dir(study_id)
    if not study_dir.exists():
        raise StoreError(f"Study {study_id!r} not found.", exit_code=2)
    expected = _load_expected(expect_path) if expect_path else []
    checks = _load_checks(expect_path) if expect_path else []
    runs = _load_runs(store, study_id)
    recovered = detect_patterns(runs)
    check_results = evaluate_checks(runs, checks, variant=variant)
    expected_items = _expected_for_variant(expected, variant)
    forbidden_items = _forbidden_for_variant(expected, variant)
    expected_ids = [str(item.get("id")) for item in expected_items if item.get("id")]
    forbidden_ids = [str(item.get("id")) for item in forbidden_items if item.get("id")]
    recovered_ids = {item["id"] for item in recovered}
    missed_expected = [item for item in expected_ids if item not in recovered_ids]
    forbidden_recovered = [item for item in forbidden_ids if item in recovered_ids]
    summary = {
        "expected_count": len(expected_ids),
        "recovered_expected_count": len([item for item in expected_ids if item in recovered_ids]),
        "missed_expected": missed_expected,
        "forbidden_count": len(forbidden_ids),
        "forbidden_recovered": forbidden_recovered,
        "unexpected_recovered": sorted(recovered_ids - set(expected_ids)),
        "checks": check_results,
        "failed_checks": [item["id"] for item in check_results if not item.get("passed")],
        "policy": policy,
        "minimum_recovered_expected": minimum_recovered_expected,
    }
    summary["passed"] = _summary_passed(summary, policy=policy, minimum_recovered_expected=minimum_recovered_expected)
    result = {
        "schema_version": 1,
        "study_id": study_id,
        "variant": variant,
        "generated_at": utc_now(),
        "expected": expected,
        "checks": checks,
        "expected_for_variant": expected_items,
        "forbidden_for_variant": forbidden_items,
        "recovered": recovered,
        "summary": summary,
    }
    output_dir = study_dir / "analysis"
    output_dir.mkdir(exist_ok=True)
    json_path = output_dir / "eval.json"
    html_path = output_dir / "eval.html"
    atomic_write_json(json_path, result)
    atomic_write_text(html_path, render_eval(result))
    return json_path, html_path


def detect_patterns(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for run in runs:
        meta = run.get("meta") or {}
        trace = run.get("trace") or []
        for index, event in enumerate(trace):
            next_event = trace[index + 1] if index + 1 < len(trace) else None
            for rule_id in _event_rule_ids(event, next_event):
                _add_rule_evidence(found, rule_id, meta, event)
        for rule_id, event in _repeated_non_navigation(trace):
            _add_rule_evidence(found, rule_id, meta, event)
    return sorted(found.values(), key=lambda item: item["id"])


def evaluate_checks(runs: list[dict[str, Any]], checks: list[dict[str, Any]], *, variant: str | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for check in checks:
        if variant and not _check_applies(check, variant):
            continue
        check_type = str(check.get("type") or "")
        if check_type == "first_click":
            results.append(_evaluate_first_click(runs, check))
        else:
            results.append({"id": str(check.get("id") or check_type or "check"), "type": check_type, "passed": False, "reason": f"Unknown check type {check_type!r}."})
    return results


def render_eval(result: dict[str, Any]) -> str:
    summary = result.get("summary") or {}
    rows = "\n".join(_rule_row(item) for item in result.get("recovered") or [])
    missed = ", ".join(summary.get("missed_expected") or []) or "none"
    forbidden = ", ".join(summary.get("forbidden_recovered") or []) or "none"
    unexpected = ", ".join(summary.get("unexpected_recovered") or []) or "none"
    failed_checks = ", ".join(summary.get("failed_checks") or []) or "none"
    passed = "pass" if summary.get("passed", True) else "fail"
    variant = result.get("variant") or "all"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_h(str(result.get("study_id") or ""))} eval</title>
  <style>
    body {{ color: #17202a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px auto; max-width: 1100px; padding: 0 20px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #d7dde4; padding: 9px; text-align: left; vertical-align: top; }}
    th {{ color: #66717f; text-transform: uppercase; font-size: .8rem; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    .muted {{ color: #66717f; }}
  </style>
</head>
<body>
  <h1>{_h(str(result.get("study_id") or ""))} Evaluation</h1>
  <p><strong>Status:</strong> {_h(passed)} <span class="muted">Variant: {_h(str(variant))} | Policy: {_h(str(summary.get("policy") or "strict"))}</span></p>
  <p>Recovered expected: {_h(str(summary.get("recovered_expected_count", 0)))} / {_h(str(summary.get("expected_count", 0)))}</p>
  <p class="muted">Missed: {_h(missed)} | Forbidden recovered: {_h(forbidden)} | Unexpected: {_h(unexpected)} | Failed checks: {_h(failed_checks)}</p>
  <table>
    <thead><tr><th>Rule</th><th>Title</th><th>Evidence</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def _event_rule_ids(event: dict[str, Any], next_event: dict[str, Any] | None) -> list[str]:
    ids: list[str] = []
    action = event.get("action") or {}
    result = event.get("result") or {}
    action_text = str(action.get("text") or action.get("type") or "").lower()
    final_url = str(result.get("final_url") or (next_event or {}).get("url") or "")
    started_url = str(event.get("url") or "")
    navigated_to_login = "/login" in final_url and "/login" not in started_url
    if navigated_to_login and "login" not in action_text and "sign up" not in action_text:
        ids.append("login_detour")
    if any(word in action_text for word in ("docs", "pricing")) and result.get("ok") is True and _no_observed_advance(result):
        ids.append("dead_docs_link")
    if any(phrase in action_text for phrase in ("get started", "continue", "open example", "view examples")):
        if navigated_to_login or result.get("ok") is False:
            ids.append("generic_cta_confusion")
    return ids


def _repeated_non_navigation(trace: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    repeated: list[tuple[str, dict[str, Any]]] = []
    last_key: tuple[Any, ...] | None = None
    count = 0
    for event in trace:
        action = event.get("action") or {}
        result = event.get("result") or {}
        key = (event.get("url"), action.get("type"), action.get("ref"), action.get("text"))
        if key == last_key and result.get("ok") is True and _no_observed_advance(result):
            count += 1
        else:
            count = 1
            last_key = key
        if count >= 2:
            repeated.append(("repeated_non_navigation", event))
    return repeated


def _no_observed_advance(result: dict[str, Any]) -> bool:
    outcome = result.get("action_outcome")
    if outcome:
        return outcome == "no_visible_change"
    return result.get("navigation") is False


def _add_rule_evidence(found: dict[str, dict[str, Any]], rule_id: str, meta: dict[str, Any], event: dict[str, Any]) -> None:
    rule = RULES[rule_id]
    item = found.setdefault(
        rule_id,
        {
            "id": rule_id,
            "title": rule["title"],
            "severity": rule["severity"],
            "category": rule["category"],
            "evidence": [],
            "affected_runs": [],
        },
    )
    run_id = str(meta.get("run_id") or "")
    if run_id and run_id not in item["affected_runs"]:
        item["affected_runs"].append(run_id)
    if len(item["evidence"]) < 20:
        item["evidence"].append(
            {
                "run_id": run_id,
                "step": event.get("step"),
                "url": event.get("url"),
                "action": event.get("action"),
                "result": event.get("result"),
            }
        )


def _load_expected(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    flaws = data.get("flaws") if isinstance(data, dict) else None
    if not isinstance(flaws, list):
        raise StoreError(f"Expected flaws YAML must contain a 'flaws' list: {path}", exit_code=2)
    return [item for item in flaws if isinstance(item, dict)]


def _load_checks(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    checks = data.get("checks") if isinstance(data, dict) else None
    if checks is None:
        return []
    if not isinstance(checks, list):
        raise StoreError(f"Expected checks YAML must contain a list when present: {path}", exit_code=2)
    return [item for item in checks if isinstance(item, dict)]


def _summary_passed(summary: dict[str, Any], *, policy: str, minimum_recovered_expected: int) -> bool:
    if summary.get("failed_checks"):
        return False
    if policy == "strict":
        return not summary.get("missed_expected") and not summary.get("forbidden_recovered")
    if policy == "threshold":
        expected_count = int(summary.get("expected_count") or 0)
        recovered_count = int(summary.get("recovered_expected_count") or 0)
        if summary.get("forbidden_recovered"):
            return False
        return expected_count == 0 or recovered_count >= minimum_recovered_expected
    if policy == "report_only":
        return True
    raise StoreError(f"Unknown eval policy {policy!r}.", exit_code=2)


def _expected_for_variant(expected: list[dict[str, Any]], variant: str | None) -> list[dict[str, Any]]:
    if not variant:
        return expected
    return [item for item in expected if item.get("expected_in") is None or _matches_variant(item.get("expected_in"), variant)]


def _forbidden_for_variant(expected: list[dict[str, Any]], variant: str | None) -> list[dict[str, Any]]:
    if not variant:
        return []
    return [item for item in expected if _matches_variant(item.get("absent_in"), variant)]


def _matches_variant(value: Any, variant: str) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value == variant
    if isinstance(value, list):
        return variant in [str(item) for item in value]
    return False


def _check_applies(check: dict[str, Any], variant: str) -> bool:
    if check.get("expected_in") is not None:
        return _matches_variant(check.get("expected_in"), variant)
    if check.get("absent_in") is not None:
        return _matches_variant(check.get("absent_in"), variant)
    return True


def _evaluate_first_click(runs: list[dict[str, Any]], check: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for run in runs:
        meta = run.get("meta") or {}
        event = _first_click_event(run.get("trace") or [])
        if not event:
            failures.append({"run_id": meta.get("run_id"), "reason": "No click event found."})
            continue
        action = event.get("action") or {}
        result = event.get("result") or {}
        observation = {
            "run_id": meta.get("run_id"),
            "step": event.get("step"),
            "action_text": action.get("text"),
            "final_url": result.get("final_url"),
        }
        observations.append(observation)
        action_contains = str(check.get("action_contains") or "").lower()
        final_url_contains = str(check.get("final_url_contains") or "")
        if action_contains and action_contains not in str(action.get("text") or "").lower():
            failures.append({**observation, "reason": f"Action text did not contain {action_contains!r}."})
        if final_url_contains and final_url_contains not in str(result.get("final_url") or ""):
            failures.append({**observation, "reason": f"Final URL did not contain {final_url_contains!r}."})
    return {
        "id": str(check.get("id") or "first_click"),
        "type": "first_click",
        "passed": not failures,
        "observations": observations,
        "failures": failures,
    }


def _first_click_event(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in trace:
        action = event.get("action") or {}
        if action.get("type") == "click":
            return event
    return None


def _load_runs(store: Store, study_id: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for run_dir in store.list_runs(study_id):
        meta_path = run_dir / "meta.json"
        trace_path = run_dir / "trace.jsonl"
        if not meta_path.exists() or not trace_path.exists():
            continue
        runs.append({"meta": read_json(meta_path), "trace": _read_trace(trace_path)})
    return runs


def _read_trace(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                break
            if isinstance(value, dict):
                events.append(value)
    return events


def _rule_row(item: dict[str, Any]) -> str:
    evidence = "<br>".join(
        f"<code>{_h(str(ev.get('run_id') or ''))}</code> step {_h(str(ev.get('step') or ''))}: {_h(str((ev.get('action') or {}).get('text') or ''))}"
        for ev in item.get("evidence") or []
    )
    return f"<tr><td><code>{_h(str(item.get('id') or ''))}</code></td><td>{_h(str(item.get('title') or ''))}</td><td>{evidence}</td></tr>"


def _h(value: str) -> str:
    return html.escape(value, quote=True)
