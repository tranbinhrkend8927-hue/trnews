import json

from src.review.feedback import create_review_feedback
from src.review.feedback_store import JsonlReviewFeedbackStore


def feedback(**kwargs):
    data = {
        "review_status": "approved",
        "content_job_key": "job-1",
        "notion_page_id": "page-1",
        "market_id": "usd_idr_id",
        "language": "id",
        "model": "model-a",
        "prompt_version": "v1",
    }
    data.update(kwargs)
    return create_review_feedback(**data)


def test_append_and_list(tmp_path):
    store = JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl"))
    store.append(feedback())

    assert store.list_feedback()[0].content_job_key == "job-1"


def test_missing_file_returns_empty(tmp_path):
    assert JsonlReviewFeedbackStore(str(tmp_path / "missing.jsonl")).list_feedback() == []


def test_filters(tmp_path):
    store = JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl"))
    store.append(feedback())
    store.append(feedback(review_status="rejected", content_job_key="job-2", notion_page_id="page-2", market_id="usd_jpy_ja", language="ja", model="model-b", prompt_version="v2"))

    assert store.filter_feedback(review_status="rejected")[0].content_job_key == "job-2"
    assert store.filter_feedback(market_id="usd_idr_id")[0].content_job_key == "job-1"
    assert store.filter_feedback(language="ja")[0].content_job_key == "job-2"
    assert store.filter_feedback(model="model-b")[0].content_job_key == "job-2"
    assert store.filter_feedback(prompt_version="v1")[0].content_job_key == "job-1"
    assert store.filter_feedback(content_job_key="job-2")[0].market_id == "usd_jpy_ja"
    assert len(store.filter_feedback(limit=1)) == 1


def test_latest_by_content_job_key_and_notion_page_id(tmp_path):
    store = JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl"))
    store.append(feedback(review_status="needs_rewrite"))
    store.append(feedback(review_status="approved"))

    assert store.latest_by_content_job_key("job-1").review_status == "approved"
    assert store.latest_by_notion_page_id("page-1").review_status == "approved"


def test_bad_json_line_is_skipped(tmp_path):
    path = tmp_path / "feedback.jsonl"
    path.write_text("bad\n" + json.dumps(feedback().model_dump()) + "\n", encoding="utf-8")

    assert len(JsonlReviewFeedbackStore(str(path)).list_feedback()) == 1


def test_auto_creates_directory(tmp_path):
    path = tmp_path / "nested" / "feedback.jsonl"
    JsonlReviewFeedbackStore(str(path)).append(feedback())

    assert path.exists()
