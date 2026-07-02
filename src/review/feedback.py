from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


ReviewStatus = Literal[
    "approved",
    "rejected",
    "needs_edit",
    "needs_rewrite",
    "needs_source_fix",
    "needs_compliance_fix",
    "needs_language_fix",
    "published",
    "ignored",
]


class ReviewFeedback(BaseModel):
    feedback_id: str
    timestamp: str

    pipeline_run_id: Optional[str] = None
    content_job_key: Optional[str] = None
    source_bundle_hash: Optional[str] = None

    notion_page_id: Optional[str] = None
    notion_url: Optional[str] = None

    market_id: Optional[str] = None
    symbol: Optional[str] = None
    language: Optional[str] = None
    task: Optional[str] = None

    model: Optional[str] = None
    prompt_version: Optional[str] = None
    llm_profile: Optional[str] = None

    review_status: ReviewStatus
    reviewer: Optional[str] = None

    editor_score: Optional[int] = None
    quality_score: Optional[int] = None
    factuality_score: Optional[int] = None
    language_score: Optional[int] = None
    seo_score: Optional[int] = None
    compliance_score: Optional[int] = None

    edit_required: bool = False
    rewrite_required: bool = False
    source_fix_required: bool = False
    compliance_fix_required: bool = False
    language_fix_required: bool = False

    issues: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    edited_headline: Optional[str] = None
    edited_summary: Optional[str] = None
    final_publish_decision: Optional[str] = None
    reviewed_at: Optional[str] = None

    metadata: dict = Field(default_factory=dict)

    @field_validator("editor_score", "quality_score", "factuality_score", "language_score", "seo_score", "compliance_score")
    @classmethod
    def score_must_be_one_to_five(cls, value):
        if value is None:
            return value
        if not 1 <= value <= 5:
            raise ValueError("score must be between 1 and 5")
        return value


def create_review_feedback(
    *,
    review_status: str,
    pipeline_run_id: str | None = None,
    content_job_key: str | None = None,
    source_bundle_hash: str | None = None,
    notion_page_id: str | None = None,
    notion_url: str | None = None,
    market_id: str | None = None,
    symbol: str | None = None,
    language: str | None = None,
    task: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    llm_profile: str | None = None,
    reviewer: str | None = None,
    editor_score: int | None = None,
    quality_score: int | None = None,
    factuality_score: int | None = None,
    language_score: int | None = None,
    seo_score: int | None = None,
    compliance_score: int | None = None,
    issues: list[str] | None = None,
    notes: str | None = None,
    rejection_reason: str | None = None,
    edited_headline: str | None = None,
    edited_summary: str | None = None,
    final_publish_decision: str | None = None,
    reviewed_at: str | None = None,
    metadata: dict | None = None,
) -> ReviewFeedback:
    timestamp = _utc_now()
    flags = _flags_for_status(review_status)
    payload = {
        "timestamp": timestamp,
        "review_status": review_status,
        "pipeline_run_id": pipeline_run_id,
        "content_job_key": content_job_key,
        "notion_page_id": notion_page_id,
        "reviewer": reviewer,
    }
    return ReviewFeedback(
        feedback_id=_feedback_id(payload),
        timestamp=timestamp,
        pipeline_run_id=pipeline_run_id,
        content_job_key=content_job_key,
        source_bundle_hash=source_bundle_hash,
        notion_page_id=notion_page_id,
        notion_url=notion_url,
        market_id=market_id,
        symbol=symbol,
        language=language,
        task=task,
        model=model,
        prompt_version=prompt_version,
        llm_profile=llm_profile,
        review_status=review_status,
        reviewer=reviewer,
        editor_score=editor_score,
        quality_score=quality_score,
        factuality_score=factuality_score,
        language_score=language_score,
        seo_score=seo_score,
        compliance_score=compliance_score,
        issues=issues or [],
        notes=notes,
        rejection_reason=rejection_reason,
        edited_headline=edited_headline,
        edited_summary=edited_summary,
        final_publish_decision=final_publish_decision,
        reviewed_at=reviewed_at,
        metadata=metadata or {},
        **flags,
    )


def _flags_for_status(review_status: str) -> dict:
    flags = {
        "edit_required": False,
        "rewrite_required": False,
        "source_fix_required": False,
        "compliance_fix_required": False,
        "language_fix_required": False,
    }
    if review_status == "needs_edit":
        flags["edit_required"] = True
    elif review_status == "needs_rewrite":
        flags["edit_required"] = True
        flags["rewrite_required"] = True
    elif review_status == "needs_source_fix":
        flags["edit_required"] = True
        flags["source_fix_required"] = True
    elif review_status == "needs_compliance_fix":
        flags["edit_required"] = True
        flags["compliance_fix_required"] = True
    elif review_status == "needs_language_fix":
        flags["edit_required"] = True
        flags["language_fix_required"] = True
    elif review_status == "rejected":
        flags["edit_required"] = True
    return flags


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _feedback_id(payload: dict) -> str:
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]
    return f"feedback-{digest}"
