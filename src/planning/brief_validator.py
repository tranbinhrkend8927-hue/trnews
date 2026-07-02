from __future__ import annotations

from src.models.brief import BriefValidationIssue, BriefValidationResult, EditorialBrief


REQUIRED_TEXT_FIELDS = [
    "event_summary",
    "why_it_matters",
    "market_context",
    "primary_angle",
    "target_reader",
]

REQUIRED_LIST_FIELDS = [
    "reader_questions",
    "must_cover",
    "avoid_claims",
    "recommended_structure",
]


def validate_editorial_brief(brief: EditorialBrief) -> BriefValidationResult:
    issues: list[BriefValidationIssue] = []

    for field in REQUIRED_TEXT_FIELDS:
        if not str(getattr(brief, field, "") or "").strip():
            issues.append(
                BriefValidationIssue(
                    code="missing_required_field",
                    message=f"{field} is required.",
                    severity="error",
                    field=field,
                )
            )

    for field in REQUIRED_LIST_FIELDS:
        if not list(getattr(brief, field, []) or []):
            issues.append(
                BriefValidationIssue(
                    code="missing_required_list",
                    message=f"{field} must contain at least one item.",
                    severity="error",
                    field=field,
                )
            )

    if brief.confidence_level == "low":
        issues.append(
            BriefValidationIssue(
                code="low_confidence",
                message="Brief confidence is low and should receive manual review.",
                severity="warning",
                field="confidence_level",
            )
        )

    if brief.source_gaps and brief.content_type == "deep_article":
        issues.append(
            BriefValidationIssue(
                code="source_gaps_for_deep_article",
                message="Deep article brief has source gaps that may require downgrade or manual review.",
                severity="warning",
                field="source_gaps",
            )
        )

    has_errors = any(issue.severity == "error" for issue in issues)
    return BriefValidationResult(
        passed=not has_errors,
        recommended_status=_recommended_status(brief, issues),
        issues=issues,
        warnings=[issue.message for issue in issues if issue.severity == "warning"],
    )


def _recommended_status(brief: EditorialBrief, issues: list[BriefValidationIssue]) -> str:
    if any(issue.severity == "error" for issue in issues):
        return "needs_brief_rewrite"
    if brief.confidence_level == "low":
        if brief.content_type == "market_brief":
            return "write_brief_only"
        return "needs_manual_review"
    if brief.content_type == "market_brief":
        return "write_brief_only"
    return "ready"
