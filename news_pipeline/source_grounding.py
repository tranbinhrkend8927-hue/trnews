"""Source grounding helpers for article drafts built from stored forex_news rows."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List


SOURCE_NEWS_FIELDS = [
    "news_id",
    "symbol",
    "title",
    "summary",
    "content",
    "url",
    "canonical_url",
    "source",
    "source_url",
    "published_at",
    "fetched_at",
    "locale",
]


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def normalize_reason_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return json_safe(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        return json_safe(loaded if isinstance(loaded, dict) else {"value": loaded})
    return {}


def _iter_candidate_ids(value: Any) -> Iterable[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return value
    return [value]


def extract_source_news_ids(topic_row: Dict[str, Any]) -> Dict[str, Any]:
    reason_json = normalize_reason_json((topic_row or {}).get("reason_json"))
    candidates = []
    candidates.extend(_iter_candidate_ids((topic_row or {}).get("source_news_ids")))
    candidates.extend(_iter_candidate_ids(reason_json.get("source_news_ids")))

    source_news_ids = []
    seen = set()
    warnings = []
    for candidate in candidates:
        try:
            news_id = int(candidate)
        except (TypeError, ValueError):
            warnings.append({"type": "invalid_source_news_id", "value": json_safe(candidate)})
            continue
        if news_id <= 0:
            warnings.append({"type": "invalid_source_news_id", "value": json_safe(candidate)})
            continue
        if news_id in seen:
            continue
        seen.add(news_id)
        source_news_ids.append(news_id)

    return json_safe({"source_news_ids": source_news_ids, "warnings": warnings})


def normalize_source_news_row(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(row or {})
    normalized = {
        "news_id": row.get("news_id", row.get("id")),
        "symbol": row.get("symbol"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "content": row.get("content"),
        "url": row.get("url"),
        "canonical_url": row.get("canonical_url"),
        "source": row.get("source"),
        "source_url": row.get("source_url"),
        "published_at": row.get("published_at"),
        "fetched_at": row.get("fetched_at"),
        "locale": row.get("locale"),
    }
    return json_safe({field: normalized.get(field) for field in SOURCE_NEWS_FIELDS})


def fetch_source_news_for_topic(dsn: str, topic_row: Dict[str, Any]) -> Dict[str, Any]:
    extracted = extract_source_news_ids(topic_row)
    source_news_ids = extracted["source_news_ids"]
    if not source_news_ids:
        return json_safe(
            {
                "sources": [],
                "missing_source_news_ids": [],
                "warnings": extracted["warnings"],
                "errors": [],
            }
        )

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id AS news_id, symbol, title, summary, content, url,
                        canonical_url, source, source_url, published_at, fetched_at, locale
                    FROM forex_news
                    WHERE id = ANY(%s)
                    """,
                    (source_news_ids,),
                )
                rows = [normalize_source_news_row(row) for row in cur.fetchall()]
    except Exception as exc:
        return json_safe(
            {
                "sources": [],
                "missing_source_news_ids": source_news_ids,
                "warnings": extracted["warnings"],
                "errors": [{"type": "source_news_fetch_failed", "error": str(exc)}],
            }
        )

    rows_by_id = {row["news_id"]: row for row in rows if row.get("news_id") is not None}
    ordered_sources = [rows_by_id[news_id] for news_id in source_news_ids if news_id in rows_by_id]
    missing_source_news_ids = [news_id for news_id in source_news_ids if news_id not in rows_by_id]

    return json_safe(
        {
            "sources": ordered_sources,
            "missing_source_news_ids": missing_source_news_ids,
            "warnings": extracted["warnings"],
            "errors": [],
        }
    )


def build_source_bundle(topic_row: Dict[str, Any], source_news_rows_or_result: Any) -> Dict[str, Any]:
    topic_row = topic_row or {}
    reason_json = normalize_reason_json(topic_row.get("reason_json"))
    extracted = extract_source_news_ids(topic_row)
    source_news_ids = extracted["source_news_ids"]

    warnings = list(extracted.get("warnings") or [])
    errors = []
    if isinstance(source_news_rows_or_result, dict) and "sources" in source_news_rows_or_result:
        sources = [normalize_source_news_row(row) for row in source_news_rows_or_result.get("sources", [])]
        missing_source_news_ids = list(source_news_rows_or_result.get("missing_source_news_ids") or [])
        warnings.extend(source_news_rows_or_result.get("warnings") or [])
        errors.extend(source_news_rows_or_result.get("errors") or [])
    else:
        sources = [normalize_source_news_row(row) for row in (source_news_rows_or_result or [])]
        found_ids = {source["news_id"] for source in sources if source.get("news_id") is not None}
        missing_source_news_ids = [news_id for news_id in source_news_ids if news_id not in found_ids]

    return json_safe(
        {
            "topic_id": topic_row.get("id"),
            "topic_type": topic_row.get("topic_type"),
            "symbol": str(topic_row.get("symbol") or "").upper(),
            "source_news_ids": source_news_ids,
            "sources": sources,
            "missing_source_news_ids": missing_source_news_ids,
            "warnings": warnings,
            "errors": errors,
            "reason_json": reason_json,
            "source_trace": {
                "topic_status": topic_row.get("status"),
                "source_news_ids_from_topic": topic_row.get("source_news_ids") or [],
                "source_news_ids_from_reason_json": reason_json.get("source_news_ids") or [],
            },
        }
    )


def choose_source_url(source: Dict[str, Any]) -> Any:
    return source.get("url") or source.get("canonical_url") or source.get("source_url")


def truncate_claim(value: Any, max_length: int = 240) -> Any:
    if value in (None, ""):
        return None
    text = " ".join(str(value).split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def build_article_sources_from_bundle(source_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    article_sources = []
    for source in (source_bundle or {}).get("sources", []) or []:
        article_sources.append(
            json_safe(
                {
                    "source_type": "forex_news",
                    "source_name": source.get("source") or "forex_news",
                    "source_url": choose_source_url(source),
                    "cited_claim": truncate_claim(source.get("title") or source.get("summary")),
                }
            )
        )
    return article_sources
