import pytest

from src.notion.client import NotionClient, chunk_blocks


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self.payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, responses=None, exc=None):
        self.responses = list(responses or [])
        self.exc = exc
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": "post", "url": url, "headers": headers, "json": json, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.responses.pop(0)

    def patch(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": "patch", "url": url, "headers": headers, "json": json, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.responses.pop(0)


def test_create_page_success():
    session = FakeSession([FakeResponse(200, {"id": "page", "url": "https://notion.so/page"})])

    result = NotionClient(api_key="unit-key", session=session).create_page(parent={"page_id": "p"}, properties={})

    assert result.success is True
    assert result.data["id"] == "page"


def test_append_blocks_success():
    session = FakeSession([FakeResponse(200, {"ok": True})])

    result = NotionClient(api_key="unit-key", session=session).append_blocks(block_id="page", children=[{}])

    assert result.success is True
    assert session.calls[0]["method"] == "patch"


def test_400_not_retryable():
    result = NotionClient(api_key="unit-key", session=FakeSession([FakeResponse(400, {"message": "bad"})])).create_page(parent={}, properties={})

    assert result.success is False
    assert result.error.retryable is False


def test_429_retryable():
    result = NotionClient(api_key="unit-key", session=FakeSession([FakeResponse(429, {"message": "rate"})])).create_page(parent={}, properties={})

    assert result.error.retryable is True


def test_500_retryable():
    result = NotionClient(api_key="unit-key", session=FakeSession([FakeResponse(500, {"message": "server"})])).create_page(parent={}, properties={})

    assert result.error.retryable is True


def test_request_exception_returns_failure():
    result = NotionClient(api_key="unit-key", session=FakeSession(exc=RuntimeError("boom"))).create_page(parent={}, properties={})

    assert result.success is False
    assert result.error.type == "notion_request_exception"


def test_response_json_parse_failure_returns_error():
    result = NotionClient(api_key="unit-key", session=FakeSession([FakeResponse(200, ValueError("bad json"), "not-json")])).create_page(parent={}, properties={})

    assert result.success is False
    assert result.error.type == "notion_response_json_error"


def test_headers_include_auth_and_version_without_printing_key():
    session = FakeSession([FakeResponse(200, {"id": "page"})])

    NotionClient(api_key="unit-key", notion_version="unit-version", session=session).create_page(parent={}, properties={})

    headers = session.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer unit-key"
    assert headers["Notion-Version"] == "unit-version"


def test_query_data_source_success():
    session = FakeSession([FakeResponse(200, {"results": []})])

    result = NotionClient(api_key="unit-key", session=session).query_data_source(data_source_id="ds", filter={"property": "x"})

    assert result.success is True
    assert "/v1/data_sources/ds/query" in session.calls[0]["url"]


def test_query_data_source_start_cursor_payload():
    session = FakeSession([FakeResponse(200, {"results": []})])

    NotionClient(api_key="unit-key", session=session).query_data_source(data_source_id="ds", start_cursor="cursor-1")

    assert session.calls[0]["json"]["start_cursor"] == "cursor-1"


def test_query_data_source_omits_empty_start_cursor():
    session = FakeSession([FakeResponse(200, {"results": []})])

    NotionClient(api_key="unit-key", session=session).query_data_source(data_source_id="ds")

    assert "start_cursor" not in session.calls[0]["json"]


def test_query_data_source_failure():
    result = NotionClient(api_key="unit-key", session=FakeSession([FakeResponse(400, {"message": "bad query"})])).query_data_source(data_source_id="ds")

    assert result.success is False
    assert result.error.retryable is False


def test_update_page_properties_success():
    session = FakeSession([FakeResponse(200, {"id": "page"})])

    result = NotionClient(api_key="unit-key", session=session).update_page_properties(page_id="page", properties={})

    assert result.success is True
    assert "/v1/pages/page" in session.calls[0]["url"]


def test_update_page_properties_failure():
    result = NotionClient(api_key="unit-key", session=FakeSession([FakeResponse(500, {"message": "server"})])).update_page_properties(page_id="page", properties={})

    assert result.success is False
    assert result.error.retryable is True


def test_query_update_headers_do_not_leak_key_in_error():
    result = NotionClient(api_key="unit-secret", session=FakeSession([FakeResponse(400, {"message": "bad"})])).query_data_source(data_source_id="ds")

    assert "unit-secret" not in str(result.error.model_dump())


def test_chunk_blocks_batches():
    chunks = chunk_blocks([{"i": i} for i in range(205)], chunk_size=100)

    assert [len(chunk) for chunk in chunks] == [100, 100, 5]


def test_chunk_blocks_empty():
    assert chunk_blocks([]) == []


def test_chunk_blocks_invalid_size_raises():
    with pytest.raises(ValueError):
        chunk_blocks([{}], chunk_size=0)
