import json
import sys
import types
from datetime import datetime, timezone

from news_pipeline import content_topics
from news_pipeline import generate_content_topics


NOW = datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc)


def _news(**overrides):
    row = {
        "id": 1,
        "symbol": "USDIDR",
        "locale": "id",
        "title": "Rupiah melemah terhadap dolar AS",
        "summary": "Bank Indonesia memantau pergerakan USD/IDR.",
        "content": "",
        "url": "https://example.com/news/rupiah",
        "canonical_url": "https://example.com/news/rupiah",
        "source": "Example",
        "published_at": "2026-01-01T12:00:00Z",
        "fetched_at": "2026-01-01T12:05:00Z",
    }
    row.update(overrides)
    return row


def test_usdidr_news_generates_candidate_topic():
    topics = content_topics.generate_usdidr_topic_candidates([_news()], now=NOW)

    assert len(topics) == 1
    assert topics[0]["symbol"] == "USDIDR"
    assert topics[0]["topic_type"] == "bank_indonesia_watch"
    assert topics[0]["status"] == "candidate"
    assert topics[0]["source_news_ids"] == [1]
    assert topics[0]["score"] >= 3


def test_no_relevant_news_does_not_generate_topic():
    topics = content_topics.generate_usdidr_topic_candidates(
        [
            _news(
                id=2,
                title="General market note",
                summary="No relevant forex keywords here.",
                content="",
                url="",
                canonical_url="",
                published_at="2025-01-01T00:00:00Z",
            )
        ],
        now=NOW,
    )

    assert topics == []


def test_non_usdidr_news_does_not_generate_topic():
    topics = content_topics.generate_usdidr_topic_candidates([_news(symbol="USDJPY")], now=NOW)

    assert topics == []


def test_reason_json_is_serializable_and_tracks_source_news_id():
    topic = content_topics.generate_usdidr_topic_candidates([_news(id=7)], now=NOW)[0]

    dumped = json.dumps(topic["reason_json"], ensure_ascii=False)

    assert "Bank Indonesia" in dumped
    assert topic["reason_json"]["source_news_ids"] == [7]
    assert topic["reason_json"]["freshness_score"] == 2
    assert topic["reason_json"]["source_score"] == 1
    assert topic["reason_json"]["locale"] == "id"


def test_topic_type_uses_macro_event_watch_for_us_data():
    topic = content_topics.generate_usdidr_topic_candidates(
        [
            _news(
                title="USD/IDR bergerak menjelang CPI AS",
                summary="The Fed dan FOMC menjadi perhatian pasar.",
            )
        ],
        now=NOW,
    )[0]

    assert topic["topic_type"] == "macro_event_watch"


def test_topic_hash_is_stable():
    first = content_topics.generate_usdidr_topic_candidates([_news()], now=NOW)[0]
    second = content_topics.generate_usdidr_topic_candidates([_news()], now=NOW)[0]

    assert first["topic_hash"] == second["topic_hash"]


def test_build_topic_generation_result_rejects_unsupported_symbol():
    result = content_topics.build_topic_generation_result(
        symbol="USDJPY",
        news_rows=[_news(symbol="USDJPY")],
        dsn="postgresql://example/db",
    )

    assert result["summary"]["news_checked"] == 1
    assert result["summary"]["topics_generated"] == 0
    assert result["errors"] == [
        {
            "symbol": "USDJPY",
            "error": "Unsupported symbol for topic generation: USDJPY. Only USDIDR is supported.",
        }
    ]


def test_dumps_json_returns_valid_json():
    payload = {"generated_at": content_topics.utc_now_iso(), "topics": [{"reason_json": {"source_news_ids": [1]}}]}

    dumped = content_topics.dumps_json(payload)

    assert json.loads(dumped)["topics"][0]["reason_json"]["source_news_ids"] == [1]


def test_save_topic_candidates_inserts_then_skips_duplicates(monkeypatch):
    state = {"rows": []}

    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            params = params or ()
            if normalized.startswith("SAVEPOINT") or normalized.startswith("RELEASE") or normalized.startswith("ROLLBACK"):
                self.next_fetchone = None
                return
            if "SELECT 1 FROM content_topics WHERE symbol = %s AND topic_hash = %s" in normalized:
                self.next_fetchone = (
                    (1,)
                    if any(row["symbol"] == params[0] and row["topic_hash"] == params[1] for row in state["rows"])
                    else None
                )
                return
            if "INSERT INTO content_topics" in normalized:
                row = {"symbol": params[0], "topic_hash": params[7]}
                if any(existing == row for existing in state["rows"]):
                    self.next_fetchone = None
                else:
                    state["rows"].append(row)
                    self.next_fetchone = (len(state["rows"]),)
                return
            raise AssertionError(f"unexpected query: {normalized}")

        def fetchone(self):
            return self.next_fetchone

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = lambda dsn: FakeConnection()
    psycopg_types_module = types.ModuleType("psycopg.types")
    psycopg_json_module = types.ModuleType("psycopg.types.json")
    psycopg_json_module.Jsonb = lambda value: value
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.types", psycopg_types_module)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", psycopg_json_module)

    topic = content_topics.generate_usdidr_topic_candidates([_news()], now=NOW)[0]

    first = content_topics.save_topic_candidates_to_postgres([dict(topic)], "postgresql://example/db")
    second = content_topics.save_topic_candidates_to_postgres([dict(topic)], "postgresql://example/db")

    assert first["inserted_count"] == 1
    assert first["skipped_count"] == 0
    assert second["inserted_count"] == 0
    assert second["skipped_count"] == 1


