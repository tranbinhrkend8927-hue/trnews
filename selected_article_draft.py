"""Build and save explicitly selected article draft candidates."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from article_drafts import build_article_draft_from_template
from draft_comparison import (
    compare_draft_candidates,
    detect_unsupported_financial_numbers,
    validate_candidate_sources,
)
from draft_quality import evaluate_draft_quality
from llm_article_drafts import generate_llm_article_draft_candidate
from safety_validation import apply_fact_check_status, validate_financial_safety
from source_grounding import build_article_sources_from_bundle


CANDIDATE_TYPES = {"template", "llm"}
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


def _error(error_type: str, message: str, *, retryable: bool = False, **extra: Any) -> Dict[str, Any]:
    payload = {"type": error_type, "message": message, "retryable": bool(retryable)}
    payload.update(extra)
    return json_safe(payload)


def _issue(issue_type: str, message: str, **extra: Any) -> Dict[str, Any]:
    payload = {"type": issue_type, "message": message}
    payload.update(extra)
    return json_safe(payload)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _base_payload(
    *,
    topic_id: Any,
    candidate_type: str,
    provider: str,
    source_bundle: Optional[Dict[str, Any]] = None,
    selected_draft: Optional[Dict[str, Any]] = None,
    safety_result: Optional[Dict[str, Any]] = None,
    quality_result: Optional[Dict[str, Any]] = None,
    comparison_result: Optional[Dict[str, Any]] = None,
    save_validation: Optional[Dict[str, Any]] = None,
    template: Optional[Dict[str, Any]] = None,
    llm: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    errors = errors or []
    save_validation = save_validation or {"can_save": False, "blockers": [], "warnings": []}
    return json_safe(
        {
            "success": not errors and bool(save_validation.get("can_save")),
            "topic_id": topic_id,
            "candidate_type": candidate_type,
            "provider": provider,
            "selected_draft": selected_draft or {},
            "source_bundle": source_bundle or {},
            "safety_result": safety_result or {},
            "quality_result": quality_result or {},
            "comparison_result": comparison_result or {},
            "save_validation": save_validation,
            "template": template or {},
            "llm": llm or {},
            "summary": {
                "would_write_db": bool(save_validation.get("can_save")),
                "would_publish": False,
                "status_after_save": "pending_review",
            },
            "errors": errors,
        }
    )


def _build_template_candidate(topic: Dict[str, Any], source_bundle: Dict[str, Any], template_hint: Optional[str]) -> Dict[str, Any]:
    draft_result = build_article_draft_from_template(topic, template=template_hint, source_bundle=source_bundle)
    if not draft_result.get("success"):
        return json_safe({"success": False, "draft": {}, "safety_result": {}, "quality_result": {}, "errors": [draft_result.get("error")]})
    draft = dict(draft_result.get("draft") or {})
    safety_result = validate_financial_safety(draft)
    draft = apply_fact_check_status(draft, safety_result)
    draft["status"] = "pending_review"
    draft["published_at"] = None
    quality_result = evaluate_draft_quality(draft, source_bundle=source_bundle, safety_result=safety_result)
    return json_safe({"success": True, "draft": draft, "safety_result": safety_result, "quality_result": quality_result, "errors": []})


def _template_only_comparison(template_section: Dict[str, Any]) -> Dict[str, Any]:
    draft = template_section.get("draft") or {}
    quality = template_section.get("quality_result") or {}
    blocked = bool(quality.get("blocking_issues")) or quality.get("level") == "blocked" or not template_section.get("success")
    return json_safe(
        {
            "success": True,
            "mode": "selected_candidate_validation",
            "is_full_comparison": False,
            "llm_status": "not_generated",
            "recommendation": "template" if not blocked else "neither",
            "winner": "template" if not blocked else None,
            "scores": {"template": int(quality.get("score", 0) or 0), "llm": None},
            "reasons": [_issue("llm_not_generated", "LLM candidate was not generated because template was explicitly selected.")],
            "blocking_issues": [],
            "warnings": [],
            "comparison": {},
            "metadata": {
                "source_count": None,
                "template_status": draft.get("status"),
                "llm_status": None,
            },
        }
    )


def _normalize_selected_draft(draft: Dict[str, Any], source_bundle: Dict[str, Any]) -> Dict[str, Any]:
    selected = dict(json_safe(draft or {}))
    selected["status"] = "pending_review"
    selected["published_at"] = None
    selected["risk_disclaimer_included"] = True
    selected.setdefault("fact_check_status", "pending")
    selected["sources_json"] = source_bundle
    return json_safe(selected)


def _has_safety_blocker(safety_result: Dict[str, Any]) -> bool:
    if safety_result.get("passed") is False:
        return True
    if safety_result.get("fact_check_status") in {"failed", "needs_sources"}:
        return True
    return any(item.get("type") in SAFETY_BLOCKER_TYPES for item in (safety_result.get("violations") or []))


def _source_grounding_for_candidate(comparison_result: Dict[str, Any], candidate_type: str) -> Dict[str, Any]:
    comparison = (comparison_result or {}).get("comparison") or {}
    grounding = comparison.get("source_grounding") or {}
    result = grounding.get(candidate_type) or {}
    return result if isinstance(result, dict) else {}


def validate_selected_candidate_for_save(
    selected_draft: Dict[str, Any],
    source_bundle: Dict[str, Any],
    safety_result: Dict[str, Any],
    quality_result: Dict[str, Any],
    comparison_result: Dict[str, Any],
    candidate_type: str,
) -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    selected_draft = selected_draft or {}
    source_bundle = source_bundle or {}
    safety_result = safety_result or {}
    quality_result = quality_result or {}
    comparison_result = comparison_result or {}

    if candidate_type not in CANDIDATE_TYPES:
        blockers.append(_issue("invalid_candidate", "candidate_type must be template or llm.", candidate_type=candidate_type))
    for field in ("title", "body", "summary"):
        if not _text(selected_draft.get(field)):
            blockers.append(_issue(f"missing_{field}", f"Selected draft is missing {field}."))
    if selected_draft.get("status") == "approved":
        blockers.append(_issue("approved_not_allowed", "Selected draft status must not be approved."))
    if selected_draft.get("status") == "published":
        blockers.append(_issue("published_not_allowed", "Selected draft status must not be published."))
    if selected_draft.get("published_at") is not None:
        blockers.append(_issue("published_at_not_allowed", "Selected draft published_at must be null."))
    if _has_safety_blocker(safety_result):
        blockers.append(_issue("safety_failed", "Safety validation failed or requires sources."))
    if any(item.get("type") in SAFETY_BLOCKER_TYPES for item in (safety_result.get("violations") or [])):
        blockers.append(_issue("blocked_phrase", "Selected draft contains a blocked safety phrase."))
    if quality_result.get("level") == "blocked":
        blockers.append(_issue("quality_blocked", "Quality gate level is blocked."))
    if quality_result.get("blocking_issues"):
        blockers.append(_issue("quality_blocking_issues", "Quality gate has blocking issues."))

    fact_check_status = selected_draft.get("fact_check_status") or safety_result.get("fact_check_status") or quality_result.get("metadata", {}).get("fact_check_status")
    if fact_check_status == "failed":
        blockers.append(_issue("fact_check_failed", "fact_check_status failed cannot be saved."))
    if fact_check_status == "needs_sources":
        blockers.append(_issue("fact_check_needs_sources", "fact_check_status needs_sources cannot be saved."))
    if selected_draft.get("risk_disclaimer_included") is not True:
        blockers.append(_issue("missing_risk_disclaimer", "risk_disclaimer_included must be true."))
    if not selected_draft.get("sources_json"):
        blockers.append(_issue("missing_sources_json", "Selected draft must include sources_json."))
    if not source_bundle.get("sources"):
        blockers.append(_issue("missing_source_bundle", "source_bundle.sources is required before saving."))

    source_result = validate_candidate_sources(selected_draft, source_bundle)
    if source_result.get("blocking_issues"):
        blockers.extend(source_result.get("blocking_issues") or [])
    warnings.extend(source_result.get("warnings") or [])

    number_result = detect_unsupported_financial_numbers(selected_draft, source_bundle)
    if number_result.get("blocking_issues"):
        blockers.extend(number_result.get("blocking_issues") or [])

    is_full_comparison = comparison_result.get("is_full_comparison", True)
    recommendation = comparison_result.get("recommendation")
    if is_full_comparison and recommendation == "neither":
        blockers.append(_issue("comparison_neither", "Comparison result recommends neither candidate."))
    if recommendation and recommendation != candidate_type:
        warnings.append(
            _issue(
                "comparison_recommendation_mismatch",
                "Human-selected candidate differs from comparison recommendation.",
                recommendation=recommendation,
                candidate_type=candidate_type,
            )
        )
    if recommendation == "needs_editor_review":
        warnings.append(_issue("comparison_needs_editor_review", "Comparison requires editor review; save is allowed only because candidate has no blockers."))
    if candidate_type == "template" and comparison_result.get("llm_status") == "not_generated":
        warnings.append(_issue("llm_not_generated", "LLM candidate was not generated because template was explicitly selected."))

    if candidate_type == "llm":
        llm_source_result = _source_grounding_for_candidate(comparison_result, "llm")
        if llm_source_result.get("blocking_issues"):
            blockers.append(_issue("llm_source_grounding_blocked", "LLM source grounding has blocking issues."))

    for check in quality_result.get("warnings") or []:
        name = check.get("name") or check.get("type")
        if name in {"has_seo_title", "has_seo_description", "has_faq", "title_length_ok", "body_long_enough", "source_metadata_complete"}:
            warnings.append(_issue(name, check.get("message", "Quality warning.")))

    return json_safe({"can_save": not blockers, "blockers": blockers, "warnings": warnings})


def _comparison_summary(comparison_result: Dict[str, Any]) -> Dict[str, Any]:
    return json_safe(
        {
            "mode": comparison_result.get("mode"),
            "is_full_comparison": comparison_result.get("is_full_comparison"),
            "llm_status": comparison_result.get("llm_status"),
            "recommendation": comparison_result.get("recommendation"),
            "winner": comparison_result.get("winner"),
            "scores": comparison_result.get("scores") or {},
            "reason_types": [item.get("type") for item in comparison_result.get("reasons") or [] if isinstance(item, dict)],
        }
    )


def _safety_summary(safety_result: Dict[str, Any]) -> Dict[str, Any]:
    return json_safe(
        {
            "passed": safety_result.get("passed"),
            "fact_check_status": safety_result.get("fact_check_status"),
            "violations": safety_result.get("violations") or [],
        }
    )


def _quality_summary(quality_result: Dict[str, Any]) -> Dict[str, Any]:
    return json_safe(
        {
            "passed": quality_result.get("passed"),
            "score": quality_result.get("score"),
            "level": quality_result.get("level"),
            "recommendation": quality_result.get("recommendation"),
            "blocking_issues": quality_result.get("blocking_issues") or [],
            "warning_count": len(quality_result.get("warnings") or []),
        }
    )


def _llm_metadata(llm_result: Dict[str, Any]) -> Dict[str, Any]:
    error = llm_result.get("error") if isinstance(llm_result.get("error"), dict) else {}
    return json_safe(
        {
            "provider": llm_result.get("provider"),
            "model": llm_result.get("model"),
            "task_name": llm_result.get("task_name"),
            "success": llm_result.get("success"),
            "error": {"type": error.get("type")} if error else None,
        }
    )


def build_sources_json_for_save(
    source_bundle: Dict[str, Any],
    candidate_type: str,
    comparison_result: Dict[str, Any],
    safety_result: Dict[str, Any],
    quality_result: Dict[str, Any],
    llm_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return json_safe(
        {
            "source_bundle": source_bundle or {},
            "candidate_type": candidate_type,
            "comparison_summary": _comparison_summary(comparison_result or {}),
            "safety_summary": _safety_summary(safety_result or {}),
            "quality_summary": _quality_summary(quality_result or {}),
            "llm_metadata": _llm_metadata(llm_result or {}) if candidate_type == "llm" else {},
            "selection": {
                "selected_by": "cli",
                "requires_human_review": True,
                "status_after_save": "pending_review",
            },
        }
    )


def build_selected_candidate_save_payload(
    topic: Dict[str, Any],
    source_bundle: Dict[str, Any],
    candidate_type: str,
    provider: str = "mock",
    template_hint: Optional[str] = None,
    language: str = "id",
    gateway: Any = None,
) -> Dict[str, Any]:
    topic = json_safe(topic or {})
    source_bundle = json_safe(source_bundle or {})
    candidate_type = str(candidate_type or "").strip()
    provider = str(provider or "mock")
    topic_id = topic.get("id") or source_bundle.get("topic_id")

    if candidate_type not in CANDIDATE_TYPES:
        return _base_payload(
            topic_id=topic_id,
            candidate_type=candidate_type,
            provider=provider,
            source_bundle=source_bundle,
            errors=[_error("invalid_candidate", "candidate must be template or llm.", candidate_type=candidate_type)],
        )

    template_section = _build_template_candidate(topic, source_bundle, template_hint)
    if not template_section.get("success"):
        return _base_payload(
            topic_id=topic_id,
            candidate_type=candidate_type,
            provider=provider,
            source_bundle=source_bundle,
            template=template_section,
            errors=template_section.get("errors") or [_error("template_candidate_failed", "Template candidate could not be built.")],
        )

    llm_section: Dict[str, Any] = {"llm_result": {}, "draft_candidate": {}, "safety_result": {}, "quality_result": {}, "errors": []}
    if candidate_type == "llm":
        if gateway is None:
            return _base_payload(
                topic_id=topic_id,
                candidate_type=candidate_type,
                provider=provider,
                source_bundle=source_bundle,
                template=template_section,
                errors=[_error("missing_gateway", "gateway is required when candidate=llm.")],
            )
        llm_result = generate_llm_article_draft_candidate(
            topic,
            source_bundle,
            gateway,
            language=language,
            template_hint=template_hint,
            model_config={"provider": provider},
        )
        llm_section = {
            "llm_result": llm_result.get("llm_result") or {},
            "draft_candidate": llm_result.get("draft_candidate") or {},
            "safety_result": llm_result.get("safety_result") or {},
            "quality_result": llm_result.get("quality_result") or {},
            "errors": llm_result.get("errors") or [],
        }
        if not llm_result.get("success"):
            return _base_payload(
                topic_id=topic_id,
                candidate_type=candidate_type,
                provider=provider,
                source_bundle=source_bundle,
                template=template_section,
                llm=llm_section,
                errors=llm_section.get("errors") or [_error("llm_candidate_failed", "LLM candidate could not be generated.")],
            )
        comparison_result = compare_draft_candidates(
            template_section.get("draft") or {},
            llm_section.get("draft_candidate") or {},
            source_bundle=source_bundle,
            template_safety_result=template_section.get("safety_result") or None,
            template_quality_result=template_section.get("quality_result") or None,
            llm_safety_result=llm_section.get("safety_result") or None,
            llm_quality_result=llm_section.get("quality_result") or None,
        )
        comparison_result["is_full_comparison"] = True
        selected_draft = _normalize_selected_draft(llm_section.get("draft_candidate") or {}, source_bundle)
        safety_result = llm_section.get("safety_result") or {}
        quality_result = llm_section.get("quality_result") or {}
    else:
        comparison_result = _template_only_comparison(template_section)
        selected_draft = _normalize_selected_draft(template_section.get("draft") or {}, source_bundle)
        safety_result = template_section.get("safety_result") or {}
        quality_result = template_section.get("quality_result") or {}

    save_validation = validate_selected_candidate_for_save(
        selected_draft,
        source_bundle,
        safety_result,
        quality_result,
        comparison_result,
        candidate_type,
    )
    selected_draft = dict(selected_draft)
    selected_draft["sources_json"] = build_sources_json_for_save(
        source_bundle,
        candidate_type,
        comparison_result,
        safety_result,
        quality_result,
        llm_section.get("llm_result") or {},
    )
    selected_draft["status"] = "pending_review"
    selected_draft["published_at"] = None
    selected_draft["risk_disclaimer_included"] = True

    errors = [] if save_validation.get("can_save") else [{"type": "save_validation_failed", "message": "Selected candidate cannot be saved.", "retryable": False}]
    return _base_payload(
        topic_id=topic_id,
        candidate_type=candidate_type,
        provider=provider,
        source_bundle=source_bundle,
        selected_draft=selected_draft,
        safety_result=safety_result,
        quality_result=quality_result,
        comparison_result=comparison_result,
        save_validation=save_validation,
        template=template_section,
        llm=llm_section,
        errors=errors,
    )


def _save_summary(
    *,
    inserted: int = 0,
    skipped: int = 0,
    article_sources_inserted: int = 0,
    article_sources_failed: int = 0,
) -> Dict[str, Any]:
    return {
        "inserted": inserted,
        "skipped": skipped,
        "article_sources_inserted": article_sources_inserted,
        "article_sources_failed": article_sources_failed,
        "status": "pending_review",
        "would_publish": False,
    }


def _save_result(
    *,
    selected_payload: Dict[str, Any],
    dry_run: bool,
    article_id: Optional[int] = None,
    summary: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    errors = errors or []
    return json_safe(
        {
            "success": not errors,
            "candidate_type": (selected_payload or {}).get("candidate_type"),
            "dry_run": bool(dry_run),
            "article_id": article_id,
            "selected_draft": (selected_payload or {}).get("selected_draft") or {},
            "save_validation": (selected_payload or {}).get("save_validation") or {},
            "summary": summary or _save_summary(),
            "errors": errors,
        }
    )


def save_selected_candidate_to_postgres(
    dsn: str,
    selected_payload: Dict[str, Any],
    dry_run: bool = True,
) -> Dict[str, Any]:
    selected_payload = json_safe(selected_payload or {})
    validation = selected_payload.get("save_validation") or {}
    if not validation.get("can_save"):
        return _save_result(
            selected_payload=selected_payload,
            dry_run=dry_run,
            errors=[_error("save_validation_failed", "Selected candidate cannot be saved.")],
        )

    draft = dict(selected_payload.get("selected_draft") or {})
    draft["status"] = "pending_review"
    draft["published_at"] = None
    draft["risk_disclaimer_included"] = True
    if draft.get("status") in {"approved", "published"}:
        return _save_result(
            selected_payload=selected_payload,
            dry_run=dry_run,
            errors=[_error("invalid_status", "Selected candidate must not be approved or published.")],
        )

    source_bundle = selected_payload.get("source_bundle") or {}
    article_sources = build_article_sources_from_bundle(source_bundle)
    if dry_run:
        return _save_result(
            selected_payload={**selected_payload, "selected_draft": draft},
            dry_run=True,
            summary=_save_summary(inserted=1, skipped=0, article_sources_inserted=len(article_sources), article_sources_failed=0),
        )

    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("psycopg is required for database operations") from exc

    with psycopg.connect(dsn) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM generated_articles WHERE topic_id = %s LIMIT 1", (int(draft["topic_id"]),))
                if cur.fetchone() is not None:
                    conn.commit()
                    return _save_result(
                        selected_payload={**selected_payload, "selected_draft": draft},
                        dry_run=False,
                        article_id=None,
                        summary=_save_summary(inserted=0, skipped=1, article_sources_inserted=0, article_sources_failed=0),
                    )
                cur.execute(
                    """
                    INSERT INTO generated_articles (
                        topic_id, symbol, language, title, slug, summary, body,
                        seo_title, seo_description, status, fact_check_status,
                        risk_disclaimer_included, sources_json, published_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
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
                        "pending_review",
                        draft.get("fact_check_status") or "pending",
                        True,
                        Jsonb(draft.get("sources_json") or {}),
                        None,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return _save_result(
                        selected_payload={**selected_payload, "selected_draft": draft},
                        dry_run=False,
                        article_id=None,
                        summary=_save_summary(inserted=0, skipped=1, article_sources_inserted=0, article_sources_failed=0),
                    )
                article_id = row[0]
                inserted_sources = 0
                for source in article_sources:
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
                    cur.fetchone()
                    inserted_sources += 1
            conn.commit()
            return _save_result(
                selected_payload={**selected_payload, "selected_draft": draft},
                dry_run=False,
                article_id=article_id,
                summary=_save_summary(inserted=1, skipped=0, article_sources_inserted=inserted_sources, article_sources_failed=0),
            )
        except Exception as exc:
            conn.rollback()
            return _save_result(
                selected_payload={**selected_payload, "selected_draft": draft},
                dry_run=False,
                summary=_save_summary(inserted=0, skipped=0, article_sources_inserted=0, article_sources_failed=len(article_sources)),
                errors=[_error("save_failed", str(exc))],
            )
