"""Create article draft shells from content topic rows."""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional


ARTICLE_STATUSES = {"draft", "pending_review", "approved", "rejected", "published"}
FACT_CHECK_STATUSES = {"pending", "passed", "failed", "needs_sources"}


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


def normalize_topic_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return json_safe(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        return json_safe(loaded if isinstance(loaded, dict) else {"value": loaded})
    return {}


def build_slug(title: str, topic_id: Optional[int] = None) -> str:
    normalized = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    if not slug:
        slug = "article-draft"
    if topic_id is not None:
        slug = f"{slug}-{int(topic_id)}"
    return slug


def build_sources_from_topic(topic_row: Dict[str, Any]) -> Dict[str, Any]:
    reason_json = normalize_topic_json(topic_row.get("reason_json"))
    source_news_ids = topic_row.get("source_news_ids") or reason_json.get("source_news_ids") or []
    source_news_ids = [int(item) for item in source_news_ids]
    return json_safe(
        {
            "topic_id": topic_row.get("id"),
            "topic_type": topic_row.get("topic_type"),
            "source_news_ids": source_news_ids,
            "reason_json": reason_json,
            "source_trace": {
                "reason_json": reason_json,
                "topic_status": topic_row.get("status"),
            },
        }
    )


def build_article_draft(topic_row: Dict[str, Any], status: str = "draft") -> Dict[str, Any]:
    status = str(status or "draft")
    if status == "published":
        raise ValueError("Article drafts cannot be created with status=published")
    if status not in ARTICLE_STATUSES:
        raise ValueError(f"Unsupported article status: {status}")

    topic_id = topic_row.get("id")
    if topic_id is None:
        raise ValueError("topic_row must include id")
    title = topic_row.get("title") or "USD/IDR Draft"
    return json_safe(
        {
            "topic_id": int(topic_id),
            "symbol": str(topic_row.get("symbol") or "").upper(),
            "language": "id",
            "title": title,
            "slug": build_slug(title, topic_id=topic_id),
            "summary": "",
            "body": "",
            "seo_title": "",
            "seo_description": "",
            "status": status,
            "fact_check_status": "pending",
            "risk_disclaimer_included": False,
            "sources_json": build_sources_from_topic(topic_row),
            "published_at": None,
        }
    )


def build_article_draft_from_template(
    topic_row: Dict[str, Any],
    *,
    template: Optional[str] = None,
    source_bundle: Optional[Dict[str, Any]] = None,
    status: str = "pending_review",
) -> Dict[str, Any]:
    from article_templates import render_article_template

    status = str(status or "pending_review")
    if status == "published":
        raise ValueError("Article drafts cannot be created with status=published")
    if status not in ARTICLE_STATUSES:
        raise ValueError(f"Unsupported article status: {status}")

    rendered = render_article_template(topic_row, template=template, source_bundle=source_bundle)
    if not rendered.get("success"):
        return json_safe(rendered)

    draft = build_article_draft(topic_row, status=status)
    draft.update(
        {
            "title": rendered["title"],
            "slug": build_slug(rendered["title"], topic_id=topic_row.get("id")),
            "summary": rendered["summary"],
            "body": rendered["body"],
            "seo_title": rendered["seo_title"],
            "seo_description": rendered["seo_description"],
            "risk_disclaimer_included": bool(rendered["risk_disclaimer_included"]),
            "sources_json": rendered["sources_json"],
            "published_at": None,
        }
    )
    return json_safe({"success": True, "draft": draft, "template": rendered["template"]})


def fetch_topic_for_draft(dsn: str, topic_id: int) -> Optional[Dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, symbol, topic_type, title, status, reason_json, source_news_ids
                FROM content_topics
                WHERE id = %s
                LIMIT 1
                """,
                (topic_id,),
            )
            row = cur.fetchone()
            return json_safe(row) if row else None


def article_draft_exists(cur: Any, topic_id: int) -> bool:
    cur.execute("SELECT 1 FROM generated_articles WHERE topic_id = %s LIMIT 1", (topic_id,))
    return cur.fetchone() is not None


def save_article_draft_to_postgres(
    draft: Dict[str, Any],
    dsn: str,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SAVEPOINT generated_article_item")
            try:
                if article_draft_exists(cur, int(draft["topic_id"])):
                    draft["db_status"] = "skipped"
                    draft["db_skip_reason"] = "topic_id"
                    cur.execute("RELEASE SAVEPOINT generated_article_item")
                    return {
                        "success": True,
                        "dry_run": dry_run,
                        "article_id": None,
                        "inserted_count": 0,
                        "skipped_count": 1,
                        "failed_count": 0,
                        "errors": [],
                    }
                if dry_run:
                    draft["db_status"] = "would_insert"
                    cur.execute("RELEASE SAVEPOINT generated_article_item")
                    return {
                        "success": True,
                        "dry_run": True,
                        "article_id": None,
                        "inserted_count": 1,
                        "skipped_count": 0,
                        "failed_count": 0,
                        "errors": [],
                    }
                cur.execute(
                    """
                    INSERT INTO generated_articles (
                        topic_id, symbol, language, title, slug, summary, body,
                        seo_title, seo_description, status, fact_check_status,
                        risk_disclaimer_included, sources_json, published_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    (
                        draft.get("topic_id"),
                        draft.get("symbol"),
                        draft.get("language"),
                        draft.get("title"),
                        draft.get("slug"),
                        draft.get("summary"),
                        draft.get("body"),
                        draft.get("seo_title"),
                        draft.get("seo_description"),
                        draft.get("status"),
                        draft.get("fact_check_status"),
                        bool(draft.get("risk_disclaimer_included", False)),
                        Jsonb(draft.get("sources_json") or {}),
                        draft.get("published_at"),
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    draft["db_status"] = "skipped"
                    draft["db_skip_reason"] = "conflict"
                    cur.execute("RELEASE SAVEPOINT generated_article_item")
                    return {
                        "success": True,
                        "dry_run": False,
                        "article_id": None,
                        "inserted_count": 0,
                        "skipped_count": 1,
                        "failed_count": 0,
                        "errors": [],
                    }
                article_id = row[0]
                draft["db_status"] = "inserted"
                draft["article_id"] = article_id
                cur.execute("RELEASE SAVEPOINT generated_article_item")
                conn.commit()
                return {
                    "success": True,
                    "dry_run": False,
                    "article_id": article_id,
                    "inserted_count": 1,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "errors": [],
                }
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT generated_article_item")
                cur.execute("RELEASE SAVEPOINT generated_article_item")
                draft["db_status"] = "failed"
                draft["db_error"] = str(exc)
                conn.commit()
                return {
                    "success": False,
                    "dry_run": dry_run,
                    "article_id": None,
                    "inserted_count": 0,
                    "skipped_count": 0,
                    "failed_count": 1,
                    "errors": [{"topic_id": draft.get("topic_id"), "error": str(exc)}],
                }


def save_article_sources_to_postgres(
    article_id: int,
    sources: Iterable[Dict[str, Any]],
    dsn: str,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    inserted_count = 0
    failed_count = 0
    errors = []
    sources = list(sources or [])
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for source in sources:
                cur.execute("SAVEPOINT article_source_item")
                try:
                    if dry_run:
                        inserted_count += 1
                        source["db_status"] = "would_insert"
                        cur.execute("RELEASE SAVEPOINT article_source_item")
                        continue
                    cur.execute(
                        """
                        INSERT INTO article_sources (
                            article_id, source_type, source_name, source_url, cited_claim
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            article_id,
                            source.get("source_type"),
                            source.get("source_name"),
                            source.get("source_url"),
                            source.get("cited_claim"),
                        ),
                    )
                    row = cur.fetchone()
                    inserted_count += 1
                    source["db_status"] = "inserted"
                    source["article_source_id"] = row[0] if row else None
                    cur.execute("RELEASE SAVEPOINT article_source_item")
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT article_source_item")
                    cur.execute("RELEASE SAVEPOINT article_source_item")
                    failed_count += 1
                    source["db_status"] = "failed"
                    source["db_error"] = str(exc)
                    errors.append({"article_id": article_id, "error": str(exc)})
        conn.commit()
    return {
        "success": failed_count == 0,
        "dry_run": dry_run,
        "inserted_count": inserted_count,
        "failed_count": failed_count,
        "errors": errors,
    }


def draft_hash(draft: Dict[str, Any]) -> str:
    payload = json.dumps(json_safe(draft), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