def test_dry_run_does_not_insert(monkeypatch):
    state = {"insert_called": False}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            if "INSERT INTO content_topics" in normalized:
                state["insert_called"] = True

        def fetchone(self):
            return None

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = lambda dsn: FakeConnection()
    psycopg_types_module = types.ModuleType("psycopg.types")
    psycopg_json_module = types.ModuleType("psycopg.types.json")
    psycopg_json_module.Jsonb = lambda value: value
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.types", psycopg_types_module)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", psycopg_json_module)

    topic = content_topics.generate_usdidr_topic_candidates([_news()], now=NOW)[0]
    result = content_topics.save_topic_candidates_to_postgres([topic], "postgresql://example/db", dry_run=True)

    assert result["inserted_count"] == 1
    assert result["dry_run"] is True
    assert state["insert_called"] is False
    assert topic["db_status"] == "would_insert"


def test_single_topic_save_failure_does_not_abort_batch(monkeypatch):
    topics = content_topics.generate_usdidr_topic_candidates(
        [_news(id=1), _news(id=2, title="USDIDR dan CPI AS menjadi perhatian")],
        now=NOW,
    )
    state = {"insert_attempts": 0}

    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            if normalized.startswith("SAVEPOINT") or normalized.startswith("RELEASE") or normalized.startswith("ROLLBACK"):
                return
            if "SELECT 1 FROM content_topics" in normalized:
                self.next_fetchone = None
                return
            if "INSERT INTO content_topics" in normalized:
                state["insert_attempts"] += 1
                if state["insert_attempts"] == 1:
                    raise RuntimeError("insert failed")
                self.next_fetchone = (2,)
                return
            raise AssertionError(f"unexpected query: {normalized}")

        def fetchone(self):
            return self.next_fetchone

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = lambda dsn: FakeConnection()
    psycopg_types_module = types.ModuleType("psycopg.types")
    psycopg_json_module = types.ModuleType("psycopg.types.json")
    psycopg_json_module.Jsonb = lambda value: value
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.types", psycopg_types_module)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", psycopg_json_module)

    result = content_topics.save_topic_candidates_to_postgres(topics, "postgresql://example/db")

    assert result["failed_count"] == 1
    assert result["inserted_count"] == 1
    assert result["errors"][0]["error"] == "insert failed"


def test_cli_generates_json_summary(monkeypatch, capsys):
    monkeypatch.setattr(generate_content_topics, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(generate_content_topics, "fetch_usdidr_news_for_topics", lambda dsn, limit=50: [_news()])

    def fake_build_result(symbol, news_rows, dsn, dry_run=False):
        topic = content_topics.generate_usdidr_topic_candidates(news_rows, now=NOW)[0]
        topic["db_status"] = "would_insert" if dry_run else "inserted"
        return {
            "generated_at": "2026-01-02T00:00:00Z",
            "symbol": symbol,
            "summary": {
                "news_checked": len(news_rows),
                "topics_generated": 1,
                "topics_inserted": 1,
                "topics_skipped": 0,
                "topics_failed": 0,
            },
            "topics": [topic],
            "errors": [],
        }

    monkeypatch.setattr(generate_content_topics, "build_topic_generation_result", fake_build_result)

    exit_code = generate_content_topics.main(["--symbol", "USDIDR", "--dry-run", "--limit", "50"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["symbol"] == "USDIDR"
    assert payload["summary"]["news_checked"] == 1
    assert payload["topics"][0]["reason_json"]["source_news_ids"] == [1]


def test_cli_unsupported_symbol_returns_structured_error(capsys):
    exit_code = generate_content_topics.main(["--symbol", "USDJPY"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["symbol"] == "USDJPY"
    assert payload["summary"]["topics_generated"] == 0
    assert payload["errors"] == [
        {
            "symbol": "USDJPY",
            "error": "Unsupported symbol for topic generation: USDJPY. Only USDIDR is supported.",
        }
    ]
