from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ._utils import parse_article, pydantic_error_summary
from .result import ValidationIssue, ValidationResult


DEFAULT_MIN_BODY_LENGTH = 180
DEFAULT_MIN_FAQ_COUNT = 1
DEFAULT_MIN_TAKEAWAYS = 1


def validate_depth_quality(article, language_profile: dict[str, Any] | None = None, source_bundle: dict[str, Any] | None = None) -> ValidationResult:
    issues: list[ValidationIssue] = []
    try:
        parsed = parse_article(article)
    except ValidationError as exc:
        return ValidationResult(
            passed=False,
            exportable=False,
            issues=[
                ValidationIssue(
                    code="article_schema_invalid",
                    message="ArticleDraft could not be parsed before depth quality validation.",
                    severity="error",
                    metadata={"validation_errors": pydantic_error_summary(exc)},
                )
            ],
        )

    profile = language_profile or {}
    quality = profile.get("quality") or {}
    min_body_length = int(quality.get("min_body_length") or DEFAULT_MIN_BODY_LENGTH)
    min_faq_count = int(quality.get("min_faq_count") or DEFAULT_MIN_FAQ_COUNT)
    min_takeaways = int(quality.get("min_key_takeaways") or DEFAULT_MIN_TAKEAWAYS)

    body = parsed.body.strip()
    if len(body) < min_body_length:
        issues.append(
            ValidationIssue(
                code="body_too_short_for_depth",
                message=f"Article body is too short for a deep FX explainer. Minimum length is {min_body_length}.",
                severity="warning",
                field="body",
                metadata={"body_length": len(body), "min_body_length": min_body_length},
            )
        )

    if len(parsed.faq) < min_faq_count:
        issues.append(
            ValidationIssue(
                code="faq_too_sparse",
                message=f"Deep FX articles should include at least {min_faq_count} FAQ item(s).",
                severity="warning",
                field="faq",
                metadata={"faq_count": len(parsed.faq), "min_faq_count": min_faq_count},
            )
        )

    if len(parsed.key_takeaways) < min_takeaways:
        issues.append(
            ValidationIssue(
                code="missing_key_takeaways",
                message=f"Deep FX articles should include at least {min_takeaways} key takeaway(s).",
                severity="warning",
                field="key_takeaways",
                metadata={"key_takeaway_count": len(parsed.key_takeaways), "min_key_takeaways": min_takeaways},
            )
        )

    if not parsed.search_intent:
        issues.append(
            ValidationIssue(
                code="missing_search_intent",
                message="Article should declare the reader/search intent it serves.",
                severity="warning",
                field="search_intent",
            )
        )

    if not parsed.editorial_angle:
        issues.append(
            ValidationIssue(
                code="missing_editorial_angle",
                message="Article should include an editorial angle for human review.",
                severity="warning",
                field="editorial_angle",
            )
        )

    source_count = _source_count(source_bundle or {})
    metadata = {
        "body_length": len(body),
        "faq_count": len(parsed.faq),
        "key_takeaway_count": len(parsed.key_takeaways),
        "source_count": source_count,
        "readability": {
            "paragraph_count": len([part for part in body.split("\n\n") if part.strip()]),
            "candidate_title_count": len(parsed.candidate_titles),
        },
    }
    has_errors = any(issue.severity == "error" for issue in issues)
    return ValidationResult(passed=not has_errors, exportable=not has_errors, issues=issues, metadata=metadata)


def _source_count(source_bundle: dict[str, Any]) -> int:
    trace_count = (source_bundle.get("source_trace") or {}).get("source_count")
    if isinstance(trace_count, int):
        return trace_count
    sources = source_bundle.get("sources")
    return len(sources) if isinstance(sources, list) else 0
