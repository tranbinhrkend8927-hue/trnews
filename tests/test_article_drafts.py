import json
import sys
import types

from news_pipeline import article_drafts
from news_pipeline import generate_article_drafts


def _topic(**overrides):
    row = {
        "id": 1,
        "symbol": "USDIDR",
        "topic_type": "macro_event_watch",
        "title": "USD/IDR Bergerak Menjelang Data AS",
        "status": "candidate",
        "reason_json": {"matched_keywords": ["USD/IDR", "CPI"], "source_news_ids": [10, 11]},
        "source_news_ids": [10, 11],
    }
    row.update(overrides)
    return row


def _source_bundle(**overrides):
    bundle = {
        "topic_id": 1,
        "topic_type": "macro_event_watch",
        "symbol": "USDIDR",
        "source_news_ids": [10, 11],
        "sources": [
            {
                "news_id": 10,
                "symbol": "USDIDR",
                "title": "USD/IDR dan CPI menjadi perhatian",
                "summary": "Pasar mencermati data AS.",
                "content": None,
                "url": "https://example.com/source-10",
                "canonical_url": None,
                "source": "Example",
                "source_url": None,
                "published_at": None,
                "fetched_at": None,
                "locale": "id",
            }
        ],
        "missing_source_news_ids": [11],
        "warnings": [],
        "errors": [],
        "reason_json": {"source_news_ids": [10, 11]},
        "source_trace": {"topic_status": "candidate"},
    }
    bundle.update(overrides)
    return bundle


def _install_fake_psycopg(monkeypatch, connection):
    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = lambda *args, **kwargs: connection
    psycopg_types_module = types.ModuleType("psycopg.types")
    psycopg_json_module = types.ModuleType("psycopg.types.json")
    psycopg_json_module.Jsonb = lambda value: value
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.types", psycopg_types_module)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", psycopg_json_module)


def test_candidate_topic_can_create_draft_shell():
    draft = article_drafts.build_article_draft(_topic(status="candidate"))

    assert draft["topic_id"] == 1
    assert draft["status"] == "draft"
    assert draft["status"] != "published"
    assert draft["fact_check_status"] == "pending"
    assert draft["risk_disclaimer_included"] is False
    assert draft["body"] == ""


def test_approved_topic_can_create_draft_shell():
    draft = article_drafts.build_article_draft(_topic(status="approved"))

    assert draft["topic_id"] == 1
    assert draft["status"] == "draft"


def test_article_draft_cannot_default_to_published():
    try:
        article_drafts.build_article_draft(_topic(), status="published")
    except ValueError as exc:
        assert "status=published" in str(exc)
    else:
        raise AssertionError("published draft should be rejected")


def test_sources_json_is_serializable_and_tracks_source_news_ids():
    draft = article_drafts.build_article_draft(_topic())

    dumped = json.dumps(draft["sources_json"], ensure_ascii=False)

    assert "source_news_ids" in dumped
    assert "reason_json" in dumped
    assert draft["sources_json"]["topic_id"] == 1
    assert draft["sources_json"]["topic_type"] == "macro_event_watch"
    assert draft["sources_json"]["source_news_ids"] == [10, 11]


def test_template_draft_defaults_to_pending_review_and_includes_content():
    result = article_drafts.build_article_draft_from_template(
        _topic(topic_type="macro_event_watch"),
        source_bundle=_source_bundle(),
    )

    assert result["success"] is True
    draft = result["draft"]
    assert draft["status"] == "pending_review"
    assert draft["status"] != "published"
    assert draft["published_at"] is None
    assert draft["risk_disclaimer_included"] is True
    assert draft["fact_check_status"] == "pending"
    assert "FAQ" in draft["body"]
    assert "Catatan risiko" in draft["body"]
    assert draft["sources_json"]["source_news_ids"] == [10, 11]
    assert draft["sources_json"]["sources"][0]["title"] == "USD/IDR dan CPI menjadi perhatian"
    assert draft["sources_json"]["missing_source_news_ids"] == [11]


def test_template_draft_returns_structured_error_for_unsupported_topic_type():
    result = article_drafts.build_article_draft_from_template(_topic(topic_type="bank_indonesia_watch"))

    assert result["success"] is False
    assert result["error"]["code"] == "unsupported_topic_type"


