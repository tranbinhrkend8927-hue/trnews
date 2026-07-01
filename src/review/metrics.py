from __future__ import annotations

from src.review.feedback import ReviewFeedback


POSITIVE_STATUSES = {"approved", "published"}
FIX_STATUSES = {"needs_rewrite", "needs_source_fix", "needs_compliance_fix", "needs_language_fix"}


def summarize_review_feedback(feedback_items: list[ReviewFeedback]) -> dict:
    total = len(feedback_items)
    summary = {
        "total": total,
        "by_status": {},
        "approval_rate": 0.0,
        "rejection_rate": 0.0,
        "rewrite_rate": 0.0,
        "source_fix_rate": 0.0,
        "compliance_fix_rate": 0.0,
        "language_fix_rate": 0.0,
        "avg_scores": {
            "quality": None,
            "factuality": None,
            "language": None,
            "seo": None,
            "compliance": None,
        },
        "by_market": {},
        "by_language": {},
        "by_model": {},
        "by_prompt_version": {},
        "top_issues": {},
    }
    if not feedback_items:
        return summary

    for item in feedback_items:
        summary["by_status"][item.review_status] = summary["by_status"].get(item.review_status, 0) + 1
        _count_bucket(summary["by_market"], item.market_id, item)
        _count_bucket(summary["by_language"], item.language, item)
        _count_quality_bucket(summary["by_model"], item.model, item)
        _count_quality_bucket(summary["by_prompt_version"], item.prompt_version, item)
        for issue in item.issues:
            summary["top_issues"][issue] = summary["top_issues"].get(issue, 0) + 1

    summary["approval_rate"] = _rate(sum(1 for item in feedback_items if item.review_status in POSITIVE_STATUSES), total)
    summary["rejection_rate"] = _rate(sum(1 for item in feedback_items if item.review_status == "rejected"), total)
    summary["rewrite_rate"] = _rate(sum(1 for item in feedback_items if item.review_status == "needs_rewrite"), total)
    summary["source_fix_rate"] = _rate(sum(1 for item in feedback_items if item.review_status == "needs_source_fix"), total)
    summary["compliance_fix_rate"] = _rate(sum(1 for item in feedback_items if item.review_status == "needs_compliance_fix"), total)
    summary["language_fix_rate"] = _rate(sum(1 for item in feedback_items if item.review_status == "needs_language_fix"), total)
    summary["avg_scores"] = {
        "quality": _avg([item.quality_score for item in feedback_items]),
        "factuality": _avg([item.factuality_score for item in feedback_items]),
        "language": _avg([item.language_score for item in feedback_items]),
        "seo": _avg([item.seo_score for item in feedback_items]),
        "compliance": _avg([item.compliance_score for item in feedback_items]),
    }
    _finalize_quality_buckets(summary["by_model"])
    _finalize_quality_buckets(summary["by_prompt_version"])
    return summary


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _avg(values: list[int | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(sum(present) / len(present), 4) if present else None


def _count_bucket(bucket: dict, key: str | None, item: ReviewFeedback) -> None:
    if not key:
        return
    data = bucket.setdefault(key, {"total": 0, "approved": 0, "rejected": 0, "needs_fix": 0})
    _count_common(data, item)


def _count_quality_bucket(bucket: dict, key: str | None, item: ReviewFeedback) -> None:
    if not key:
        return
    data = bucket.setdefault(key, {"total": 0, "approved": 0, "rejected": 0, "needs_fix": 0, "quality_scores": [], "avg_quality_score": None})
    _count_common(data, item)
    if item.quality_score is not None:
        data["quality_scores"].append(item.quality_score)


def _count_common(data: dict, item: ReviewFeedback) -> None:
    data["total"] += 1
    if item.review_status in POSITIVE_STATUSES:
        data["approved"] += 1
    if item.review_status == "rejected":
        data["rejected"] += 1
    if item.review_status in FIX_STATUSES:
        data["needs_fix"] += 1


def _finalize_quality_buckets(bucket: dict) -> None:
    for data in bucket.values():
        scores = data.pop("quality_scores", [])
        data["avg_quality_score"] = _avg(scores)
