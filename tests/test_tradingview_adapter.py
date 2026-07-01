from src.config.loader import load_config_registry
from src.ingest.tradingview import TradingViewNewsAdapter


def market():
    return load_config_registry().pipeline.markets[0]


class FakeScraper:
    def __init__(self, items=None, exc=None):
        self.items = items or []
        self.exc = exc
        self.calls = []

    def fetch_news(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.items


class FakeHeadlineScraper:
    def scrape_headlines(self, **kwargs):
        return [{"id": "1", "title": "Headline", "storyPath": "/news/test:1/"}]

    def scrape_news_contents(self, story_paths):
        return {
            "results": [
                {
                    "title": "Headline",
                    "body": [{"type": "text", "content": "Full article body."}],
                    "published_datetime": "2026-07-01T00:00:00Z",
                }
            ],
            "errors": [],
        }


def test_fetch_success_returns_source_fetch_result():
    adapter = TradingViewNewsAdapter(
        scraper=FakeScraper(items=[{"id": "1", "title": "USD/IDR headline", "summary": "Summary"}])
    )

    result = adapter.fetch(market())

    assert result.success is True
    assert result.market_id == "usd_idr_id"
    assert result.symbol == "USDIDR"
    assert result.language == "id"


def test_adapter_normalizes_items():
    result = TradingViewNewsAdapter(
        scraper=FakeScraper(items=[{"id": "1", "title": "USD/IDR headline", "summary": "Summary"}])
    ).fetch(market())

    assert result.items[0].source_id
    assert result.items[0].symbol == "USDIDR"


def test_adapter_enriches_headlines_with_article_body():
    result = TradingViewNewsAdapter(scraper=FakeHeadlineScraper()).fetch(market())

    assert result.success is True
    assert result.items[0].content == "Full article body."
    assert result.items[0].published_at == "2026-07-01T00:00:00Z"


def test_adapter_dedupes_items():
    result = TradingViewNewsAdapter(
        scraper=FakeScraper(
            items=[
                {"id": "1", "title": "First", "url": "https://example.com/a", "summary": "A"},
                {"id": "2", "title": "Duplicate", "url": "https://example.com/a", "summary": "B"},
            ]
        )
    ).fetch(market())

    assert len(result.items) == 1


def test_single_item_normalization_failure_becomes_warning():
    result = TradingViewNewsAdapter(
        scraper=FakeScraper(items=[{"id": "bad"}, {"id": "ok", "title": "Good", "summary": "Summary"}])
    ).fetch(market())

    assert result.success is True
    assert len(result.items) == 1
    assert result.warnings[0]["type"] == "normalize_failed"


def test_scraper_exception_returns_failure():
    result = TradingViewNewsAdapter(scraper=FakeScraper(exc=RuntimeError("network blocked"))).fetch(market())

    assert result.success is False
    assert result.errors[0]["type"] == "tradingview_fetch_failed"