def test_build_slug_is_stable_and_url_safe():
    first = article_drafts.build_slug("USD/IDR Bergerak Menjelang Data AS", topic_id=1)
    second = article_drafts.build_slug("USD/IDR Bergerak Menjelang Data AS", topic_id=1)

    assert first == second
    assert first == "usd-idr-bergerak-menjelang-data-as-1"


def test_save_article_draft_inserts_then_skips_duplicate(monkeypatch):
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
                return
            if "SELECT 1 FROM generated_articles WHERE topic_id = %s" in normalized:
                self.next_fetchone = (1,) if any(row["topic_id"] == params[0] for row in state["rows"]) else None
                return
            if "INSERT INTO generated_articles" in normalized:
                row = {"topic_id": params[0]}
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

    _install_fake_psycopg(monkeypatch, FakeConnection())
    draft = article_drafts.build_article_draft(_topic())

    first = article_drafts.save_article_draft_to_postgres(dict(draft), "postgresql://example/db")
    second = article_drafts.save_article_draft_to_postgres(dict(draft), "postgresql://example/db")

    assert first["inserted_count"] == 1
    assert first["article_id"] == 1
    assert second["inserted_count"] == 0
    assert second["skipped_count"] == 1


def test_dry_run_does_not_insert_article(monkeypatch):
    state = {"insert_called": False}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            if "INSERT INTO generated_articles" in " ".join(str(query).split()):
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

    _install_fake_psycopg(monkeypatch, FakeConnection())
    draft = article_drafts.build_article_draft(_topic())

    result = article_drafts.save_article_draft_to_postgres(draft, "postgresql://example/db", dry_run=True)

    assert result["dry_run"] is True
    assert result["inserted_count"] == 1
    assert draft["db_status"] == "would_insert"
    assert state["insert_called"] is False


def test_article_sources_can_link_to_article(monkeypatch):
    inserted = []

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
                return
            if "INSERT INTO article_sources" in normalized:
                inserted.append({"article_id": params[0], "source_url": params[3]})
                self.next_fetchone = (len(inserted),)
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

    _install_fake_psycopg(monkeypatch, FakeConnection())
    result = article_drafts.save_article_sources_to_postgres(
        5,
        [{"source_type": "forex_news", "source_name": "Example", "source_url": "https://example.com", "cited_claim": "CPI"}],
        "postgresql://example/db",
    )

    assert result["inserted_count"] == 1
    assert inserted == [{"article_id": 5, "source_url": "https://example.com"}]


