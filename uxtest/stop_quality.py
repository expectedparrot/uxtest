from __future__ import annotations

from collections import Counter
from typing import Any


STOP_QUALITY_LABELS = {
    "done": "Stopped with enough evidence",
    "enough_evidence_but_continued": "Had enough evidence but continued",
    "looping": "Looped or repeated a path",
    "blocked_by_auth": "Blocked by authentication",
    "blocked_by_no_visible_advance": "Blocked by no visible advance",
    "unresolved": "Unresolved",
    "error": "Execution error",
}


def classify_run_stop_quality(meta: dict[str, Any], trace: list[dict[str, Any]]) -> dict[str, Any]:
    outcome = str(meta.get("outcome") or "unknown")
    if outcome == "error":
        return _quality("error", "Run ended with an execution error.", trace[-1] if trace else None)
    if outcome == "done":
        return _quality("done", "The agent or success criteria marked the run complete.", _last_done_event(trace) or (trace[-1] if trace else None))
    if _has_enough_evidence(trace):
        return _quality(
            "enough_evidence_but_continued",
            "The trace contains enough self-reported understanding to answer the exploratory task, but the run did not stop.",
            _first_enough_evidence_event(trace),
        )
    if _blocked_by_auth(meta, trace):
        return _quality("blocked_by_auth", "The path moved into login or sign-up before the task was completed.", _first_auth_event(trace) or (trace[-1] if trace else None))
    if _blocked_by_no_visible_advance(trace):
        return _quality("blocked_by_no_visible_advance", "The run ended after a click that produced no observed page, menu, tab, scroll, or URL change.", trace[-1] if trace else None)
    if _looping(trace):
        return _quality("looping", "The trace repeated an action or cycled through the same URL path.", _loop_event(trace) or (trace[-1] if trace else None))
    return _quality("unresolved", "The run ended before the task was completed and no clearer stop-quality class was detected.", trace[-1] if trace else None)


def stop_quality_counts(runs: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for run in runs:
        counts[classify_run_stop_quality(run.get("meta") or {}, run.get("trace") or [])["class"]] += 1
    return counts


def event_has_enough_evidence(event: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(event.get("thinking") or ""),
            str(((event.get("observation") or {}).get("visible_text_preview") if isinstance(event.get("observation"), dict) else "") or ""),
            str((event.get("action") or {}).get("text") or ""),
        ]
    ).lower()
    return _text_suggests_enough_evidence(text)


def compact_stop_hint(recent_events: list[dict[str, Any]]) -> dict[str, str] | None:
    if not recent_events:
        return None
    if any((event.get("stop_signal") or {}).get("enough_evidence") for event in recent_events[-2:]):
        return {
            "event_type": "stop_hint",
            "message": "A recent step appears to have enough evidence to answer the exploratory task. If the purpose, next action, and hesitation can be explained, set status=done and action_type=none.",
        }
    if _compact_looping(recent_events):
        return {
            "event_type": "stop_hint",
            "message": "The recent path is looping. Choose a different strategy or stop with status=done if the task can already be answered.",
        }
    return None


def _quality(class_name: str, reason: str, event: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "class": class_name,
        "label": STOP_QUALITY_LABELS[class_name],
        "reason": reason,
        "step": event.get("step") if isinstance(event, dict) else None,
        "url": event.get("url") if isinstance(event, dict) else None,
    }


def _last_done_event(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(trace):
        if event.get("status") == "done":
            return event
    return None


def _has_enough_evidence(trace: list[dict[str, Any]]) -> bool:
    return _first_enough_evidence_event(trace) is not None


def _first_enough_evidence_event(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in trace:
        if event_has_enough_evidence(event):
            return event
    return None


def _text_suggests_enough_evidence(text: str) -> bool:
    strong_phrases = (
        "enough evidence",
        "i understand",
        "i can explain",
        "can explain",
        "site appears to be",
        "appears to be for",
        "site is for",
        "product is for",
        "what this product",
        "purpose",
        "next step",
        "would click",
        "remaining hesitation",
    )
    if any(phrase in text for phrase in strong_phrases):
        return True
    return (
        any(phrase in text for phrase in ("ai simulation", "survey research", "stakeholder", "research workflow"))
        and any(phrase in text for phrase in ("get started", "products", "docs", "about", "demo", "login", "sign up"))
    )


def _blocked_by_auth(meta: dict[str, Any], trace: list[dict[str, Any]]) -> bool:
    final_url = str(meta.get("final_url") or "")
    if _is_auth_url(final_url) and str(meta.get("outcome") or "") != "done":
        return True
    return _first_auth_event(trace) is not None and str(meta.get("outcome") or "") in {"max_steps", "gave_up"}


def _first_auth_event(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in trace:
        result = event.get("result") if isinstance(event.get("result"), dict) else {}
        if _is_auth_url(str(result.get("final_url") or event.get("url") or "")):
            return event
    return None


def _is_auth_url(url: str) -> bool:
    lowered = url.lower()
    return any(part in lowered for part in ("/login", "/signin", "/sign-in", "/signup", "/sign-up", "/auth"))


def _blocked_by_no_visible_advance(trace: list[dict[str, Any]]) -> bool:
    if not trace:
        return False
    result = trace[-1].get("result") if isinstance(trace[-1].get("result"), dict) else {}
    return result.get("action_outcome") == "no_visible_change"


def _looping(trace: list[dict[str, Any]]) -> bool:
    return _loop_event(trace) is not None


def _loop_event(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    action_counts: Counter[tuple[Any, ...]] = Counter()
    url_counts: Counter[str] = Counter()
    for event in trace:
        action = event.get("action") if isinstance(event.get("action"), dict) else {}
        key = (event.get("url"), action.get("type"), action.get("ref"), action.get("text"))
        action_counts[key] += 1
        url_path = _url_path(str(event.get("url") or ""))
        if url_path:
            url_counts[url_path] += 1
        if action_counts[key] >= 2 and len(trace) >= 3:
            return event
        if url_counts[url_path] >= 3 and len(trace) >= 4:
            return event
    return None


def _compact_looping(events: list[dict[str, Any]]) -> bool:
    if len(events) < 3:
        return False
    latest = events[-3:]
    keys = [
        (event.get("url"), (event.get("action") or {}).get("type"), (event.get("action") or {}).get("ref"), (event.get("action") or {}).get("text"))
        for event in latest
    ]
    return len(set(keys)) < len(keys)


def _url_path(url: str) -> str:
    if "://" in url:
        url = url.split("://", 1)[1]
        url = "/" + url.split("/", 1)[1] if "/" in url else "/"
    return url.split("?", 1)[0].split("#", 1)[0]
