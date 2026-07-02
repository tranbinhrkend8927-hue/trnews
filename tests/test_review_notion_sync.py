from src.notion.client import NotionAPIError, NotionAPIResult
from src.notion.target_resolver import ResolvedNotionTarget
from src.review.feedback import create_review_feedback
from src.review.feedback_store import JsonlReviewFeedbackStore
from src.review.notion_sync import (
    NotionReviewSyncer,
    extract_date,
    extract_number,
    extract_rich_text,
    extract_select,
    extract_title,
    extract_url,
    map_notion_status_to_review_status,
    notion_page_to_review_feedback,
)


def title_prop(text):
    return {"title": [{"plain_text": text}]}


def rich_prop(text):
    return {"rich_text": [{"plain_text": text}]}


def select_prop(name):
    return {"select": {"name": name}}


def number_prop(value):
    return {"number": value}


def page(status="Approved", page_id="page-1", score=5, content_job_key="job-1"):
    return {
        "id": page_id,
        "url": f"https://notion.so/{page_id}",
        "properties": {
            "Name": title_prop("Title"),
            "Status": select_prop(status),
            "Review Notes": rich_prop("Looks good"),
            "Editor Notes": rich_prop("Editor says good"),
            "Editor Score": number_prop(4),
            "Rejection Reason": rich_prop("Unsupported claim"),
            "Edited Headline": rich_prop("Edited USD/IDR headline"),
            "Edited Summary": rich_prop("Edited summary text"),
            "Final Publish Decision": select_prop("publish"),
            "Reviewed At": {"date": {"start": "2026-07-02T10:00:00Z"}},
            "Quality Score": number_prop(score),
            "Factuality Score": number_prop(4),
            "Language Score": number_prop(3),
            "SEO Score": number_prop(2),
            "Compliance Score": number_prop(1),
            "Content Job Key": rich_prop(content_job_key),
            "Source Bundle Hash": rich_prop("hash-1"),
            "Pipeline Run ID": rich_prop("run-1"),
            "Market": select_prop("usd_idr_id"),
            "Symbol": rich_prop("USDIDR"),
            "Language": select_prop("id"),
            "Article Type": select_prop("article_draft"),
            "LLM Model": rich_prop("model-a"),
            "Prompt Version": rich_prop("v1"),
            "URL": {"url": "https://example.com"},
            "Date": {"date": {"start": "2026-07-01"}},
        },
    }


class FakeResolver:
    def __init__(self, target):
        self.target = target

    def resolve(self, target_name):
        return self.target


