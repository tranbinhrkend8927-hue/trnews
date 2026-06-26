from unittest import mock

from tradingview_scraper.symbols.fundamental_graphs import FundamentalGraphs
from tradingview_scraper.symbols.minds import Minds
from tradingview_scraper.symbols.news import NewsScraper


def test_news_scrape_news_contents_preserves_order_and_collects_errors():
    scraper = NewsScraper(export_result=False)

    def fake_scrape(self, path):
        if path == "/bad/":
            raise RuntimeError("boom")
        return {"title": path}

    with mock.patch.object(NewsScraper, "scrape_news_content", fake_scrape):
        result = scraper.scrape_news_contents(["/one/", "/bad/", "/two/"], max_workers=2)

    assert result["results"] == [{"title": "/one/"}, {"title": "/two/"}]
    assert result["errors"] == [{"story_path": "/bad/", "error": "boom"}]


def test_news_scrape_news_contents_does_not_share_parent_http_client():
    scraper = NewsScraper(export_result=False)
    parent_client = scraper.http_client
    seen_clients = []

    def fake_scrape(self, path):
        seen_clients.append(self.http_client)
        return {"title": path}

    with mock.patch.object(NewsScraper, "scrape_news_content", fake_scrape):
        result = scraper.scrape_news_contents(["/one/", "/two/"], max_workers=2)

    assert result["errors"] == []
    assert all(client is not parent_client for client in seen_clients)
    assert len({id(client) for client in seen_clients}) == 2


def test_compare_fundamentals_keeps_input_order_with_workers():
    fundamentals = FundamentalGraphs(export_result=False)

    def fake_get(symbol, fields=None):
        return {"status": "success", "data": {"symbol": symbol, "total_revenue": len(symbol)}}

    fundamentals.get_fundamentals = fake_get

    result = fundamentals.compare_fundamentals(
        ["NASDAQ:AAPL", "NASDAQ:MSFT", "NASDAQ:GOOGL"],
        fields=["total_revenue"],
        max_workers=3,
    )

    assert [item["symbol"] for item in result["data"]] == ["NASDAQ:AAPL", "NASDAQ:MSFT", "NASDAQ:GOOGL"]
    assert result["comparison"]["total_revenue"] == {
        "NASDAQ:AAPL": len("NASDAQ:AAPL"),
        "NASDAQ:MSFT": len("NASDAQ:MSFT"),
        "NASDAQ:GOOGL": len("NASDAQ:GOOGL"),
    }


def test_iter_minds_pages_yields_pages_lazily(monkeypatch):
    minds = Minds(export_result=False)

    first = mock.Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = {
        "results": [
            {
                "uid": "one",
                "text": "first page",
                "author": {"username": "u1"},
                "symbols": {"AAPL": "NASDAQ:AAPL"},
            }
        ],
        "next": "/api/v1/minds/?c=cursor-2&symbol=NASDAQ:AAPL",
        "meta": {"symbols_info": {"NASDAQ:AAPL": {"short_name": "AAPL"}}},
    }
    second = mock.Mock()
    second.raise_for_status.return_value = None
    second.json.return_value = {
        "results": [
            {
                "uid": "two",
                "text": "second page",
                "author": {"username": "u2"},
                "symbols": {"AAPL": "NASDAQ:AAPL"},
            }
        ],
        "next": "",
        "meta": {"symbols_info": {"NASDAQ:AAPL": {"short_name": "AAPL"}}},
    }
    get = mock.Mock(side_effect=[first, second])
    monkeypatch.setattr("tradingview_scraper.symbols.minds.requests.get", get)

    pages = minds.iter_minds_pages("NASDAQ:AAPL", page_size=1)

    assert next(pages)["data"][0]["uid"] == "one"
    assert get.call_count == 1
    assert next(pages)["data"][0]["uid"] == "two"
    assert get.call_count == 2
