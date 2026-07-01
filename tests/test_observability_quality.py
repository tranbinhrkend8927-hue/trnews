from src.observability.quality import summarize_article_quality


def test_valid_article_quality_summary():
    summary = summarize_article_quality(
        {"title": "Title", "summary": "Summary", "body": "Body text", "faq": [{"q": "x"}], "sources_used": [{"url": "u"}], "uncertain_claims": [{}]},
        {"sources": [{}, {}]},
        {"schema": {"passed": True, "issues": []}},
    )

    assert summary["body_length"] == len("Body text")
    assert summary["summary_length"] == len("Summary")
    assert summary["title_length"] == len("Title")
    assert summary["faq_count"] == 1
    assert summary["sources_used_count"] == 1
    assert summary["source_bundle_count"] == 2
    assert summary["uncertain_claims_count"] == 1
    assert summary["validation_passed"] is True


def test_missing_article_does_not_crash():
    summary = summarize_article_quality(None, None, None)

    assert summary["body_length"] == 0
    assert summary["source_bundle_count"] == 0


def test_source_trace_count_is_used():
    summary = summarize_article_quality({}, {"source_trace": {"source_count": 3}, "sources": [{}]}, {})

    assert summary["source_bundle_count"] == 3


def test_validation_issue_counts_and_codes():
    summary = summarize_article_quality(
        {},
        {},
        {
            "a": {"passed": False, "issues": [{"severity": "error", "code": "bad"}, {"severity": "warning", "code": "warn"}]},
            "b": {"passed": True, "issues": []},
        },
    )

    assert summary["validation_passed"] is False
    assert summary["validator_error_count"] == 1
    assert summary["validator_warning_count"] == 1
    assert summary["validator_codes"] == ["bad", "warn"]
