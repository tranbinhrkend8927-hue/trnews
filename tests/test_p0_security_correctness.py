import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from tradingview_scraper.symbols import utils
from tradingview_scraper.symbols.stream import stream_handler as stream_handler_module
from tradingview_scraper.symbols.stream import streamer as streamer_module
from tradingview_scraper.symbols.stream import price as price_module


def _frame(payload):
    message = json.dumps(payload, separators=(",", ":"))
    return f"~m~{len(message)}~m~{message}"


def test_streamer_heartbeat_does_not_drop_next_data_frame(monkeypatch):
    ws = mock.Mock()
    ws.recv.side_effect = ["~m~4~m~~h~1", _frame({"m": "du", "p": []})]
    streamer = object.__new__(streamer_module.Streamer)
    streamer.stream_obj = SimpleNamespace(ws=ws)
    monkeypatch.setattr(streamer_module, "sleep", lambda _: None)

    generator = streamer.get_data()
    try:
        assert next(generator) == {"m": "du", "p": []}
    finally:
        generator.close()

    assert ws.recv.call_count == 2
    ws.send.assert_called_once_with("~m~4~m~~h~1")
    ws.close.assert_called_once()


def test_realtime_price_heartbeat_does_not_drop_next_data_frame(monkeypatch):
    ws = mock.Mock()
    ws.recv.side_effect = ["~m~4~m~~h~1", _frame({"m": "qsd", "p": []})]
    realtime = object.__new__(price_module.RealTimeData)
    realtime.ws = ws
    monkeypatch.setattr(price_module, "sleep", lambda _: None)

    generator = realtime.get_data()
    try:
        assert next(generator) == {"m": "qsd", "p": []}
    finally:
        generator.close()

    assert ws.recv.call_count == 2
    ws.send.assert_called_once_with("~m~4~m~~h~1")
    ws.close.assert_called_once()


def test_stream_handler_redacts_set_auth_token_from_debug_logs(monkeypatch, caplog):
    ws = mock.Mock()
    monkeypatch.setattr(stream_handler_module, "create_connection", lambda *args, **kwargs: ws)
    caplog.set_level(logging.DEBUG)

    stream_handler_module.StreamHandler(
        websocket_url="wss://example.invalid/socket",
        jwt_token="secret.jwt.token",
    )

    log_output = caplog.text
    assert "secret.jwt.token" not in log_output
    assert "<redacted>" in log_output
    assert any("secret.jwt.token" in call.args[0] for call in ws.send.call_args_list)


def test_export_filepath_is_restricted_to_export_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    output_path = utils.generate_export_filepath(
        symbol="../outside",
        data_category="../category",
        timeframe="../1m",
        file_extension=".json",
    )

    export_dir = tmp_path / "export"
    resolved_output = Path(output_path).resolve()
    assert os.path.commonpath([export_dir.resolve(), resolved_output]) == str(export_dir.resolve())
    assert ".." not in resolved_output.name
    assert "/" not in resolved_output.name


def test_json_export_uses_unique_files_for_concurrent_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def write_one(index):
        utils.save_json_file(
            {"index": index},
            symbol="../BTC/USDT",
            data_category="ohlc",
            timeframe="1m",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_one, range(8)))

    files = list((tmp_path / "export").glob("*.json"))
    assert len(files) == 8
    assert not list(tmp_path.glob("*.json"))


def test_csv_export_uses_unique_files_for_concurrent_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def write_one(index):
        utils.save_csv_file(
            [{"index": index, "value": index * 2}],
            symbol="../BTC/USDT",
            data_category="ohlc",
            timeframe="1m",
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write_one, range(4)))

    files = list((tmp_path / "export").glob("*.csv"))
    assert len(files) == 4
    assert not list(tmp_path.glob("*.csv"))
