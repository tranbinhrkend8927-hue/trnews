from src.content.article_pipeline import ArticlePipeline
from src.content.source_bundle import SourceBundleBuilder
from src.llm.result import LLMTaskError, LLMTaskResult
from tests.test_article_pipeline_dry_run import FakeAdapter, news_item, registry
from tests.test_article_schema import valid_article


RISK_DISCLAIMER = "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan."


class FakeLLMRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class FakeNotionExporter:
    def __init__(self, export_result=None):
        self.calls = []
        self.export_calls = []
        self.export_result = export_result or {"success": True, "dry_run": False, "page_id": "page-id", "url": "url"}

    def build_payload(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "dry_run": True,
            "payload": {"target": {}, "parent": {}, "properties": {}, "blocks": [], "warnings": []},
        }

    def export(self, **kwargs):
        self.export_calls.append(kwargs)
        return self.export_result


def pipeline_with_runner(result, notion_exporter=None):
    return ArticlePipeline(
        config_registry=registry(),
        tradingview_adapter=FakeAdapter(),
        source_bundle_builder=SourceBundleBuilder(),
        llm_runner=FakeLLMRunner(result),
        notion_exporter=notion_exporter,
    )


def success_result(output=None):
    article = valid_article(risk_disclaimer=RISK_DISCLAIMER)
    article["body"] = article["body"].replace("Artikel ini hanya untuk informasi dan edukasi.", RISK_DISCLAIMER)
    return LLMTaskResult(
        success=True,
        task="article_draft",
        language="id",
        profile="article_writer_id",
        model="unit-model",
        prompt_version="unit",
        output=output or article,
    )


def test_llm_runner_success_returns_dry_run_success():
    result = pipeline_with_runner(success_result()).run_market("usd_idr_id", dry_run=True)

    assert result["success"] is True
    assert result["status"] == "DRY_RUN_SUCCESS"


def test_result_contains_llm():
    result = pipeline_with_runner(success_result()).run_market("usd_idr_id", dry_run=True)

    assert "llm" in result
    assert result["llm"]["success"] is True


def test_llm_runner_failure_returns_llm_failed():
    llm_failure = LLMTaskResult(
        success=False,
        task="article_draft",
        language="id",
        profile="article_writer_id",
        error=LLMTaskError(type="llm_config_error", message="missing key"),
    )

    result = pipeline_with_runner(llm_failure).run_market("usd_idr_id", dry_run=True)

    assert result["success"] is False
    assert result["status"] == "LLM_FAILED"
    assert result["llm"]["error"]["type"] == "llm_config_error"


def test_invalid_llm_output_returns_validation_failed():
    result = pipeline_with_runner(success_result(output={"title": "Missing fields"})).run_market("usd_idr_id", dry_run=True)

    assert result["success"] is False
    assert result["status"] == "VALIDATION_FAILED"


def test_numeric_source_id_from_llm_is_normalized_before_validation():
    article = valid_article(risk_disclaimer=RISK_DISCLAIMER)
    article["body"] = article["body"].replace("Artikel ini hanya untuk informasi dan edukasi.", RISK_DISCLAIMER)
    article["sources_used"][0]["source_id"] = 101
    article["sources_used"][0]["news_id"] = "101"

    item = news_item()
    item.source_id = "101"
    item.raw = {"news_id": "101"}
    result = ArticlePipeline(
        config_registry=registry(),
        tradingview_adapter=FakeAdapter(items=[item]),
        source_bundle_builder=SourceBundleBuilder(),
        llm_runner=FakeLLMRunner(success_result(output=article)),
    ).run_market("usd_idr_id", dry_run=True)

    assert result["success"] is True
    assert result["article"]["sources_used"][0]["source_id"] == "101"


def test_dry_run_false_still_notion_not_implemented():
    result = pipeline_with_runner(success_result()).run_market("usd_idr_id", dry_run=False)

    assert result["success"] is False
    assert result["status"] == "NOTION_EXPORTER_MISSING"


def test_with_notion_exporter_includes_preview():
    result = pipeline_with_runner(success_result(), notion_exporter=FakeNotionExporter()).run_market("usd_idr_id", dry_run=True)

    assert result["status"] == "DRY_RUN_SUCCESS"
    assert "notion_preview" in result


