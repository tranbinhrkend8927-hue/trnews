import json
import sys
import types

from news_pipeline import fetch_forex_news_json as forex_news


class FakeScraper:
    def __init__(self, headlines=None, articles=None, fail_symbols=None):
        self.headlines = headlines or {}
        self.articles = articles or {}
        self.fail_symbols = set(fail_symbols or [])
        self.calls = []
        self.content_calls = []

    def scrape_headlines(self, symbol, exchange, sort, language):
        self.calls.append((symbol, exchange, sort, language))
        if symbol in self.fail_symbols:
            raise RuntimeError(f"{symbol} failed")
        return self.headlines.get(symbol, [])

    def scrape_news_content(self, story_path):
        self.content_calls.append(story_path)
        article = self.articles.get(story_path)
        if isinstance(article, Exception):
            raise article
        return article or {
            "breadcrumbs": None,
            "title": None,
            "published_datetime": None,
            "related_symbols": [],
            "body": [],
            "tags": [],
        }


def _source(symbol="USDIDR"):
    return {
        "url": f"https://id.tradingview.com/symbols/{symbol}/news/",
        "base_currency": symbol[:3],
        "quote_currency": symbol[3:],
        "locale": "id",
        "language": "id",
        "exchange": "FX_IDC",
        "enabled": True,
    }


def test_result_is_json_serializable():
    scraper = FakeScraper(
        headlines={
            "USDIDR": [
                {
                    "id": "n1",
                    "title": "Headline title",
                    "source": "TradingView",
                    "published": 1767225600,
                    "storyPath": "/news/test-story/",
                }
            ]
        },
        articles={
            "/news/test-story/": {
                "title": "Article title",
                "published_datetime": "2026-01-01T00:00:00Z",
                "body": [{"type": "text", "content": "Body text"}],
                "related_symbols": [{"symbol": "FX_IDC:USDIDR", "logo": object()}],
                "tags": ["FX"],
            }
        },
    )

    result = forex_news.fetch_forex_news_batch([("USDIDR", _source())], scraper=scraper, limit=10)

    dumped = json.dumps(result, ensure_ascii=False)
    assert "Article title" in dumped
    assert result["items"][0]["published_at"] == "2026-01-01T00:00:00Z"
    assert result["items"][0]["content"] == "Body text"


def test_usdidr_config_has_expected_url(monkeypatch):
    monkeypatch.delenv("FOREX_NEWS_SOURCES_JSON", raising=False)

    sources = forex_news.load_forex_news_sources()

    assert sources["USDIDR"] == {
        "url": "https://id.tradingview.com/symbols/USDIDR/news/",
        "base_currency": "USD",
        "quote_currency": "IDR",
        "locale": "id",
        "language": "id",
        "exchange": "FX_IDC",
        "enabled": True,
    }


def test_source_config_override_supports_future_symbols(monkeypatch):
    monkeypatch.setenv(
        "FOREX_NEWS_SOURCES_JSON",
        json.dumps(
            {
                "usdidr": _source("USDIDR"),
                "eurusd": {
                    "url": "https://www.tradingview.com/symbols/EURUSD/news/",
                    "base_currency": "EUR",
                    "quote_currency": "USD",
                    "locale": "www",
                    "language": "en",
                    "exchange": "FX_IDC",
                    "enabled": True,
                },
            }
        ),
    )

    sources = forex_news.load_forex_news_sources()

    assert list(sources) == ["USDIDR", "EURUSD"]
    assert sources["EURUSD"]["base_currency"] == "EUR"


def test_unknown_symbol_returns_clear_error():
    targets, errors = forex_news.resolve_sources(
        symbol="NOPE",
        all_symbols=False,
        url=None,
        sources={"USDIDR": _source()},
    )

    assert targets == []
    assert errors == [{"symbol": "NOPE", "source_url": None, "error": "Unknown symbol: NOPE"}]


