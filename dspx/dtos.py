from __future__ import annotations

from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class LMRequest(BaseModel):
    prompt: Optional[str] = None
    messages: Optional[List[Message]] = None
    options: dict[str, Any] = Field(default_factory=dict)


class LMResponse(BaseModel):
    outputs: List[str]
    model: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    raw: Optional[dict[str, Any]] = None

