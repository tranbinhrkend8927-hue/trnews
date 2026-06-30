"""Human review workflow for generated article drafts."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from .draft_quality import evaluate_draft_quality
from .safety_validation import validate_financial_safety


REVIEW_DECISIONS = {"approved", "rejected", "needs_changes"}
DECISION_STATUS = {
    "approved": "approved",
    "rejected": "rejected",
    "needs_changes": "pending_review",
}
SAFETY_BLOCKER_TYPES = {"profit_promise", "buy_sell_instruction", "take_profit_stop_loss"}


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


def _error(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    payload = {"code": code, "message": message}
    payload.update(extra)
    return json_safe(payload)


def _normalize_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return json_safe(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        return json_safe(loaded if isinstance(loaded, dict) else {"value": loaded})
    return {}


def _article_source_to_bundle_source(source: Dict[str, Any]) -> Dict[str, Any]:
    return json_safe(
        {
            "news_id": source.get("news_id"),
            "source_type": source.get("source_type"),
            "source": source.get("source_name"),
            "source_name": source.get("source_name"),
            "url": source.get("source_url"),
            "source_url": source.get("source_url"),
            "title": source.get("cited_claim"),
            "summary": source.get("cited_claim"),
        }
    )


def _source_bundle_from_article(article: Dict[str, Any], article_sources: Optional[Iterable[Dict[str, Any]]]) -> Dict[str, Any]:
    sources_json = _normalize_json_object((article or {}).get("sources_json"))
    bundled_sources = sources_json.get("sources")
    if not isinstance(bundled_sources, list):
        bundled_sources = []

    review_sources = [_article_source_to_bundle_source(source) for source in (article_sources or []) if source]
    sources = bundled_sources or review_sources
    return json_safe(
        {
            "topic_id": sources_json.get("topic_id") or article.get("topic_id"),
            "topic_type": sources_json.get("topic_type"),
            "symbol": article.get("symbol") or sources_json.get("symbol"),
            "source_news_ids": sources_json.get("source_news_ids") or [],
            "sources": sources,
            "missing_source_news_ids": sources_json.get("missing_source_news_ids") or [],
            "warnings": sources_json.get("warnings") or [],
            "errors": sources_json.get("errors") or [],
            "reason_json": sources_json.get("reason_json") or {},
            "source_trace": sources_json.get("source_trace") or {},
        }
    )


def _has_safety_blocker(safety_result: Dict[str, Any]) -> bool:
    if safety_result.get("fact_check_status") == "failed":
        return True
    if safety_result.get("passed") is False:
        return any(item.get("type") in SAFETY_BLOCKER_TYPES for item in safety_result.get("violations") or [])
    return False


def _approval_blockers(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    blockers = []
    status = str(report.get("status") or "")
    fact_check_status = str(report.get("fact_check_status") or "")
    safety_result = report.get("safety_result") or {}
    quality_result = report.get("quality_result") or {}

    if status == "published":
        blockers.append(_error("article_published", "Published articles cannot be modified by review workflow."))
    if status == "rejected":
        blockers.append(_error("article_rejected", "Rejected articles cannot be approved without a new review-ready draft."))
    if fact_check_status == "failed":
        blockers.append(_error("fact_check_failed", "Articles with failed fact check status cannot be approved."))
    if fact_check_status == "needs_sources":
        blockers.append(_error("fact_check_needs_sources", "Articles that need sources cannot be approved."))
    if _has_safety_blocker(safety_result):
        blockers.append(_error("safety_failed", "Safety validation has blocking violations."))
    if safety_result.get("fact_check_status") == "needs_sources":
        blockers.append(_error("safety_needs_sources", "Safety validation requires additional sources."))
    if quality_result.get("level") == "blocked":
        blockers.append(_error("quality_blocked", "Quality gate level is blocked."))
    if quality_result.get("blocking_issues"):
        blockers.append(_error("quality_blocking_issues", "Quality gate has blocking issues."))
    if not report.get("has_risk_disclaimer"):
        blockers.append(_error("missing_risk_disclaimer", "Risk disclaimer is required before approval."))
    if not report.get("has_sources"):
        source_issue = any(
            item.get("name") in {"financial_terms_have_sources", "has_sources"}
            for item in (quality_result.get("blocking_issues") or [])
        )
        if source_issue or report.get("source_count", 0) == 0:
            blockers.append(_error("missing_sources", "At least one source is required before approval."))
    return json_safe(blockers)


def fetch_article_for_review(dsn: str, article_id: int) -> Optional[Dict[str, Any]]:
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
                    id, topic_id, symbol, language, title, slug, summary, body,
                    seo_title, seo_description, status, fact_check_status,
                    risk_disclaimer_included, sources_json, created_at, updated_at,
                    published_at
                FROM generated_articles
                WHERE id = %s
                LIMIT 1
                """,
                (article_id,),
            )
            row = cur.fetchone()
            return json_safe(row) if row else None