def test_article_sources_failure_is_structured(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            if normalized.startswith("SAVEPOINT") or normalized.startswith("ROLLBACK") or normalized.startswith("RELEASE"):
                return
            if "INSERT INTO article_sources" in normalized:
                raise RuntimeError("source insert failed")

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

    _install_fake_psycopg(monkeypatch, FakeConnection())

    result = article_drafts.save_article_sources_to_postgres(
        5,
        [{"source_type": "forex_news", "source_name": "Example", "source_url": "https://example.com"}],
        "postgresql://example/db",
    )

    assert result["success"] is False
    assert result["failed_count"] == 1
    assert result["errors"][0]["error"] == "source insert failed"


def test_cli_dry_run_outputs_json(monkeypatch, capsys):
    monkeypatch.setattr(generate_article_drafts, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(generate_article_drafts, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        generate_article_drafts,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )
    monkeypatch.setattr(
        generate_article_drafts,
        "save_article_draft_to_postgres",
        lambda draft, dsn, dry_run=False: {
            "success": True,
            "dry_run": dry_run,
            "article_id": None,
            "inserted_count": 1,
            "skipped_count": 0,
            "failed_count": 0,
            "errors": [],
        },
    )
    article_sources_called = {"value": False}
    monkeypatch.setattr(
        generate_article_drafts,
        "save_article_sources_to_postgres",
        lambda *args, **kwargs: article_sources_called.update(value=True),
    )

    exit_code = generate_article_drafts.main(["--topic-id", "9", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["topic_id"] == 9
    assert payload["success"] is True
    assert payload["dry_run"] is True
    assert payload["summary"]["drafts_generated"] == 1
    assert payload["summary"]["drafts_inserted"] == 1
    assert payload["summary"]["inserted"] == 0
    assert payload["summary"]["would_insert"] == 1
    assert payload["draft"]["status"] == "pending_review"
    assert payload["draft"]["status"] != "published"
    assert payload["source_bundle"]["sources"][0]["title"] == "USD/IDR dan CPI menjadi perhatian"
    assert "safety_result" in payload
    assert payload["safety_result"]["fact_check_status"] == "pending"
    assert "quality_result" in payload
    assert payload["quality_result"]["recommendation"] not in {"approved", "published"}
    assert payload["draft"]["status"] not in {"approved", "published"}
    assert article_sources_called["value"] is False


def test_cli_missing_topic_returns_structured_error(monkeypatch, capsys):
    monkeypatch.setattr(generate_article_drafts, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(generate_article_drafts, "fetch_topic_for_draft", lambda dsn, topic_id: None)

    exit_code = generate_article_drafts.main(["--topic-id", "404", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["success"] is False
    assert payload["errors"] == [{"topic_id": 404, "error": "Topic not found: 404"}]


def test_cli_unsupported_template_returns_structured_error(monkeypatch, capsys):
    monkeypatch.setattr(generate_article_drafts, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(
        generate_article_drafts,
        "fetch_topic_for_draft",
        lambda dsn, topic_id: _topic(id=topic_id, topic_type="bank_indonesia_watch"),
    )
    monkeypatch.setattr(
        generate_article_drafts,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": [], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )

    exit_code = generate_article_drafts.main(["--topic-id", "3", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["success"] is False
    assert payload["errors"][0]["code"] == "unsupported_topic_type"


def test_cli_save_db_inserted_writes_article_sources(monkeypatch, capsys):
    saved_sources = []
    monkeypatch.setattr(generate_article_drafts, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(generate_article_drafts, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        generate_article_drafts,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )
    monkeypatch.setattr(
        generate_article_drafts,
        "save_article_draft_to_postgres",
        lambda draft, dsn, dry_run=False: {
            "success": True,
            "dry_run": dry_run,
            "article_id": 77,
            "inserted_count": 1,
            "skipped_count": 0,
            "failed_count": 0,
            "errors": [],
        },
    )

    def fake_save_sources(article_id, sources, dsn, dry_run=False):
        saved_sources.extend(sources)
        return {"success": True, "dry_run": dry_run, "inserted_count": len(sources), "failed_count": 0, "skipped_count": 0, "errors": []}

    monkeypatch.setattr(generate_article_drafts, "save_article_sources_to_postgres", fake_save_sources)

    exit_code = generate_article_drafts.main(["--topic-id", "9", "--save-db"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["summary"]["article_sources_inserted"] == 1
    assert "quality_result" in payload
    assert "safety_result" in payload
    assert "source_bundle" in payload
    assert payload["quality_result"]["recommendation"] not in {"approved", "published"}
    assert payload["draft"]["status"] not in {"approved", "published"}
    assert saved_sources[0]["source_type"] == "forex_news"
    assert saved_sources[0]["source_url"] == "https://example.com/source-10"


def test_cli_duplicate_draft_does_not_write_article_sources(monkeypatch, capsys):
    article_sources_called = {"value": False}
    monkeypatch.setattr(generate_article_drafts, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(generate_article_drafts, "fetch_topic_for_draft", lambda dsn, topic_id: _topic(id=topic_id))
    monkeypatch.setattr(
        generate_article_drafts,
        "fetch_source_news_for_topic",
        lambda dsn, topic: {"sources": _source_bundle()["sources"], "missing_source_news_ids": [], "warnings": [], "errors": []},
    )
    monkeypatch.setattr(
        generate_article_drafts,
        "save_article_draft_to_postgres",
        lambda draft, dsn, dry_run=False: {
            "success": True,
            "dry_run": dry_run,
            "article_id": None,
            "inserted_count": 0,
            "skipped_count": 1,
            "failed_count": 0,
            "errors": [],
        },
    )
    monkeypatch.setattr(
        generate_article_drafts,
        "save_article_sources_to_postgres",
        lambda *args, **kwargs: article_sources_called.update(value=True),
    )

    exit_code = generate_article_drafts.main(["--topic-id", "9", "--save-db"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["summary"]["drafts_skipped"] == 1
    assert payload["summary"]["article_sources_inserted"] == 0
    assert article_sources_called["value"] is False
