from src.notion.client import NotionAPIError, NotionAPIResult
from src.notion.exporter import (
    NotionUpsertExporter,
    build_content_job_key_filter,
    extract_first_page_from_query_result,
)
from src.notion.target_resolver import ResolvedNotionTarget
from tests.test_notion_exporter_dry_run import FakeResolver, _inputs


class FakeClient:
    def __init__(self, query_result=None, create_result=None, update_result=None, append_results=None):
        self.query_result = query_result or NotionAPIResult(success=True, data={"results": []})
        self.create_result = create_result or NotionAPIResult(success=True, data={"id": "new-page", "url": "new-url"})
        self.update_result = update_result or NotionAPIResult(success=True, data={"id": "existing-page", "url": "existing-url"})
        self.append_results = list(append_results or [])
        self.query_calls = []
        self.create_calls = []
        self.update_calls = []
        self.append_calls = []

    def query_data_source(self, **kwargs):
        self.query_calls.append(kwargs)
        return self.query_result

    def create_page(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.create_result

    def update_page_properties(self, **kwargs):
        self.update_calls.append(kwargs)
        return self.update_result

    def append_blocks(self, **kwargs):
        self.append_calls.append(kwargs)
        if self.append_results:
            return self.append_results.pop(0)
        return NotionAPIResult(success=True, data={"ok": True})


def target(parent_id="ds", parent_type="data_source"):
    return ResolvedNotionTarget(
        name="notion_articles_id",
        language="id",
        market="Indonesia",
        parent_type=parent_type,
        parent_id=parent_id,
    )


def test_content_job_key_missing_fails():
    result = NotionUpsertExporter(FakeResolver(target()), notion_client=FakeClient()).export(**_inputs())

    assert result.success is False
    assert result.error["type"] == "missing_content_job_key"


def test_parent_id_missing_fails():
    result = NotionUpsertExporter(FakeResolver(target(parent_id=None)), notion_client=FakeClient()).export(
        **_inputs(), content_job_key="job"
    )

    assert result.success is False
    assert result.error["type"] == "missing_notion_parent_id"


def test_non_data_source_parent_fails():
    result = NotionUpsertExporter(FakeResolver(target(parent_type="database")), notion_client=FakeClient()).export(
        **_inputs(), content_job_key="job"
    )

    assert result.success is False
    assert result.error["type"] == "upsert_requires_data_source_parent"


def test_query_failure_fails():
    client = FakeClient(query_result=NotionAPIResult(success=False, error=NotionAPIError(type="query_failed", message="bad")))

    result = NotionUpsertExporter(FakeResolver(target()), notion_client=client).export(**_inputs(), content_job_key="job")

    assert result.success is False
    assert result.error["type"] == "notion_query_failed"


def test_query_no_result_creates_and_appends():
    client = FakeClient(query_result=NotionAPIResult(success=True, data={"results": []}))

    result = NotionUpsertExporter(FakeResolver(target()), notion_client=client).export(**_inputs(), content_job_key="job")

    assert result.success is True
    assert result.metadata["action"] == "created"
    assert client.create_calls
    assert client.append_calls


def test_query_existing_updates_properties_without_body_append():
    client = FakeClient(query_result=NotionAPIResult(success=True, data={"results": [{"id": "existing", "url": "url"}]}))

    result = NotionUpsertExporter(FakeResolver(target()), notion_client=client).export(**_inputs(), content_job_key="job")

    assert result.success is True
    assert result.metadata["action"] == "updated"
    assert client.update_calls
    assert client.create_calls == []
    assert client.append_calls == []


def test_append_update_note_only_appends_one_note():
    client = FakeClient(query_result=NotionAPIResult(success=True, data={"results": [{"id": "existing", "url": "url"}]}))

    result = NotionUpsertExporter(FakeResolver(target()), notion_client=client).export(
        **_inputs(), content_job_key="job", append_update_note=True
    )

    assert result.success is True
    assert len(client.append_calls) == 1
    assert "Updated existing draft" in str(client.append_calls[0]["children"])


def test_update_properties_failure_returns_failure():
    client = FakeClient(
        query_result=NotionAPIResult(success=True, data={"results": [{"id": "existing", "url": "url"}]}),
        update_result=NotionAPIResult(success=False, error=NotionAPIError(type="update_failed", message="bad")),
    )

    result = NotionUpsertExporter(FakeResolver(target()), notion_client=client).export(**_inputs(), content_job_key="job")

    assert result.success is False
    assert result.error["type"] == "update_failed"


def test_created_result_metadata_action_created():
    result = NotionUpsertExporter(FakeResolver(target()), notion_client=FakeClient()).export(**_inputs(), content_job_key="job")

    assert result.metadata["action"] == "created"


def test_updated_result_metadata_action_updated():
    client = FakeClient(query_result=NotionAPIResult(success=True, data={"results": [{"id": "existing", "url": "url"}]}))

    result = NotionUpsertExporter(FakeResolver(target()), notion_client=client).export(**_inputs(), content_job_key="job")

    assert result.metadata["action"] == "updated"


def test_no_real_notion_api_called():
    client = FakeClient()

    NotionUpsertExporter(FakeResolver(target()), notion_client=client).export(**_inputs(), content_job_key="job")

    assert client.query_calls


def test_filter_builder_and_extract_helpers():
    assert build_content_job_key_filter("job") == {"property": "Content Job Key", "rich_text": {"equals": "job"}}
    assert extract_first_page_from_query_result({"results": [{"id": "a"}, {"id": "b"}]}) == {"id": "a"}
    assert extract_first_page_from_query_result({"results": []}) is None
    assert extract_first_page_from_query_result({}) is None
