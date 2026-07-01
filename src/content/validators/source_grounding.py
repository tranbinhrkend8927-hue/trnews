from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from ._utils import parse_article, pydantic_error_summary
from .result import ValidationIssue, ValidationResult


URL_RE = re.compile(r"https?://[^\s<>()\"']+")


def validate_source_grounding(article, source_bundle: dict[str, Any]) -> ValidationResult:
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
                    message="ArticleDraft could not be parsed before source grounding validation.",
                    severity="error",
                    metadata={"validation_errors": pydantic_error_summary(exc)},
                )
            ],
        )

    sources = list((source_bundle or {}).get("sources") or [])
    source_ids = {str(source.get("source_id")) for source in sources if source.get("source_id") is not None}
    news_ids = set()
    for source in sources:
        for key in ("news_id", "id"):
            if source.get(key) is not None:
                news_ids.add(str(source.get(key)))
        raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
        for key in ("news_id", "id"):
            if raw.get(key) is not None:
                news_ids.add(str(raw.get(key)))
    urls = {
        _clean_url(str(source.get(key)))
        for source in sources
        for key in ("url", "canonical_url")
        if source.get(key)
    }

    if not parsed.sources_used:
        issues.append(
            ValidationIssue(
                code="missing_sources_used",
                message="article.sources_used must contain at least one source.",
                severity="error",
                field="sources_used",
            )
        )

    for index, source in enumerate(parsed.sources_used):
        field_prefix = f"sources_used.{index}"
        if str(source.source_id) not in source_ids:
            issues.append(
                ValidationIssue(
                    code="unknown_source_id",
                    message=f"Unknown source_id: {source.source_id}",
                    severity="error",
                    field=f"{field_prefix}.source_id",
                )
            )
        if source.news_id is not None and str(source.news_id) not in news_ids:
            issues.append(
                ValidationIssue(
                    code="unknown_news_id",
                    message=f"Unknown news_id: {source.news_id}",
                    severity="error",
                    field=f"{field_prefix}.news_id",
                )
            )
        if source.url and _clean_url(source.url) not in urls:
            issues.append(
                ValidationIssue(
                    code="unknown_source_url",
                    message=f"Unknown source URL: {source.url}",
                    severity="error",
                    field=f"{field_prefix}.url",
                )
            )

    for url in _extract_urls(parsed.body):
        if url not in urls:
            issues.append(
                ValidationIssue(
                    code="unknown_body_url",
                    message=f"Body contains URL outside source_bundle: {url}",
                    severity="error",
                    field="body",
                )
            )

    return ValidationResult(
        passed=not any(issue.severity == "error" for issue in issues),
        exportable=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        metadata={"source_count": len(sources), "sources_used_count": len(parsed.sources_used)},
    )


def _extract_urls(text: str) -> list[str]:
    return [_clean_url(match.group(0)) for match in URL_RE.finditer(text or "")]


def _clean_url(url: str) -> str:
    return str(url or "").rstrip(".,);]}>\"'")
