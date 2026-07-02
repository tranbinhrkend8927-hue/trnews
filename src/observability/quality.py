from __future__ import annotations


def summarize_article_quality(article: dict | None, source_bundle: dict | None, validation: dict | None) -> dict:
    article_data = article if isinstance(article, dict) else {}
    bundle_data = source_bundle if isinstance(source_bundle, dict) else {}
    validation_data = validation if isinstance(validation, dict) else {}
    issues = [issue for result in validation_data.values() if isinstance(result, dict) for issue in result.get("issues", []) if isinstance(issue, dict)]
    quality_report = bundle_data.get("source_quality_report") if isinstance(bundle_data.get("source_quality_report"), dict) else {}
    return {
        "body_length": len(str(article_data.get("body") or "")),
        "summary_length": len(str(article_data.get("summary") or "")),
        "title_length": len(str(article_data.get("title") or "")),
        "faq_count": len(article_data.get("faq") or []),
        "candidate_title_count": len(article_data.get("candidate_titles") or []),
        "key_takeaway_count": len(article_data.get("key_takeaways") or []),
        "has_search_intent": bool(article_data.get("search_intent")),
        "has_editorial_angle": bool(article_data.get("editorial_angle")),
        "sources_used_count": len(article_data.get("sources_used") or []),
        "source_bundle_count": _source_bundle_count(bundle_data),
        "uncertain_claims_count": len(article_data.get("uncertain_claims") or []),
        "source_quality": quality_report.get("overall_source_quality"),
        "usable_source_count": quality_report.get("usable_source_count"),
        "source_quality_action": quality_report.get("recommended_action"),
        "validation_passed": all(bool(result.get("passed")) for result in validation_data.values() if isinstance(result, dict)),
        "validator_error_count": sum(1 for issue in issues if issue.get("severity") == "error"),
        "validator_warning_count": sum(1 for issue in issues if issue.get("severity") == "warning"),
        "validator_codes": sorted({str(issue.get("code")) for issue in issues if issue.get("code")}),
    }


def _source_bundle_count(source_bundle: dict) -> int:
    trace_count = (source_bundle.get("source_trace") or {}).get("source_count")
    if isinstance(trace_count, int):
        return trace_count
    sources = source_bundle.get("sources")
    return len(sources) if isinstance(sources, list) else 0
