"""Tests for src.ingest.source_enricher module."""

from __future__ import annotations

from unittest import mock

import pytest

from src.ingest.source_enricher import (
    SourceEnrichmentResult,
    enrich_source,
    enrich_sources,
    is_enrichment_enabled,
)


class TestSourceEnrichmentResult:
    def test_default_values(self):
        result = SourceEnrichmentResult(source_id="abc")
        assert result.source_id == "abc"
        assert result.extraction_quality == "failed"
        assert result.usable_for_deep_article is False
        assert result.metadata_confidence == "low"
        assert result.extraction_method == "trafilatura"

    def test_good_quality_result(self):
        result = SourceEnrichmentResult(
            source_id="abc",
            original_url="https://example.com/article",
            extracted_text="x" * 700,
            text_length=700,
            extraction_quality="good",
            usable_for_deep_article=True,
            metadata_confidence="high",
        )
        assert result.extraction_quality == "good"
        assert result.usable_for_deep_article is True


class TestEnrichSource:
    def test_no_url_returns_failed(self):
        source = {"source_id": "s1", "title": "Headline"}
        result = enrich_source(source)
        assert result.extraction_quality == "failed"
        assert result.failure_reason == "no_url"

    def test_empty_url_returns_failed(self):
        source = {"source_id": "s2", "url": "", "canonical_url": ""}
        result = enrich_source(source)
        assert result.extraction_quality == "failed"
        assert result.failure_reason == "no_url"

    def test_trafilatura_not_installed(self):
        source = {"source_id": "s3", "url": "https://example.com/news"}
        with mock.patch.dict("sys.modules", {"trafilatura": None}):
            result = enrich_source(source)
        assert result.extraction_quality == "failed"
        assert result.failure_reason == "trafilatura_not_installed"

    def test_fetch_failed(self):
        source = {"source_id": "s4", "url": "https://example.com/news"}
        mock_trafilatura = mock.MagicMock()
        mock_trafilatura.fetch_url.return_value = None
        with mock.patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = enrich_source(source)
        assert result.extraction_quality == "failed"
        assert result.failure_reason == "fetch_failed"

    def test_extraction_empty(self):
        source = {"source_id": "s5", "url": "https://example.com/news"}
        mock_trafilatura = mock.MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html></html>"
        mock_trafilatura.extract.return_value = None
        with mock.patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = enrich_source(source)
        assert result.extraction_quality == "failed"
        assert result.failure_reason == "extraction_empty"

    def test_good_extraction(self):
        source = {"source_id": "s6", "url": "https://example.com/news"}
        long_text = "A" * 700
        mock_trafilatura = mock.MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html><body>content</body></html>"
        mock_trafilatura.extract.return_value = long_text
        mock_metadata = mock.MagicMock()
        mock_metadata.title = "Article Title"
        mock_metadata.author = "Author Name"
        mock_metadata.sitename = "Example News"
        mock_metadata.date = "2026-07-01"
        mock_trafilatura.extract_metadata.return_value = mock_metadata
        with mock.patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = enrich_source(source, min_text_length=600)
        assert result.extraction_quality == "good"
        assert result.usable_for_deep_article is True
        assert result.text_length == 700
        assert result.extracted_title == "Article Title"
        assert result.metadata_confidence == "high"

    def test_partial_extraction(self):
        source = {"source_id": "s7", "url": "https://example.com/news"}
        short_text = "B" * 350
        mock_trafilatura = mock.MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html>ok</html>"
        mock_trafilatura.extract.return_value = short_text
        mock_trafilatura.extract_metadata.return_value = None
        with mock.patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = enrich_source(source, min_text_length=600)
        assert result.extraction_quality == "partial"
        assert result.usable_for_deep_article is True

    def test_poor_extraction(self):
        source = {"source_id": "s8", "url": "https://example.com/news"}
        tiny_text = "C" * 100
        mock_trafilatura = mock.MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html>ok</html>"
        mock_trafilatura.extract.return_value = tiny_text
        mock_trafilatura.extract_metadata.return_value = None
        with mock.patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = enrich_source(source, min_text_length=600)
        assert result.extraction_quality == "poor"
        assert result.usable_for_deep_article is False

    def test_exception_handling(self):
        source = {"source_id": "s9", "url": "https://example.com/news"}
        mock_trafilatura = mock.MagicMock()
        mock_trafilatura.fetch_url.side_effect = TimeoutError("timed out")
        with mock.patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = enrich_source(source)
        assert result.extraction_quality == "failed"
        assert "TimeoutError" in result.failure_reason

    def test_uses_canonical_url_fallback(self):
        source = {"source_id": "s10", "canonical_url": "https://example.com/canonical"}
        mock_trafilatura = mock.MagicMock()
        mock_trafilatura.fetch_url.return_value = None
        with mock.patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = enrich_source(source)
        assert result.original_url == "https://example.com/canonical"
        assert mock_trafilatura.fetch_url.call_args.args == ("https://example.com/canonical",)

    def test_uses_timeout_config_when_supported(self):
        source = {"source_id": "s11", "url": "https://example.com/news"}
        mock_config = mock.MagicMock()
        mock_trafilatura = mock.MagicMock()
        mock_trafilatura.settings.use_config.return_value = mock_config
        mock_trafilatura.fetch_url.return_value = "<html>ok</html>"
        mock_trafilatura.extract.return_value = "A" * 700
        mock_trafilatura.extract_metadata.return_value = None

        with mock.patch.dict("sys.modules", {"trafilatura": mock_trafilatura}):
            result = enrich_source(source, timeout=3, min_text_length=600)

        assert result.extraction_quality == "good"
        mock_config.set.assert_called_once_with("DEFAULT", "DOWNLOAD_TIMEOUT", "3")
        mock_trafilatura.fetch_url.assert_called_once_with("https://example.com/news", config=mock_config)


class TestEnrichSources:
    def test_enriches_multiple_sources(self):
        sources = [
            {"source_id": "a", "title": "No URL"},
            {"source_id": "b", "url": "", "title": "Empty URL"},
        ]
        results = enrich_sources(sources)
        assert len(results) == 2
        assert all(r.extraction_quality == "failed" for r in results)

    def test_empty_list(self):
        assert enrich_sources([]) == []


class TestIsEnrichmentEnabled:
    def test_default_disabled(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            assert is_enrichment_enabled() is False

    def test_enabled_with_1(self):
        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_ENRICHMENT": "1"}):
            assert is_enrichment_enabled() is True

    def test_enabled_with_true(self):
        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_ENRICHMENT": "true"}):
            assert is_enrichment_enabled() is True

    def test_disabled_with_0(self):
        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_ENRICHMENT": "0"}):
            assert is_enrichment_enabled() is False
