from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ContentType = Literal["deep_article", "market_brief", "explainer", "news_update"]
ConfidenceLevel = Literal["high", "medium", "low"]


class EditorialBrief(BaseModel):
    event_summary: str
    why_it_matters: str
    market_context: str
    primary_angle: str
    reader_questions: list[str] = Field(default_factory=list)
    must_cover: list[str] = Field(default_factory=list)
    avoid_claims: list[str] = Field(default_factory=list)
    source_gaps: list[str] = Field(default_factory=list)
    recommended_structure: list[str] = Field(default_factory=list)
    target_reader: str
    content_type: ContentType = "deep_article"
    confidence_level: ConfidenceLevel = "medium"
    editorial_notes: list[str] = Field(default_factory=list)


class BriefValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["warning", "error"]
    field: str | None = None


class BriefValidationResult(BaseModel):
    passed: bool
    recommended_status: Literal["ready", "needs_brief_rewrite", "needs_manual_review", "write_brief_only"]
    issues: list[BriefValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
