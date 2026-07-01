from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ._utils import parse_article, pydantic_error_summary
from .result import ValidationIssue, ValidationResult


def validate_notion_exportable(article, notion_target: dict[str, Any] | None = None) -> ValidationResult:
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
                    message="ArticleDraft could not be parsed before Notion exportability validation.",
                    severity="error",
                    metadata={"validation_errors": pydantic_error_summary(exc)},
                )
            ],
        )

    required_text_fields = [
        "title",
        "body",
        "summary",
        "seo_title",
        "seo_description",
        "risk_disclaimer",
    ]
    for field_name in required_text_fields:
        if not str(getattr(parsed, field_name) or "").strip():
            issues.append(
                ValidationIssue(
                    code=f"missing_{field_name}",
                    message=f"{field_name} is required for Notion export.",
                    severity="error",
                    field=field_name,
                )
            )
    if not parsed.sources_used:
        issues.append(
            ValidationIssue(
                code="missing_sources_used",
                message="sources_used is required for Notion export.",
                severity="error",
                field="sources_used",
            )
        )

    has_errors = any(issue.severity == "error" for issue in issues)
    return ValidationResult(
        passed=not has_errors,
        exportable=not has_errors,
        issues=issues,
        metadata={"notion_target": notion_target or {}},
    )
