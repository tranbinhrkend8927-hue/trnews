from __future__ import annotations

from typing import Any

from src.models.quality import ArticleQualityReport


MARKET_CONTEXT_HINTS = [
    "bank sentral",
    "central bank",
    "inflasi",
    "inflation",
    "suku bunga",
    "interest rate",
    "data ekonomi",
    "macro",
    "makro",
    "risk sentiment",
    "sentimen risiko",
]


def build_article_quality_report(
    *,
    article: dict[str, Any],
    source_bundle: dict[str, Any],
    validation: dict[str, Any] | None = None,
    ai_review: dict[str, Any] | None = None,
) -> ArticleQualityReport:
    """Aggregate deterministic, source, and reviewer signals into one quality report."""
    article_data = article if isinstance(article, dict) else {}
    bundle_data = source_bundle if isinstance(source_bundle, dict) else {}
    validation_data = validation if isinstance(validation, dict) else {}
    ai_review_data = ai_review if isinstance(ai_review, dict) else _ai_review_from_bundle(bundle_data)
    source_quality = bundle_data.get("source_quality_report") if isinstance(bundle_data.get("source_quality_report"), dict) else {}
    issues = _validation_issues(validation_data)
    blocking = _blocking_issues(issues, ai_review_data, source_quality)
    warnings = _warnings(issues, ai_review_data, source_quality)
    headline_risk = _headline_risk(article_data, ai_review_data)
    financial_advice = _financial_advice_detected(issues, ai_review_data)
    grounded_ratio = _grounded_claim_ratio(validation_data, ai_review_data)
    score = _editor_ready_score(
        article=article_data,
        source_quality=source_quality,
        validation_issues=issues,
        ai_review=ai_review_data,
        blocking_issues=blocking,
        warnings=warnings,
        financial_advice_detected=financial_advice,
    )
    return ArticleQualityReport(
        source_count=_source_count(bundle_data, source_quality),
        usable_source_count=int(source_quality.get("usable_source_count") or 0),
        body_length=len(str(article_data.get("body") or "")),
        faq_count=len(article_data.get("faq") or []),
        has_market_context=_has_market_context(article_data),
        has_risk_disclaimer=bool(str(article_data.get("risk_disclaimer") or "").strip()),
        has_source_attribution=bool(article_data.get("sources_used")) or "Sumber" in str(article_data.get("body") or ""),
        grounded_claim_ratio=grounded_ratio,
        headline_risk_level=headline_risk,
        financial_advice_detected=financial_advice,
        editor_ready_score=score,
        blocking_issues=blocking,
        warnings=warnings,
        final_recommended_status=_final_status(score, blocking, ai_review_data, source_quality),
    )


def _ai_review_from_bundle(source_bundle: dict[str, Any]) -> dict[str, Any]:
    review = source_bundle.get("ai_review")
    return review if isinstance(review, dict) else {}


def _validation_issues(validation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {**issue, "validator": name}
        for name, result in validation.items()
        if isinstance(result, dict)
        for issue in result.get("issues", [])
        if isinstance(issue, dict)
    ]


def _blocking_issues(issues: list[dict[str, Any]], ai_review: dict[str, Any], source_quality: dict[str, Any]) -> list[str]:
    blocking = [f"{issue.get('validator')}: {issue.get('code') or issue.get('message')}" for issue in issues if issue.get("severity") == "error"]
    if source_quality.get("recommended_action") == "skip_or_manual_review":
        blocking.append("source_quality: skip_or_manual_review")
    if ai_review.get("publish_readiness") == "reject":
        blocking.append("ai_review: reject")
    return _unique(blocking)


def _warnings(issues: list[dict[str, Any]], ai_review: dict[str, Any], source_quality: dict[str, Any]) -> list[str]:
    warnings = [f"{issue.get('validator')}: {issue.get('code') or issue.get('message')}" for issue in issues if issue.get("severity") == "warning"]
    if source_quality.get("recommended_action") == "write_brief_only":
        warnings.append("source_quality: write_brief_only")
    for item in ai_review.get("missing_context") or []:
        warnings.append(f"ai_review missing_context: {item}")
    for issue in ai_review.get("issues") or []:
        if isinstance(issue, dict) and issue.get("severity") in ("low", "medium"):
            warnings.append(f"ai_review: {issue.get('issue_type')} - {issue.get('description')}")
    return _unique(warnings)


