from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ._utils import parse_article, pydantic_error_summary
from .result import ValidationIssue, ValidationResult


def validate_language_rules(article, language_profile: dict[str, Any]) -> ValidationResult:
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
                    message="ArticleDraft could not be parsed before language validation.",
                    severity="error",
                    metadata={"validation_errors": pydantic_error_summary(exc)},
                )
            ],
        )

    profile = language_profile or {}
    expected_language = profile.get("language")
    if expected_language and parsed.language != expected_language:
        issues.append(
            ValidationIssue(
                code="language_mismatch",
                message=f"Article language {parsed.language!r} does not match profile language {expected_language!r}.",
                severity="error",
                field="language",
            )
        )

    expected_disclaimer = str(profile.get("risk_disclaimer") or "")
    if expected_disclaimer and expected_disclaimer not in parsed.risk_disclaimer:
        issues.append(
            ValidationIssue(
                code="risk_disclaimer_mismatch",
                message="Article risk disclaimer must contain the configured language disclaimer.",
                severity="error",
                field="risk_disclaimer",
            )
        )

    for section in profile.get("required_sections") or []:
        if str(section) not in parsed.body:
            issues.append(
                ValidationIssue(
                    code="missing_required_section",
                    message=f"Article body is missing required section: {section}",
                    severity="error",
                    field="body",
                    metadata={"section": section},
                )
            )

    seo = profile.get("seo") or {}
    title_limit = seo.get("title_max_length")
    if title_limit is not None and len(parsed.seo_title) > int(title_limit):
        issues.append(
            ValidationIssue(
                code="seo_title_too_long",
                message=f"seo_title exceeds max length {title_limit}.",
                severity="error",
                field="seo_title",
            )
        )
    description_limit = seo.get("description_max_length")
    if description_limit is not None and len(parsed.seo_description) > int(description_limit):
        issues.append(
            ValidationIssue(
                code="seo_description_too_long",
                message=f"seo_description exceeds max length {description_limit}.",
                severity="error",
                field="seo_description",
            )
        )

    has_errors = any(issue.severity == "error" for issue in issues)
    return ValidationResult(passed=not has_errors, exportable=not has_errors, issues=issues)