class FakeClient:
    def __init__(self, results=None, fail=False):
        self.results = list(results or [])
        self.fail = fail
        self.calls = []

    def query_data_source(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            return NotionAPIResult(success=False, error=NotionAPIError(type="bad", message="query failed"))
        return NotionAPIResult(success=True, data=self.results.pop(0))


def target(parent_type="data_source", parent_id="ds"):
    return ResolvedNotionTarget(name="target", language="id", market="fx", parent_type=parent_type, parent_id=parent_id)


def test_extract_property_types():
    props = page()["properties"]

    assert extract_title(props["Name"]) == "Title"
    assert extract_rich_text(props["Review Notes"]) == "Looks good"
    assert extract_select(props["Status"]) == "Approved"
    assert extract_number(props["Quality Score"]) == 5
    assert extract_url(props["URL"]) == "https://example.com"
    assert extract_date(props["Date"]) == "2026-07-01"


def test_status_mapping():
    assert map_notion_status_to_review_status("Approved") == "approved"
    assert map_notion_status_to_review_status("Needs Edit") == "needs_edit"
    assert map_notion_status_to_review_status("Needs Review") is None
    assert map_notion_status_to_review_status("unknown") is None


def test_notion_page_to_review_feedback_approved_page():
    feedback = notion_page_to_review_feedback(page(), reviewer="editor")

    assert feedback.review_status == "approved"
    assert feedback.notion_page_id == "page-1"
    assert feedback.content_job_key == "job-1"
    assert feedback.editor_score == 4
    assert feedback.quality_score == 5
    assert feedback.reviewer == "editor"
    assert feedback.notes == "Editor says good"
    assert feedback.rejection_reason == "Unsupported claim"
    assert feedback.edited_headline == "Edited USD/IDR headline"
    assert feedback.edited_summary == "Edited summary text"
    assert feedback.final_publish_decision == "publish"
    assert feedback.reviewed_at == "2026-07-02T10:00:00Z"


def test_notion_page_to_review_feedback_needs_edit_page():
    feedback = notion_page_to_review_feedback(page(status="Needs Edit"))

    assert feedback.review_status == "needs_edit"
    assert feedback.edit_required is True


def test_notion_page_to_review_feedback_skips_draft_page():
    assert notion_page_to_review_feedback(page(status="AI Draft")) is None


def test_invalid_score_does_not_crash():
    feedback = notion_page_to_review_feedback(page(score=6))

    assert feedback.quality_score is None
    assert feedback.metadata["warnings"][0]["type"] == "invalid_review_score"


def test_sync_success_imports_feedback(tmp_path):
    store = JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl"))
    syncer = NotionReviewSyncer(FakeResolver(target()), FakeClient([{"results": [page()], "has_more": False}]), store)

    result = syncer.sync(target_name="target")

    assert result.success is True
    assert result.imported == 1
    assert len(store.list_feedback()) == 1


def test_sync_dry_run_does_not_write_store(tmp_path):
    store = JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl"))
    syncer = NotionReviewSyncer(FakeResolver(target()), FakeClient([{"results": [page()], "has_more": False}]), store)

    result = syncer.sync(target_name="target", dry_run=True)

    assert result.imported == 1
    assert store.list_feedback() == []


def test_sync_skips_existing_notion_page_id(tmp_path):
    store = JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl"))
    store.append(create_review_feedback(review_status="approved", notion_page_id="page-1", content_job_key="old"))
    syncer = NotionReviewSyncer(FakeResolver(target()), FakeClient([{"results": [page()], "has_more": False}]), store)

    result = syncer.sync(target_name="target")

    assert result.skipped == 1
    assert result.imported == 0


def test_sync_query_failure_returns_false(tmp_path):
    syncer = NotionReviewSyncer(FakeResolver(target()), FakeClient(fail=True), JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl")))

    result = syncer.sync(target_name="target")

    assert result.success is False
    assert result.errors[0]["type"] == "notion_query_failed"


def test_sync_pagination(tmp_path):
    client = FakeClient(
        [
            {"results": [page(page_id="page-1", content_job_key="job-1")], "has_more": True, "next_cursor": "next"},
            {"results": [page(page_id="page-2", content_job_key="job-2")], "has_more": False},
        ]
    )
    syncer = NotionReviewSyncer(FakeResolver(target()), client, JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl")))

    result = syncer.sync(target_name="target")

    assert result.imported == 2
    assert client.calls[1]["start_cursor"] == "next"


def test_sync_limit(tmp_path):
    syncer = NotionReviewSyncer(FakeResolver(target()), FakeClient([{"results": [page(page_id="a", content_job_key="a"), page(page_id="b", content_job_key="b")], "has_more": False}]), JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl")))

    result = syncer.sync(target_name="target", limit=1)

    assert result.scanned == 1
    assert result.imported == 1


def test_target_parent_type_non_data_source_fails(tmp_path):
    syncer = NotionReviewSyncer(FakeResolver(target(parent_type="database")), FakeClient(), JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl")))

    result = syncer.sync(target_name="target")

    assert result.success is False
    assert result.errors[0]["type"] == "review_sync_requires_data_source_parent"


def test_target_parent_id_missing_fails(tmp_path):
    syncer = NotionReviewSyncer(FakeResolver(target(parent_id=None)), FakeClient(), JsonlReviewFeedbackStore(str(tmp_path / "feedback.jsonl")))

    result = syncer.sync(target_name="target")

    assert result.success is False
    assert result.errors[0]["type"] == "missing_notion_parent_id"
