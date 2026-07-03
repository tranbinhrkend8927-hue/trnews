"""Tests for src.ingest.source_quality module."""

from __future__ import annotations

from unittest import mock

import pytest

from src.ingest.source_quality import (
    SourceQualityReport,
    assess_source_quality,
    is_quality_gate_enabled,
)


class TestSourceQualityReport:
    def test_default_values(self):
        report = SourceQualityReport()
        assert report.source_count == 0
        assert report.overall_source_quality == "insufficient"
        assert report.recommended_action == "skip_or_manual_review"
        assert report.reasons == []

    def test_strong_report(self):
        report = SourceQualityReport(
            source_count=3,
            usable_source_count=3,
            overall_source_quality="strong",
            recommended_action="write_article",
        )
        assert report.recommended_action == "write_article"


class TestAssessSourceQuality:
    def test_no_sources_returns_insufficient(self):
        report = assess_source_quality([])
        assert report.source_count == 0
        assert report.overall_source_quality == "insufficient"
        assert report.recommended_action == "skip_or_manual_review"
        assert "no_sources" in report.reasons

    def test_sources_with_good_enrichment(self):
        sources = [
            {"source_id": "s1", "content": "short"},
            {"source_id": "s2", "content": "short"},
        ]
        enrichment = [
            {"source_id": "s1", "extraction_quality": "good", "text_length": 800},
            {"source_id": "s2", "extraction_quality": "good", "text_length": 700},
        ]
        report = assess_source_quality(sources, enrichment, min_usable_sources=2, min_text_length=600)
        assert report.overall_source_quality == "strong"
        assert report.recommended_action == "write_article"
        assert report.usable_source_count == 2
        assert report.has_primary_source is True

    def test_sources_with_partial_enrichment(self):
        sources = [
            {"source_id": "s1", "content": "x"},
            {"source_id": "s2", "content": "x"},
        ]
        enrichment = [
            {"source_id": "s1", "extraction_quality": "partial", "text_length": 400},
            {"source_id": "s2", "extraction_quality": "partial", "text_length": 350},
        ]
        report = assess_source_quality(sources, enrichment, min_usable_sources=2, min_text_length=600)
        assert report.overall_source_quality == "acceptable"
        assert report.recommended_action == "write_article"

    def test_sources_with_failed_enrichment(self):
        sources = [
            {"source_id": "s1", "content": ""},
            {"source_id": "s2", "content": ""},
        ]
        enrichment = [
            {"source_id": "s1", "extraction_quality": "failed", "text_length": 0},
            {"source_id": "s2", "extraction_quality": "failed", "text_length": 0},
        ]
        report = assess_source_quality(sources, enrichment, min_usable_sources=2, min_text_length=600)
        assert report.overall_source_quality == "insufficient"
        assert report.recommended_action == "skip_or_manual_review"

    def test_failed_enrichment_falls_back_to_raw_content(self):
        sources = [
            {"source_id": "s1", "content": "A" * 900},
            {"source_id": "s2", "content": "B" * 850},
        ]
        enrichment = [
            {"source_id": "s1", "extraction_quality": "failed", "text_length": 0, "failure_reason": "trafilatura_not_installed"},
            {"source_id": "s2", "extraction_quality": "failed", "text_length": 0, "failure_reason": "trafilatura_not_installed"},
        ]
        report = assess_source_quality(sources, enrichment, min_usable_sources=2, min_text_length=600)
        assert report.overall_source_quality == "strong"
        assert report.recommended_action == "write_article"
        assert report.usable_source_count == 2
        assert report.extraction_success_rate == 0.0

    def test_sources_without_enrichment_uses_content(self):
        sources = [
            {"source_id": "s1", "content": "A" * 700},
            {"source_id": "s2", "content": "B" * 800},
        ]
        report = assess_source_quality(sources, None, min_usable_sources=2, min_text_length=600)
        assert report.overall_source_quality == "strong"
        assert report.recommended_action == "write_article"
        assert report.usable_source_count == 2

    def test_sources_with_short_content_no_enrichment(self):
        sources = [
            {"source_id": "s1", "content": "Short text"},
            {"source_id": "s2", "summary": "Brief summary"},
        ]
        report = assess_source_quality(sources, None, min_usable_sources=2, min_text_length=600)
        assert report.overall_source_quality == "insufficient"
        assert report.recommended_action == "skip_or_manual_review"

    def test_weak_quality_single_usable(self):
        sources = [
            {"source_id": "s1", "content": "A" * 400},
            {"source_id": "s2", "content": "tiny"},
        ]
        report = assess_source_quality(sources, None, min_usable_sources=2, min_text_length=600)
        assert report.overall_source_quality == "weak"
        assert report.recommended_action == "write_brief_only"
        assert report.usable_source_count == 1

    def test_mixed_enrichment_and_raw_sources(self):
        sources = [
            {"source_id": "s1", "content": ""},
            {"source_id": "s2", "content": "A" * 700},
        ]
        enrichment = [
            {"source_id": "s1", "extraction_quality": "good", "text_length": 900},
        ]
        report = assess_source_quality(sources, enrichment, min_usable_sources=2, min_text_length=600)
        assert report.usable_source_count == 2
        assert report.recommended_action == "write_article"

    def test_enrichment_with_pydantic_models(self):
        from src.ingest.source_enricher import SourceEnrichmentResult

        sources = [{"source_id": "s1", "content": ""}]
        enrichment = [
            SourceEnrichmentResult(
                source_id="s1",
                extraction_quality="good",
                text_length=800,
                usable_for_deep_article=True,
            )
        ]
        report = assess_source_quality(sources, enrichment, min_usable_sources=1, min_text_length=600)
        assert report.usable_source_count == 1
        assert report.recommended_action == "write_article"

    def test_extraction_success_rate(self):
        sources = [
            {"source_id": "s1", "content": ""},
            {"source_id": "s2", "content": ""},
            {"source_id": "s3", "content": ""},
        ]
        enrichment = [
            {"source_id": "s1", "extraction_quality": "good", "text_length": 800},
            {"source_id": "s2", "extraction_quality": "failed", "text_length": 0},
            {"source_id": "s3", "extraction_quality": "partial", "text_length": 400},
        ]
        report = assess_source_quality(sources, enrichment, min_usable_sources=2, min_text_length=600)
        assert report.extraction_success_rate == pytest.approx(0.67, abs=0.01)

    def test_duplicate_count_uses_canonical_url(self):
        sources = [
            {"source_id": "s1", "canonical_url": "https://example.com/a", "content": "A" * 700},
            {"source_id": "s2", "canonical_url": "https://example.com/a", "content": "B" * 700},
            {"source_id": "s3", "canonical_url": "https://example.com/b", "content": "C" * 700},
        ]
        report = assess_source_quality(sources, None, min_usable_sources=2, min_text_length=600)
        assert report.duplicate_count == 1

    def test_duplicate_count_falls_back_to_title_provider_day(self):
        sources = [
            {"source_id": "s1", "provider": "Example", "published_at": "2026-07-01T01:00:00Z", "title": "Same headline", "content": "A" * 700},
            {"source_id": "s2", "provider": "Example", "published_at": "2026-07-01T02:00:00Z", "title": "Same headline", "content": "B" * 700},
        ]
        report = assess_source_quality(sources, None, min_usable_sources=2, min_text_length=600)
        assert report.duplicate_count == 1


class TestIsQualityGateEnabled:
    def test_default_disabled(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            assert is_quality_gate_enabled() is False

    def test_disabled_with_0(self):
        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_QUALITY_GATE": "0"}):
            assert is_quality_gate_enabled() is False

    def test_enabled_with_1(self):
        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_QUALITY_GATE": "1"}):
            assert is_quality_gate_enabled() is True
