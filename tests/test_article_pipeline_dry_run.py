from src.config.loader import load_config_registry
from src.content.article_pipeline import ArticlePipeline
from src.content.source_bundle import SourceBundleBuilder
from src.ingest.normalize import NormalizedNewsItem
from src.ingest.tradingview import SourceFetchResult
from src.notion.exporter import NotionDryRunExporter
from src.notion.target_resolver import ResolvedNotionTarget


def registry():
    return load_config_registry()


def news_item():
    return NormalizedNewsItem(
        source_id="src-1",
        provider="TradingView",
        symbol="USDIDR",
        exchange="FX_IDC",
        language="id",
        title="USD/IDR moves after Fed comments",
        summary="Market watches Fed comments.",
        content="Market watches Fed comments.",
        url="https://example.com/a",
        canonical_url="https://example.com/a",
        fetched_at="2026-07-01T00:00:00Z",
        raw={"news_id": "101"},
    )


class FakeAdapter:
    def __init__(self, items=None, success=True):
        self.items = [news_item()] if items is None else items
        self.success = success

    def fetch(self, market):
        return SourceFetchResult(
            success=self.success,
            market_id=market.id,
            symbol=market.symbol,
            language=market.content.language,
            items=self.items,
            errors=[] if self.success else [{"type": "fetch_failed"}],
        )


class FakeNotionExporter:
    def __init__(self, export_result=None):
        self.calls = []
        self.export_calls = []
        self.export_result = export_result or {
            "success": True,
            "dry_run": False,
            "page_id": "page-id",
            "url": "https://notion.so/page",
            "payload": {},
            "error": None,
        }

    def build_payload(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "dry_run": True,
            "payload": {
                "target": {"name": kwargs["target_name"]},
                "parent": {"data_source_id": None},
                "properties": {},
                "blocks": [],
                "warnings": [],
            },
        }

    def export(self, **kwargs):
        self.export_calls.append(kwargs)
        return self.export_result


def pipeline(adapter=None, notion_exporter=None):
    return ArticlePipeline(
        config_registry=registry(),
        tradingview_adapter=adapter or FakeAdapter(),
        source_bundle_builder=SourceBundleBuilder(),
        notion_exporter=notion_exporter,
    )


def test_dry_run_success_returns_status():
    result = pipeline().run_market("usd_idr_id", dry_run=True)

    assert result["success"] is True
    assert result["status"] == "DRY_RUN_SUCCESS"


def test_source_bundle_failure_returns_status():
    result = pipeline(FakeAdapter(items=[])).run_market("usd_idr_id", dry_run=True)

    assert result["success"] is False
    assert result["status"] == "SOURCE_BUNDLE_FAILED"


def test_fake_article_passes_validators():
    result = pipeline().run_market("usd_idr_id", dry_run=True)

    assert all(item["passed"] for item in result["validation"].values())


def test_dry_run_false_returns_not_implemented():
    result = pipeline().run_market("usd_idr_id", dry_run=False)

    assert result["success"] is False
    assert result["status"] == "NOTION_EXPORTER_MISSING"


def test_result_contains_core_structured_fields():
    result = pipeline().run_market("usd_idr_id", dry_run=True)

    assert result["market_id"] == "usd_idr_id"
    assert result["symbol"] == "USDIDR"
    assert result["language"] == "id"
    assert "source_bundle" in result
    assert "validation" in result


def test_result_contains_pipeline_run_id():
    result = pipeline().run_market("usd_idr_id", dry_run=True)

    assert result["pipeline_run_id"].startswith("run-usd_idr_id-USDIDR-id-")


def test_result_contains_source_bundle_hash():
    result = pipeline().run_market("usd_idr_id", dry_run=True)

    assert result["source_bundle_hash"]
    assert result["source_bundle"]["source_bundle_hash"] == result["source_bundle_hash"]


