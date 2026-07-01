from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.content.article_schema import ArticleDraft

from ._utils import article_to_dict, pydantic_error_summary
from .result import ValidationIssue, ValidationResult


def validate_article_schema(raw_output: dict[str, Any]) -> ValidationResult:
    try:
        article = ArticleDraft.model_validate(raw_output) if hasattr(ArticleDraft, "model_validate") else ArticleDraft.parse_obj(raw_output)
    except ValidationError as exc:
        issues = [
            ValidationIssue(
                code="article_schema_invalid",
                message=item["message"],
                severity="error",
                field=item["field"] or None,
                metadata={"type": item["type"]},
            )
            for item in pydantic_error_summary(exc)
        ]
        return ValidationResult(
            passed=False,
            exportable=False,
            issues=issues,
            metadata={"validation_errors": pydantic_error_summary(exc)},
        )

    return ValidationResult(
        passed=True,
        exportable=True,
        metadata={"article": article_to_dict(article), "parsed_model": article},
    )
