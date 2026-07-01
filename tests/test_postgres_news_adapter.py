import sys
import types
from datetime import datetime, timezone

from src.config.loader import load_config_registry
from src.ingest.postgres_news import PostgresNewsAdapter


def market():
    return load_config_registry().pipeline.markets[0]


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        self.executed.append({"query": query, "params": params})

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


def install_fake_psycopg(monkeypatch, cursor):
    module = types.SimpleNamespace(connect=lambda *args, **kwargs: FakeConnection(cursor))
    rows_module = types.SimpleNamespace(dict_row=object())
    monkeypatch.setitem(sys.modules, "psycopg", module)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows_module)


def test_fetch_reads_recent_news_from_postgres_with_limit(monkeypatch):
    cursor = FakeCursor(
        [
            {
                "id": 10,
                "title": "Rupiah headline",
                "summary": "Summary",
                "content": "Body",
                "url": "https://example.com/news",
                "canonical_url": "https://example.com/news",
                "source": "Kontan",
                "published_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
                "fetched_at": datetime(2026, 7, 1, 1, tzinfo=timezone.utc),
                "locale": "id",
                "raw_json": {"provider": "kontan"},
            }
        ]
    )
    install_fake_psycopg(monkeypatch, cursor)

    result = PostgresNewsAdapter(dsn="postgresql://unit/db", lookback_hours=24).fetch(market())

    assert result.success is True
    assert result.items[0].source_id == "10"
    assert result.items[0].provider == "Kontan"
    assert result.items[0].content == "Body"
    assert cursor.executed[0]["params"] == ("USDIDR", 24, 5)
    assert "COALESCE(published_at, fetched_at)" in cursor.executed[0]["query"]


def test_fetch_failure_is_structured(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)

    result = PostgresNewsAdapter(dsn="postgresql://unit/db").fetch(market())

    assert result.success is False
    assert result.errors[0]["type"] == "postgres_source_fetch_failed"
