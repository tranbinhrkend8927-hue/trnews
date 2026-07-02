"""Source enrichment via Trafilatura full-text extraction.

Enriches NormalizedNewsItem sources by extracting full article text from
their URLs. Controlled by ENABLE_SOURCE_ENRICHMENT env var (default off).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MIN_ENRICHED_TEXT_LENGTH_DEFAULT = 600
SOURCE_ENRICHMENT_TIMEOUT_DEFAULT = 8


class SourceEnrichmentResult(BaseModel):
    source_id: str
    original_url: str | None = None
    extracted_title: str | None = None
    extracted_text: str | None = None
    author: str | None = None
    published_at: str | None = None
    site_name: str | None = None
    language: str | None = None
    text_length: int = 0
    extraction_quality: Literal["good", "partial", "poor", "failed"] = "failed"
    failure_reason: str | None = None
    usable_for_deep_article: bool = False
    metadata_confidence: Literal["high", "medium", "low"] = "low"
    extraction_method: str = "trafilatura"


def enrich_source(source: dict[str, Any], *, timeout: int | None = None, min_text_length: int | None = None) -> SourceEnrichmentResult:
    """Enrich a single source by extracting full text from its URL."""
    source_id = str(source.get("source_id") or "")
    url = str(source.get("url") or source.get("canonical_url") or "").strip()
    if not url:
        return SourceEnrichmentResult(
            source_id=source_id,
            extraction_quality="failed",
            failure_reason="no_url",
        )

    effective_timeout = timeout or _env_int("SOURCE_ENRICHMENT_TIMEOUT_SECONDS", SOURCE_ENRICHMENT_TIMEOUT_DEFAULT)
    effective_min_length = min_text_length or _env_int("MIN_ENRICHED_TEXT_LENGTH", MIN_ENRICHED_TEXT_LENGTH_DEFAULT)

    try:
        import trafilatura
    except ImportError:
        return SourceEnrichmentResult(
            source_id=source_id,
            original_url=url,
            extraction_quality="failed",
            failure_reason="trafilatura_not_installed",
        )

    try:
        downloaded = _fetch_url(trafilatura, url, effective_timeout)
        if not downloaded:
            return SourceEnrichmentResult(
                source_id=source_id,
                original_url=url,
                extraction_quality="failed",
                failure_reason="fetch_failed",
            )

        extracted_text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        metadata = trafilatura.extract_metadata(downloaded)

        if not extracted_text:
            return SourceEnrichmentResult(
                source_id=source_id,
                original_url=url,
                extraction_quality="failed",
                failure_reason="extraction_empty",
            )

        text_length = len(extracted_text)
        quality = _classify_quality(text_length, effective_min_length)
        meta_title = getattr(metadata, "title", None) if metadata else None
        meta_author = getattr(metadata, "author", None) if metadata else None
        meta_sitename = getattr(metadata, "sitename", None) if metadata else None
        meta_date = getattr(metadata, "date", None) if metadata else None

        return SourceEnrichmentResult(
            source_id=source_id,
            original_url=url,
            extracted_title=meta_title,
            extracted_text=extracted_text,
            author=meta_author,
            published_at=str(meta_date) if meta_date else None,
            site_name=meta_sitename,
            text_length=text_length,
            extraction_quality=quality,
            usable_for_deep_article=quality in ("good", "partial"),
            metadata_confidence=_metadata_confidence(metadata),
            extraction_method="trafilatura",
        )
    except Exception as exc:
        logger.warning("Source enrichment failed for %s: %s", url, exc)
        return SourceEnrichmentResult(
            source_id=source_id,
            original_url=url,
            extraction_quality="failed",
            failure_reason=f"exception: {type(exc).__name__}: {exc}",
        )


def enrich_sources(sources: list[dict[str, Any]], *, timeout: int | None = None, min_text_length: int | None = None) -> list[SourceEnrichmentResult]:
    """Enrich multiple sources sequentially."""
    return [enrich_source(source, timeout=timeout, min_text_length=min_text_length) for source in sources]


def is_enrichment_enabled() -> bool:
    """Check whether source enrichment is enabled via env var."""
    return os.getenv("ENABLE_SOURCE_ENRICHMENT", "0").strip() in ("1", "true", "yes")


def _classify_quality(text_length: int, min_length: int) -> Literal["good", "partial", "poor", "failed"]:
    if text_length >= min_length:
        return "good"
    if text_length >= min_length // 2:
        return "partial"
    if text_length > 0:
        return "poor"
    return "failed"


def _metadata_confidence(metadata: Any) -> Literal["high", "medium", "low"]:
    if metadata is None:
        return "low"
    has_title = bool(getattr(metadata, "title", None))
    has_author = bool(getattr(metadata, "author", None))
    has_date = bool(getattr(metadata, "date", None))
    score = sum([has_title, has_author, has_date])
    if score >= 3:
        return "high"
    if score >= 1:
        return "medium"
    return "low"


def _fetch_url(trafilatura: Any, url: str, timeout: int) -> Any:
    try:
        config = trafilatura.settings.use_config()
        config.set("DEFAULT", "DOWNLOAD_TIMEOUT", str(timeout))
        return trafilatura.fetch_url(url, config=config)
    except (AttributeError, TypeError):
        return trafilatura.fetch_url(url)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
