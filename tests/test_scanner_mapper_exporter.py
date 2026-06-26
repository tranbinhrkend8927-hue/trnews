import json

import pandas as pd

from tradingview_scraper.symbols.scanner import ScannerResponseMapper
from tradingview_scraper.symbols.utils import Exporter


def test_scanner_response_mapper_maps_symbol_and_fields():
    rows = [{"s": "NASDAQ:AAPL", "d": ["Apple Inc.", 150.25, 50_000_000]}]

    result = ScannerResponseMapper.map_rows(rows, ["name", "close", "volume"])

    assert result == [
        {
            "symbol": "NASDAQ:AAPL",
            "name": "Apple Inc.",
            "close": 150.25,
            "volume": 50_000_000,
        }
    ]


def test_scanner_response_mapper_field_schema_change_only_changes_field_names():
    rows = [{"s": "NASDAQ:AAPL", "d": ["Apple Inc.", 150.25]}]

    result = ScannerResponseMapper.map_rows(rows, ["description", "last_price"])

    assert result == [{"symbol": "NASDAQ:AAPL", "description": "Apple Inc.", "last_price": 150.25}]


def test_scanner_response_mapper_ignores_empty_rows_and_short_data():
    rows = [
        {"s": "NASDAQ:AAPL", "d": []},
        {"s": "NASDAQ:MSFT", "d": ["Microsoft"]},
    ]

    result = ScannerResponseMapper.map_rows(rows, ["name", "close"])

    assert result == [{"symbol": "NASDAQ:MSFT", "name": "Microsoft"}]


def test_exporter_writes_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exporter = Exporter("json")

    exporter.export([{"symbol": "NASDAQ:AAPL"}], symbol="AAPL", data_category="scanner")

    files = list((tmp_path / "export").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == [{"symbol": "NASDAQ:AAPL"}]


def test_exporter_writes_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exporter = Exporter("csv")

    exporter.export([{"symbol": "NASDAQ:AAPL", "close": 150.25}], symbol="AAPL", data_category="scanner")

    files = list((tmp_path / "export").glob("*.csv"))
    assert len(files) == 1
    frame = pd.read_csv(files[0])
    assert frame.to_dict("records") == [{"symbol": "NASDAQ:AAPL", "close": 150.25}]