def test_symbols_resolves_multiple_and_skips_disabled():
    targets, errors = forex_news.resolve_sources(
        symbol=None,
        symbols="USDIDR,USDJPY,USDOFF",
        all_symbols=False,
        url=None,
        sources={
            "USDIDR": _source("USDIDR"),
            "USDJPY": _source("USDJPY"),
            "USDOFF": {**_source("USDOFF"), "enabled": False},
        },
    )

    assert [symbol for symbol, _source_config in targets] == ["USDIDR", "USDJPY"]
    assert errors == [
        {
            "symbol": "USDOFF",
            "source_url": "https://id.tradingview.com/symbols/USDOFF/news/",
            "error": "Symbol is disabled: USDOFF",
        }
    ]


def test_all_reads_enabled_symbols_only():
    targets, errors = forex_news.resolve_sources(
        symbol=None,
        symbols=None,
        all_symbols=True,
        url=None,
        sources={
            "USDIDR": _source("USDIDR"),
            "USDOFF": {**_source("USDOFF"), "enabled": False},
        },
    )

    assert errors == []
    assert [symbol for symbol, _source_config in targets] == ["USDIDR"]


def test_split_postgres_dsn_uses_maintenance_database(monkeypatch):
    monkeypatch.setenv("POSTGRES_MAINTENANCE_DB", "postgres")

    maintenance_dsn, database = forex_news.split_postgres_dsn(
        "postgresql://user:pass@localhost:5432/tradingview_news"
    )

    assert maintenance_dsn == "postgresql://user:pass@localhost:5432/postgres"
    assert database == "tradingview_news"


def test_postgres_schema_file_defines_unified_news_tables_and_unique_indexes():
    schema_sql = forex_news.load_postgres_schema_sql()
    normalized = " ".join(schema_sql.lower().split())

    assert "create table if not exists forex_symbols" in normalized
    assert "create table if not exists forex_news" in normalized
    assert "create table if not exists content_topics" in normalized
    assert "create table if not exists generated_articles" in normalized
    assert "create table if not exists article_sources" in normalized
    assert "create table if not exists article_reviews" in normalized
    assert "create table if not exists usdidr" not in normalized
    assert "create unique index if not exists forex_news_symbol_canonical_url_uidx" in normalized
    assert "on forex_news(symbol, canonical_url)" in normalized
    assert "create unique index if not exists forex_news_symbol_content_hash_uidx" in normalized
    assert "on forex_news(symbol, content_hash)" in normalized
    assert "create unique index if not exists content_topics_symbol_topic_hash_uidx" in normalized
    assert "on content_topics(symbol, topic_hash)" in normalized
    assert "daily_usdidr_update" in normalized
    assert "bank_indonesia_watch" in normalized
    assert "generated_articles_status_check" in normalized
    assert "generated_articles_fact_check_status_check" in normalized
    assert "foreign key (topic_id) references content_topics(id) on delete restrict" in normalized
    assert "foreign key (article_id) references generated_articles(id) on delete cascade" in normalized
    assert "create unique index if not exists generated_articles_topic_id_uidx" in normalized
    assert "article_reviews_decision_check" in normalized
    assert "decision in ('approved', 'rejected', 'needs_changes')" in normalized
    assert "article_id bigint not null references generated_articles(id) on delete cascade" in normalized
    assert "create index if not exists idx_article_reviews_article_id" in normalized
    assert "create index if not exists idx_article_reviews_decision" in normalized
    assert "create index if not exists idx_article_reviews_created_at" in normalized
    assert "create table if not exists article_exports" in normalized
    assert "article_exports_target_check" in normalized
    assert "target in ('notion')" in normalized
    assert "article_exports_status_check" in normalized
    assert "status in ('dry_run', 'exported', 'failed', 'skipped')" in normalized
    assert "article_id bigint not null references generated_articles(id) on delete cascade" in normalized
    assert "create index if not exists idx_article_exports_article_id" in normalized
    assert "create index if not exists idx_article_exports_target" in normalized
    assert "create index if not exists idx_article_exports_status" in normalized
    assert "create index if not exists idx_article_exports_exported_at" in normalized


