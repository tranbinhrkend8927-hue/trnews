# tests/test_indicators.py

import os
import sys
import json
import pytest

path = str(os.getcwd())
if path not in sys.path:
    sys.path.append(path)

from tradingview_scraper.symbols.technicals import Indicators


class TestIndicators:

    def setup_method(self):
        """Setup method to create an Indicators instance."""
        self.indicators_scraper = Indicators(export_result=True, export_type='json')

    @staticmethod
    def _mock_response(mocker, status_code=200, json_data=None):
        """Helper to mock requests.get with given JSON data."""
        mock_resp = mocker.Mock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data or {}
        mocker.patch('tradingview_scraper.symbols.technicals.requests.get', return_value=mock_resp)

    def test_scrape_indicators_success(self, mocker):
        """Test scraping indicators successfully."""
        mock_json = {"RSI|1d": 50.0, "Stoch.K|1d": 80.0}
        self._mock_response(mocker, json_data=mock_json)

        indicators = self.indicators_scraper.scrape(
            exchange="BINANCE",
            symbol="BTCUSD",
            timeframe="1d",
            indicators=["RSI", "Stoch.K"]
        )

        assert indicators['status'] == 'success'
        assert 'data' in indicators
        assert indicators['data']['RSI'] == 50.0
        assert indicators['data']['Stoch.K'] == 80.0
        # Verify timeframe suffix is stripped from keys
        assert 'Stoch.K|1d' not in indicators['data']

    def test_scrape_indicators_invalid_exchange(self, mocker):
        """Test scraping indicators with an invalid exchange."""
        with pytest.raises(ValueError, match="exchange is not supported"):
            self.indicators_scraper.scrape(
                exchange="INVALID_EXCHANGE",
                symbol="BTCUSD",
                timeframe="1d",
                indicators=["RSI", "Stoch.K"]
            )

    def test_scrape_indicators_empty_response(self, mocker):
        """Test scraping indicators returns empty response."""
        self._mock_response(mocker, json_data={})

        indicators = self.indicators_scraper.scrape(
            exchange="BINANCE",
            symbol="BTCUSD",
            timeframe="1d",
            indicators=["RSI", "Stoch.K"]
        )

        assert indicators['status'] == 'failed'

    def test_scrape_indicators_valid_response(self, mocker):
        """Test scraping indicators with a valid success response."""
        mock_json = {"RSI|1d": 50.0, "Stoch.K|1d": 80.0}
        self._mock_response(mocker, json_data=mock_json)

        indicators = self.indicators_scraper.scrape(
            exchange="BINANCE",
            symbol="BTCUSD",
            timeframe="1d",
            indicators=["RSI", "Stoch.K"]
        )

        assert indicators['status'] == 'success'
        assert 'data' in indicators
        assert 'RSI' in indicators['data']
        assert 'Stoch.K' in indicators['data']
        assert indicators['data']['RSI'] == 50.0
        assert indicators['data']['Stoch.K'] == 80.0