def fetch_article_sources_for_review(dsn: str, article_id: int) -> List[Dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, article_id, source_type, source_name, source_url, cited_claim, created_at
                FROM article_sources
                WHERE article_id = %s
                ORDER BY id
                """,
                (article_id,),
            )
            return json_safe(cur.fetchall())


def build_article_review_report(
    article: Dict[str, Any],
    article_sources: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    article = json_safe(article or {})
    article_sources = json_safe(list(article_sources or []))
    source_bundle = _source_bundle_from_article(article, article_sources)
    safety_result = validate_financial_safety(article, article_sources)
    quality_result = evaluate_draft_quality(article, source_bundle=source_bundle, safety_result=safety_result)
    source_count = len(source_bundle.get("sources") or [])

    report = {
        "article_id": article.get("id"),
        "status": article.get("status"),
        "fact_check_status": article.get("fact_check_status") or safety_result.get("fact_check_status") or "pending",
        "title": article.get("title"),
        "slug": article.get("slug"),
        "symbol": article.get("symbol"),
        "language": article.get("language"),
        "source_count": source_count,
        "has_sources": source_count > 0,
        "has_risk_disclaimer": bool(article.get("risk_disclaimer_included", False)),
        "safety_result": safety_result,
        "quality_result": quality_result,
        "warnings": [],
        "source_bundle": source_bundle,
    }
    blockers = _approval_blockers(report)
    report["approval_blockers"] = blockers
    report["can_approve"] = not blockers
    if quality_result.get("warnings"):
        report["warnings"].extend(quality_result.get("warnings") or [])
    if source_bundle.get("missing_source_news_ids"):
        report["warnings"].append(
            _error(
                "missing_source_news_ids",
                "Some source_news_ids could not be resolved.",
                missing_source_news_ids=source_bundle.get("missing_source_news_ids"),
            )
        )
    return json_safe(report)


def validate_review_decision(
    report: Dict[str, Any],
    decision: str,
    reviewer_notes: Optional[str] = None,
) -> Dict[str, Any]:
    decision = str(decision or "").strip()
    warnings = []
    errors = []
    previous_status = (report or {}).get("status")
    new_status = DECISION_STATUS.get(decision)

    if decision not in REVIEW_DECISIONS:
        errors.append(_error("invalid_decision", "Unsupported review decision.", decision=decision))
    if previous_status == "published":
        errors.append(_error("article_published", "Published articles cannot be modified by review workflow."))
    if new_status == "published":
        errors.append(_error("published_not_allowed", "Review workflow must never set status=published."))

    if decision == "approved":
        for blocker in (report or {}).get("approval_blockers") or []:
            errors.append(blocker)
    elif decision in {"rejected", "needs_changes"} and not str(reviewer_notes or "").strip():
        warnings.append(_error("reviewer_notes_recommended", "Reviewer notes are recommended for this decision."))

    return json_safe(
        {
            "valid": not errors,
            "decision": decision,
            "previous_status": previous_status,
            "new_status": new_status,
            "errors": errors,
            "warnings": warnings,
        }
    )


def _result(
    *,
    article_id: int,
    decision: str,
    dry_run: bool,
    previous_status: Optional[str] = None,
    new_status: Optional[str] = None,
    review_report: Optional[Dict[str, Any]] = None,
    validation: Optional[Dict[str, Any]] = None,
    review_id: Optional[int] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    errors = errors or []
    validation = validation or {}
    return json_safe(
        {
            "success": not errors and bool(validation.get("valid", True)),
            "article_id": article_id,
            "decision": decision,
            "dry_run": bool(dry_run),
            "previous_status": previous_status,
            "new_status": new_status,
            "review_id": review_id,
            "review_report": review_report or {},
            "validation": validation,
            "summary": {
                "reviews_inserted": 0 if dry_run or errors else 1,
                "articles_updated": 0 if dry_run or errors else 1,
                "would_insert": 1 if dry_run and not errors and validation.get("valid", True) else 0,
                "would_update": 1 if dry_run and not errors and validation.get("valid", True) else 0,
            },
            "errors": errors,
        }
    )


def save_article_review_to_postgres(
    dsn: str,
    article_id: int,
    decision: str,
    reviewer: Optional[str] = None,
    reviewer_notes: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id, topic_id, symbol, language, title, slug, summary, body,
                        seo_title, seo_description, status, fact_check_status,
                        risk_disclaimer_included, sources_json, created_at, updated_at,
                        published_at
                    FROM generated_articles
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (article_id,),
                )
                article = cur.fetchone()
                if not article:
                    return _result(
                        article_id=article_id,
                        decision=decision,
                        dry_run=dry_run,
                        errors=[_error("article_not_found", f"Article not found: {article_id}")],
                    )
                article = json_safe(article)
                if article.get("status") == "published":
                    report = build_article_review_report(article, [])
                    validation = validate_review_decision(report, decision, reviewer_notes=reviewer_notes)
                    return _result(
                        article_id=article_id,
                        decision=decision,
                        dry_run=dry_run,
                        previous_status=article.get("status"),
                        new_status=validation.get("new_status"),
                        review_report=report,
                        validation=validation,
                        errors=[_error("article_published", "Published articles cannot be modified by review workflow.")],
                    )

                cur.execute(
                    """
                    SELECT id, article_id, source_type, source_name, source_url, cited_claim, created_at
                    FROM article_sources
                    WHERE article_id = %s
                    ORDER BY id
                    """,
                    (article_id,),
                )
                article_sources = json_safe(cur.fetchall())
                report = build_article_review_report(article, article_sources)
                validation = validate_review_decision(report, decision, reviewer_notes=reviewer_notes)
                previous_status = article.get("status")
                new_status = validation.get("new_status")
                if not validation.get("valid"):
                    return _result(
                        article_id=article_id,
                        decision=decision,
                        dry_run=dry_run,
                        previous_status=previous_status,
                        new_status=new_status,
                        review_report=report,
                        validation=validation,
                        errors=validation.get("errors") or [],
                    )
                if dry_run:
                    return _result(
                        article_id=article_id,
                        decision=decision,
                        dry_run=True,
                        previous_status=previous_status,
                        new_status=new_status,
                        review_report=report,
                        validation=validation,
                    )

                cur.execute("SAVEPOINT article_review_item")
                try:
                    cur.execute(
                        """
                        INSERT INTO article_reviews (
                            article_id, decision, reviewer, reviewer_notes,
                            previous_status, new_status, safety_result_json,
                            quality_result_json, review_report_json
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            article_id,
                            decision,
                            reviewer,
                            reviewer_notes,
                            previous_status,
                            new_status,
                            Jsonb(report.get("safety_result") or {}),
                            Jsonb(report.get("quality_result") or {}),
                            Jsonb(report),
                        ),
                    )
                    row = cur.fetchone()
                    review_id = row["id"] if isinstance(row, dict) else row[0]
                    cur.execute(
                        """
                        UPDATE generated_articles
                        SET status = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (new_status, article_id),
                    )
                    cur.execute("RELEASE SAVEPOINT article_review_item")
                    conn.commit()
                    return _result(
                        article_id=article_id,
                        decision=decision,
                        dry_run=False,
                        previous_status=previous_status,
                        new_status=new_status,
                        review_report=report,
                        validation=validation,
                        review_id=review_id,
                    )
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT article_review_item")
                    cur.execute("RELEASE SAVEPOINT article_review_item")
                    conn.commit()
                    return _result(
                        article_id=article_id,
                        decision=decision,
                        dry_run=dry_run,
                        previous_status=previous_status,
                        new_status=new_status,
                        review_report=report,
                        validation=validation,
                        errors=[_error("review_save_failed", str(exc))],
                    )
    except Exception as exc:
        return _result(
            article_id=article_id,
            decision=decision,
            dry_run=dry_run,
            errors=[_error("review_failed", str(exc))],
        )
