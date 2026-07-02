"""Tests for source quality gate integration in ArticlePipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest import mock

import pytest

from src.content.article_pipeline import ArticlePipeline
from src.content.source_bundle import SourceBundle, SourceBundleBuilder
from src.llm.result import LLMTaskResult
from src.ingest.normalize import NormalizedNewsItem
from src.ingest.tradingview import SourceFetchResult


def _make_market(market_id="test_market"):
    """Minimal market config stub for pipeline tests."""

    @dataclass
    class _SourcePolicy:
        min_sources: int = 1
        max_sources: int = 5
        require_body: bool = False
        allow_paywalled_summary: bool = True
        max_source_age_hours: int | None = 72

    @dataclass
    class _Content:
        language: str = "id"
        market: str = "forex_idr"
        task: str = "article_draft"
        article_type: str = "fx_news_explainer"
        topic_strategy: str = "latest_forex_news"
        source_policy: _SourcePolicy = field(default_factory=_SourcePolicy)

    @dataclass
    class _TradingView:
        language: str = "id"
        url: str = "https://id.tradingview.com/symbols/USDIDR/news/"
        locale: str = "id"
        sort: str = "latest"
        section: str = "all"
        provider: str | None = None
        area: str | None = None
        max_headlines: int = 10
        max_articles: int = 3

    @dataclass
    class _LLM:
        draft_profile: str = "article_writer_id"
        review_profile: str | None = None
        grounding_profile: str | None = None

    @dataclass
    class _Notion:
        target: str = "notion_articles_id"

    @dataclass
    class _Market:
        id: str = "test_market"
        symbol: str = "USDIDR"
        exchange: str = "FX_IDC"
        base_currency: str = "USD"
        quote_currency: str = "IDR"
        tradingview: _TradingView = field(default_factory=_TradingView)
        content: _Content = field(default_factory=_Content)
        llm: _LLM = field(default_factory=_LLM)
        notion: _Notion = field(default_factory=_Notion)
        enabled: bool = True

    return _Market(id=market_id)


def _make_news_item(source_id="src1", title="Test Headline", content="Short content"):
    return NormalizedNewsItem(
        source_id=source_id,
        symbol="USDIDR",
        exchange="FX_IDC",
        language="id",
        title=title,
        content=content,
        url=f"https://example.com/{source_id}",
        fetched_at="2026-07-01T00:00:00Z",
        raw={"news_id": source_id},
    )


def _make_config_registry(market):
    @dataclass
    class _Pipeline:
        version: int = 1
        defaults: dict = field(default_factory=dict)
        markets: list = field(default_factory=list)

    @dataclass
    class _Registry:
        root: str = "/tmp"
        pipeline: _Pipeline = field(default_factory=_Pipeline)
        llm_profiles: object = None
        notion_targets: object = None
        languages: dict = field(default_factory=dict)

    pipeline = _Pipeline(markets=[market])
    return _Registry(pipeline=pipeline)


class _FakeAdapter:
    def __init__(self, items=None, success=True):
        self._items = items or []
        self._success = success

    def fetch(self, market):
        return SourceFetchResult(
            success=self._success,
            market_id=market.id,
            symbol=market.symbol,
            language=market.content.language,
            items=self._items,
            warnings=[],
            errors=[] if self._success else [{"type": "fetch_failed"}],
        )


class _FakeLLMRunner:
    def __init__(self, output=None):
        self.calls = []
        self.output = output or _valid_article()

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return LLMTaskResult(
            success=True,
            task="article_draft",
            language="id",
            profile="article_writer_id",
            model="unit-model",
            prompt_version="unit",
            output=self.output,
        )


class _TaskAwareLLMRunner:
    def __init__(self):
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["task"] == "article_review":
            return LLMTaskResult(
                success=True,
                task="article_review",
                language="id",
                profile=kwargs.get("profile"),
                output={
                    "publish_readiness": "needs_edit",
                    "scores": {
                        "grounding": 70,
                        "depth": 70,
                        "readability": 80,
                        "headline_quality": 80,
                        "financial_safety": 90,
                        "source_usefulness": 75,
                    },
                    "issues": [],
                    "unsupported_claims": [],
                    "overstatements": [],
                    "missing_context": [],
                    "rewrite_suggestions": [],
                    "recommended_editor_action": "Send to editor.",
                },
            )
        return LLMTaskResult(
            success=True,
            task="article_draft",
            language="id",
            profile=kwargs.get("profile"),
            output=_valid_article(),
        )


class _FakeNotionExporter:
    def __init__(self):
        self.calls = []

    def build_payload(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "dry_run": True, "payload": {"properties": {}, "blocks": []}}


def _valid_article(article_type="fx_news_explainer"):
    risk_disclaimer = "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan."
    return {
        "title": "USD/IDR bergerak setelah berita terbaru",
        "slug": "usd-idr-berita-terbaru",
        "summary": "Ringkasan edukatif tentang USD/IDR berdasarkan sumber yang tersedia.",
        "body": "\n\n".join(
            [
                "Ikhtisar peristiwa\nUSD/IDR bergerak setelah berita terbaru yang tersedia dalam sumber.",
                "Latar belakang\nPergerakan pasangan mata uang perlu dibaca bersama data ekonomi dan sentimen risiko.",
                "Dampak pasar\nSumber yang tersedia membantu pembaca memahami konteks, tanpa menyimpulkan arah harga secara pasti.",
                "Hal yang perlu dipantau\nPantau data ekonomi lanjutan dan komunikasi bank sentral.",
                "Sumber\nTest Headline\nhttps://example.com/s1",
                f"Catatan risiko\n{risk_disclaimer}",
            ]
        ),
        "seo_title": "USD/IDR bergerak setelah berita terbaru",
        "seo_description": "Ringkasan edukatif USD/IDR berdasarkan sumber berita yang tersedia.",
        "language": "id",
        "market": "forex_idr",
        "symbol": "USDIDR",
        "article_type": article_type,
        "risk_disclaimer": risk_disclaimer,
        "region": "id",
        "search_intent": "Memahami berita terbaru USD/IDR dan konteksnya.",
        "primary_keyword": "USDIDR berita forex",
        "secondary_keywords": ["USDIDR", "forex"],
        "candidate_titles": ["USD/IDR bergerak setelah berita terbaru"],
        "editorial_angle": "Menjelaskan konteks berita tanpa rekomendasi transaksi.",
        "key_takeaways": ["Berita perlu dibaca bersama konteks ekonomi."],
        "evergreen_context": "USD/IDR dipengaruhi data ekonomi dan sentimen risiko.",
        "editor_notes": [],
        "faq": [{"question": "Apa yang perlu dipantau?", "answer": "Pantau data ekonomi lanjutan dan komunikasi bank sentral."}],
        "sources_used": [{"source_id": "s1", "title": "Test Headline", "url": "https://example.com/s1", "provider": "TradingView"}],
        "uncertain_claims": [],
    }


class TestSourceQualityGateIntegration:
    def test_quality_gate_blocks_insufficient_sources(self):
        """Pipeline returns SOURCE_QUALITY_INSUFFICIENT when sources have no usable content."""
        market = _make_market()
        items = [_make_news_item("s1", content="tiny"), _make_news_item("s2", content="also tiny")]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)

        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
        )

        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "SOURCE_QUALITY_INSUFFICIENT"
        assert result["success"] is False
        assert "source_quality_report" in result
        assert result["source_quality_report"]["recommended_action"] == "skip_or_manual_review"

    def test_quality_gate_passes_with_rich_content(self):
        """Pipeline proceeds normally when sources have enough content."""
        market = _make_market()
        items = [
            _make_news_item("s1", content="A" * 700),
            _make_news_item("s2", content="B" * 800),
        ]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)

        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
        )

        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["success"] is True
        assert result["source_bundle"]["source_quality_report"]["recommended_action"] == "write_article"

    def test_quality_gate_disabled_skips_check(self):
        """Pipeline proceeds even with thin sources when gate is disabled."""
        market = _make_market()
        items = [_make_news_item("s1", content="tiny")]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)

        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
        )

        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_QUALITY_GATE": "0", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        # Should not be blocked by quality gate
        assert result["status"] != "SOURCE_QUALITY_INSUFFICIENT"

    def test_enrichment_disabled_by_default(self):
        """Enrichment does not run when ENABLE_SOURCE_ENRICHMENT is not set."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)

        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
        )

        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_ENRICHMENT": "0", "ENABLE_SOURCE_QUALITY_GATE": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        bundle = result.get("source_bundle", {})
        assert bundle.get("enriched_sources") == []

    def test_source_quality_report_in_result(self):
        """Source quality report is always present in the pipeline result."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)

        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
        )

        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_QUALITY_GATE": "0", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        report = result["source_bundle"]["source_quality_report"]
        assert "overall_source_quality" in report
        assert "recommended_action" in report
        assert "usable_source_count" in report

    def test_quality_report_reflects_in_observability(self):
        """Quality summary includes source quality fields."""
        from src.observability.quality import summarize_article_quality

        article = {"body": "test", "sources_used": []}
        source_bundle = {
            "sources": [{"source_id": "s1"}],
            "source_trace": {"source_count": 1},
            "source_quality_report": {
                "overall_source_quality": "strong",
                "usable_source_count": 1,
                "recommended_action": "write_article",
            },
        }
        summary = summarize_article_quality(article, source_bundle, {})
        assert summary["source_quality"] == "strong"
        assert summary["usable_source_count"] == 1
        assert summary["source_quality_action"] == "write_article"

    def test_llm_uses_enriched_text_when_available(self):
        """Enriched full text is passed to the writer instead of short TradingView content."""
        market = _make_market()
        items = [_make_news_item("s1", content="tiny")]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        long_text = "Extracted full article text " + ("A" * 900)
        enrichment = [
            {
                "source_id": "s1",
                "original_url": "https://example.com/s1",
                "extracted_title": "Extracted Title",
                "extracted_text": long_text,
                "text_length": len(long_text),
                "extraction_quality": "good",
                "usable_for_deep_article": True,
            }
        ]

        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_ENRICHMENT": "1", "ENABLE_SOURCE_QUALITY_GATE": "1"}):
            with mock.patch("src.content.article_pipeline.enrich_sources", return_value=enrichment):
                result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        llm_source = runner.calls[0]["input_data"]["source_bundle"]["sources"][0]
        assert llm_source["content_source"] == "enriched_text"
        assert "Extracted full article text" in llm_source["content"]
        assert llm_source["title"] == "Extracted Title"
        assert "content_source: enriched_text" in runner.calls[0]["input_data"]["article_brief"]

    def test_weak_source_quality_downgrades_to_market_brief(self):
        """Weak sources should not be presented to the writer as a deep article."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 400), _make_news_item("s2", content="tiny")]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner(output=_valid_article(article_type="market_brief"))
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["source_bundle"]["recommended_action"] == "write_brief_only"
        assert result["source_bundle"]["content_type_override"] == "market_brief"
        brief = runner.calls[0]["input_data"]["article_brief"]
        assert "Write a concise FX market brief" in brief
        assert "Do not present it as a deep article" in brief
        assert "article_type: market_brief" in brief

    def test_structured_brief_disabled_by_default(self):
        """Structured brief remains opt-in while Phase 2 is rolled out."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_STRUCTURED_BRIEF": "0", "ENABLE_SOURCE_QUALITY_GATE": "0", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert "editorial_brief" not in result
        assert runner.calls[0]["input_data"]["editorial_brief"] is None

    def test_structured_brief_enabled_adds_brief_to_result_and_llm_input(self):
        """Structured EditorialBrief is generated and passed alongside the legacy string prompt."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_STRUCTURED_BRIEF": "1", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["editorial_brief"]["content_type"] == "deep_article"
        assert result["brief_validation"]["recommended_status"] == "ready"
        llm_input = runner.calls[0]["input_data"]
        assert llm_input["editorial_brief"]["primary_angle"]
        assert llm_input["brief_validation"]["passed"] is True
        assert "event_summary:" in llm_input["article_brief"]

    def test_structured_brief_enabled_uses_market_brief_for_weak_sources(self):
        """Weak source quality produces a structured market_brief when the gate is enabled."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 400), _make_news_item("s2", content="tiny")]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner(output=_valid_article(article_type="market_brief"))
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_STRUCTURED_BRIEF": "1", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["editorial_brief"]["content_type"] == "market_brief"
        assert result["brief_validation"]["recommended_status"] == "write_brief_only"
        assert runner.calls[0]["input_data"]["editorial_brief"]["confidence_level"] == "low"

    def test_structured_brief_reaches_notion_preview_payload(self):
        """Dry-run Notion payload receives structured brief metadata via source_bundle."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        exporter = _FakeNotionExporter()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
            notion_exporter=exporter,
        )

        with mock.patch.dict("os.environ", {"ENABLE_STRUCTURED_BRIEF": "1", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        notion_source_bundle = exporter.calls[0]["source_bundle"]
        assert notion_source_bundle["editorial_brief"]["content_type"] == "deep_article"
        assert notion_source_bundle["brief_validation"]["passed"] is True

    def test_ai_reviewer_disabled_by_default(self):
        """AI review is opt-in while Phase 3 is rolled out."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_AI_REVIEWER": "0", "ENABLE_SOURCE_QUALITY_GATE": "0", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert "ai_review" not in result

    def test_ai_reviewer_enabled_adds_review_to_result(self):
        """AI reviewer produces structured review after validators pass."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_AI_REVIEWER": "1", "ENABLE_STRUCTURED_BRIEF": "1", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["ai_review"]["publish_readiness"] in ("ready", "needs_edit", "reject")
        assert "grounding" in result["ai_review"]["scores"]
        assert result["source_bundle"]["ai_review"]["reviewer_mode"] == "deterministic"

    def test_ai_review_reaches_notion_preview_payload(self):
        """Notion payload receives AI review metadata via source_bundle."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        exporter = _FakeNotionExporter()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
            notion_exporter=exporter,
        )

        with mock.patch.dict("os.environ", {"ENABLE_AI_REVIEWER": "1", "ENABLE_STRUCTURED_BRIEF": "1", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        notion_source_bundle = exporter.calls[0]["source_bundle"]
        assert notion_source_bundle["ai_review"]["reviewer_mode"] == "deterministic"

    def test_ai_reviewer_does_not_call_llm_when_llm_review_disabled(self):
        """ENABLE_AI_REVIEWER alone keeps deterministic review and does not call review_profile."""
        market = _make_market()
        market.llm.review_profile = "article_reviewer_id"
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _TaskAwareLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_AI_REVIEWER": "1", "ENABLE_LLM_AI_REVIEWER": "0", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["ai_review"]["reviewer_mode"] == "deterministic"
        assert [call["task"] for call in runner.calls] == ["article_draft"]

    def test_llm_ai_reviewer_calls_review_profile_when_enabled(self):
        """LLM reviewer is opt-in and uses the configured review_profile."""
        market = _make_market()
        market.llm.review_profile = "article_reviewer_id"
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _TaskAwareLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_AI_REVIEWER": "1", "ENABLE_LLM_AI_REVIEWER": "1", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["ai_review"]["reviewer_mode"] == "llm"
        assert [call["task"] for call in runner.calls] == ["article_draft", "article_review"]
        assert runner.calls[1]["profile"] == "article_reviewer_id"

    def test_quality_report_disabled_by_default(self):
        """ArticleQualityReport remains opt-in during Phase 4 rollout."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_QUALITY_REPORT": "0", "ENABLE_SOURCE_QUALITY_GATE": "0", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert "article_quality_report" not in result

    def test_quality_report_enabled_adds_report_to_result(self):
        """ArticleQualityReport aggregates article, source, validation, and AI review signals."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
        )

        with mock.patch.dict("os.environ", {"ENABLE_QUALITY_REPORT": "1", "ENABLE_AI_REVIEWER": "1", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["article_quality_report"]["final_recommended_status"] in ("needs_review", "needs_edit", "needs_rewrite", "rejected")
        assert "editor_ready_score" in result["article_quality_report"]
        assert result["source_bundle"]["article_quality_report"]["source_count"] == 2

    def test_quality_report_reaches_notion_preview_payload(self):
        """Notion payload receives ArticleQualityReport metadata via source_bundle."""
        market = _make_market()
        items = [_make_news_item("s1", content="A" * 700), _make_news_item("s2", content="B" * 700)]
        adapter = _FakeAdapter(items=items)
        registry = _make_config_registry(market)
        runner = _FakeLLMRunner()
        exporter = _FakeNotionExporter()
        pipeline = ArticlePipeline(
            config_registry=registry,
            tradingview_adapter=adapter,
            source_bundle_builder=SourceBundleBuilder(),
            llm_runner=runner,
            notion_exporter=exporter,
        )

        with mock.patch.dict("os.environ", {"ENABLE_QUALITY_REPORT": "1", "ENABLE_SOURCE_QUALITY_GATE": "1", "ENABLE_SOURCE_ENRICHMENT": "0"}):
            result = pipeline.run_market("test_market", dry_run=True)

        assert result["status"] == "DRY_RUN_SUCCESS"
        notion_source_bundle = exporter.calls[0]["source_bundle"]
        assert "article_quality_report" in notion_source_bundle
        assert "editor_ready_score" in notion_source_bundle["article_quality_report"]