def test_validation_failed_does_not_build_notion_preview():
    exporter = FakeNotionExporter()
    result = pipeline_with_runner(success_result(output={"title": "Missing fields"}), notion_exporter=exporter).run_market("usd_idr_id", dry_run=True)

    assert result["status"] == "VALIDATION_FAILED"
    assert "notion_preview" not in result
    assert exporter.calls == []


def test_dry_run_false_exporter_success_returns_exported():
    result = pipeline_with_runner(success_result(), notion_exporter=FakeNotionExporter()).run_market("usd_idr_id", dry_run=False)

    assert result["success"] is True
    assert result["status"] == "NOTION_EXPORTED"


def test_dry_run_false_exporter_failure_returns_failed():
    exporter = FakeNotionExporter(export_result={"success": False, "dry_run": False, "error": {"type": "notion_api_error"}})

    result = pipeline_with_runner(success_result(), notion_exporter=exporter).run_market("usd_idr_id", dry_run=False)

    assert result["success"] is False
    assert result["status"] == "NOTION_EXPORT_FAILED"


def test_llm_failed_does_not_call_exporter():
    exporter = FakeNotionExporter()
    llm_failure = LLMTaskResult(success=False, task="article_draft", error=LLMTaskError(type="llm_failed", message="bad"))

    result = pipeline_with_runner(llm_failure, notion_exporter=exporter).run_market("usd_idr_id", dry_run=False)

    assert result["status"] == "LLM_FAILED"
    assert exporter.export_calls == []


def test_exporter_receives_idempotency_metadata_with_llm_runner():
    exporter = FakeNotionExporter()
    result = pipeline_with_runner(success_result(), notion_exporter=exporter).run_market("usd_idr_id", dry_run=False)

    assert exporter.export_calls[0]["content_job_key"] == result["content_job_key"]
    assert exporter.export_calls[0]["source_bundle_hash"] == result["source_bundle_hash"]
    assert exporter.export_calls[0]["pipeline_run_id"] == result["pipeline_run_id"]


def test_llm_runner_receives_compact_source_bundle_without_raw_payload():
    item = news_item()
    item.content = "x" * 2000
    item.raw = {"news_id": "101", "article": {"body": [{"content": "large raw payload"}]}}
    runner = FakeLLMRunner(success_result())
    pipeline = ArticlePipeline(
        config_registry=registry(),
        tradingview_adapter=FakeAdapter(items=[item]),
        source_bundle_builder=SourceBundleBuilder(),
        llm_runner=runner,
    )

    result = pipeline.run_market("usd_idr_id", dry_run=True)

    assert result["success"] is True
    assert result["source_bundle"]["sources"][0]["raw"]["article"]["body"][0]["content"] == "large raw payload"
    llm_source = runner.calls[0]["input_data"]["source_bundle"]["sources"][0]
    assert "raw" not in llm_source
    assert llm_source["news_id"] == "101"
    assert len(llm_source["content"]) < 1500
    assert llm_source["content"].endswith("[truncated]")
    article_brief = runner.calls[0]["input_data"]["article_brief"]
    assert "deep, readable FX news explainer" in article_brief
    assert "EDITORIAL_BRIEF" in article_brief
    assert "REQUIRED_BODY_SECTIONS" in article_brief
    assert "SOURCE 1" in article_brief
    assert "source_id: src-1" in article_brief
    assert "title: USD/IDR moves after Fed comments" in article_brief
    assert "content:" in article_brief
    assert "large raw payload" not in article_brief


def test_llm_runner_receives_configured_profile_overrides(monkeypatch):
    monkeypatch.setattr("src.content.article_pipeline._local_env", lambda: {})
    monkeypatch.delenv("LLM_WRITER_MODEL", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    runner = FakeLLMRunner(success_result())
    pipeline = ArticlePipeline(
        config_registry=registry(),
        tradingview_adapter=FakeAdapter(),
        source_bundle_builder=SourceBundleBuilder(),
        llm_runner=runner,
    )

    result = pipeline.run_market("usd_idr_id", dry_run=True)

    assert result["success"] is True
    assert runner.calls[0]["profile"] == "article_writer_id"
    assert runner.calls[0]["overrides"]["model"] == "openrouter/auto"
    assert runner.calls[0]["overrides"]["temperature"] == 0.35
    assert runner.calls[0]["overrides"]["max_tokens"] == 2200
