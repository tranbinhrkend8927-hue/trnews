import json

import pytest

from src.jobs import sync_notion_reviews
from src.review.feedback import create_review_feedback
from src.review.feedback_store import JsonlReviewFeedbackStore
from src.review.notion_sync import NotionReviewSyncResult


class FakeSyncer:
    calls = []
    result = NotionReviewSyncResult(success=True, target_name="notion_articles_id", scanned=1, imported=0, skipped=1)
    write_feedback = False

    def __init__(self, target_resolver, notion_client, feedback_store):
        self.feedback_store = feedback_store

    def sync(self, **kwargs):
        self.__class__.calls.append(kwargs)
        if self.__class__.write_feedback and not kwargs.get("dry_run"):
            self.feedback_store.append(create_review_feedback(review_status="approved", content_job_key="job-1", notion_page_id="page-1"))
            return NotionReviewSyncResult(success=True, target_name=kwargs["target_name"], scanned=1, imported=1, feedback_ids=["feedback"])
        return self.__class__.result


def install(monkeypatch, *, result=None, write_feedback=False):
    FakeSyncer.calls = []
    FakeSyncer.result = result or NotionReviewSyncResult(success=True, target_name="notion_articles_id", scanned=1, imported=0, skipped=1)
    FakeSyncer.write_feedback = write_feedback
    monkeypatch.setattr(sync_notion_reviews, "load_config_registry", lambda: object())
    monkeypatch.setattr(sync_notion_reviews, "NotionTargetResolver", lambda registry: object())
    monkeypatch.setattr(sync_notion_reviews, "NotionClient", lambda: object())
    monkeypatch.setattr(sync_notion_reviews, "NotionReviewSyncer", FakeSyncer)


def test_missing_target_exit_code_2():
    with pytest.raises(SystemExit) as exc:
        sync_notion_reviews.sync_notion_reviews_command([])

    assert exc.value.code == 2


def test_dry_run_success_does_not_write_store(monkeypatch, tmp_path, capsys):
    path = tmp_path / "feedback.jsonl"
    install(monkeypatch)

    exit_code = sync_notion_reviews.sync_notion_reviews_command(["--target", "notion_articles_id", "--feedback-store-path", str(path), "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "NOTION_REVIEWS_SYNCED"
    assert JsonlReviewFeedbackStore(str(path)).list_feedback() == []
    assert FakeSyncer.calls[0]["dry_run"] is True


def test_sync_success_writes_feedback(monkeypatch, tmp_path, capsys):
    path = tmp_path / "feedback.jsonl"
    install(monkeypatch, write_feedback=True)
    monkeypatch.setenv("ENABLE_NOTION_FEEDBACK_SYNC", "1")

    exit_code = sync_notion_reviews.sync_notion_reviews_command(["--target", "notion_articles_id", "--feedback-store-path", str(path)])

    assert exit_code == 0
    assert JsonlReviewFeedbackStore(str(path)).list_feedback()[0].content_job_key == "job-1"


def test_sync_write_is_disabled_by_default(monkeypatch, tmp_path, capsys):
    path = tmp_path / "feedback.jsonl"
    install(monkeypatch, write_feedback=True)
    monkeypatch.delenv("ENABLE_NOTION_FEEDBACK_SYNC", raising=False)

    exit_code = sync_notion_reviews.sync_notion_reviews_command(["--target", "notion_articles_id", "--feedback-store-path", str(path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "NOTION_REVIEW_SYNC_DISABLED"
    assert JsonlReviewFeedbackStore(str(path)).list_feedback() == []
    assert FakeSyncer.calls == []


def test_sync_write_can_be_forced_without_env(monkeypatch, tmp_path, capsys):
    path = tmp_path / "feedback.jsonl"
    install(monkeypatch, write_feedback=True)
    monkeypatch.delenv("ENABLE_NOTION_FEEDBACK_SYNC", raising=False)

    exit_code = sync_notion_reviews.sync_notion_reviews_command(["--target", "notion_articles_id", "--feedback-store-path", str(path), "--force"])

    assert exit_code == 0
    assert JsonlReviewFeedbackStore(str(path)).list_feedback()[0].content_job_key == "job-1"


def test_query_failure_exit_code_1(monkeypatch, tmp_path, capsys):
    install(monkeypatch, result=NotionReviewSyncResult(success=False, target_name="notion_articles_id", errors=[{"type": "notion_query_failed"}]))
    monkeypatch.setenv("ENABLE_NOTION_FEEDBACK_SYNC", "1")

    exit_code = sync_notion_reviews.sync_notion_reviews_command(["--target", "notion_articles_id", "--feedback-store-path", str(tmp_path / "feedback.jsonl")])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "NOTION_REVIEW_SYNC_FAILED"


def test_output_json_status_repeatable_and_limit(monkeypatch, tmp_path, capsys):
    install(monkeypatch)
    monkeypatch.setenv("ENABLE_NOTION_FEEDBACK_SYNC", "1")

    exit_code = sync_notion_reviews.sync_notion_reviews_command(
        [
            "--target",
            "notion_articles_id",
            "--feedback-store-path",
            str(tmp_path / "feedback.jsonl"),
            "--status",
            "Approved",
            "--status",
            "Published",
            "--limit",
            "5",
            "--reviewer",
            "editor-a",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert FakeSyncer.calls[0]["status_filter"] == ["Approved", "Published"]
    assert FakeSyncer.calls[0]["limit"] == 5
    assert FakeSyncer.calls[0]["reviewer"] == "editor-a"


def test_limit_argument_error(monkeypatch, tmp_path, capsys):
    install(monkeypatch)

    exit_code = sync_notion_reviews.sync_notion_reviews_command(["--target", "notion_articles_id", "--feedback-store-path", str(tmp_path / "feedback.jsonl"), "--limit", "0"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "NOTION_REVIEW_SYNC_ARGUMENT_ERROR"


def test_does_not_call_llm_or_write_notion(monkeypatch, tmp_path):
    install(monkeypatch)
    monkeypatch.setenv("ENABLE_NOTION_FEEDBACK_SYNC", "1")

    exit_code = sync_notion_reviews.sync_notion_reviews_command(["--target", "notion_articles_id", "--feedback-store-path", str(tmp_path / "feedback.jsonl")])

    assert exit_code == 0
