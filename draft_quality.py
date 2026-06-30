"""Draft quality gate for generated article drafts before human review."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from safety_validation import (
    BUY_SELL_PHRASES,
    KEY_FINANCIAL_TERMS,
    PROFIT_PROMISE_PHRASES,
    TAKE_PROFIT_STOP_LOSS_PHRASES,
    contains_blocked_phrase,
    has_key_financial_terms,
)


BLOCKING_SAFETY_TYPES = {"profit_promise", "buy_sell_instruction", "take_profit_stop_loss"}
MIN_BODY_CHARS = 500
MIN_SUMMARY_CHARS = 40
MIN_TITLE_CHARS = 20
MAX_TITLE_CHARS = 120


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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _article_text(draft: Dict[str, Any]) -> str:
    return "\n".join(_text(draft.get(field)) for field in ("title", "summary", "body", "seo_title", "seo_description"))


def _sources_from_bundle_or_draft(draft: Dict[str, Any], source_bundle: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if source_bundle and isinstance(source_bundle.get("sources"), list):
        return [source for source in source_bundle.get("sources", []) if source]
    sources_json = draft.get("sources_json")
    if isinstance(sources_json, str):
        try:
            sources_json = json.loads(sources_json)
        except json.JSONDecodeError:
            sources_json = {}
    if isinstance(sources_json, dict) and isinstance(sources_json.get("sources"), list):
        return [source for source in sources_json.get("sources", []) if source]
    return []


def _missing_source_news_ids(draft: Dict[str, Any], source_bundle: Optional[Dict[str, Any]]) -> List[Any]:
    if source_bundle and isinstance(source_bundle.get("missing_source_news_ids"), list):
        return source_bundle.get("missing_source_news_ids") or []
    sources_json = draft.get("sources_json")
    if isinstance(sources_json, str):
        try:
            sources_json = json.loads(sources_json)
        except json.JSONDecodeError:
            return []
    if isinstance(sources_json, dict) and isinstance(sources_json.get("missing_source_news_ids"), list):
        return sources_json.get("missing_source_news_ids") or []
    return []


def _add_check(
    checks: List[Dict[str, Any]],
    issues: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
    *,
    name: str,
    passed: bool,
    severity: str,
    message: str,
) -> None:
    check = {"name": name, "passed": bool(passed), "severity": severity, "message": message}
    checks.append(check)
    if passed:
        return
    if severity == "error":
        issues.append(check)
    else:
        warnings.append(check)


def _has_blocked_phrase(text: str) -> bool:
    return bool(
        contains_blocked_phrase(text, PROFIT_PROMISE_PHRASES)
        or contains_blocked_phrase(text, BUY_SELL_PHRASES)
        or contains_blocked_phrase(text, TAKE_PROFIT_STOP_LOSS_PHRASES)
    )


def _has_section_line(body: str, prefixes: List[str]) -> bool:
    for line in str(body or "").splitlines():
        normalized = line.strip().lower()
        if any(normalized.startswith(prefix) for prefix in prefixes):
            return True
    return False


def evaluate_draft_quality(
    draft: Dict[str, Any],
    source_bundle: Optional[Dict[str, Any]] = None,
    safety_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    draft = draft or {}
    safety_result = safety_result or {}
    checks: List[Dict[str, Any]] = []
    blocking_issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    title = _text(draft.get("title"))
    body = _text(draft.get("body"))
    summary = _text(draft.get("summary"))
    status = _text(draft.get("status"))
    fact_check_status = _text(draft.get("fact_check_status")) or _text(safety_result.get("fact_check_status")) or "pending"
    text = _article_text(draft)
    sources = _sources_from_bundle_or_draft(draft, source_bundle)
    source_count = len(sources)
    missing_ids = _missing_source_news_ids(draft, source_bundle)

    _add_check(checks, blocking_issues, warnings, name="has_title", passed=bool(title), severity="error", message="Title is present.")
    _add_check(checks, blocking_issues, warnings, name="has_body", passed=bool(body), severity="error", message="Body is present.")
    _add_check(checks, blocking_issues, warnings, name="has_summary", passed=bool(summary), severity="error", message="Summary is present.")
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="not_published_or_approved",
        passed=status not in {"published", "approved"},
        severity="error",
        message="Draft status is not approved or published.",
    )

    safety_violations = safety_result.get("violations") or []
    has_safety_blocker = any(item.get("type") in BLOCKING_SAFETY_TYPES for item in safety_violations)
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="safety_has_no_blocked_phrase_violation",
        passed=not has_safety_blocker,
        severity="error",
        message="Safety validation has no blocked phrase violations.",
    )
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="fact_check_not_failed",
        passed=fact_check_status != "failed",
        severity="error",
        message="Fact check status is not failed.",
    )
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="has_risk_disclaimer_flag",
        passed=bool(draft.get("risk_disclaimer_included", False)),
        severity="error",
        message="Risk disclaimer flag is present.",
    )
    body_lower = body.lower()
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="body_has_risk_disclaimer_section",
        passed=_has_section_line(body, ["catatan risiko", "risiko"]),
        severity="error",
        message="Body includes a risk section.",
    )
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="body_has_source_section",
        passed=_has_section_line(body, ["sumber"]),
        severity="error",
        message="Body includes a source section.",
    )
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="supported_template",
        passed=not bool(draft.get("template_error") or draft.get("unsupported_template")),
        severity="error",
        message="Draft template is supported.",
    )
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="financial_terms_have_sources",
        passed=not (source_count == 0 and has_key_financial_terms(text)),
        severity="error",
        message="Financial terms have at least one source.",
    )
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="no_blocked_phrases",
        passed=not _has_blocked_phrase(text),
        severity="error",
        message="Draft contains no buy/sell, TP/SL, or profit-promise phrases.",
    )

    body_too_short = len(body) < MIN_BODY_CHARS
    faq_missing = "faq" not in body_lower
    _add_check(checks, blocking_issues, warnings, name="has_sources", passed=source_count > 0, severity="warning", message="At least one source is present.")
    _add_check(checks, blocking_issues, warnings, name="no_missing_source_news_ids", passed=not missing_ids, severity="warning", message="All source news IDs were resolved.")
    _add_check(checks, blocking_issues, warnings, name="fact_check_not_needs_sources", passed=fact_check_status != "needs_sources", severity="warning", message="Fact check status does not need sources.")
    _add_check(checks, blocking_issues, warnings, name="body_long_enough", passed=not body_too_short, severity="warning", message="Body is long enough for review.")
    _add_check(checks, blocking_issues, warnings, name="has_faq", passed=not faq_missing, severity="warning", message="FAQ section is present.")
    _add_check(checks, blocking_issues, warnings, name="has_seo_title", passed=bool(_text(draft.get("seo_title"))), severity="warning", message="SEO title is present.")
    _add_check(checks, blocking_issues, warnings, name="has_seo_description", passed=bool(_text(draft.get("seo_description"))), severity="warning", message="SEO description is present.")
    _add_check(checks, blocking_issues, warnings, name="has_slug", passed=bool(_text(draft.get("slug"))), severity="warning", message="Slug is present.")
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="title_length_ok",
        passed=MIN_TITLE_CHARS <= len(title) <= MAX_TITLE_CHARS,
        severity="warning",
        message="Title length is within review range.",
    )
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="summary_length_ok",
        passed=len(summary) >= MIN_SUMMARY_CHARS,
        severity="warning",
        message="Summary is long enough.",
    )

    missing_source_metadata = any(not source.get("title") or not (source.get("url") or source.get("canonical_url") or source.get("source_url")) for source in sources)
    _add_check(
        checks,
        blocking_issues,
        warnings,
        name="source_metadata_complete",
        passed=not missing_source_metadata,
        severity="warning",
        message="Source title and URL are present when sources exist.",
    )

    score = 100
    score -= 25 * len(blocking_issues)
    score -= 5 * len(warnings)
    if source_count == 0:
        score -= 20
    if fact_check_status == "needs_sources":
        score -= 15
    if body_too_short:
        score -= 10
    if faq_missing:
        score -= 10
    score = max(0, min(100, score))

    if blocking_issues:
        level = "blocked"
    elif score >= 85:
        level = "ready_for_review"
    elif score >= 60:
        level = "needs_review"
    else:
        level = "needs_rework"

    recommendation = "pending_review" if level in {"ready_for_review", "needs_review"} else "needs_rework"

    return json_safe(
        {
            "passed": not blocking_issues,
            "score": score,
            "level": level,
            "recommendation": recommendation,
            "checks": checks,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "metadata": {
                "source_count": source_count,
                "missing_source_news_ids": missing_ids,
                "has_risk_disclaimer": bool(draft.get("risk_disclaimer_included", False)),
                "fact_check_status": fact_check_status,
                "status": status,
            },
        }
    )
