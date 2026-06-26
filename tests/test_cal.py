import json
from unittest import mock

import pytest

from tradingview_scraper.symbols.cal import CalendarScraper


def _response(payload):
    response = mock.Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    response.status_code = 200
    return response


class TestCalendar:
    @pytest.fixture
    def calendar_scraper(self):
        return CalendarScraper(export_result=False)

    def test_scrape_earnings_all_markets(self, calendar_scraper):
        payload = {
            "data": [
                {
                    "s": "NASDAQ:AAPL",
                    "d": [1710000000, "apple", "Apple Inc.", "Consumer electronics", 1.2],
                }
            ]
        }

        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response(payload)):
            result = calendar_scraper.scrape_earnings(values=["logoid", "name", "earnings_per_share_fq"])

        assert result == [
            {
                "full_symbol": "NASDAQ:AAPL",
                "logoid": 1710000000,
                "name": "apple",
                "earnings_per_share_fq": "Apple Inc.",
            }
        ]

    def test_scrape_earnings_specific_market(self, calendar_scraper):
        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response({"data": []})) as mock_post:
            result = calendar_scraper.scrape_earnings(
                100,
                200,
                ["america"],
                values=["logoid", "name", "earnings_per_share_fq"],
            )

        request_payload = json.loads(mock_post.call_args.kwargs["data"])
        assert request_payload["markets"] == ["america"]
        assert request_payload["filter"][0]["right"] == [100, 200]
        assert result == []

    def test_scrape_earnings_with_custom_fields(self, calendar_scraper):
        payload = {"data": [{"s": "NASDAQ:MSFT", "d": ["msft", "Microsoft", 3.1, 1000]}]}

        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response(payload)):
            result = calendar_scraper.scrape_earnings(
                values=["logoid", "name", "earnings_per_share_fq", "market_cap_basic"]
            )

        assert result[0]["market_cap_basic"] == 1000

    def test_scrape_dividends_all_markets(self, calendar_scraper):
        payload = {
            "data": [
                {
                    "s": "NYSE:IBM",
                    "d": [1710000000, 1720000000, "ibm", "IBM", "Tech", 4.2],
                }
            ]
        }

        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response(payload)):
            result = calendar_scraper.scrape_dividends()

        assert result[0]["full_symbol"] == "NYSE:IBM"
        assert result[0]["logoid"] == "ibm"
        assert result[0]["dividends_yield"] == 4.2

    def test_scrape_dividends_specific_market(self, calendar_scraper):
        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response({"data": []})) as mock_post:
            result = calendar_scraper.scrape_dividends(
                100,
                200,
                ["america"],
                values=["logoid", "name", "dividends_yield"],
            )

        request_payload = json.loads(mock_post.call_args.kwargs["data"])
        assert request_payload["markets"] == ["america"]
        assert request_payload["filter"][0]["right"] == [100, 200]
        assert result == []

    def test_scrape_dividends_with_custom_fields(self, calendar_scraper):
        payload = {"data": [{"s": "NYSE:IBM", "d": ["ibm", "IBM", 4.2]}]}

        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response(payload)):
            result = calendar_scraper.scrape_dividends(values=["logoid", "name", "dividends_yield"])

        assert result == [{"full_symbol": "NYSE:IBM", "logoid": "ibm", "name": "IBM", "dividends_yield": 4.2}]

    def test_scrape_earnings_date_range(self, calendar_scraper):
        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response({"data": []})) as mock_post:
            calendar_scraper.scrape_earnings(100, 200, values=["logoid", "name"])

        request_payload = json.loads(mock_post.call_args.kwargs["data"])
        assert request_payload["filter"][0]["right"] == [100, 200]

    def test_scrape_earnings_no_data(self, calendar_scraper):
        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response({"data": []})):
            result = calendar_scraper.scrape_earnings(values=["logoid"])

        assert result == []

    def test_scrape_dividends_multiple_markets(self, calendar_scraper):
        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response({"data": []})) as mock_post:
            result = calendar_scraper.scrape_dividends(
                100,
                200,
                ["america", "uk"],
                values=["logoid", "name", "dividends_yield"],
            )

        request_payload = json.loads(mock_post.call_args.kwargs["data"])
        assert request_payload["markets"] == ["america", "uk"]
        assert result == []

    def test_missing_data_key_returns_empty_list(self, calendar_scraper):
        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response({})):
            assert calendar_scraper.scrape_earnings(values=["logoid"]) == []
            assert calendar_scraper.scrape_dividends(values=["logoid"]) == []

    def test_short_event_data_does_not_raise(self, calendar_scraper):
        payload = {"data": [{"s": "NASDAQ:AAPL", "d": ["apple"]}]}

        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response(payload)):
            result = calendar_scraper.scrape_earnings(values=["logoid", "name"])

        assert result == [{"full_symbol": "NASDAQ:AAPL", "logoid": "apple", "name": None}]

    def test_zero_event_values_are_preserved(self, calendar_scraper):
        payload = {"data": [{"s": "NASDAQ:AAPL", "d": [0, 0.0]}]}

        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response(payload)):
            result = calendar_scraper.scrape_earnings(values=["earnings_per_share_fq", "revenue_surprise_fq"])

        assert result == [
            {
                "full_symbol": "NASDAQ:AAPL",
                "earnings_per_share_fq": 0,
                "revenue_surprise_fq": 0.0,
            }
        ]

    def test_none_event_data_does_not_raise(self, calendar_scraper):
        payload = {"data": [{"s": "NASDAQ:AAPL", "d": None}]}

        with mock.patch("tradingview_scraper.symbols.cal.TradingViewHttpClient.post", return_value=_response(payload)):
            result = calendar_scraper.scrape_dividends(values=["logoid"])

        assert result == [{"full_symbol": "NASDAQ:AAPL", "logoid": None}]

    def test_invalid_values_raise_value_error(self, calendar_scraper):
        with pytest.raises(ValueError):
            calendar_scraper.scrape_earnings(values=["invalid_field"])
