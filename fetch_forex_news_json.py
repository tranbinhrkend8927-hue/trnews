"""Fetch TradingView forex news and print database-friendly JSON.

Examples:
    .venv/bin/python fetch_forex_news_json.py --symbol USDIDR
    .venv/bin/python fetch_forex_news_json.py --all
    .venv/bin/python fetch_forex_news_json.py --url https://id.tradingview.com/symbols/USDIDR/news/ --symbol USDIDR
"""

import argparse
import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

from tradingview_scraper.symbols.news import NewsScraper


POSTGRES_SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "postgres_forex_news.sql"


LOCALE_LANGUAGE_MAP = {
    "www": "en",
    "com": "en",
    "id": "id",
    "jp": "ja",
    "ja": "ja",
    "kr": "ko",
    "ko": "ko",
    "cn": "ch",
    "zh": "ch",
}


DEFAULT_FOREX_NEWS_SOURCES = {
    "USDIDR": {
        "url": "https://id.tradingview.com/symbols/USDIDR/news/",
        "base_currency": "USD",
        "quote_currency": "IDR",
        "locale": "id",
        "language": "id",
        "exchange": "FX_IDC",
        "enabled": True,
    },
    "USDJPY": {
        "url": "https://jp.tradingview.com/symbols/USDJPY/news/",
        "base_currency": "USD",
        "quote_currency": "JPY",
        "locale": "jp",
        "language": "ja",
        "exchange": "FX_IDC",
        "enabled": True,
    },
    "USDKRW": {
        "url": "https://kr.tradingview.com/symbols/USDKRW/news/",
        "base_currency": "USD",
        "quote_currency": "KRW",
        "locale": "kr",
        "language": "ko",
        "exchange": "FX_IDC",
        "enabled": True,
    },
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def unix_to_iso(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        if isinstance(value, str):
            return value
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def canonicalize_url(value: Any) -> str:
    raw_url = str(value or "").strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        return raw_url.rstrip("/")

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    canonical = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        params="",
        query="",
        fragment="",
    )
    return urlunparse(canonical)


def json_safe(value: Any) -> Any:
    """Return a JSON-serializable copy of value, dropping parser objects safely."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


def load_forex_news_sources() -> Dict[str, Dict[str, Any]]:
    """Load source configuration from FOREX_NEWS_SOURCES_JSON or defaults."""
    raw_config = os.getenv("FOREX_NEWS_SOURCES_JSON", "").strip()
    if not raw_config:
        return copy.deepcopy(DEFAULT_FOREX_NEWS_SOURCES)

    try:
        loaded = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise ValueError("FOREX_NEWS_SOURCES_JSON must be valid JSON") from exc

    if not isinstance(loaded, dict):
        raise ValueError("FOREX_NEWS_SOURCES_JSON must be a JSON object keyed by symbol")

    normalized = {}
    for symbol, source in loaded.items():
        if not isinstance(source, dict):
            raise ValueError(f"Source config for {symbol} must be a JSON object")
        normalized[str(symbol).upper()] = dict(source)
    return normalized


def get_postgres_dsn() -> str:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        raise ValueError("POSTGRES_DSN is not configured")
    return dsn


def split_postgres_dsn(dsn: str) -> Tuple[str, str]:
    parsed = urlparse(dsn)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError("POSTGRES_DSN must use postgres:// or postgresql://")
    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("POSTGRES_DSN must include a database name")

    maintenance_db = os.getenv("POSTGRES_MAINTENANCE_DB", "postgres")
    maintenance = parsed._replace(path=f"/{maintenance_db}", query="", fragment="")
    return urlunparse(maintenance), database


def load_postgres_schema_sql(path: Path = POSTGRES_SCHEMA_PATH) -> str:
    return path.read_text(encoding="utf-8")


def iter_postgres_schema_statements(schema_sql: str) -> List[str]:
    return [statement.strip() for statement in schema_sql.split(";") if statement.strip()]


def init_postgres_schema(dsn: str) -> Dict[str, Any]:
    """Create the target database and tables if they do not already exist."""
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    maintenance_dsn, database = split_postgres_dsn(dsn)
    created_database = False

    with psycopg.connect(maintenance_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
                created_database = True

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for statement in iter_postgres_schema_statements(load_postgres_schema_sql()):
                cur.execute(statement)
        conn.commit()

    return {"success": True, "database": database, "created_database": created_database}


def save_result_to_postgres(
    result: Dict[str, Any],
    targets: Iterable[Tuple[str, Dict[str, Any]]],
    dsn: str,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Insert new configured symbols/news into Postgres and skip duplicates."""
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    target_map = {symbol: source for symbol, source in targets}
    symbols_upserted = 0
    inserted_count = 0
    skipped_count = 0
    failed_count = 0
    errors = []

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            if not dry_run:
                for symbol, source in target_map.items():
                    cur.execute(
                        """
                        INSERT INTO forex_symbols (
                            symbol, base_currency, quote_currency, locale,
                            tradingview_news_url, enabled, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (symbol) DO UPDATE SET
                            base_currency = EXCLUDED.base_currency,
                            quote_currency = EXCLUDED.quote_currency,
                            locale = EXCLUDED.locale,
                            tradingview_news_url = EXCLUDED.tradingview_news_url,
                            enabled = EXCLUDED.enabled,
                            updated_at = NOW()
                        """,
                        (
                            symbol,
                            source.get("base_currency"),
                            source.get("quote_currency"),
                            source.get("locale"),
                            source.get("url"),
                            bool(source.get("enabled", True)),
                        ),
                    )
                    symbols_upserted += 1

            for item in result.get("items", []):
                cur.execute("SAVEPOINT forex_news_item")
                try:
                    exists, reason = news_item_exists(cur, item)
                    if exists:
                        skipped_count += 1
                        item["db_status"] = "skipped"
                        item["db_skip_reason"] = reason
                        cur.execute("RELEASE SAVEPOINT forex_news_item")
                        continue

                    if dry_run:
                        inserted_count += 1
                        item["db_status"] = "would_insert"
                        cur.execute("RELEASE SAVEPOINT forex_news_item")
                        continue

                    raw_json = Jsonb(item.get("raw") or {})
                    cur.execute(
                        """
                        INSERT INTO forex_news (
                            symbol, base_currency, quote_currency, locale,
                            title, summary, content, url, canonical_url, source,
                            published_at, fetched_at, source_url, content_hash,
                            raw_json, updated_at
                        )
                        VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, NOW()
                        )
                        ON CONFLICT DO NOTHING
                        RETURNING id
                        """,
                        (
                            item.get("symbol"),
                            item.get("base_currency"),
                            item.get("quote_currency"),
                            item.get("locale"),
                            item.get("title"),
                            item.get("summary"),
                            item.get("content"),
                            item.get("url"),
                            item.get("canonical_url"),
                            item.get("source"),
                            item.get("published_at"),
                            item.get("fetched_at"),
                            item.get("source_url"),
                            item.get("content_hash"),
                            raw_json,
                        ),
                    )
                    inserted = cur.fetchone() is not None
                    if inserted:
                        inserted_count += 1
                        item["db_status"] = "inserted"
                    else:
                        skipped_count += 1
                        item["db_status"] = "skipped"
                        item["db_skip_reason"] = "conflict"
                    cur.execute("RELEASE SAVEPOINT forex_news_item")
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT forex_news_item")
                    cur.execute("RELEASE SAVEPOINT forex_news_item")
                    failed_count += 1
                    error = {
                        "symbol": item.get("symbol"),
                        "url": item.get("url"),
                        "content_hash": item.get("content_hash"),
                        "error": str(exc),
                    }
                    errors.append(error)
                    item["db_status"] = "failed"
                    item["db_error"] = str(exc)
        conn.commit()

    return {
        "success": True,
        "dry_run": dry_run,
        "symbols_upserted": symbols_upserted,
        "inserted_count": inserted_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "errors": errors,
    }


def news_item_exists(cur: Any, item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    symbol = item.get("symbol")
    canonical_url = item.get("canonical_url")
    url = item.get("url")
    content_hash = item.get("content_hash")

    if canonical_url:
        cur.execute(
            "SELECT 1 FROM forex_news WHERE symbol = %s AND canonical_url = %s LIMIT 1",
            (symbol, canonical_url),
        )
        if cur.fetchone() is not None:
            return True, "canonical_url"

    if url:
        cur.execute(
            "SELECT 1 FROM forex_news WHERE symbol = %s AND url = %s LIMIT 1",
            (symbol, url),
        )
        if cur.fetchone() is not None:
            return True, "url"

    if content_hash:
        cur.execute(
            "SELECT 1 FROM forex_news WHERE symbol = %s AND content_hash = %s LIMIT 1",
            (symbol, content_hash),
        )
        if cur.fetchone() is not None:
            return True, "content_hash"

    return False, None


class PostgresNewsExistenceChecker:
    """Reusable DB existence checker used before fetching article bodies."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn = None

    def __enter__(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required for database operations") from exc

        self.conn = psycopg.connect(self.dsn)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        return False

    def __call__(self, item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if self.conn is None:
            raise RuntimeError("PostgresNewsExistenceChecker must be used as a context manager")
        with self.conn.cursor() as cur:
            return news_item_exists(cur, item)


def infer_source_from_url(symbol: str, url: str, existing_source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source = dict(existing_source or {})
    parsed = urlparse(url)
    host = parsed.netloc.split(":")[0]
    host_locale = host.split(".")[0] if host else "www"
    locale = source.get("locale") or ("en" if host_locale == "www" else host_locale)
    language = source.get("language") or LOCALE_LANGUAGE_MAP.get(locale, locale)
    symbol = symbol.upper()

    source.update(
        {
            "url": url,
            "base_currency": source.get("base_currency") or symbol[:3] or None,
            "quote_currency": source.get("quote_currency") or symbol[3:] or None,
            "locale": locale,
            "language": language or "en",
            "exchange": source.get("exchange") or "FX_IDC",
            "enabled": True,
        }
    )
    return source


def resolve_sources(
    *,
    symbol: Optional[str],
    symbols: Optional[str] = None,
    all_symbols: bool,
    url: Optional[str],
    sources: Dict[str, Dict[str, Any]],
) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[Dict[str, Any]]]:
    errors = []

    if all_symbols and url:
        return [], [{"symbol": None, "source_url": url, "error": "--url cannot be combined with --all"}]
    if all_symbols and symbol:
        return [], [{"symbol": symbol.upper(), "source_url": None, "error": "--symbol cannot be combined with --all"}]
    if all_symbols and symbols:
        return [], [{"symbol": None, "source_url": None, "error": "--symbols cannot be combined with --all"}]
    if symbol and symbols:
        return [], [{"symbol": symbol.upper(), "source_url": None, "error": "--symbol cannot be combined with --symbols"}]
    if symbols and url:
        return [], [{"symbol": None, "source_url": url, "error": "--url cannot be combined with --symbols"}]
    if url and not symbol:
        return [], [{"symbol": None, "source_url": url, "error": "--url requires --symbol"}]

    if all_symbols:
        targets = [
            (item_symbol, dict(source))
            for item_symbol, source in sources.items()
            if source.get("enabled", True)
        ]
        return targets, errors

    if symbols:
        targets = []
        seen_symbols = set()
        for raw_symbol in symbols.split(","):
            selected_symbol = raw_symbol.strip().upper()
            if not selected_symbol or selected_symbol in seen_symbols:
                continue
            seen_symbols.add(selected_symbol)
            source = sources.get(selected_symbol)
            if not source:
                errors.append({"symbol": selected_symbol, "source_url": None, "error": f"Unknown symbol: {selected_symbol}"})
                continue
            if not source.get("enabled", True):
                errors.append(
                    {
                        "symbol": selected_symbol,
                        "source_url": source.get("url"),
                        "error": f"Symbol is disabled: {selected_symbol}",
                    }
                )
                continue
            targets.append((selected_symbol, dict(source)))
        return targets, errors

    selected_symbol = (symbol or "USDIDR").upper()
    source = sources.get(selected_symbol)
    if url:
        return [(selected_symbol, infer_source_from_url(selected_symbol, url, source))], errors
    if not source:
        return [], [{"symbol": selected_symbol, "source_url": None, "error": f"Unknown symbol: {selected_symbol}"}]
    if not source.get("enabled", True):
        return [], [{"symbol": selected_symbol, "source_url": source.get("url"), "error": f"Symbol is disabled: {selected_symbol}"}]
    return [(selected_symbol, dict(source))], errors


def build_content_hash(
    symbol: str,
    title: str,
    canonical_url: str = "",
    published_at: Optional[str] = None,
    source: Optional[str] = None,
) -> str:
    payload = "\n".join(
        [
            normalize_text(symbol).upper(),
            normalize_text(title),
            canonicalize_url(canonical_url),
            published_at or "",
            normalize_text(source),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_news_item(
    *,
    symbol: str,
    source_config: Dict[str, Any],
    headline: Dict[str, Any],
    article: Dict[str, Any],
    fetched_at: str,
) -> Dict[str, Any]:
    story_path = headline.get("storyPath") or headline.get("story_path") or ""
    url = headline.get("url") or (f"https://www.tradingview.com{story_path}" if story_path else "")
    body = article.get("body") or []
    body_text = [
        item.get("content", "")
        for item in body
        if isinstance(item, dict) and item.get("type") == "text" and item.get("content")
    ]
    content = "\n\n".join(body_text)
    title = article.get("title") or headline.get("title") or ""
    published_at = article.get("published_datetime") or unix_to_iso(headline.get("published"))
    summary = headline.get("summary") or headline.get("description") or ""
    canonical_url = canonicalize_url(url)
    source = headline.get("source")
    content_hash = build_content_hash(symbol, title, canonical_url or url, published_at, source)

    return {
        "symbol": symbol,
        "base_currency": source_config.get("base_currency"),
        "quote_currency": source_config.get("quote_currency"),
        "locale": source_config.get("locale"),
        "source_url": source_config.get("url"),
        "title": title,
        "summary": summary,
        "content": content,
        "url": url,
        "canonical_url": canonical_url,
        "source": source,
        "published_at": published_at,
        "fetched_at": fetched_at,
        "content_hash": content_hash,
        "raw": {
            "headline": json_safe(headline),
            "article": json_safe(article),
        },
    }


def empty_article() -> Dict[str, Any]:
    return {"breadcrumbs": None, "title": None, "published_datetime": None, "related_symbols": [], "body": [], "tags": []}


def fetch_symbol_news(
    symbol: str,
    source_config: Dict[str, Any],
    *,
    scraper: Optional[NewsScraper] = None,
    limit: int = 10,
    fetched_at: Optional[str] = None,
    existing_checker: Optional[Callable[[Dict[str, Any]], Tuple[bool, Optional[str]]]] = None,
) -> Dict[str, Any]:
    scraper = scraper or NewsScraper()
    fetched_at = fetched_at or utc_now_iso()
    exchange = source_config.get("exchange", "FX_IDC")
    language = source_config.get("language") or source_config.get("locale") or "en"

    headlines = scraper.scrape_headlines(
        symbol=symbol,
        exchange=exchange,
        sort="latest",
        language=language,
    )

    items = []
    errors = []
    seen = set()
    for headline in headlines[:limit]:
        story_path = headline.get("storyPath") or headline.get("story_path")
        article = empty_article()
        item = normalize_news_item(
            symbol=symbol,
            source_config=source_config,
            headline=headline,
            article=article,
            fetched_at=fetched_at,
        )

        if existing_checker is not None:
            try:
                exists, reason = existing_checker(item)
            except Exception as exc:
                errors.append(
                    {
                        "symbol": symbol,
                        "source_url": source_config.get("url"),
                        "story_path": story_path,
                        "error": f"DB precheck failed: {exc}",
                    }
                )
            else:
                if exists:
                    item["db_status"] = "skipped"
                    item["db_skip_reason"] = reason
                    item["body_fetch_skipped"] = True
                    dedupe_key = (symbol, item["url"]) if item.get("url") else (symbol, item["content_hash"])
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    items.append(item)
                    continue

        if story_path:
            try:
                article = scraper.scrape_news_content(story_path)
            except Exception as exc:
                errors.append({"symbol": symbol, "source_url": source_config.get("url"), "story_path": story_path, "error": str(exc)})

        item = normalize_news_item(
            symbol=symbol,
            source_config=source_config,
            headline=headline,
            article=article,
            fetched_at=fetched_at,
        )
        dedupe_key = (symbol, item["url"]) if item.get("url") else (symbol, item["content_hash"])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(item)

    return {
        "symbol": symbol,
        "success": True,
        "count": len(items),
        "items": items,
        "errors": errors,
    }


def fetch_forex_news_batch(
    targets: Iterable[Tuple[str, Dict[str, Any]]],
    *,
    scraper: Optional[NewsScraper] = None,
    limit: int = 10,
    initial_errors: Optional[List[Dict[str, Any]]] = None,
    existing_checker: Optional[Callable[[Dict[str, Any]], Tuple[bool, Optional[str]]]] = None,
) -> Dict[str, Any]:
    fetched_at = utc_now_iso()
    targets = list(targets)
    initial_errors = list(initial_errors or [])
    requested_symbols = [symbol for symbol, _source in targets]
    for error in initial_errors:
        error_symbol = error.get("symbol")
        if error_symbol and error_symbol not in requested_symbols:
            requested_symbols.append(error_symbol)
    result = {
        "fetched_at": fetched_at,
        "requested_symbols": requested_symbols,
        "summary": {
            "symbols_total": len(requested_symbols),
            "symbols_success": 0,
            "symbols_failed": sum(1 for error in initial_errors if error.get("symbol")),
            "items_fetched": 0,
            "items_inserted": 0,
            "items_skipped": 0,
            "items_failed": 0,
        },
        "count": 0,
        "items": [],
        "results": [],
        "errors": initial_errors,
    }

    for symbol, source_config in targets:
        try:
            symbol_result = fetch_symbol_news(
                symbol,
                source_config,
                scraper=scraper,
                limit=limit,
                fetched_at=fetched_at,
                existing_checker=existing_checker,
            )
            result["items"].extend(symbol_result["items"])
            result["errors"].extend(symbol_result["errors"])
            item_count = symbol_result["count"]
            result["results"].append(
                {
                    "symbol": symbol,
                    "source_url": source_config.get("url"),
                    "success": True,
                    "count": item_count,
                    "items_fetched": item_count,
                    "items_inserted": 0,
                    "items_skipped": 0,
                    "items_failed": 0,
                    "items": symbol_result["items"],
                    "error": None,
                }
            )
            result["summary"]["symbols_success"] += 1
            result["summary"]["items_fetched"] += item_count
        except Exception as exc:
            result["errors"].append({"symbol": symbol, "source_url": source_config.get("url"), "error": str(exc)})
            result["results"].append(
                {
                    "symbol": symbol,
                    "source_url": source_config.get("url"),
                    "success": False,
                    "count": 0,
                    "items_fetched": 0,
                    "items_inserted": 0,
                    "items_skipped": 0,
                    "items_failed": 0,
                    "items": [],
                    "error": str(exc),
                }
            )
            result["summary"]["symbols_failed"] += 1

    result["count"] = len(result["items"])
    return json_safe(result)


def fetch_latest_forex_news_json(symbol: str = "USDIDR", exchange: str = "FX_IDC", limit: int = 10) -> Dict[str, Any]:
    """Backward-compatible helper for callers that used the old script API."""
    sources = load_forex_news_sources()
    source = dict(sources.get(symbol.upper()) or {})
    source.setdefault("exchange", exchange)
    source.setdefault("url", f"https://www.tradingview.com/symbols/{symbol.upper()}/news/")
    source.setdefault("base_currency", symbol.upper()[:3])
    source.setdefault("quote_currency", symbol.upper()[3:])
    source.setdefault("locale", "en")
    source.setdefault("language", "en")
    return fetch_forex_news_batch([(symbol.upper(), source)], limit=limit)


def apply_database_counts(result: Dict[str, Any], save_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    per_symbol = {}
    has_item_status = False
    for item in result.get("items", []):
        symbol = item.get("symbol")
        status = item.get("db_status")
        if status:
            has_item_status = True
        counts = per_symbol.setdefault(symbol, {"items_inserted": 0, "items_skipped": 0, "items_failed": 0})
        if status in ("inserted", "would_insert"):
            counts["items_inserted"] += 1
        elif status == "skipped":
            counts["items_skipped"] += 1
        elif status == "failed":
            counts["items_failed"] += 1

    totals = {"items_inserted": 0, "items_skipped": 0, "items_failed": 0}
    for symbol_result in result.get("results", []):
        counts = per_symbol.get(symbol_result.get("symbol"), {})
        for key in totals:
            value = counts.get(key, 0)
            symbol_result[key] = value
            totals[key] += value

    result.setdefault("summary", {})
    result["summary"].update(totals)
    if not has_item_status and save_result:
        fallback_counts = {
            "items_inserted": int(save_result.get("inserted_count", 0) or 0),
            "items_skipped": int(save_result.get("skipped_count", 0) or 0),
            "items_failed": int(save_result.get("failed_count", 0) or 0),
        }
        result["summary"].update(fallback_counts)
        if len(result.get("results", [])) == 1:
            result["results"][0].update(fallback_counts)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch TradingView forex news and print JSON.")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--symbol", help="Fetch one configured symbol, for example USDIDR.")
    target.add_argument("--symbols", help="Fetch comma-separated configured symbols, for example USDIDR,USDJPY.")
    target.add_argument("--all", action="store_true", help="Fetch every enabled configured symbol.")
    parser.add_argument("--url", help="Temporary TradingView symbol news URL. Requires --symbol.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum headlines per symbol.")
    parser.add_argument("--init-db", action="store_true", help="Create the configured Postgres database and tables if needed.")
    parser.add_argument("--init-db-only", action="store_true", help="Create the configured Postgres database and tables, then exit.")
    parser.add_argument("--save-db", action="store_true", help="Upsert fetched symbols and news into Postgres.")
    parser.add_argument("--dry-run", action="store_true", help="Check database duplicates without writing to Postgres.")
    parser.add_argument("--no-db", action="store_true", help="Do not connect to Postgres; only print JSON.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        sources = load_forex_news_sources()
        targets, errors = resolve_sources(
            symbol=args.symbol,
            symbols=args.symbols,
            all_symbols=args.all,
            url=args.url,
            sources=sources,
        )
        database_result = None
        dsn = None
        if args.no_db and (args.save_db or args.dry_run or args.init_db or args.init_db_only):
            raise ValueError("--no-db cannot be combined with --save-db, --dry-run, --init-db, or --init-db-only")
        if args.save_db and args.dry_run:
            raise ValueError("--save-db cannot be combined with --dry-run")
        if args.init_db or args.save_db or args.dry_run:
            dsn = get_postgres_dsn()
        if args.init_db or args.init_db_only:
            dsn = dsn or get_postgres_dsn()
            database_result = {"init": init_postgres_schema(dsn)}
        if args.init_db_only:
            result = {
                "fetched_at": utc_now_iso(),
                "count": 0,
                "items": [],
                "results": [],
                "errors": [],
                "database": json_safe(database_result),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.save_db or args.dry_run:
            with PostgresNewsExistenceChecker(dsn) as existing_checker:
                result = fetch_forex_news_batch(
                    targets,
                    limit=max(args.limit, 0),
                    initial_errors=errors,
                    existing_checker=existing_checker,
                )
        else:
            result = fetch_forex_news_batch(targets, limit=max(args.limit, 0), initial_errors=errors)
        if args.save_db or args.dry_run:
            database_result = database_result or {}
            database_result["save"] = save_result_to_postgres(result, targets, dsn, dry_run=args.dry_run)
            result = apply_database_counts(result, database_result["save"])
        if database_result is not None:
            result["database"] = json_safe(database_result)
    except Exception as exc:
        result = {"fetched_at": utc_now_iso(), "count": 0, "items": [], "results": [], "errors": [{"error": str(exc)}]}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
