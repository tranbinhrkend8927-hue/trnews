"""
Comprehensive tests for the Streamer class functionality.
Tests cover: OHLC streaming, single/multiple indicators, error handling.

Set the TRADINGVIEW_JWT_TOKEN environment variable to run these tests:
    export TRADINGVIEW_JWT_TOKEN="your_jwt_token_here"
"""
import pytest
import json
import importlib
import os
import time
from types import SimpleNamespace
from unittest import mock
from tradingview_scraper.symbols.stream import Streamer


# Get JWT token from environment variable
JWT_TOKEN = os.getenv("TRADINGVIEW_JWT_TOKEN", "")
LIVE_STREAMER_TEST = pytest.mark.skipif(
    not JWT_TOKEN,
    reason="TRADINGVIEW_JWT_TOKEN environment variable not set. Set it to run these tests.",
)
streamer_module = importlib.import_module("tradingview_scraper.symbols.stream.streamer")


class TestStreamerMock:
    def _streamer(self):
        streamer = object.__new__(Streamer)
        streamer.export_result = True
        streamer.export_type = "json"
        streamer.study_id_to_name_map = {}
        streamer.stream_obj = SimpleNamespace(
            quote_session="qs_mock",
            chart_session="cs_mock",
            ws=mock.Mock(),
        )
        return streamer

    def test_get_data_handles_bad_websocket_message(self, monkeypatch):
        streamer = self._streamer()
        streamer.stream_obj.ws.recv.return_value = "~m~3~m~bad"
        monkeypatch.setattr(streamer_module, "sleep", lambda _: None)

        assert list(streamer.get_data()) == []
        streamer.stream_obj.ws.close.assert_called_once()

    def test_stream_raises_when_no_ohlc_packet_arrives(self, monkeypatch):
        streamer = self._streamer()
        packets = iter({"m": "du", "p": []} for _ in range(17))
        monkeypatch.setattr(streamer_module, "validate_symbols", lambda symbol: True)
        monkeypatch.setattr(streamer, "_add_symbol_to_sessions", lambda *args, **kwargs: None)
        monkeypatch.setattr(streamer, "get_data", lambda: packets)

        with pytest.raises(Exception, match="No 'OHLC' packet"):
            streamer.stream(exchange="BINANCE", symbol="BTCUSDT", numb_price_candles=1)

    def test_add_indicators_skips_missing_metadata(self, monkeypatch):
        streamer = self._streamer()
        monkeypatch.setattr(streamer_module, "fetch_indicator_metadata", lambda **kwargs: None)

        streamer._add_indicators([("STD;RSI", "37.0")])

        assert streamer.study_id_to_name_map == {}

    def test_serialize_ohlc_handles_missing_volume(self):
        streamer = self._streamer()
        raw_data = {
            "p": [
                {},
                {"sds_1": {"s": [{"i": 1, "v": [1710000000, 1.0, 2.0, 0.5, 1.5]}]}},
            ]
        }

        assert streamer._serialize_ohlc(raw_data) == [
            {"index": 1, "timestamp": 1710000000, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}
        ]

@LIVE_STREAMER_TEST
class TestStreamerOHLC:
    """Test OHLC data streaming without indicators"""
    
    def test_stream_ohlc_only(self):
        """Test streaming OHLC data without any indicators"""
        streamer = Streamer(
            export_result=True,
            export_type='json',
            websocket_jwt_token=JWT_TOKEN
        )
        
        result = streamer.stream(
            exchange="BINANCE",
            symbol="BTCUSDT",
            timeframe="1m",
            numb_price_candles=3
        )
        
        # Assertions
        assert "ohlc" in result
        assert "indicator" in result
        assert isinstance(result["ohlc"], list)
        assert isinstance(result["indicator"], dict)
        assert len(result["ohlc"]) > 0
        assert len(result["indicator"]) == 0  # No indicators requested
        
        # Sleep to avoid forbidden error
        time.sleep(10)


@LIVE_STREAMER_TEST
class TestStreamerSingleIndicator:
    """Test streaming with a single indicator"""
    
    def test_stream_with_rsi(self):
        """Test streaming OHLC data with RSI indicator"""
        streamer = Streamer(
            export_result=True,
            export_type='json',
            websocket_jwt_token=JWT_TOKEN
        )
        
        result = streamer.stream(
            exchange="BINANCE",
            symbol="BTCUSDT",
            indicators=[("STD;RSI", "37.0")],
            timeframe="1m",
            numb_price_candles=3
        )
        
        # Assertions
        assert "ohlc" in result
        assert "indicator" in result
        assert len(result["ohlc"]) > 0
        assert len(result["indicator"]) == 1
        assert "STD;RSI" in result["indicator"]
        assert isinstance(result["indicator"]["STD;RSI"], list)
        assert len(result["indicator"]["STD;RSI"]) > 0
        
        # Sleep to avoid forbidden error
        time.sleep(10)


