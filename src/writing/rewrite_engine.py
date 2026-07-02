from __future__ import annotations

import os
from typing import Any

from src.models.rewrite import RewriteAction, RewritePlan


def is_optional_rewrite_enabled() -> bool:
    return os.getenv("ENABLE_OPTIONAL_REWRITE", "0").strip().lower() in ("1", "true", "yes")


def build_rewrite_plan(
    *,
    article: dict[str, Any],
    ai_review: dict[str, Any] | None = None,
    article_quality_report: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
) -> RewritePlan:
    review = ai_review if isinstance(ai_review, dict) else {}
    quality = article_quality_report if isinstance(article_quality_report, dict) else {}
    validators = validation if isinstance(validation, dict) else {}
    actions: list[RewriteAction] = []
    warnings: list[str] = []

    readiness = str(review.get("publish_readiness") or "")
    final_status = str(quality.get("final_recommended_status") or "")
    if readiness == "reject" or final_status == "rejected":
        actions.append(
            RewriteAction(
                action_type="reject_or_rebuild",
                priority="high",
                reason="Reviewer or quality report rejected the draft.",
                suggested_change="Do not auto-rewrite. Return to editor or rebuild from stronger sources.",
                source="quality_gate",
            )
        )
    elif readiness == "needs_edit" or final_status in {"needs_edit", "needs_rewrite"}:
        actions.append(
            RewriteAction(
                action_type="editorial_revision",
                priority="medium",
                reason="Reviewer or quality report requires edits before human approval.",
                suggested_change="Revise only the flagged sections while preserving sourced facts and financial-safety constraints.",
                source="quality_gate",
            )
        )

    for claim in review.get("unsupported_claims") or []:
        actions.append(
            RewriteAction(
                action_type="remove_or_source_claim",
                priority="high",
                reason=str(claim),
                suggested_change="Remove this claim or tie it to a specific source before review.",
                source="ai_review",
            )
        )
    for statement in review.get("overstatements") or []:
        actions.append(
            RewriteAction(
                action_type="soften_overstatement",
                priority="high",
                reason=str(statement),
                suggested_change="Replace deterministic or causal wording with source-bounded language.",
                source="ai_review",
            )
        )
    for context in review.get("missing_context") or []:
        actions.append(
            RewriteAction(
                action_type="add_context",
                priority="medium",
                reason=str(context),
                suggested_change="Add concise market context only if supported by available sources.",
                source="ai_review",
            )
        )
    for suggestion in review.get("rewrite_suggestions") or []:
        actions.append(
            RewriteAction(
                action_type="reviewer_suggestion",
                priority="medium",
                reason="Reviewer suggested a rewrite action.",
                suggested_change=str(suggestion),
                source="ai_review",
            )
        )

    for issue in quality.get("blocking_issues") or []:
        actions.append(
            RewriteAction(
                action_type="fix_blocking_issue",
                priority="high",
                reason=str(issue),
                suggested_change="Resolve this blocking issue before sending the draft to normal review.",
                source="quality_report",
            )
        )
    for warning in quality.get("warnings") or []:
        actions.append(
            RewriteAction(
                action_type="review_warning",
                priority="low",
                reason=str(warning),
                suggested_change="Check whether this warning requires an editorial adjustment.",
                source="quality_report",
            )
        )

    for validator_name, result in validators.items():
        if isinstance(result, dict) and not result.get("passed", True):
            actions.append(
                RewriteAction(
                    action_type="validator_failure",
                    priority="high",
                    reason=str(validator_name),
                    suggested_change="Fix deterministic validator failures before any rewrite attempt.",
                    source="validator",
                )
            )

    if not article:
        warnings.append("missing_article")

    return _plan_from_actions(actions=actions, warnings=warnings)


def disabled_rewrite_plan() -> RewritePlan:
    return RewritePlan(enabled=False, status="not_needed", should_rewrite=False, reason="Optional rewrite is disabled.")


def _plan_from_actions(*, actions: list[RewriteAction], warnings: list[str]) -> RewritePlan:
    if not actions:
        return RewritePlan(enabled=True, status="not_needed", should_rewrite=False, reason="No rewrite signals found.", warnings=warnings)
    if any(action.priority == "high" and action.action_type in {"reject_or_rebuild", "validator_failure"} for action in actions):
        status = "blocked"
        reason = "Rewrite is not safe to run automatically because high-priority blocking issues exist."
    else:
        status = "suggested"
        reason = "Rewrite is suggested, but automatic rewriting is not enabled in this phase."
    return RewritePlan(
        enabled=True,
        status=status,
        should_rewrite=True,
        automatic_rewrite_performed=False,
        reason=reason,
        actions=actions,
        warnings=warnings,
    )
