import json

from src.jobs import report_feedback
from src.review.feedback import create_review_feedback
from src.review.feedback_store import JsonlReviewFeedbackStore


def add(store, **kwargs):
    data = {
        "review_status": "approved",
        "content_job_key": "job-1",
        "market_id": "usd_idr_id",
        "language": "id",
        "model": "m1",
        "prompt_version": "v1",
        "quality_score": 5,
    }
    data.update(kwargs)
    store.append(create_review_feedback(**data))


def test_empty_store_returns_report_generated(tmp_path, capsys):
    exit_code = report_feedback.report_feedback_command(["--feedback-store-path", str(tmp_path / "feedback.jsonl")])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "FEEDBACK_REPORT_GENERATED"
    assert payload["summary"]["total"] == 0


def test_feedback_outputs_summary(tmp_path, capsys):
    path = tmp_path / "feedback.jsonl"
    add(JsonlReviewFeedbackStore(str(path)))

    exit_code = report_feedback.report_feedback_command(["--feedback-store-path", str(path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["summary"]["total"] == 1


def test_filters(tmp_path, capsys):
    path = tmp_path / "feedback.jsonl"
    store = JsonlReviewFeedbackStore(str(path))
    add(store)
    add(store, review_status="rejected", content_job_key="job-2", market_id="usd_jpy_ja", language="ja", model="m2", prompt_version="v2")

    report_feedback.report_feedback_command(
        [
            "--feedback-store-path",
            str(path),
            "--review-status",
            "approved",
            "--market-id",
            "usd_idr_id",
            "--language",
            "id",
            "--model",
            "m1",
            "--prompt-version",
            "v1",
            "--content-job-key",
            "job-1",
            "--limit",
            "1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["total"] == 1
    assert payload["filters"]["model"] == "m1"
    assert payload["filters"]["content_job_key"] == "job-1"


def test_limit_argument_error(tmp_path, capsys):
    exit_code = report_feedback.report_feedback_command(["--feedback-store-path", str(tmp_path / "feedback.jsonl"), "--limit", "0"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "FEEDBACK_REPORT_ARGUMENT_ERROR"