@LIVE_STREAMER_TEST
class TestStreamerMultipleIndicators:
    """Test streaming with multiple indicators"""
    
    def test_stream_with_rsi_and_macd(self):
        """Test streaming with RSI and MACD indicators"""
        streamer = Streamer(
            export_result=True,
            export_type='json',
            websocket_jwt_token=JWT_TOKEN
        )
        
        result = streamer.stream(
            exchange="BINANCE",
            symbol="BTCUSDT",
            indicators=[("STD;RSI", "37.0"), ("STD;MACD", "31.0")],
            timeframe="1m",
            numb_price_candles=3
        )
        
        # Assertions
        assert "ohlc" in result
        assert "indicator" in result
        assert len(result["ohlc"]) > 0
        assert len(result["indicator"]) == 2
        assert "STD;RSI" in result["indicator"]
        assert "STD;MACD" in result["indicator"]
        assert isinstance(result["indicator"]["STD;RSI"], list)
        assert isinstance(result["indicator"]["STD;MACD"], list)
        assert len(result["indicator"]["STD;RSI"]) > 0
        assert len(result["indicator"]["STD;MACD"]) > 0
        
        # Sleep to avoid forbidden error
        time.sleep(10)
    
    def test_stream_with_three_indicators(self):
        """Test streaming with three indicators: RSI, MACD, and CCI
        
        Note: Free TradingView accounts are limited to 2 indicators maximum.
        This test will only receive 2 indicators (RSI and MACD), and CCI will timeout.
        The error message "❌ Unable to scrape indicator: STD;CCI" should be logged.
        """
        streamer = Streamer(
            export_result=True,
            export_type='json',
            websocket_jwt_token=JWT_TOKEN
        )
        
        result = streamer.stream(
            exchange="BINANCE",
            symbol="BTCUSDT",
            indicators=[
                ("STD;RSI", "37.0"),
                ("STD;MACD", "31.0"),
                ("STD;CCI", "37.0")
            ],
            timeframe="1m",
            numb_price_candles=3
        )
        
        # Assertions for free account (2 indicator limit)
        # We expect only 2 indicators to be received
        assert len(result["indicator"]) == 2, f"Free accounts can only stream 2 indicators, got {len(result['indicator'])}"
        assert "STD;RSI" in result["indicator"], "RSI should be present"
        assert "STD;MACD" in result["indicator"], "MACD should be present"
        
        # Sleep to avoid forbidden error
        time.sleep(10)


@LIVE_STREAMER_TEST
class TestStreamerDataStructure:
    """Test data structure and content validation"""
    
    def test_ohlc_data_structure(self):
        """Test that OHLC data has correct structure"""
        streamer = Streamer(
            export_result=True,
            export_type='json',
            websocket_jwt_token=JWT_TOKEN
        )
        
        result = streamer.stream(
            exchange="BINANCE",
            symbol="BTCUSDT",
            timeframe="1m",
            numb_price_candles=3
        )
        
        # Check OHLC structure
        ohlc_candle = result["ohlc"][0]
        required_keys = ['index', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
        for key in required_keys:
            assert key in ohlc_candle, f"Missing key: {key}"
        
        # Sleep to avoid forbidden error
        time.sleep(10)
    
    def test_indicator_data_structure(self):
        """Test that indicator data has correct structure"""
        streamer = Streamer(
            export_result=True,
            export_type='json',
            websocket_jwt_token=JWT_TOKEN
        )
        
        result = streamer.stream(
            exchange="BINANCE",
            symbol="BTCUSDT",
            indicators=[("STD;RSI", "37.0")],
            timeframe="1m",
            numb_price_candles=3
        )
        
        # Check indicator structure
        rsi_data = result["indicator"]["STD;RSI"][0]
        assert 'index' in rsi_data
        assert 'timestamp' in rsi_data
        assert isinstance(rsi_data['timestamp'], (int, float))
        
        # Sleep to avoid forbidden error
        time.sleep(10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
