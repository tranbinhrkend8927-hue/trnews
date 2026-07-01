from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from src.ingest.normalize import NormalizedNewsItem
from src.ingest.tradingview import SourceFetchResult


DEFAULT_LOOKBACK_HOURS = 24


class PostgresNewsAdapter:
    def __init__(self, dsn: str | None = None, *, lookback_hours: int = DEFAULT_LOOKBACK_HOURS):
        self.dsn = dsn
        self.lookback_hours = lookback_hours

    def fetch(self, market) -> SourceFetchResult:
        try:
            rows = self._fetch_rows(market)
            items = [_row_to_news_item(row, market=market) for row in rows]
            return SourceFetchResult(
                success=True,
                market_id=market.id,
                symbol=market.symbol,
                language=market.content.language,
                items=items,
                warnings=[{"type": "db_source_window", "lookback_hours": self.lookback_hours, "source": "forex_news"}],
            )
        except Exception as exc:
            return SourceFetchResult(
                success=False,
                market_id=market.id,
                symbol=market.symbol,
                language=market.content.language,
                errors=[{"type": "postgres_source_fetch_failed", "error": str(exc)}],
            )

    def _fetch_rows(self, market) -> list[dict[str, Any]]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg is required for database source mode") from exc

        dsn = self.dsn or _env_value("POSTGRES_DSN")
        if not dsn:
            raise RuntimeError("POSTGRES_DSN is required for database source mode")

        limit = max(int(getattr(market.content.source_policy, "max_sources", 5) or 5), 0)
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id, symbol, base_currency, quote_currency, locale, title,
                        summary, content, url, canonical_url, source, source_url,
                        published_at, fetched_at, raw_json
                    FROM forex_news
                    WHERE symbol = %s
                      AND COALESCE(published_at, fetched_at) >= NOW() - (%s * INTERVAL '1 hour')
                    ORDER BY published_at DESC NULLS LAST, fetched_at DESC NULLS LAST, id DESC
                    LIMIT %s
                    """,
                    (market.symbol, max(int(self.lookback_hours), 1), limit),
                )
                return [dict(row) for row in cur.fetchall()]


class RefreshingPostgresNewsAdapter:
    def __init__(self, inner: PostgresNewsAdapter | None = None):
        self.inner = inner or PostgresNewsAdapter()

    def fetch(self, market) -> SourceFetchResult:
        refresh_result = _refresh_market_sources(market)
        result = self.inner.fetch(market)
        if refresh_result.get("errors"):
            result.warnings.append({"type": "source_refresh_failed", "errors": refresh_result.get("errors")})
        else:
            result.warnings.append({"type": "source_refresh_completed", "summary": refresh_result.get("summary") or {}})
        return result


def _refresh_market_sources(market) -> dict:
    from news_pipeline.fetch_forex_news_json import (
        fetch_forex_news_batch,
        get_postgres_dsn,
        load_forex_news_sources,
        resolve_sources,
        save_result_to_postgres,
    )

    sources = load_forex_news_sources()
    targets, errors = resolve_sources(
        symbol=market.symbol,
        symbols=None,
        all_symbols=False,
        url=None,
        sources=sources,
    )
    result = fetch_forex_news_batch(targets, limit=int(market.tradingview.max_headlines or 10), initial_errors=errors)
    if errors:
        return result
    save_result = save_result_to_postgres(result, targets, get_postgres_dsn(), dry_run=False)
    result["database"] = {"save": save_result}
    return result


def _row_to_news_item(row: dict[str, Any], *, market) -> NormalizedNewsItem:
    news_id = row.get("id")
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    raw = {**raw, "id": news_id, "news_id": news_id}
    return NormalizedNewsItem(
        source_id=str(news_id),
        provider=row.get("source"),
        symbol=market.symbol,
        exchange=market.exchange,
        language=market.content.language,
        locale=row.get("locale") or market.tradingview.locale,
        title=str(row.get("title") or ""),
        summary=row.get("summary") or None,
        content=row.get("content") or None,
        url=row.get("url") or None,
        canonical_url=row.get("canonical_url") or row.get("url") or None,
        published_at=_iso(row.get("published_at")),
        fetched_at=_iso(row.get("fetched_at")) or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        raw=raw,
    )


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def _env_value(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        from src.config.loader import load_local_env
    except Exception:
        return ""
    return str(load_local_env().get(name) or "")
