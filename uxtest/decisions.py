from __future__ import annotations

from typing import Any

from .models import BrowserAction, BrowserDecision


def heuristic_decision(study: dict[str, Any], state: dict[str, Any]) -> BrowserDecision:
    text = state["visible_text"].lower()
    elements = state["interactive_elements"]

    if "order number" in text or "order confirmed" in text:
        return BrowserDecision(action=BrowserAction(type="none"), thinking="The confirmation page is visible.", frustration=0, status="done", driver="heuristic")

    field_values = {
        "email": "tester@example.com",
        "name": "Test Shopper",
        "card": "4242424242424242",
        "zip": "02139",
    }
    for key, value in field_values.items():
        found = find_element(elements, name=key)
        if found and str(found.get("value") or "") != value:
            return BrowserDecision(action=BrowserAction(type="type", ref=found["ref"], text=value), thinking=f"Fill {key}.", frustration=1, status="continue", driver="heuristic")

    for label in ["place order", "checkout as guest", "continue", "add to cart"]:
        found = find_element(elements, label=label)
        if found:
            return BrowserDecision(action=BrowserAction(type="click", ref=found["ref"]), thinking=f"Click {label}.", frustration=1, status="continue", driver="heuristic")

    return BrowserDecision(action=BrowserAction(type="wait"), thinking="Wait for the page to settle.", frustration=3, status="continue", driver="heuristic")


def scripted_decision(study: dict[str, Any], state: dict[str, Any], recent_events: list[dict[str, Any]] | None = None) -> BrowserDecision:
    text = state["visible_text"].lower()
    url = state["url"].lower()
    elements = state["interactive_elements"]
    recent_events = recent_events or []
    recent_actions = [
        str((event.get("action") or {}).get("text") or (event.get("action") or {}).get("type") or "").lower()
        for event in recent_events
    ]
    is_flawed_saas = "variant=flawed" in str(study.get("url", "")).lower() or "variant=flawed" in url

    if "order number" in text or "order confirmed" in text:
        return BrowserDecision(action=BrowserAction(type="none"), thinking="The confirmation page is visible.", frustration=0, status="done", driver="scripted")

    if "northstar" in text or "research agent" in text or "ai interviewer" in text:
        if is_flawed_saas:
            for label in ["view examples", "open example", "docs", "pricing", "menu"]:
                found = find_element(elements, label=label)
                if found and not scripted_recently_clicked(label, recent_actions, limit=2):
                    return BrowserDecision(
                        action=BrowserAction(type="click", ref=found["ref"], text=str(found.get("label") or label)),
                        thinking=f"Click {label} to follow the fixture's flawed discovery path.",
                        frustration=2,
                        status="continue",
                        driver="scripted",
                    )
            repeated_docs = find_element(elements, label="docs")
            if repeated_docs:
                return BrowserDecision(
                    action=BrowserAction(type="click", ref=repeated_docs["ref"], text=str(repeated_docs.get("label") or "Docs")),
                    thinking="Repeat Docs to verify whether the page advances after an acknowledged click.",
                    frustration=5,
                    status="continue",
                    driver="scripted",
                )
        else:
            for label in ["explore products", "menu", "docs", "quickstart", "overview"]:
                found = find_element(elements, label=label)
                if found and not scripted_recently_clicked(label, recent_actions, limit=1):
                    return BrowserDecision(
                        action=BrowserAction(type="click", ref=found["ref"], text=str(found.get("label") or label)),
                        thinking=f"Click {label} to follow the fixture's clear discovery path.",
                        frustration=1,
                        status="continue",
                        driver="scripted",
                    )
            return BrowserDecision(action=BrowserAction(type="none"), thinking="The clear discovery route has enough evidence.", frustration=1, status="done", driver="scripted")

    return heuristic_decision(study, state).model_copy(update={"driver": "scripted"})


def scripted_recently_clicked(label: str, recent_actions: list[str], *, limit: int) -> bool:
    normalized = label.lower()
    return sum(1 for action in recent_actions if normalized in action) >= limit


def find_element(elements: list[dict[str, Any]], *, label: str | None = None, name: str | None = None) -> dict[str, Any] | None:
    for element in elements:
        if name and element.get("name") == name:
            return element
        if label and label in str(element.get("label", "")).lower():
            return element
    return None
