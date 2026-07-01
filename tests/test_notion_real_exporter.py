from src.notion.client import NotionAPIError, NotionAPIResult
from src.notion.exporter import NotionRealExporter
from src.notion.target_resolver import ResolvedNotionTarget
from tests.test_notion_exporter_dry_run import FakeResolver, _inputs


class FakeClient:
    def __init__(self, create_result=None, append_results=None):
        self.create_result = create_result or NotionAPIResult(success=True, data={"id": "page-id", "url": "https://notion.so/page"})
        self.append_results = list(append_results or [])
        self.create_calls = []
        self.append_calls = []

    def create_page(self, *, parent, properties):
        self.create_calls.append({"parent": parent, "properties": properties})
        return self.create_result

    def append_blocks(self, *, block_id, children):
        self.append_calls.append({"block_id": block_id, "children": children})
        if self.append_results:
            return self.append_results.pop(0)
        return NotionAPIResult(success=True, data={"ok": True})


def target(parent_id="ds"):
    return ResolvedNotionTarget(name="notion_articles_id", language="id", market="Indonesia", parent_type="data_source", parent_id=parent_id)


def test_export_success_create_page_and_append_blocks():
    client = FakeClient()

    result = NotionRealExporter(FakeResolver(target()), notion_client=client).export(**_inputs())

    assert result.success is True
    assert result.dry_run is False
    assert result.page_id == "page-id"
    assert client.create_calls
    assert client.append_calls


def test_blocks_over_100_are_chunked():
    class ManyBlocksBuilder:
        def build_blocks(self, **kwargs):
            return [{"type": "paragraph"} for _ in range(205)]

    client = FakeClient()

    result = NotionRealExporter(FakeResolver(target()), notion_client=client, block_builder=ManyBlocksBuilder()).export(**_inputs())

    assert result.success is True
    assert [len(call["children"]) for call in client.append_calls] == [100, 100, 5]


def test_missing_parent_id_fails_without_create():
    client = FakeClient()

    result = NotionRealExporter(FakeResolver(target(parent_id=None)), notion_client=client).export(**_inputs())

    assert result.success is False
    assert result.error["type"] == "missing_notion_parent_id"
    assert client.create_calls == []


def test_create_page_failure_returns_error():
    client = FakeClient(create_result=NotionAPIResult(success=False, error=NotionAPIError(type="notion_api_error", message="bad", status_code=400)))

    result = NotionRealExporter(FakeResolver(target()), notion_client=client).export(**_inputs())

    assert result.success is False
    assert result.error["type"] == "notion_api_error"
    assert not client.append_calls


def test_append_failure_returns_page_id_and_url():
    client = FakeClient(append_results=[NotionAPIResult(success=False, error=NotionAPIError(type="append_failed", message="bad"))])

    result = NotionRealExporter(FakeResolver(target()), notion_client=client).export(**_inputs())

    assert result.success is False
    assert result.page_id == "page-id"
    assert result.url == "https://notion.so/page"
    assert result.error["type"] == "append_failed"


def test_empty_blocks_only_creates_page():
    class EmptyBlocksBuilder:
        def build_blocks(self, **kwargs):
            return []

    client = FakeClient()

    result = NotionRealExporter(FakeResolver(target()), notion_client=client, block_builder=EmptyBlocksBuilder()).export(**_inputs())

    assert result.success is True
    assert client.create_calls
    assert client.append_calls == []


def test_export_result_dry_run_false():
    result = NotionRealExporter(FakeResolver(target()), notion_client=FakeClient()).export(**_inputs())

    assert result.dry_run is False


def test_does_not_call_real_notion_api():
    client = FakeClient()

    NotionRealExporter(FakeResolver(target()), notion_client=client).export(**_inputs())

    assert client.create_calls
