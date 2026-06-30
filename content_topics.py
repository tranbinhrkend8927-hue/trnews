"""Generate minimal USDIDR content topic candidates from stored forex news."""

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple


SUPPORTED_TOPIC_SYMBOL = "USDIDR"
SUPPORTED_TOPIC_TYPES = {
    "daily_usdidr_update",
    "rupiah_explainer",
    "macro_event_watch",
    "bank_indonesia_watch",
}
SUPPORTED_TOPIC_STATUSES = {"candidate", "approved", "rejected", "generated"}

KEYWORD_SCORES = [
    ("rupiah", 2),
    ("dolar AS", 2),
    ("dolar", 1),
    ("USD/IDR", 3),
    ("USDIDR", 3),
    ("Bank Indonesia", 3),
    ("The Fed", 2),
    ("Fed", 1),
    ("CPI", 2),
    ("NFP", 2),
    ("FOMC", 2),
    ("inflasi", 1),
    ("suku bunga", 2),
    ("yen", 1),
    ("won", 1),
    ("BI", 1),
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def freshness_score(news_row: Dict[str, Any], now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    published = parse_datetime(news_row.get("published_at")) or parse_datetime(news_row.get("fetched_at"))
    if published is None:
        return 0
    age_seconds = (now - published).total_seconds()
    return 2 if 0 <= age_seconds <= 48 * 60 * 60 else 0


def match_topic_keywords(news_row: Dict[str, Any]) -> Tuple[List[str], int]:
    haystack = normalize_text(
        " ".join(
            str(news_row.get(field) or "")
            for field in ("title", "summary", "content", "source", "url", "canonical_url")
        )
    )
    matched = []
    score = 0
    for keyword, keyword_score in KEYWORD_SCORES:
        normalized_keyword = normalize_text(keyword)
        if keyword == "BI":
            is_match = re.search(r"\bbi\b", haystack, flags=re.IGNORECASE) is not None
        else:
            is_match = normalized_keyword in haystack
        if is_match and keyword not in matched:
            matched.append(keyword)
            score += keyword_score
    return matched, score


def infer_topic_type(matched_keywords: Iterable[str]) -> str:
    matched = set(matched_keywords)
    if matched.intersection({"Bank Indonesia", "BI", "suku bunga"}):
        return "bank_indonesia_watch"
    if matched.intersection({"The Fed", "Fed", "CPI", "NFP", "FOMC", "inflasi"}):
        return "macro_event_watch"
    if "rupiah" in matched and matched.intersection({"dolar", "dolar AS"}):
        return "rupiah_explainer"
    return "daily_usdidr_update"


def title_for_topic_type(topic_type: str) -> str:
    titles = {
        "daily_usdidr_update": "USD/IDR Hari Ini: Faktor yang Mempengaruhi Pergerakan Rupiah",
        "rupiah_explainer": "Rupiah terhadap Dolar AS, Apa Faktor yang Perlu Dipantau?",
        "macro_event_watch": "USD/IDR Bergerak Menjelang Data AS, Ini Hal yang Perlu Diperhatikan",
        "bank_indonesia_watch": "Bank Indonesia dan Arah Rupiah: Faktor yang Mempengaruhi USD/IDR Hari Ini",
    }
    return titles[topic_type]


def build_topic_hash(topic: Dict[str, Any]) -> str:
    payload = "\n".join(
        [
            normalize_text(topic.get("symbol")).upper(),
            normalize_text(topic.get("topic_type")),
            normalize_text(topic.get("title")),
            ",".join(str(item) for item in sorted(topic.get("source_news_ids") or [])),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def score_usdidr_news_item(news_row: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    matched_keywords, keyword_score = match_topic_keywords(news_row)
    freshness = freshness_score(news_row, now=now)
    source = 1 if news_row.get("canonical_url") or news_row.get("url") else 0
    source_news_ids = [int(news_row["id"])] if news_row.get("id") is not None else []
    reason_json = {
        "matched_keywords": matched_keywords,
        "source_news_ids": source_news_ids,
        "freshness_score": freshness,
        "source_score": source,
        "locale": news_row.get("locale"),
    }
    topic_type = infer_topic_type(matched_keywords)
    return {
        "score": keyword_score + freshness + source,
        "topic_type": topic_type,
        "title": title_for_topic_type(topic_type),
        "reason_json": json_safe(reason_json),
        "source_news_ids": source_news_ids,
    }


def generate_usdidr_topic_candidates(
    news_rows: Iterable[Dict[str, Any]],
    *,
    min_score: int = 3,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    candidates = []
    seen_hashes = set()
    for news_row in news_rows:
        if str(news_row.get("symbol") or "").upper() != SUPPORTED_TOPIC_SYMBOL:
            continue
        scored = score_usdidr_news_item(news_row, now=now)
        if scored["score"] < min_score:
            continue
        topic = {
            "symbol": SUPPORTED_TOPIC_SYMBOL,
            "topic_type": scored["topic_type"],
            "title": scored["title"],
            "score": scored["score"],
            "status": "candidate",
            "reason_json": scored["reason_json"],
            "source_news_ids": scored["source_news_ids"],
        }
        topic["topic_hash"] = build_topic_hash(topic)
        if topic["topic_hash"] in seen_hashes:
            continue
        seen_hashes.add(topic["topic_hash"])
        candidates.append(json_safe(topic))
    return candidates


def fetch_usdidr_news_for_topics(dsn: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id, symbol, locale, title, summary, content, url,
                    canonical_url, source, published_at, fetched_at
                FROM forex_news
                WHERE symbol = %s
                ORDER BY published_at DESC NULLS LAST, fetched_at DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (SUPPORTED_TOPIC_SYMBOL, max(int(limit), 0)),
            )
            return [json_safe(row) for row in cur.fetchall()]


def topic_exists(cur: Any, topic: Dict[str, Any]) -> bool:
    cur.execute(
        "SELECT 1 FROM content_topics WHERE symbol = %s AND topic_hash = %s LIMIT 1",
        (topic.get("symbol"), topic.get("topic_hash")),
    )
    return cur.fetchone() is not None


def save_topic_candidates_to_postgres(
    candidates: Iterable[Dict[str, Any]],
    dsn: str,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    inserted_count = 0
    skipped_count = 0
    failed_count = 0
    errors = []
    candidates = list(candidates or [])

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for topic in candidates:
                cur.execute("SAVEPOINT content_topic_item")
                try:
                    if topic_exists(cur, topic):
                        skipped_count += 1
                        topic["db_status"] = "skipped"
                        topic["db_skip_reason"] = "topic_hash"
                        cur.execute("RELEASE SAVEPOINT content_topic_item")
                        continue
                    if dry_run:
                        inserted_count += 1
                        topic["db_status"] = "would_insert"
                        cur.execute("RELEASE SAVEPOINT content_topic_item")
                        continue
                    cur.execute(
                        """
                        INSERT INTO content_topics (
                            symbol, topic_type, title, score, status,
                            reason_json, source_news_ids, topic_hash, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT DO NOTHING
                        RETURNING id
                        """,
                        (
                            topic.get("symbol"),
                            topic.get("topic_type"),
                            topic.get("title"),
                            topic.get("score"),
                            topic.get("status", "candidate"),
                            Jsonb(topic.get("reason_json") or {}),
                            topic.get("source_news_ids") or [],
                            topic.get("topic_hash"),
                        ),
                    )
                    inserted = cur.fetchone() is not None
                    if inserted:
                        inserted_count += 1
                        topic["db_status"] = "inserted"
                    else:
                        skipped_count += 1
                        topic["db_status"] = "skipped"
                        topic["db_skip_reason"] = "conflict"
                    cur.execute("RELEASE SAVEPOINT content_topic_item")
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT content_topic_item")
                    cur.execute("RELEASE SAVEPOINT content_topic_item")
                    failed_count += 1
                    topic["db_status"] = "failed"
                    topic["db_error"] = str(exc)
                    errors.append(
                        {
                            "symbol": topic.get("symbol"),
                            "topic_hash": topic.get("topic_hash"),
                            "error": str(exc),
                        }
                    )
        conn.commit()

    return {
        "success": True,
        "dry_run": dry_run,
        "inserted_count": inserted_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "errors": errors,
    }


def build_topic_generation_result(
    *,
    symbol: str,
    news_rows: Iterable[Dict[str, Any]],
    dsn: str,
    dry_run: bool = False,
    min_score: int = 3,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    symbol = str(symbol or "").upper()
    news_rows = list(news_rows or [])
    result = {
        "generated_at": utc_now_iso(),
        "symbol": symbol,
        "summary": {
            "news_checked": len(news_rows),
            "topics_generated": 0,
            "topics_inserted": 0,
            "topics_skipped": 0,
            "topics_failed": 0,
        },
        "topics": [],
        "errors": [],
    }
    if symbol != SUPPORTED_TOPIC_SYMBOL:
        result["errors"].append(
            {
                "symbol": symbol,
                "error": f"Unsupported symbol for topic generation: {symbol}. Only USDIDR is supported.",
            }
        )
        return result

    topics = generate_usdidr_topic_candidates(news_rows, min_score=min_score, now=now)
    result["topics"] = topics
    result["summary"]["topics_generated"] = len(topics)
    save_result = save_topic_candidates_to_postgres(topics, dsn, dry_run=dry_run)
    result["summary"]["topics_inserted"] = save_result["inserted_count"]
    result["summary"]["topics_skipped"] = save_result["skipped_count"]
    result["summary"]["topics_failed"] = save_result["failed_count"]
    result["errors"].extend(save_result.get("errors") or [])
    return json_safe(result)


def dumps_json(payload: Dict[str, Any]) -> str:
    return json.dumps(json_safe(payload), ensure_ascii=False, indent=2)
