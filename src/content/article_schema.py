from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


class FAQItem(BaseModel):
    question: str
    answer: str


class SourceUsed(BaseModel):
    source_id: str
    news_id: Optional[Union[str, int]] = None
    title: str
    url: Optional[str] = None
    provider: Optional[str] = None
    published_at: Optional[str] = None
    used_for: Optional[str] = None


class UncertainClaim(BaseModel):
    claim: str
    reason: str
    severity: Literal["low", "medium", "high"] = "low"


class ArticleDraft(BaseModel):
    title: str
    slug: str
    summary: str
    body: str
    seo_title: str
    seo_description: str
    language: str
    market: str
    symbol: str
    article_type: str
    risk_disclaimer: str
    faq: list[FAQItem] = Field(default_factory=list)
    sources_used: list[SourceUsed] = Field(default_factory=list)
    uncertain_claims: list[UncertainClaim] = Field(default_factory=list)


def article_draft_json_schema() -> dict:
    if hasattr(ArticleDraft, "model_json_schema"):
        return ArticleDraft.model_json_schema()
    return ArticleDraft.schema()