def test_init_postgres_schema_executes_schema_file(monkeypatch):
    executed = []

    class FakeSQL:
        def __init__(self, value):
            self.value = value

        def format(self, identifier):
            return f"{self.value} {identifier.value}"

    class FakeIdentifier:
        def __init__(self, value):
            self.value = value

    class FakeSqlModule:
        SQL = FakeSQL
        Identifier = FakeIdentifier

    class FakeCursor:
        def __init__(self, maintenance=False):
            self.maintenance = maintenance
            self.next_fetchone = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            executed.append(str(query))
            if self.maintenance and "SELECT 1 FROM pg_database" in str(query):
                self.next_fetchone = None

        def fetchone(self):
            return self.next_fetchone

    class FakeConnection:
        def __init__(self, maintenance=False):
            self.maintenance = maintenance

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor(maintenance=self.maintenance)

        def commit(self):
            executed.append("COMMIT")

    def fake_connect(dsn, autocommit=False):
        return FakeConnection(maintenance=autocommit)

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = fake_connect
    psycopg_module.sql = FakeSqlModule
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setattr(
        forex_news,
        "load_postgres_schema_sql",
        lambda: "CREATE TABLE IF NOT EXISTS forex_symbols (id BIGSERIAL);"
        "CREATE UNIQUE INDEX IF NOT EXISTS forex_news_symbol_content_hash_uidx ON forex_news(symbol, content_hash);",
    )

    result = forex_news.init_postgres_schema("postgresql://user:pass@localhost:5432/tradingview_news")

    assert result == {"success": True, "database": "tradingview_news", "created_database": True}
    assert any("CREATE DATABASE" in query for query in executed)
    assert "CREATE TABLE IF NOT EXISTS forex_symbols (id BIGSERIAL)" in executed
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS forex_news_symbol_content_hash_uidx "
        "ON forex_news(symbol, content_hash)"
    ) in executed
    assert executed[-1] == "COMMIT"


def test_empty_news_list_returns_empty_items():
    scraper = FakeScraper(headlines={"USDIDR": []})

    result = forex_news.fetch_forex_news_batch([("USDIDR", _source())], scraper=scraper)

    assert result["count"] == 0
    assert result["items"] == []
    assert result["errors"] == []


def test_malformed_article_does_not_crash():
    scraper = FakeScraper(
        headlines={
            "USDIDR": [
                {
                    "title": "Headline fallback",
                    "source": "TradingView",
                    "published": 1767225600,
                    "storyPath": "/news/malformed/",
                }
            ]
        },
        articles={"/news/malformed/": {"body": []}},
    )

    result = forex_news.fetch_forex_news_batch([("USDIDR", _source())], scraper=scraper)

    assert result["count"] == 1
    assert result["items"][0]["title"] == "Headline fallback"
    assert result["items"][0]["content"] == ""


