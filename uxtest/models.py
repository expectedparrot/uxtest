from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, StrictStr


ActionType = Literal["click", "type", "scroll", "find", "select", "back", "wait", "none"]
RunDriver = Literal["edsl", "heuristic", "scripted"]


class BrowserAction(BaseModel):
    type: ActionType = Field(description="Browser action to take.")
    ref: str | None = Field(default=None, description="Element ref from the supplied interactive elements.")
    text: str | None = Field(default=None, description="Short action description, or text/topic to find for find actions.")
    value: str | None = Field(default=None, description="Optional value for selects.")


class BrowserDecision(BaseModel):
    action: BrowserAction
    thinking: str
    frustration: int = Field(ge=0, le=10)
    status: Literal["continue", "done", "gave_up"]
    driver: RunDriver = "heuristic"
    raw_response: str | None = None
    edsl: dict[str, Any] = Field(default_factory=dict)


class BrowserDecisionAnswer(BaseModel):
    action_type: ActionType = Field(description="Browser action to take.")
    ref: str | None = Field(default=None, description="Element ref from the supplied interactive elements.")
    text: str | None = Field(default=None, description="Short action description, or text/topic to find for find actions.")
    value: str | None = Field(default=None, description="Exact value to enter for type/select actions.")
    thinking: StrictStr = Field(description="Brief rationale for the next action.")
    frustration: int = Field(ge=0, le=10, description="Current frustration from 0 to 10.")
    status: Literal["continue", "done", "gave_up"] = Field(description="Agent assessment of task status.")