def test_result_contains_content_job_key():
    result = pipeline().run_market("usd_idr_id", dry_run=True)

    assert result["content_job_key"].startswith("usd_idr_id:USDIDR:id:article_draft:")


def test_notion_preview_uses_same_pipeline_run_id():
    exporter = FakeNotionExporter()
    result = pipeline(notion_exporter=exporter).run_market("usd_idr_id", dry_run=True)

    assert exporter.calls[0]["pipeline_run_id"] == result["pipeline_run_id"]


def test_exporter_receives_content_job_key_and_source_hash():
    exporter = FakeNotionExporter()
    result = pipeline(notion_exporter=exporter).run_market("usd_idr_id", dry_run=False)

    assert exporter.export_calls[0]["content_job_key"] == result["content_job_key"]
    assert exporter.export_calls[0]["source_bundle_hash"] == result["source_bundle_hash"]
    assert exporter.export_calls[0]["pipeline_run_id"] == result["pipeline_run_id"]


class FakeResolver:
    def resolve(self, target_name):
        return ResolvedNotionTarget(name=target_name, language="id", market="Indonesia", parent_type="data_source", parent_id=None)


def test_dry_run_preview_properties_include_idempotency_fields():
    result = pipeline(notion_exporter=NotionDryRunExporter(FakeResolver())).run_market("usd_idr_id", dry_run=True)
    properties = result["notion_preview"]["payload"]["properties"]

    assert properties["Content Job Key"]["rich_text"][0]["text"]["content"] == result["content_job_key"]
    assert properties["Source Bundle Hash"]["rich_text"][0]["text"]["content"] == result["source_bundle_hash"]
    assert properties["Pipeline Run ID"]["rich_text"][0]["text"]["content"] == result["pipeline_run_id"]


def test_with_notion_exporter_dry_run_contains_preview():
    result = pipeline(notion_exporter=FakeNotionExporter()).run_market("usd_idr_id", dry_run=True)

    assert result["success"] is True
    assert "notion_preview" in result


def test_without_notion_exporter_keeps_old_behavior():
    result = pipeline().run_market("usd_idr_id", dry_run=True)

    assert "notion_preview" not in result


def test_dry_run_false_with_notion_preview_still_not_implemented():
    result = pipeline(notion_exporter=FakeNotionExporter()).run_market("usd_idr_id", dry_run=False)

    assert result["status"] == "NOTION_EXPORTED"
    assert "notion" in result


def test_validation_failed_does_not_build_notion_preview():
    exporter = FakeNotionExporter()
    result = pipeline(FakeAdapter(items=[]), notion_exporter=exporter).run_market("usd_idr_id", dry_run=True)

    assert result["status"] == "SOURCE_BUNDLE_FAILED"
    assert "notion_preview" not in result
    assert exporter.calls == []


def test_dry_run_true_does_not_call_real_exporter():
    exporter = FakeNotionExporter()
    result = pipeline(notion_exporter=exporter).run_market("usd_idr_id", dry_run=True)

    assert result["status"] == "DRY_RUN_SUCCESS"
    assert exporter.calls
    assert exporter.export_calls == []


def test_dry_run_false_without_exporter_returns_missing():
    result = pipeline().run_market("usd_idr_id", dry_run=False)

    assert result["success"] is False
    assert result["status"] == "NOTION_EXPORTER_MISSING"


def test_dry_run_false_exporter_success_returns_exported():
    result = pipeline(notion_exporter=FakeNotionExporter()).run_market("usd_idr_id", dry_run=False)

    assert result["success"] is True
    assert result["status"] == "NOTION_EXPORTED"


def test_dry_run_false_exporter_failure_returns_failed():
    exporter = FakeNotionExporter(export_result={"success": False, "dry_run": False, "error": {"type": "notion_api_error"}})

    result = pipeline(notion_exporter=exporter).run_market("usd_idr_id", dry_run=False)

    assert result["success"] is False
    assert result["status"] == "NOTION_EXPORT_FAILED"
