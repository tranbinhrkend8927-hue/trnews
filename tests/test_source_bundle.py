from src.config.loader import load_config_registry
from src.content.source_bundle import SourceBundleBuilder
from src.ingest.normalize import NormalizedNewsItem
from src.ingest.tradingview import SourceFetchResult


def market():
    return load_config_registry().pipeline.markets[0]


def item(source_id="src-1", title="Title", summary="Summary", content=None, url="https://example.com/a"):
    return NormalizedNewsItem(
        source_id=source_id,
        provider="TradingView",
        symbol="USDIDR",
        exchange="FX_IDC",
        language="id",
        title=title,
        summary=summary,
        content=content,
        url=url,
        canonical_url=url,
        fetched_at="2026-07-01T00:00:00Z",
        raw={"id": source_id},
    )


def fetch_result(items, success=True):
    return SourceFetchResult(success=success, market_id="usd_idr_id", symbol="USDIDR", language="id", items=items)


def test_successful_fetch_with_enough_sources_builds_bundle():
    bundle = SourceBundleBuilder().build(market(), fetch_result([item()]))

    assert bundle.errors == []
    assert bundle.sources[0].source_id == "src-1"


def test_sources_are_truncated_to_max_sources():
    sources = [item(source_id=f"src-{index}", url=f"https://example.com/{index}") for index in range(8)]

    bundle = SourceBundleBuilder().build(market(), fetch_result(sources))

    assert len(bundle.sources) == market().content.source_policy.max_sources


def test_not_enough_sources_error():
    bundle = SourceBundleBuilder().build(market(), fetch_result([]))

    assert any(error["type"] == "not_enough_sources" for error in bundle.errors)


def test_require_body_without_content_or_summary_errors():
    bundle = SourceBundleBuilder().build(market(), fetch_result([item(summary=None, content=None)]))

    assert any(error["type"] == "missing_source_content" for error in bundle.errors)


def test_bundle_id_is_stable():
    builder = SourceBundleBuilder()
    result = fetch_result([item()])

    assert builder.build(market(), result).bundle_id == builder.build(market(), result).bundle_id


def test_source_trace_contains_source_count():
    bundle = SourceBundleBuilder().build(market(), fetch_result([item()]))

    assert bundle.source_trace["source_count"] == 1
    assert bundle.source_trace["fetch_success"] is True
