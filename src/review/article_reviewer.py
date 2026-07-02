from __future__ import annotations

import os
from typing import Any

from pydantic import ValidationError

from src.content.article_schema import ArticleDraft
from src.content.validators._utils import parse_article
from src.llm.result import LLMTaskResult
from src.models.review import AIReview, AIReviewIssue, AIReviewScores


DEFAULT_MIN_READY_SCORE = 75
LLM_REVIEW_TASK = "article_review"


def review_article(
    *,
    article: dict[str, Any] | ArticleDraft,
    editorial_brief: dict[str, Any] | None,
    source_bundle: dict[str, Any],
    source_quality_report: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    language: str | None = None,
    language_profile: dict[str, Any] | None = None,
    llm_runner: Any | None = None,
    review_profile: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> AIReview:
    """Review an article with optional LLM reviewer and deterministic fallback."""
    deterministic = review_article_deterministic(
        article=article,
        editorial_brief=editorial_brief,
        source_bundle=source_bundle,
        source_quality_report=source_quality_report,
        validation=validation,
    )
    if not _llm_ai_reviewer_enabled() or llm_runner is None or not review_profile:
        return deterministic

    try:
        result = llm_runner.run(
            task=LLM_REVIEW_TASK,
            language=language or _language_from_profile(language_profile),
            profile=review_profile,
            input_data={
                "article": _article_payload(article),
                "editorial_brief": editorial_brief or {},
                "source_bundle": source_bundle or {},
                "source_quality_report": source_quality_report or _source_quality(source_bundle),
                "validation": validation or {},
                "language_profile": language_profile or {},
            },
            overrides=dict(overrides or {}),
        )
    except Exception as exc:
        return _fallback_review(deterministic, f"LLM reviewer raised {type(exc).__name__}: {exc}")

    if isinstance(result, LLMTaskResult):
        if not result.success:
            message = result.error.message if result.error else "LLM reviewer failed."
            return _fallback_review(deterministic, message)
        output = result.output or {}
    elif isinstance(result, dict):
        if result.get("success") is False:
            return _fallback_review(deterministic, str(result.get("error") or "LLM reviewer failed."))
        output = result.get("output") if isinstance(result.get("output"), dict) else result
    else:
        return _fallback_review(deterministic, "LLM reviewer returned an unsupported result type.")

    try:
        review = AIReview.model_validate(output)
    except ValidationError as exc:
        return _fallback_review(deterministic, f"LLM reviewer output failed AIReview validation: {exc.errors()}")
    return review.model_copy(update={"reviewer_mode": "llm"})


def review_article_deterministic(
    *,
    article: dict[str, Any] | ArticleDraft,
    editorial_brief: dict[str, Any] | None,
    source_bundle: dict[str, Any],
    source_quality_report: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
) -> AIReview:
    """Create a structured review from deterministic signals.

    This does not rewrite the article and does not call an LLM. It provides the
    Phase 3 review contract while AI reviewer prompts are still opt-in work.
    """
    parsed = _parse_or_none(article)
    issues = _issues_from_validation(validation or {})
    unsupported_claims = _unsupported_claims(validation or {})
    financial_issues = [issue for issue in issues if issue.issue_type == "financial_safety"]
    source_quality = source_quality_report or _source_quality(source_bundle)

    issues.extend(_issues_from_source_quality(source_quality))
    issues.extend(_issues_from_brief(parsed, editorial_brief or {}))
    issues.extend(_headline_issues(parsed))

    missing_context = _missing_context(parsed, editorial_brief or {}, source_quality)
    overstatements = _overstatements(parsed)
    for claim in overstatements:
        issues.append(
            AIReviewIssue(
                issue_type="overstatement",
                severity="high",
                location="article",
                description=claim,
                suggested_fix="Soften deterministic market language and tie the statement to source evidence.",
            )
        )

    scores = _scores(
        parsed=parsed,
        source_quality=source_quality,
        issues=issues,
        unsupported_claims=unsupported_claims,
        missing_context=missing_context,
    )
    readiness = _publish_readiness(scores, issues, unsupported_claims, financial_issues)
    return AIReview(
        publish_readiness=readiness,
        scores=scores,
        issues=issues,
        unsupported_claims=unsupported_claims,
        overstatements=overstatements,
        missing_context=missing_context,
        rewrite_suggestions=_rewrite_suggestions(issues, missing_context),
        recommended_editor_action=_editor_action(readiness),
        reviewer_mode="deterministic",
    )


def is_ai_reviewer_enabled() -> bool:
    return os.getenv("ENABLE_AI_REVIEWER", "0").strip().lower() in ("1", "true", "yes")


def is_llm_ai_reviewer_enabled() -> bool:
    return _llm_ai_reviewer_enabled()


def _parse_or_none(article: dict[str, Any] | ArticleDraft) -> ArticleDraft | None:
    try:
        return parse_article(article)
    except ValidationError:
        return None


def _fallback_review(review: AIReview, message: str) -> AIReview:
    issue = AIReviewIssue(
        issue_type="reviewer_runtime",
        severity="medium",
        location="ai_reviewer",
        description=message,
        suggested_fix="Use deterministic review and inspect LLM reviewer configuration before enabling automated LLM review.",
    )
    return review.model_copy(
        update={
            "reviewer_mode": "deterministic_fallback",
            "issues": [*review.issues, issue],
            "rewrite_suggestions": [*review.rewrite_suggestions, issue.suggested_fix],
        }
    )


def _article_payload(article: dict[str, Any] | ArticleDraft) -> dict[str, Any]:
    if hasattr(article, "model_dump"):
        return article.model_dump(mode="json")
    return dict(article or {})


def _language_from_profile(language_profile: dict[str, Any] | None) -> str:
    return str((language_profile or {}).get("language") or "").strip()


def _llm_ai_reviewer_enabled() -> bool:
    return os.getenv("ENABLE_LLM_AI_REVIEWER", "0").strip().lower() in ("1", "true", "yes")


def _issues_from_validation(validation: dict[str, Any]) -> list[AIReviewIssue]:
    issues: list[AIReviewIssue] = []
    for validator_name, result in validation.items():
        if not isinstance(result, dict):
            continue
        for issue in result.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            severity = "high" if issue.get("severity") == "error" else "medium"
            issues.append(
                AIReviewIssue(
                    issue_type=_issue_type_for_validator(validator_name),
                    severity=severity,
                    location=issue.get("field"),
                    description=str(issue.get("message") or issue.get("code") or "Validation issue."),
                    suggested_fix=_suggested_fix_for_validator(validator_name),
                )
            )
    return issues


def _unsupported_claims(validation: dict[str, Any]) -> list[str]:
    claims = []
    for validator_name in ("source_grounding", "article_schema"):
        result = validation.get(validator_name)
        if not isinstance(result, dict):
            continue
        for issue in result.get("issues") or []:
            if isinstance(issue, dict):
                claims.append(str(issue.get("message") or issue.get("code") or "Unsupported claim."))
    return claims


def _issues_from_source_quality(source_quality: dict[str, Any]) -> list[AIReviewIssue]:
    action = source_quality.get("recommended_action")
    if action not in ("write_brief_only", "skip_or_manual_review"):
        return []
    severity = "high" if action == "skip_or_manual_review" else "medium"
    return [
        AIReviewIssue(
            issue_type="source_quality",
            severity=severity,
            location="source_bundle",
            description=f"Source quality recommends {action}.",
            suggested_fix="Add stronger sources or downgrade the article format.",
        )
    ]


def _issues_from_brief(parsed: ArticleDraft | None, editorial_brief: dict[str, Any]) -> list[AIReviewIssue]:
    if parsed is None or not editorial_brief:
        return []
    content_type = editorial_brief.get("content_type")
    if content_type == "market_brief" and parsed.article_type != "market_brief":
        return [
            AIReviewIssue(
                issue_type="brief_alignment",
                severity="medium",
                location="article_type",
                description="Editorial brief recommends market_brief, but article_type is not market_brief.",
                suggested_fix="Change article_type and body structure to a brief format.",
            )
        ]
    return []


def _headline_issues(parsed: ArticleDraft | None) -> list[AIReviewIssue]:
    if parsed is None:
        return []
    risky_terms = ["pasti", "必ず", "guaranteed", "profit", "buy now", "sell now", "beli sekarang", "jual sekarang"]
    title = parsed.title.lower()
    matches = [term for term in risky_terms if term.lower() in title]
    if not matches:
        return []
    return [
        AIReviewIssue(
            issue_type="headline_quality",
            severity="high",
            location="title",
            description="Headline contains overly promotional or deterministic wording.",
            suggested_fix="Use a neutral news headline without trading implication.",
        )
    ]


def _missing_context(parsed: ArticleDraft | None, editorial_brief: dict[str, Any], source_quality: dict[str, Any]) -> list[str]:
    if parsed is None:
        return ["Article could not be parsed for context review."]
    missing = []
    if not parsed.editorial_angle:
        missing.append("Missing editorial angle.")
    if not parsed.key_takeaways:
        missing.append("Missing reader-focused key takeaways.")
    if editorial_brief.get("source_gaps") and "Batasan informasi" not in parsed.body:
        missing.append("Source gaps are not visible in the article body.")
    if source_quality.get("overall_source_quality") in ("weak", "insufficient") and parsed.article_type != "market_brief":
        missing.append("Weak source quality is not reflected in article type.")
    return missing


def _overstatements(parsed: ArticleDraft | None) -> list[str]:
    if parsed is None:
        return []
    text = "\n".join([parsed.title, parsed.summary, parsed.body, parsed.seo_title, parsed.seo_description]).lower()
    phrases = ["pasti naik", "pasti turun", "guaranteed", "certainly rise", "certainly fall", "必ず上昇", "必ず下落"]
    return [f"Overly certain phrase detected: {phrase}" for phrase in phrases if phrase in text]


def _scores(
    *,
    parsed: ArticleDraft | None,
    source_quality: dict[str, Any],
    issues: list[AIReviewIssue],
    unsupported_claims: list[str],
    missing_context: list[str],
) -> AIReviewScores:
    high = sum(1 for issue in issues if issue.severity == "high")
    medium = sum(1 for issue in issues if issue.severity == "medium")
    quality = source_quality.get("overall_source_quality")
    source_score = {"strong": 90, "acceptable": 78, "weak": 55, "insufficient": 25}.get(quality, 65)
    return AIReviewScores(
        grounding=_clamp(source_score - high * 20 - len(unsupported_claims) * 20),
        depth=_clamp(_depth_base(parsed) - len(missing_context) * 12 - medium * 6),
        readability=_clamp(82 - medium * 4 - high * 10),
        headline_quality=_clamp(88 - sum(25 for issue in issues if issue.issue_type == "headline_quality")),
        financial_safety=_clamp(95 - sum(35 for issue in issues if issue.issue_type == "financial_safety") - len(_overstatements(parsed)) * 20),
        source_usefulness=_clamp(source_score),
    )


def _publish_readiness(
    scores: AIReviewScores,
    issues: list[AIReviewIssue],
    unsupported_claims: list[str],
    financial_issues: list[AIReviewIssue],
) -> str:
    if financial_issues or any(issue.issue_type == "overstatement" and issue.severity == "high" for issue in issues):
        return "reject" if _reject_on_financial_safety() else "needs_edit"
    if unsupported_claims:
        return "needs_edit"
    if any(issue.severity == "high" for issue in issues):
        return "needs_edit"
    min_ready = _env_int("AI_REVIEW_MIN_READY_SCORE", DEFAULT_MIN_READY_SCORE)
    score_values = [
        scores.grounding,
        scores.depth,
        scores.readability,
        scores.headline_quality,
        scores.financial_safety,
        scores.source_usefulness,
    ]
    if min(score_values) < min_ready:
        return "needs_edit"
    return "ready"


def _rewrite_suggestions(issues: list[AIReviewIssue], missing_context: list[str]) -> list[str]:
    suggestions = [issue.suggested_fix for issue in issues if issue.suggested_fix]
    suggestions.extend(f"Address missing context: {item}" for item in missing_context)
    return list(dict.fromkeys(suggestions))


def _editor_action(readiness: str) -> str:
    if readiness == "ready":
        return "Send to Notion human review."
    if readiness == "needs_edit":
        return "Send to editor with highlighted issues or rewrite before review."
    return "Reject draft or require rewrite before editor review."


def _issue_type_for_validator(name: str) -> str:
    if name == "financial_safety":
        return "financial_safety"
    if name == "source_grounding":
        return "unsupported_claim"
    if name == "depth_quality":
        return "depth"
    if name == "language_rules":
        return "readability"
    if name == "article_schema":
        return "format"
    return name


def _suggested_fix_for_validator(name: str) -> str:
    if name == "financial_safety":
        return "Remove trading advice, guaranteed outcomes, price targets, and deterministic predictions."
    if name == "source_grounding":
        return "Remove unsupported claim or cite a known source from source_bundle."
    if name == "depth_quality":
        return "Add supported context, FAQ, or takeaways without inventing facts."
    return "Revise the article to satisfy this validation rule."


def _source_quality(source_bundle: dict[str, Any]) -> dict[str, Any]:
    report = source_bundle.get("source_quality_report")
    return report if isinstance(report, dict) else {}


def _depth_base(parsed: ArticleDraft | None) -> int:
    if parsed is None:
        return 0
    body_length = len(parsed.body or "")
    if parsed.article_type == "market_brief":
        return 78 if body_length >= 250 else 60
    if body_length >= 900:
        return 90
    if body_length >= 500:
        return 78
    return 60


def _reject_on_financial_safety() -> bool:
    return os.getenv("AI_REVIEW_REJECT_ON_FINANCIAL_SAFETY", "1").strip().lower() in ("1", "true", "yes")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int) -> int:
    return max(0, min(100, int(value)))
