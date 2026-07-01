from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LLMTaskError(BaseModel):
    type: str
    message: str
    retryable: bool = False
    raw: dict = Field(default_factory=dict)


class LLMTaskResult(BaseModel):
    success: bool
    task: str
    language: Optional[str] = None
    profile: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    output: Optional[dict] = None
    raw_text: Optional[str] = None
    usage: dict = Field(default_factory=dict)
    latency_ms: Optional[int] = None
    error: Optional[LLMTaskError] = None
    metadata: dict = Field(default_factory=dict)
