from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


PublishReadiness = Literal["ready", "needs_edit", "reject"]
IssueSeverity = Literal["low", "medium", "high"]


class AIReviewIssue(BaseModel):
    issue_type: str
    severity: IssueSeverity
    location: str | None = None
    description: str
    suggested_fix: str | None = None


class AIReviewScores(BaseModel):
    grounding: int = 0
    depth: int = 0
    readability: int = 0
    headline_quality: int = 0
    financial_safety: int = 0
    source_usefulness: int = 0

    @field_validator("*")
    @classmethod
    def score_range(cls, value: int) -> int:
        if value < 0:
            return 0
        if value > 100:
            return 100
        return value


class AIReview(BaseModel):
    publish_readiness: PublishReadiness
    scores: AIReviewScores
    issues: list[AIReviewIssue] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    overstatements: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    rewrite_suggestions: list[str] = Field(default_factory=list)
    recommended_editor_action: str
    reviewer_mode: Literal["deterministic", "llm", "deterministic_fallback"] = "deterministic"