def _headline_risk(article: dict[str, Any], ai_review: dict[str, Any]) -> str:
    if any(isinstance(issue, dict) and issue.get("issue_type") == "headline_quality" and issue.get("severity") == "high" for issue in ai_review.get("issues") or []):
        return "high"
    title = str(article.get("title") or "").lower()
    high_terms = ["pasti", "guaranteed", "profit", "buy now", "sell now", "beli sekarang", "jual sekarang"]
    if any(term in title for term in high_terms):
        return "high"
    medium_terms = ["melonjak", "anjlok", "soars", "plunges"]
    if any(term in title for term in medium_terms):
        return "medium"
    return "low"


def _financial_advice_detected(issues: list[dict[str, Any]], ai_review: dict[str, Any]) -> bool:
    if any(issue.get("validator") == "financial_safety" and issue.get("severity") == "error" for issue in issues):
        return True
    return any(isinstance(issue, dict) and issue.get("issue_type") == "financial_safety" for issue in ai_review.get("issues") or [])


def _grounded_claim_ratio(validation: dict[str, Any], ai_review: dict[str, Any]) -> float | None:
    source_grounding = validation.get("source_grounding")
    if isinstance(source_grounding, dict):
        issue_count = len(source_grounding.get("issues") or [])
        if issue_count == 0:
            return 1.0
        return max(0.0, 1.0 - min(issue_count, 5) * 0.2)
    unsupported = len(ai_review.get("unsupported_claims") or [])
    if unsupported:
        return max(0.0, 1.0 - min(unsupported, 5) * 0.2)
    return None


def _editor_ready_score(
    *,
    article: dict[str, Any],
    source_quality: dict[str, Any],
    validation_issues: list[dict[str, Any]],
    ai_review: dict[str, Any],
    blocking_issues: list[str],
    warnings: list[str],
    financial_advice_detected: bool,
) -> int:
    score = 100
    score -= len(blocking_issues) * 25
    score -= len(warnings) * 5
    score -= sum(8 for issue in validation_issues if issue.get("severity") == "warning")
    source_quality_name = source_quality.get("overall_source_quality")
    score += {"strong": 0, "acceptable": -8, "weak": -22, "insufficient": -45}.get(source_quality_name, -10)
    if ai_review:
        scores = ai_review.get("scores") if isinstance(ai_review.get("scores"), dict) else {}
        if scores:
            score = min(score, int(sum(int(scores.get(key) or 0) for key in scores) / max(len(scores), 1)) + 10)
        if ai_review.get("publish_readiness") == "needs_edit":
            score -= 15
        if ai_review.get("publish_readiness") == "reject":
            score -= 35
    if not article.get("faq"):
        score -= 5
    if not article.get("sources_used"):
        score -= 15
    if financial_advice_detected:
        score = min(score, 25)
    return max(0, min(100, int(score)))


def _final_status(score: int, blocking: list[str], ai_review: dict[str, Any], source_quality: dict[str, Any]) -> str:
    if ai_review.get("publish_readiness") == "reject" or any("financial_safety" in issue for issue in blocking):
        return "rejected"
    if source_quality.get("recommended_action") == "skip_or_manual_review":
        return "needs_rewrite"
    if blocking:
        return "needs_rewrite"
    if ai_review.get("publish_readiness") == "needs_edit" or score < 75:
        return "needs_edit"
    return "needs_review"


def _source_count(source_bundle: dict[str, Any], source_quality: dict[str, Any]) -> int:
    if source_quality.get("source_count") is not None:
        return int(source_quality.get("source_count") or 0)
    trace_count = (source_bundle.get("source_trace") or {}).get("source_count")
    if isinstance(trace_count, int):
        return trace_count
    sources = source_bundle.get("sources")
    return len(sources) if isinstance(sources, list) else 0


def _has_market_context(article: dict[str, Any]) -> bool:
    text = "\n".join(
        [
            str(article.get("body") or ""),
            str(article.get("evergreen_context") or ""),
            str(article.get("editorial_angle") or ""),
        ]
    ).lower()
    return any(hint in text for hint in MARKET_CONTEXT_HINTS)


def _unique(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
