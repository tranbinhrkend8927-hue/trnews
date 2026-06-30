import json
import sys
import types
from datetime import datetime, timezone

import source_grounding


def _topic(**overrides):
    row = {
        "id": 1,
        "symbol": "USDIDR",
        "topic_type": "daily_usdidr_update",
        "status": "candidate",
        "reason_json": {"source_news_ids": [2, 3]},
        "source_news_ids": [1, 2],
    }
    row.update(overrides)
    return row


def _install_fake_psycopg(monkeypatch, rows=None, error=None):
    rows = rows or []

    class FakeCursor:
        def __init__(self):
            self.rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            if error:
                raise error
            requested_ids = set((params or [[]])[0])
            self.rows = [row for row in rows if row.get("id", row.get("news_id")) in requested_ids]

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = lambda *args, **kwargs: FakeConnection()
    psycopg_rows_module = types.ModuleType("psycopg.rows")
    psycopg_rows_module.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.rows", psycopg_rows_module)


def test_extract_source_news_ids_from_topic_row_source_news_ids():
    result = source_grounding.extract_source_news_ids(_topic(reason_json={}, source_news_ids=[1, 2]))

    assert result["source_news_ids"] == [1, 2]
    assert result["warnings"] == []


def test_extract_source_news_ids_from_reason_json():
    result = source_grounding.extract_source_news_ids(_topic(source_news_ids=[], reason_json={"source_news_ids": [4, 5]}))

    assert result["source_news_ids"] == [4, 5]


def test_extract_source_news_ids_merges_deduplicates_and_preserves_order():
    result = source_grounding.extract_source_news_ids(_topic(source_news_ids=[1, 2], reason_json={"source_news_ids": [2, 3, 1]}))

    assert result["source_news_ids"] == [1, 2, 3]


def test_extract_source_news_ids_records_invalid_ids_without_crashing():
    result = source_grounding.extract_source_news_ids(
        _topic(source_news_ids=[1, "bad", -2, None], reason_json='{"source_news_ids": ["3", "x"]}')
    )

    assert result["source_news_ids"] == [1, 3]
    assert len(result["warnings"]) == 4
    assert result["warnings"][0]["type"] == "invalid_source_news_id"


def test_extract_source_news_ids_empty_and_bad_json_returns_empty():
    result = source_grounding.extract_source_news_ids(_topic(source_news_ids=None, reason_json="{bad json"))

    assert result["source_news_ids"] == []
    assert result["warnings"] == []


def test_fetch_source_news_for_topic_returns_json_serializable_rows(monkeypatch):
    published = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    _install_fake_psycopg(
        monkeypatch,
        rows=[
            {
                "id": 1,
                "symbol": "USDIDR",
                "title": "Rupiah dan Dolar AS",
                "summary": "Ringkasan sumber",
                "content": "Konten",
                "url": "https://example.com/1",
                "canonical_url": "https://example.com/canonical-1",
                "source": "Example News",
                "source_url": "https://example.com",
                "published_at": published,
                "fetched_at": published,
                "locale": "id",
            }
        ],
    )

    result = source_grounding.fetch_source_news_for_topic("postgresql://example/db", _topic(source_news_ids=[1], reason_json={}))

    dumped = json.dumps(result, ensure_ascii=False)
    assert "2026-01-02T03:04:00Z" in dumped
    assert result["sources"][0]["news_id"] == 1
    assert result["sources"][0]["title"] == "Rupiah dan Dolar AS"
    assert result["missing_source_news_ids"] == []


def test_fetch_source_news_for_topic_records_missing_source_news_ids(monkeypatch):
    _install_fake_psycopg(monkeypatch, rows=[{"id": 1, "title": "Ada"}])

    result = source_grounding.fetch_source_news_for_topic("postgresql://example/db", _topic(source_news_ids=[1, 2], reason_json={}))

    assert [source["news_id"] for source in result["sources"]] == [1]
    assert result["missing_source_news_ids"] == [2]


def test_fetch_source_news_for_topic_returns_structured_error(monkeypatch):
    _install_fake_psycopg(monkeypatch, error=RuntimeError("db unavailable"))

    result = source_grounding.fetch_source_news_for_topic("postgresql://example/db", _topic(source_news_ids=[1], reason_json={}))

    assert result["sources"] == []
    assert result["missing_source_news_ids"] == [1]
    assert result["errors"][0]["type"] == "source_news_fetch_failed"


def test_build_source_bundle_contains_sources_warnings_and_missing_ids():
    bundle = source_grounding.build_source_bundle(
        _topic(source_news_ids=[1, "bad"], reason_json={"source_news_ids": [2]}),
        {
            "sources": [{"news_id": 1, "title": "Stored source"}],
            "missing_source_news_ids": [2],
            "warnings": [{"type": "fetch_warning"}],
            "errors": [],
        },
    )

    assert bundle["topic_id"] == 1
    assert bundle["symbol"] == "USDIDR"
    assert bundle["source_news_ids"] == [1, 2]
    assert bundle["sources"][0]["title"] == "Stored source"
    assert bundle["missing_source_news_ids"] == [2]
    assert bundle["warnings"][0]["type"] == "invalid_source_news_id"
    assert bundle["warnings"][1]["type"] == "fetch_warning"
    assert json.loads(json.dumps(bundle, ensure_ascii=False))["topic_id"] == 1


def test_build_article_sources_from_bundle_uses_real_source_metadata_without_fabricating_url():
    bundle = source_grounding.build_source_bundle(
        _topic(),
        [
            {"news_id": 1, "title": "Judul sumber", "summary": "Ringkasan", "source": "Media A", "url": "https://example.com/a"},
            {"news_id": 2, "summary": "Ringkasan tanpa URL", "source": None, "url": None, "canonical_url": None, "source_url": None},
        ],
    )

    article_sources = source_grounding.build_article_sources_from_bundle(bundle)

    assert article_sources[0] == {
        "source_type": "forex_news",
        "source_name": "Media A",
        "source_url": "https://example.com/a",
        "cited_claim": "Judul sumber",
    }
    assert article_sources[1]["source_name"] == "forex_news"
    assert article_sources[1]["source_url"] is None
    assert article_sources[1]["cited_claim"] == "Ringkasan tanpa URL"
