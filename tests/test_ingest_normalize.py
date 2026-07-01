import pytest

from src.config.loader import load_config_registry
from src.ingest.normalize import normalize_tradingview_item


def market():
    return load_config_registry().pipeline.markets[0]


def test_raw_item_normalizes_to_news_item():
    item = normalize_tradingview_item(
        {
            "id": "tv-1",
            "title": "USD/IDR moves after Fed comments",
            "summary": "Market summary.",
            "url": "https://example.com/a",
            "provider": "TradingView",
            "published": "2026-07-01T00:00:00Z",
        },
        market=market(),
    )

    assert item.title == "USD/IDR moves after Fed comments"
    assert item.source_id
    assert item.symbol == "USDIDR"
    assert item.exchange == "FX_IDC"
    assert item.language == "id"


def test_title_missing_raises_value_error():
    with pytest.raises(ValueError):
        normalize_tradingview_item({"id": "tv-1"}, market=market())


def test_source_id_is_stable():
    raw = {"id": "tv-1", "title": "Stable title", "url": "https://example.com/a"}

    first = normalize_tradingview_item(raw, market=market())
    second = normalize_tradingview_item(raw, market=market())

    assert first.source_id == second.source_id


def test_market_fields_come_from_config():
    item = normalize_tradingview_item({"title": "No explicit symbol"}, market=market())

    assert item.symbol == market().symbol
    assert item.exchange == market().exchange
    assert item.language == market().tradingview.language
