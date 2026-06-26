import json
from unittest import mock

import pytest
import requests

from tradingview_scraper.symbols.stream import price as price_module
from tradingview_scraper.symbols.stream.price import RealTimeData


def _frame(payload):
    message = json.dumps(payload, separators=(",", ":"))
    return f"~m~{len(message)}~m~{message}"


def _ok_response():
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    return response


class TestRealTimeData:
    def test_returns_generator_without_mocking_method(self, monkeypatch):
        ws = mock.Mock()
        monkeypatch.setattr(price_module, "create_connection", lambda *args, **kwargs: ws)
        real_time_data = RealTimeData()

        data_generator = real_time_data.get_latest_trade_info(
            exchange_symbol=["BINANCE:BTCUSDT", "BINANCE:ETHUSDT"]
        )

        assert hasattr(data_generator, "__iter__")
        assert ws.send.call_count >= 1

    def test_generator_yields_valid_data_without_mocking_method(self, monkeypatch):
        ws = mock.Mock()
        ws.recv.side_effect = [_frame({"m": "qsd", "p": ["payload"]})]
        monkeypatch.setattr(price_module, "create_connection", lambda *args, **kwargs: ws)
        monkeypatch.setattr(price_module, "sleep", lambda _: None)
        real_time_data = RealTimeData()

        data_generator = real_time_data.get_latest_trade_info(exchange_symbol=["BINANCE:BTCUSDT"])
        try:
            packet = next(data_generator)
        finally:
            data_generator.close()

        assert packet == {"m": "qsd", "p": ["payload"]}
        ws.close.assert_called_once()

    def test_validate_symbols_rejects_empty_list(self, monkeypatch):
        monkeypatch.setattr(price_module, "create_connection", lambda *args, **kwargs: mock.Mock())
        real_time_data = RealTimeData()

        with pytest.raises(ValueError, match="could not be empty"):
            real_time_data.validate_symbols([])

    def test_validate_symbols_rejects_bad_format(self, monkeypatch):
        monkeypatch.setattr(price_module, "create_connection", lambda *args, **kwargs: mock.Mock())
        real_time_data = RealTimeData()

        with pytest.raises(ValueError, match="Invalid symbol format"):
            real_time_data.validate_symbols(["BTCUSDT"])

    def test_validate_symbols_raises_for_404(self, monkeypatch):
        monkeypatch.setattr(price_module, "create_connection", lambda *args, **kwargs: mock.Mock())
        response = mock.Mock(status_code=404)
        error = requests.HTTPError(response=response)
        response.raise_for_status.side_effect = error
        monkeypatch.setattr(price_module.requests, "get", mock.Mock(return_value=response))
        real_time_data = RealTimeData()

        with pytest.raises(ValueError, match="Invalid exchange:symbol"):
            real_time_data.validate_symbols(["BINANCE:UNKNOWN"])

    def test_validate_symbols_raises_after_retries(self, monkeypatch):
        monkeypatch.setattr(price_module, "create_connection", lambda *args, **kwargs: mock.Mock())
        monkeypatch.setattr(price_module.time, "sleep", lambda _: None)
        get = mock.Mock(side_effect=requests.Timeout("timeout"))
        monkeypatch.setattr(price_module.requests, "get", get)
        real_time_data = RealTimeData()

        with pytest.raises(ValueError, match="Invalid exchange:symbol"):
            real_time_data.validate_symbols(["BINANCE:BTCUSDT"])

        assert get.call_count == 3

    def test_validate_symbols_succeeds_after_retry(self, monkeypatch):
        monkeypatch.setattr(price_module, "create_connection", lambda *args, **kwargs: mock.Mock())
        monkeypatch.setattr(price_module.time, "sleep", lambda _: None)
        get = mock.Mock(side_effect=[requests.Timeout("timeout"), _ok_response()])
        monkeypatch.setattr(price_module.requests, "get", get)
        real_time_data = RealTimeData()

        assert real_time_data.validate_symbols(["BINANCE:BTCUSDT"]) is True
        assert get.call_count == 2
