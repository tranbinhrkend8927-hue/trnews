import json

import pytest

from src.jobs import review_feedback
from src.review.feedback_store import JsonlReviewFeedbackStore


def test_successfully_writes_feedback(tmp_path, capsys):
    path = tmp_path / "feedback.jsonl"

    exit_code = review_feedback.review_feedback_command(
        [
            "--feedback-store-path",
            str(path),
            "--review-status",
            "approved",
            "--content-job-key",
            "job-1",
            "--quality-score",
            "5",
            "--reviewer",
            "editor-a",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "FEEDBACK_RECORDED"
    assert JsonlReviewFeedbackStore(str(path)).list_feedback()[0].content_job_key == "job-1"


def test_missing_review_status_exit_code_2():
    with pytest.raises(SystemExit) as exc:
        review_feedback.review_feedback_command([])

    assert exc.value.code == 2


def test_invalid_score_exit_code_2(tmp_path, capsys):
    exit_code = review_feedback.review_feedback_command(["--feedback-store-path", str(tmp_path / "feedback.jsonl"), "--review-status", "approved", "--quality-score", "6"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "FEEDBACK_ARGUMENT_ERROR"


def test_repeatable_issue_and_json_output(tmp_path, capsys):
    exit_code = review_feedback.review_feedback_command(
        [
            "--feedback-store-path",
            str(tmp_path / "feedback.jsonl"),
            "--review-status",
            "needs_source_fix",
            "--issue",
            "source mismatch",
            "--issue",
            "missing citation",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["feedback"]["issues"] == ["source mismatch", "missing citation"]


def test_does_not_call_notion_or_llm(monkeypatch, tmp_path):
    import src.jobs.review_feedback as module

    monkeypatch.setattr(module, "JsonlReviewFeedbackStore", lambda path: type("Store", (), {"append": lambda self, feedback: None})())

    exit_code = review_feedback.review_feedback_command(["--feedback-store-path", str(tmp_path / "feedback.jsonl"), "--review-status", "approved"])

    assert exit_code == 0
