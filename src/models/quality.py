from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


HeadlineRiskLevel = Literal["low", "medium", "high"]
FinalRecommendedStatus = Literal["needs_review", "needs_edit", "needs_rewrite", "rejected"]


class ArticleQualityReport(BaseModel):
    source_count: int = 0
    usable_source_count: int = 0
    body_length: int = 0
    faq_count: int = 0
    has_market_context: bool = False
    has_risk_disclaimer: bool = False
    has_source_attribution: bool = False
    grounded_claim_ratio: float | None = None
    headline_risk_level: HeadlineRiskLevel = "low"
    financial_advice_detected: bool = False
    editor_ready_score: int = 0
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    final_recommended_status: FinalRecommendedStatus = "needs_edit"

    @field_validator("editor_ready_score")
    @classmethod
    def clamp_editor_ready_score(cls, value: int) -> int:
        if value < 0:
            return 0
        if value > 100:
            return 100
        return value

    @field_validator("grounded_claim_ratio")
    @classmethod
    def clamp_grounded_claim_ratio(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < 0:
            return 0.0
        if value > 1:
            return 1.0
        return value
