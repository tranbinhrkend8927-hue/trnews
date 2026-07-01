from src.review.feedback import create_review_feedback
from src.review.metrics import summarize_review_feedback


def fb(**kwargs):
    data = {"review_status": "approved"}
    data.update(kwargs)
    return create_review_feedback(**data)


def test_empty_feedback_summary():
    summary = summarize_review_feedback([])

    assert summary["total"] == 0
    assert summary["avg_scores"]["quality"] is None


def test_by_status_and_rates():
    summary = summarize_review_feedback(
        [
            fb(review_status="approved"),
            fb(review_status="published"),
            fb(review_status="rejected"),
            fb(review_status="needs_rewrite"),
            fb(review_status="needs_source_fix"),
            fb(review_status="needs_compliance_fix"),
            fb(review_status="needs_language_fix"),
        ]
    )

    assert summary["by_status"]["approved"] == 1
    assert summary["approval_rate"] == round(2 / 7, 4)
    assert summary["rejection_rate"] == round(1 / 7, 4)
    assert summary["rewrite_rate"] == round(1 / 7, 4)
    assert summary["source_fix_rate"] == round(1 / 7, 4)
    assert summary["compliance_fix_rate"] == round(1 / 7, 4)
    assert summary["language_fix_rate"] == round(1 / 7, 4)


def test_avg_scores():
    summary = summarize_review_feedback([fb(quality_score=5, factuality_score=4, language_score=3, seo_score=2, compliance_score=1), fb(quality_score=3)])

    assert summary["avg_scores"]["quality"] == 4.0
    assert summary["avg_scores"]["factuality"] == 4.0


def test_grouping_by_market_language_model_prompt_and_issues():
    summary = summarize_review_feedback(
        [
            fb(market_id="usd_idr_id", language="id", model="m1", prompt_version="v1", quality_score=5, issues=["tone", "source"]),
            fb(review_status="rejected", market_id="usd_idr_id", language="id", model="m1", prompt_version="v1", quality_score=1, issues=["tone"]),
            fb(review_status="needs_language_fix", market_id="usd_jpy_ja", language="ja", model="m2", prompt_version="v2", quality_score=2),
        ]
    )

    assert summary["by_market"]["usd_idr_id"]["total"] == 2
    assert summary["by_language"]["id"]["rejected"] == 1
    assert summary["by_model"]["m1"]["avg_quality_score"] == 3.0
    assert summary["by_prompt_version"]["v1"]["approved"] == 1
    assert summary["by_prompt_version"]["v2"]["needs_fix"] == 1
    assert summary["top_issues"]["tone"] == 2
