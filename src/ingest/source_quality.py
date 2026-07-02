"""Source quality assessment for the content pipeline.

Evaluates whether a set of sources (optionally enriched) are sufficient
for writing a deep article, a brief-only summary, or should be skipped.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceQualityReport(BaseModel):
    source_count: int = 0
    usable_source_count: int = 0
    average_text_length: float = 0.0
    has_primary_source: bool = False
    has_recent_sources: bool = False
    duplicate_count: int = 0
    extraction_success_rate: float = 0.0
    overall_source_quality: Literal["strong", "acceptable", "weak", "insufficient"] = "insufficient"
    recommended_action: Literal["write_article", "write_brief_only", "skip_or_manual_review"] = "skip_or_manual_review"
    reasons: list[str] = Field(default_factory=list)
    source_gaps: list[str] = Field(default_factory=list)


def assess_source_quality(
    sources: list[dict[str, Any]],
    enrichment_results: list[dict[str, Any]] | None = None,
    *,
    min_usable_sources: int | None = None,
    min_text_length: int | None = None,
) -> SourceQualityReport:
    """Build a SourceQualityReport from sources and optional enrichment results."""
    effective_min_usable = min_usable_sources or _env_int("MIN_USABLE_SOURCE_COUNT", 2)
    effective_min_length = min_text_length or _env_int("MIN_ENRICHED_TEXT_LENGTH", 600)

    source_count = len(sources)
    duplicate_count = _count_duplicates(sources)
    if source_count == 0:
        return SourceQualityReport(
            source_count=0,
            duplicate_count=0,
            overall_source_quality="insufficient",
            recommended_action="skip_or_manual_review",
            reasons=["no_sources"],
        )

    enrichment_map = _build_enrichment_map(enrichment_results)
    usable_sources = []
    text_lengths: list[int] = []
    success_count = 0
    has_primary = False

    for source in sources:
        source_id = str(source.get("source_id") or "")
        enrichment = enrichment_map.get(source_id)

        if enrichment:
            quality = enrichment.get("extraction_quality", "failed")
            text_length = int(enrichment.get("text_length") or 0)
            if quality != "failed":
                success_count += 1
            if quality in ("good", "partial"):
                usable_sources.append(source_id)
                if quality == "good":
                    has_primary = True
            if text_length > 0:
                text_lengths.append(text_length)
        else:
            content = str(source.get("content") or "").strip()
            summary = str(source.get("summary") or "").strip()
            text = content or summary
            text_length = len(text)
            if text_length > 0:
                text_lengths.append(text_length)
            if text_length >= effective_min_length:
                usable_sources.append(source_id)
                has_primary = True
                success_count += 1
            elif text_length >= effective_min_length // 2:
                usable_sources.append(source_id)
                success_count += 1

    usable_count = len(usable_sources)
    avg_length = sum(text_lengths) / len(text_lengths) if text_lengths else 0.0
    success_rate = success_count / source_count if source_count > 0 else 0.0

    quality, action, reasons, gaps = _evaluate(
        source_count=source_count,
        usable_count=usable_count,
        has_primary=has_primary,
        avg_length=avg_length,
        success_rate=success_rate,
        min_usable=effective_min_usable,
        min_length=effective_min_length,
    )

    return SourceQualityReport(
        source_count=source_count,
        usable_source_count=usable_count,
        average_text_length=round(avg_length, 1),
        has_primary_source=has_primary,
        has_recent_sources=source_count > 0,
        duplicate_count=duplicate_count,
        extraction_success_rate=round(success_rate, 2),
        overall_source_quality=quality,
        recommended_action=action,
        reasons=reasons,
        source_gaps=gaps,
    )


def is_quality_gate_enabled() -> bool:
    """Check whether the source quality gate is enabled."""
    return os.getenv("ENABLE_SOURCE_QUALITY_GATE", "0").strip() in ("1", "true", "yes")


def _build_enrichment_map(results: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if not results:
        return {}
    mapping: dict[str, dict[str, Any]] = {}
    for item in results:
        if isinstance(item, dict):
            source_id = str(item.get("source_id") or "")
            if source_id:
                mapping[source_id] = item
        elif hasattr(item, "model_dump"):
            dump = item.model_dump()
            source_id = str(dump.get("source_id") or "")
            if source_id:
                mapping[source_id] = dump
    return mapping


def _count_duplicates(sources: list[dict[str, Any]]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for source in sources:
        key = _dedupe_key(source)
        if not key:
            continue
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
    return duplicates


def _dedupe_key(source: dict[str, Any]) -> str:
    url = str(source.get("canonical_url") or source.get("url") or "").strip().lower()
    if url:
        return f"url:{url}"
    title = str(source.get("title") or source.get("original_title") or "").strip().lower()
    provider = str(source.get("provider") or source.get("source") or "").strip().lower()
    published_day = str(source.get("published_at") or "").strip()[:10]
    if title:
        return f"title:{provider}:{published_day}:{title}"
    return ""


def _evaluate(
    *,
    source_count: int,
    usable_count: int,
    has_primary: bool,
    avg_length: float,
    success_rate: float,
    min_usable: int,
    min_length: int,
) -> tuple[str, str, list[str], list[str]]:
    reasons: list[str] = []
    gaps: list[str] = []

    if usable_count >= min_usable and has_primary and avg_length >= min_length * 0.6:
        quality = "strong"
        action = "write_article"
        reasons.append(f"usable_sources={usable_count} (>= {min_usable})")
        reasons.append("has_primary_source")
    elif usable_count >= min_usable and avg_length >= min_length * 0.3:
        quality = "acceptable"
        action = "write_article"
        reasons.append(f"usable_sources={usable_count} (>= {min_usable})")
        if not has_primary:
            reasons.append("no_primary_source_but_enough_usable")
    elif usable_count >= 1:
        quality = "weak"
        action = "write_brief_only"
        reasons.append(f"usable_sources={usable_count} (< {min_usable})")
        gaps.append("not_enough_usable_sources_for_deep_article")
        if avg_length < min_length * 0.3:
            gaps.append("average_text_too_short")
    else:
        quality = "insufficient"
        action = "skip_or_manual_review"
        reasons.append(f"no_usable_sources (total={source_count})")
        gaps.append("no_usable_source_content")
        if source_count > 0:
            gaps.append("sources_exist_but_content_not_extractable")

    return quality, action, reasons, gaps


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
