from unittest import mock

from tradingview_scraper.symbols.news import NewsScraper


def _response(json_data=None, text=""):
    response = mock.Mock()
    response.json.return_value = json_data or {}
    response.text = text
    response.raise_for_status.return_value = None
    response.status_code = 200
    return response


class TestNews:
    def test_scrape_headlines_by_symbol(self):
        news_scraper = NewsScraper(export_result=False)
        payload = {
            "items": [
                {"id": "2", "title": "Second", "published": 20, "urgency": 1},
                {"id": "1", "title": "First", "published": 10, "urgency": 2},
            ]
        }

        with mock.patch("tradingview_scraper.symbols.news.TradingViewHttpClient.get", return_value=_response(payload)) as mock_get:
            headlines = news_scraper.scrape_headlines(symbol="BTCUSD", exchange="BINANCE", sort="latest")

        assert [item["id"] for item in headlines] == ["2", "1"]
        mock_get.assert_called_once()

    def test_scrape_headlines_with_provider(self):
        news_scraper = NewsScraper(export_result=False)
        payload = {"items": [{"id": "1", "title": "Provider item", "published": 1, "urgency": 1}]}

        with mock.patch("tradingview_scraper.symbols.news.TradingViewHttpClient.get", return_value=_response(payload)) as mock_get:
            headlines = news_scraper.scrape_headlines(
                symbol="BTCUSD",
                exchange="BINANCE",
                provider="cointelegraph",
                sort="latest",
            )

        assert len(headlines) == 1
        assert "provider=cointelegraph" in mock_get.call_args.args[0]

    def test_scrape_news_content(self):
        news_scraper = NewsScraper(export_result=False)
        html = """
        <html>
          <body>
            <article>
              <nav aria-label="Breadcrumbs">
                <span class="breadcrumb-content-abc">Markets</span>
                <span class="breadcrumb-content-def">Crypto</span>
              </nav>
              <h1>Bitcoin update</h1>
              <time datetime="2026-06-01T12:00:00Z"></time>
              <div class="body-KX2tCBZq">
                <p>First paragraph.</p>
                <p></p>
                <img src="https://example.com/chart.png" alt="Chart">
                <img alt="Missing src">
              </div>
            </article>
            <div class="rowTags-abc"><span>BTC</span><span>Markets</span></div>
          </body>
        </html>
        """

        with mock.patch("tradingview_scraper.symbols.news.TradingViewHttpClient.get", return_value=_response(text=html)):
            content = news_scraper.scrape_news_content(story_path="/news/test-story/")

        assert content["breadcrumbs"] == "Markets > Crypto"
        assert content["title"] == "Bitcoin update"
        assert content["published_datetime"] == "2026-06-01T12:00:00Z"
        assert content["body"] == [
            {"type": "text", "content": "First paragraph."},
            {"type": "image", "src": "https://example.com/chart.png", "alt": "Chart"},
        ]
        assert content["tags"] == ["BTC", "Markets"]

    def test_scrape_news_content_handles_malformed_html(self):
        news_scraper = NewsScraper(export_result=False)

        with mock.patch(
            "tradingview_scraper.symbols.news.TradingViewHttpClient.get",
            return_value=_response(text="<html><body>No article</body></html>"),
        ):
            content = news_scraper.scrape_news_content(story_path="/news/malformed/")

        assert content == {
            "breadcrumbs": None,
            "title": None,
            "published_datetime": None,
            "related_symbols": [],
            "body": [],
            "tags": [],
        }

    def test_scrape_headlines_no_data(self):
        news_scraper = NewsScraper(export_result=False)

        with mock.patch("tradingview_scraper.symbols.news.TradingViewHttpClient.get", return_value=_response({"items": []})):
            headlines = news_scraper.scrape_headlines(symbol="BTCUSD", exchange="BINANCE")

        assert headlines == []

    def test_scrape_headlines_with_area_filter(self):
        news_scraper = NewsScraper(export_result=False)
        payload = {"items": [{"id": "1", "title": "Area item", "published": 1, "urgency": 1}]}

        with mock.patch("tradingview_scraper.symbols.news.TradingViewHttpClient.get", return_value=_response(payload)) as mock_get:
            headlines = news_scraper.scrape_headlines(
                symbol="BTCUSD",
                exchange="BINANCE",
                area="americas",
                sort="latest",
            )

        assert len(headlines) == 1
        assert "area=AME" in mock_get.call_args.args[0]

    def test_scrape_headlines_sort_options(self):
        news_scraper = NewsScraper(export_result=False)
        payload = {
            "items": [
                {"id": "low", "published": 1, "urgency": 1},
                {"id": "high", "published": 2, "urgency": 10},
            ]
        }

        with mock.patch("tradingview_scraper.symbols.news.TradingViewHttpClient.get", return_value=_response(payload)):
            latest = news_scraper.scrape_headlines(symbol="BTCUSD", exchange="BINANCE", sort="latest")
        with mock.patch("tradingview_scraper.symbols.news.TradingViewHttpClient.get", return_value=_response(payload)):
            urgent = news_scraper.scrape_headlines(symbol="BTCUSD", exchange="BINANCE", sort="most_urgent")

        assert [item["id"] for item in latest] == ["high", "low"]
        assert [item["id"] for item in urgent] == ["high", "low"]
