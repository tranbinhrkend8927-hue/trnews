from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from news_pipeline.safety_validation import validate_financial_safety as legacy_validate_financial_safety

from ._utils import article_to_dict, parse_article, pydantic_error_summary
from .result import ValidationIssue, ValidationResult


PROFIT_PROMISE_EXTRA = ["利益保証", "必ず利益", "guaranteed returns"]
BUY_SELL_EXTRA = ["今すぐ買う", "今すぐ売る"]
STRONG_PREDICTION_PHRASES = [
    "certainly rise",
    "certainly fall",
    "pasti naik",
    "pasti turun",
    "必ず上昇",
    "必ず下落",
]


def validate_financial_safety(article, language_profile: dict[str, Any] | None = None) -> ValidationResult:
    try:
        parsed = parse_article(article)
    except ValidationError as exc:
        return ValidationResult(
            passed=False,
            exportable=False,
            issues=[
                ValidationIssue(
                    code="article_schema_invalid",
                    message="ArticleDraft could not be parsed before financial safety validation.",
                    severity="error",
                    metadata={"validation_errors": pydantic_error_summary(exc)},
                )
            ],
        )

    article_dict = article_to_dict(parsed)
    expected_disclaimer = str((language_profile or {}).get("risk_disclaimer") or "")
    article_dict["risk_disclaimer_included"] = bool(
        parsed.risk_disclaimer.strip()
        and (not expected_disclaimer or expected_disclaimer in parsed.risk_disclaimer)
    )
    legacy_result = legacy_validate_financial_safety(article_dict, article_dict.get("sources_used") or [])
    issues = [
        ValidationIssue(
            code=str(violation.get("type") or "financial_safety_violation"),
            message=_message_for_violation(violation),
            severity="error",
            metadata={"legacy_violation": violation},
        )
        for violation in legacy_result.get("violations") or []
    ]

    text = "\n".join(
        [
            parsed.title,
            parsed.summary,
            parsed.body,
            parsed.seo_title,
            parsed.seo_description,
            parsed.risk_disclaimer,
        ]
    )
    issues.extend(_extra_phrase_issues(text, PROFIT_PROMISE_EXTRA, "profit_promise", "Article contains guaranteed profit language."))
    issues.extend(_extra_phrase_issues(text, BUY_SELL_EXTRA, "buy_sell_instruction", "Article contains buy/sell instruction language."))
    issues.extend(_extra_phrase_issues(text, STRONG_PREDICTION_PHRASES, "strong_prediction", "Article contains overly certain prediction language."))

    has_errors = any(issue.severity == "error" for issue in issues)
    return ValidationResult(
        passed=not has_errors,
        exportable=not has_errors,
        issues=issues,
        metadata={"legacy_result": legacy_result},
    )


def _extra_phrase_issues(text: str, phrases: list[str], code: str, message: str) -> list[ValidationIssue]:
    normalized = text.lower()
    matches = [phrase for phrase in phrases if phrase.lower() in normalized]
    if not matches:
        return []
    return [
        ValidationIssue(
            code=code,
            message=message,
            severity="error",
            metadata={"matches": matches},
        )
    ]


def _message_for_violation(violation: dict[str, Any]) -> str:
    violation_type = str(violation.get("type") or "financial_safety_violation")
    matches = violation.get("matches") or []
    if matches:
        return f"Financial safety violation {violation_type}: {', '.join(str(match) for match in matches)}"
    return f"Financial safety violation: {violation_type}"