def test_cli_symbol_outputs_json(monkeypatch, capsys):
    scraper = FakeScraper(headlines={"USDIDR": []})
    monkeypatch.setattr(forex_news, "NewsScraper", lambda: scraper)
    monkeypatch.setattr(forex_news, "load_forex_news_sources", lambda: {"USDIDR": _source()})

    exit_code = forex_news.main(["--symbol", "USDIDR"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["results"][0]["symbol"] == "USDIDR"
    assert payload["summary"]["symbols_success"] == 1
    assert scraper.calls == [("USDIDR", "FX_IDC", "latest", "id")]


def test_cli_all_isolates_symbol_errors(monkeypatch, capsys):
    scraper = FakeScraper(headlines={"USDIDR": []}, fail_symbols={"USDJPY"})
    monkeypatch.setattr(forex_news, "NewsScraper", lambda: scraper)
    monkeypatch.setattr(
        forex_news,
        "load_forex_news_sources",
        lambda: {
            "USDIDR": _source("USDIDR"),
            "USDJPY": _source("USDJPY"),
        },
    )

    exit_code = forex_news.main(["--all"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["summary"]["symbols_success"] == 1
    assert payload["summary"]["symbols_failed"] == 1
    assert payload["results"][0]["symbol"] == "USDIDR"
    assert payload["results"][0]["success"] is True
    assert payload["results"][1]["symbol"] == "USDJPY"
    assert payload["results"][1]["success"] is False
    assert payload["results"][1]["error"] == "USDJPY failed"
    assert payload["errors"] == [
        {
            "symbol": "USDJPY",
            "source_url": "https://id.tradingview.com/symbols/USDJPY/news/",
            "error": "USDJPY failed",
        }
    ]


def test_cli_url_with_symbol_uses_temporary_source(monkeypatch, capsys):
    scraper = FakeScraper(headlines={"USDIDR": []})
    monkeypatch.setattr(forex_news, "NewsScraper", lambda: scraper)
    monkeypatch.setattr(forex_news, "load_forex_news_sources", lambda: {})

    exit_code = forex_news.main(["--url", "https://id.tradingview.com/symbols/USDIDR/news/", "--symbol", "USDIDR"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["results"][0]["source_url"] == "https://id.tradingview.com/symbols/USDIDR/news/"
    assert scraper.calls == [("USDIDR", "FX_IDC", "latest", "id")]


def test_cli_symbols_outputs_batch_summary(monkeypatch, capsys):
    scraper = FakeScraper(headlines={"USDIDR": [], "USDJPY": []})
    monkeypatch.setattr(forex_news, "NewsScraper", lambda: scraper)
    monkeypatch.setattr(
        forex_news,
        "load_forex_news_sources",
        lambda: {"USDIDR": _source("USDIDR"), "USDJPY": _source("USDJPY")},
    )

    exit_code = forex_news.main(["--symbols", "USDIDR,USDJPY"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["requested_symbols"] == ["USDIDR", "USDJPY"]
    assert payload["summary"]["symbols_total"] == 2
    assert payload["summary"]["symbols_success"] == 2
    assert [call[0] for call in scraper.calls] == ["USDIDR", "USDJPY"]


def test_temporary_url_maps_tradingview_locale_to_language():
    jpy_source = forex_news.infer_source_from_url("USDJPY", "https://jp.tradingview.com/symbols/USDJPY/news/")
    krw_source = forex_news.infer_source_from_url("USDKRW", "https://kr.tradingview.com/symbols/USDKRW/news/")

    assert jpy_source["locale"] == "jp"
    assert jpy_source["language"] == "ja"
    assert krw_source["locale"] == "kr"
    assert krw_source["language"] == "ko"


def test_deduplicates_same_symbol_and_url():
    headline = {
        "title": "Same story",
        "source": "TradingView",
        "published": 1767225600,
        "storyPath": "/news/same/",
    }
    scraper = FakeScraper(headlines={"USDIDR": [headline, dict(headline)]})

    result = forex_news.fetch_forex_news_batch([("USDIDR", _source())], scraper=scraper)

    assert result["count"] == 1
    assert result["items"][0]["url"] == "https://www.tradingview.com/news/same/"
    assert result["summary"]["items_fetched"] == 1


def test_article_failure_is_reported_but_item_uses_headline_fields():
    scraper = FakeScraper(
        headlines={
            "USDIDR": [
                {
                    "title": "Headline only",
                    "source": "TradingView",
                    "published": 1767225600,
                    "storyPath": "/news/bad-article/",
                }
            ]
        },
        articles={"/news/bad-article/": RuntimeError("article failed")},
    )

    result = forex_news.fetch_forex_news_batch([("USDIDR", _source())], scraper=scraper)

    assert result["count"] == 1
    assert result["items"][0]["title"] == "Headline only"
    assert result["errors"] == [
        {
            "symbol": "USDIDR",
            "source_url": "https://id.tradingview.com/symbols/USDIDR/news/",
            "story_path": "/news/bad-article/",
            "error": "article failed",
        }
    ]


def test_existing_db_item_skips_body_fetch():
    headline = {
        "title": "Existing story",
        "source": "TradingView",
        "published": 1767225600,
        "storyPath": "/news/existing/",
    }
    scraper = FakeScraper(headlines={"USDIDR": [headline]})
    checked_items = []

    def existing_checker(item):
        checked_items.append(item)
        return True, "canonical_url"

    result = forex_news.fetch_forex_news_batch(
        [("USDIDR", _source())],
        scraper=scraper,
        existing_checker=existing_checker,
    )

    assert scraper.content_calls == []
    assert len(checked_items) == 1
    assert result["items"][0]["db_status"] == "skipped"
    assert result["items"][0]["db_skip_reason"] == "canonical_url"
    assert result["items"][0]["body_fetch_skipped"] is True
    assert result["items"][0]["content"] == ""


def test_content_hash_is_stable_for_whitespace_case_and_url_slash():
    first = forex_news.build_content_hash(
        "USDIDR",
        "  Rupiah   Update ",
        "https://www.tradingview.com/news/story/",
        "2026-01-01T00:00:00Z",
        "FXStreet",
    )
    second = forex_news.build_content_hash(
        "usdidr",
        "rupiah update",
        "https://www.tradingview.com/news/story",
        "2026-01-01T00:00:00Z",
        "fxstreet",
    )

    assert first == second


def test_no_db_does_not_call_database_save(monkeypatch, capsys):
    scraper = FakeScraper(headlines={"USDIDR": []})
    monkeypatch.setattr(forex_news, "NewsScraper", lambda: scraper)
    monkeypatch.setattr(forex_news, "load_forex_news_sources", lambda: {"USDIDR": _source()})

    def fail_save(*args, **kwargs):
        raise AssertionError("database should not be called")

    monkeypatch.setattr(forex_news, "save_result_to_postgres", fail_save)
    exit_code = forex_news.main(["--symbol", "USDIDR", "--no-db"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert "database" not in payload


def test_dry_run_calls_database_without_writing(monkeypatch, capsys):
    scraper = FakeScraper(
        headlines={
            "USDIDR": [
                {
                    "title": "Dry run story",
                    "source": "TradingView",
                    "published": 1767225600,
                    "storyPath": "/news/dry-run/",
                }
            ]
        }
    )
    calls = []
    monkeypatch.setattr(forex_news, "NewsScraper", lambda: scraper)
    monkeypatch.setattr(forex_news, "load_forex_news_sources", lambda: {"USDIDR": _source()})
    monkeypatch.setattr(forex_news, "get_postgres_dsn", lambda: "postgresql://user:pass@localhost/db")

    class FakeChecker:
        def __init__(self, dsn):
            self.dsn = dsn

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __call__(self, item):
            return False, None

    monkeypatch.setattr(forex_news, "PostgresNewsExistenceChecker", FakeChecker)

    def fake_save(result, targets, dsn, dry_run=False):
        calls.append({"dsn": dsn, "dry_run": dry_run, "targets": list(targets)})
        for item in result["items"]:
            item["db_status"] = "would_insert"
        return {"success": True, "dry_run": dry_run, "inserted_count": 1, "skipped_count": 0, "failed_count": 0, "errors": []}

    monkeypatch.setattr(forex_news, "save_result_to_postgres", fake_save)

    exit_code = forex_news.main(["--symbol", "USDIDR", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls == [{"dsn": "postgresql://user:pass@localhost/db", "dry_run": True, "targets": [("USDIDR", _source())]}]
    assert payload["summary"]["items_inserted"] == 1
    assert payload["database"]["save"]["dry_run"] is True


def test_save_db_outputs_batch_summary_and_database_save(monkeypatch, capsys):
    scraper = FakeScraper(
        headlines={
            "USDIDR": [
                {
                    "title": "Save story",
                    "source": "TradingView",
                    "published": 1767225600,
                    "storyPath": "/news/save-story/",
                }
            ]
        }
    )
    monkeypatch.setattr(forex_news, "NewsScraper", lambda: scraper)
    monkeypatch.setattr(forex_news, "load_forex_news_sources", lambda: {"USDIDR": _source()})
    monkeypatch.setattr(forex_news, "get_postgres_dsn", lambda: "postgresql://user:pass@localhost/db")

    class FakeChecker:
        def __init__(self, dsn):
            self.dsn = dsn

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __call__(self, item):
            return False, None

    monkeypatch.setattr(forex_news, "PostgresNewsExistenceChecker", FakeChecker)
    monkeypatch.setattr(
        forex_news,
        "save_result_to_postgres",
        lambda result, targets, dsn, dry_run=False: {
            "success": True,
            "dry_run": dry_run,
            "symbols_upserted": 1,
            "inserted_count": 1,
            "skipped_count": 0,
            "failed_count": 0,
            "errors": [],
        },
    )

    exit_code = forex_news.main(["--symbol", "USDIDR", "--save-db"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["requested_symbols"] == ["USDIDR"]
    assert payload["summary"] == {
        "symbols_total": 1,
        "symbols_success": 1,
        "symbols_failed": 0,
        "items_fetched": 1,
        "items_inserted": 1,
        "items_skipped": 0,
        "items_failed": 0,
    }
    assert payload["results"][0]["items_inserted"] == 1
    assert payload["items"][0]["title"] == "Save story"
    assert payload["database"]["save"] == {
        "success": True,
        "dry_run": False,
        "symbols_upserted": 1,
        "inserted_count": 1,
        "skipped_count": 0,
        "failed_count": 0,
        "errors": [],
    }


def test_save_result_to_postgres_inserts_then_skips_duplicates(monkeypatch):
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
            if "INSERT INTO forex_symbols" in normalized:
                self.next_fetchone = None
                return
            if "SELECT 1 FROM forex_news WHERE symbol = %s AND canonical_url = %s" in normalized:
                self.next_fetchone = (1,) if any(row["symbol"] == params[0] and row["canonical_url"] == params[1] for row in state["rows"]) else None
                return
            if "SELECT 1 FROM forex_news WHERE symbol = %s AND url = %s" in normalized:
                self.next_fetchone = (1,) if any(row["symbol"] == params[0] and row["url"] == params[1] for row in state["rows"]) else None
                return
            if "SELECT 1 FROM forex_news WHERE symbol = %s AND content_hash = %s" in normalized:
                self.next_fetchone = (1,) if any(row["symbol"] == params[0] and row["content_hash"] == params[1] for row in state["rows"]) else None
                return
            if "INSERT INTO forex_news" in normalized:
                row = {
                    "symbol": params[0],
                    "url": params[7],
                    "canonical_url": params[8],
                    "content_hash": params[13],
                }
                duplicate = any(
                    existing["symbol"] == row["symbol"]
                    and (
                        existing["canonical_url"] == row["canonical_url"]
                        or existing["url"] == row["url"]
                        or existing["content_hash"] == row["content_hash"]
                    )
                    for existing in state["rows"]
                )
                if duplicate:
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

    item = {
        "symbol": "USDIDR",
        "base_currency": "USD",
        "quote_currency": "IDR",
        "locale": "id",
        "title": "Story",
        "summary": "",
        "content": "",
        "url": "https://www.tradingview.com/news/story/",
        "canonical_url": "https://www.tradingview.com/news/story",
        "source": "TradingView",
        "published_at": "2026-01-01T00:00:00Z",
        "fetched_at": "2026-01-01T00:01:00Z",
        "source_url": "https://id.tradingview.com/symbols/USDIDR/news/",
        "content_hash": "hash-1",
        "raw": {},
    }

    first = {"items": [dict(item)]}
    second = {"items": [dict(item)]}
    targets = [("USDIDR", _source())]

    first_result = forex_news.save_result_to_postgres(first, targets, "postgresql://example/db")
    second_result = forex_news.save_result_to_postgres(second, targets, "postgresql://example/db")

    assert first_result["inserted_count"] == 1
    assert first_result["skipped_count"] == 0
    assert second_result["inserted_count"] == 0
    assert second_result["skipped_count"] == 1
    assert len(state["rows"]) == 1
