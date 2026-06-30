import json
import sys
import types

import pytest
import requests

import export_article_to_notion as notion_cli
import notion_config
import notion_exporter


def _body(extra_sections=0):
    sections = [
        "Pembuka singkat\nUSD/IDR menjadi perhatian pembaca Indonesia.",
        "Apa yang terjadi?\nBerdasarkan sumber berita yang tersimpan, pasar mencermati Rupiah dan Dolar AS.",
        "Mengapa ini penting untuk Rupiah?\nKonteks ini membantu pembaca memahami hubungan Rupiah, Dolar AS, The Fed, dan Bank Indonesia.",
        "Faktor yang perlu dipantau\n- Sentimen Dolar AS.\n- Kebijakan Bank Indonesia.\n- Agenda ekonomi global.",
        "Apa dampaknya bagi pembaca Indonesia?\nPembaca dapat memahami konteks pasar tanpa menganggap arah pasar sebagai hal yang sudah tentu.",
        "FAQ\nQ: Apakah ini saran trading?\nA: Tidak, ini informasi umum.",
        "Sumber\nSource news ID 10: Rupiah bergerak terhadap Dolar AS\nURL: https://example.com/source-10",
        "Catatan risiko: Artikel ini bersifat informasi umum dan bukan rekomendasi investasi, ajakan beli atau jual, maupun saran trading. Keputusan finansial tetap memerlukan pertimbangan pribadi dan sumber resmi.",
    ]
    sections.extend(f"Paragraf tambahan {index} tentang konteks makro USD/IDR." for index in range(extra_sections))
    return "\n\n".join(sections)


def _article(**overrides):
    article = {
        "id": 1,
        "topic_id": 5,
        "symbol": "USDIDR",
        "language": "id",
        "title": "USD/IDR Hari Ini: Rupiah Bergerak, Ini Faktor yang Perlu Dipantau",
        "slug": "usd-idr-hari-ini-5",
        "summary": "Ringkasan USD/IDR untuk pembaca Indonesia dengan sumber berita tersimpan.",
        "body": _body(),
        "seo_title": "USD/IDR Hari Ini: Rupiah Bergerak",
        "seo_description": "Konteks USD/IDR dan Rupiah untuk pembaca Indonesia.",
        "status": "approved",
        "fact_check_status": "passed",
        "risk_disclaimer_included": True,
        "sources_json": {
            "topic_id": 5,
            "topic_type": "daily_usdidr_update",
            "symbol": "USDIDR",
            "source_news_ids": [10],
            "sources": [
                {
                    "news_id": 10,
                    "title": "Rupiah bergerak terhadap Dolar AS",
                    "url": "https://example.com/source-10",
                    "source": "Example News",
                }
            ],
            "missing_source_news_ids": [],
        },
        "published_at": None,
    }
    article.update(overrides)
    return article


def _article_sources(**overrides):
    source = {
        "id": 100,
        "article_id": 1,
        "source_type": "forex_news",
        "source_name": "Example News",
        "source_url": "https://example.com/source-10",
        "cited_claim": "Rupiah bergerak terhadap Dolar AS",
    }
    source.update(overrides)
    return [source]


def _blocker_types(validation):
    return {item["type"] for item in validation["blockers"]}


def _assert_json_serializable(value):
    json.dumps(value, ensure_ascii=False)


def test_status_approved_is_exportable():
    validation = notion_exporter.validate_article_exportable(_article(), _article_sources())

    assert validation["exportable"] is True
    assert validation["blockers"] == []


@pytest.mark.parametrize("status", ["pending_review", "draft", "rejected", "published"])
def test_non_approved_statuses_cannot_export(status):
    validation = notion_exporter.validate_article_exportable(_article(status=status), _article_sources())

    assert validation["exportable"] is False
    assert "status_not_approved" in _blocker_types(validation)
    assert f"status_{status}_blocked" in _blocker_types(validation)


@pytest.mark.parametrize(
    ("fact_check_status", "expected"),
    [
        ("failed", "fact_check_failed"),
        ("needs_sources", "fact_check_needs_sources"),
    ],
)
def test_bad_fact_check_status_cannot_export(fact_check_status, expected):
    validation = notion_exporter.validate_article_exportable(
        _article(fact_check_status=fact_check_status),
        _article_sources(),
    )

    assert validation["exportable"] is False
    assert expected in _blocker_types(validation)


def test_missing_article_sources_cannot_export():
    validation = notion_exporter.validate_article_exportable(_article(), [])

    assert validation["exportable"] is False
    assert "missing_article_sources" in _blocker_types(validation)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("title", "", "missing_title"),
        ("body", "", "missing_body"),
        ("risk_disclaimer_included", False, "missing_risk_disclaimer"),
    ],
)
def test_missing_required_article_fields_cannot_export(field, value, expected):
    validation = notion_exporter.validate_article_exportable(_article(**{field: value}), _article_sources())

    assert validation["exportable"] is False
    assert expected in _blocker_types(validation)


def test_build_notion_page_properties_are_json_serializable():
    properties = notion_exporter.build_notion_page_properties(_article(), _article_sources())
    page_properties = notion_exporter.build_notion_page_properties(_article(), _article_sources(), parent_type="page")

    _assert_json_serializable(properties)
    _assert_json_serializable(page_properties)
    assert properties["Name"]["title"][0]["text"]["content"].startswith("USD/IDR")
    assert properties["Status"]["select"]["name"] == "Approved"
    assert page_properties["title"][0]["text"]["content"].startswith("USD/IDR")


def test_build_notion_blocks_are_json_serializable_and_include_article_sections():
    blocks = notion_exporter.build_notion_blocks(_article(), _article_sources())
    dumped = json.dumps(blocks, ensure_ascii=False)

    assert "USD/IDR Hari Ini" in dumped
    assert "Ringkasan USD/IDR" in dumped
    assert "Apa yang terjadi?" in dumped
    assert "FAQ" in dumped
    assert "Sumber" in dumped
    assert "Catatan risiko" in dumped
    _assert_json_serializable(blocks)


def test_dry_run_does_not_call_notion():
    class FailingClient:
        parent_type = "data_source"

        def create_page(self, properties):
            raise AssertionError("dry-run must not call Notion")

        def append_blocks(self, block_id, blocks):
            raise AssertionError("dry-run must not call Notion")

    result = notion_exporter.export_article_to_notion(_article(), _article_sources(), FailingClient(), dry_run=True)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["summary"]["would_write_export_record"] is False


def test_dry_run_does_not_write_article_exports(monkeypatch):
    def fail_connect(*args, **kwargs):
        raise AssertionError("dry-run must not connect to postgres")

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = fail_connect
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)

    result = notion_exporter.save_article_export_record_to_postgres("postgresql://example/db", {"success": True}, dry_run=True)

    assert result["success"] is True
    assert result["inserted_count"] == 0


class FakeNotionClient:
    parent_type = "data_source"

    def __init__(self, *, success=True):
        self.success = success
        self.create_calls = 0
        self.append_calls = 0

    def create_page(self, properties):
        self.create_calls += 1
        if not self.success:
            return {
                "success": False,
                "status_code": 403,
                "data": {"message": "forbidden"},
                "error": {"type": "api_error", "message": "forbidden", "retryable": False},
            }
        return {"success": True, "data": {"id": "page-1", "url": "https://notion.example/page-1", "object": "page"}}

    def append_blocks(self, block_id, blocks):
        self.append_calls += 1
        return {"success": True, "results": [{"success": True}]}


def _install_fake_psycopg(monkeypatch, state):
    class FakeCursor:
        def __init__(self):
            self.next_fetchone = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            params = params or ()
            if "UPDATE generated_articles" in normalized:
                state["status_updates"] += 1
                raise AssertionError("P15 must not update generated_articles status")
            if "INSERT INTO article_reviews" in normalized:
                state["review_inserts"] += 1
                raise AssertionError("P15 must not write article_reviews")
            if "INSERT INTO article_exports" in normalized:
                state["export_inserts"].append(
                    {
                        "article_id": params[0],
                        "target": params[1],
                        "target_id": params[2],
                        "target_url": params[3],
                        "status": params[4],
                        "request_json": params[5],
                        "response_json": params[6],
                        "error_json": params[7],
                    }
                )
                self.next_fetchone = (88,)
                return
            raise AssertionError(f"unexpected query: {normalized}")

        def fetchone(self):
            return self.next_fetchone

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            state["commits"] += 1

    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.connect = lambda *args, **kwargs: FakeConnection()
    psycopg_types_module = types.ModuleType("psycopg.types")
    psycopg_json_module = types.ModuleType("psycopg.types.json")
    psycopg_json_module.Jsonb = lambda value: value
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.types", psycopg_types_module)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", psycopg_json_module)


def test_export_success_writes_article_exports_exported(monkeypatch):
    state = {"export_inserts": [], "review_inserts": 0, "status_updates": 0, "commits": 0}
    _install_fake_psycopg(monkeypatch, state)

    export_result = notion_exporter.export_article_to_notion(_article(), _article_sources(), FakeNotionClient(), dry_run=False)
    record = notion_exporter.save_article_export_record_to_postgres("postgresql://example/db", export_result, dry_run=False)

    assert export_result["success"] is True
    assert record["success"] is True
    assert state["export_inserts"][0]["status"] == "exported"
    assert state["export_inserts"][0]["target"] == "notion"
    assert state["status_updates"] == 0
    assert state["review_inserts"] == 0


def test_export_failure_writes_article_exports_failed(monkeypatch):
    state = {"export_inserts": [], "review_inserts": 0, "status_updates": 0, "commits": 0}
    _install_fake_psycopg(monkeypatch, state)

    export_result = notion_exporter.export_article_to_notion(_article(), _article_sources(), FakeNotionClient(success=False), dry_run=False)
    record = notion_exporter.save_article_export_record_to_postgres("postgresql://example/db", export_result, dry_run=False)

    assert export_result["success"] is False
    assert record["success"] is True
    assert state["export_inserts"][0]["status"] == "failed"
    assert state["status_updates"] == 0


def test_export_result_does_not_set_published_or_expose_secrets(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "not-a-real-key")
    monkeypatch.setenv("NOTION_DATA_SOURCE_ID", "data-source-id")

    config = notion_config.load_notion_config(require_api_key=True)
    export_result = notion_exporter.export_article_to_notion(_article(), _article_sources(), FakeNotionClient(), dry_run=False)
    dumped = json.dumps({"config": config, "export_result": export_result}, ensure_ascii=False)

    assert export_result["summary"]["would_publish"] is False
    assert "published" not in export_result.get("notion", {})
    assert "not-a-real-key" not in dumped
    assert "Authorization" not in dumped
    assert "raw_response" not in dumped
    assert config["has_api_key"] is True


class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout})
        next_response = self.responses.pop(0)
        if isinstance(next_response, BaseException):
            raise next_response
        return next_response


@pytest.mark.parametrize("status_code", [401, 403])
def test_401_and_403_do_not_retry(status_code):
    session = FakeSession([FakeResponse(status_code, {"message": "auth failed"})])
    client = notion_exporter.NotionClient("not-a-real-key", data_source_id="database-id", session=session, max_retries=2)

    result = client.create_page({"Name": {"title": [{"text": {"content": "Title"}}]}})

    assert result["success"] is False
    assert result["attempts"] == 1
    assert len(session.calls) == 1


@pytest.mark.parametrize("status_code", [429, 500])
def test_429_and_5xx_retry(status_code):
    session = FakeSession(
        [
            FakeResponse(status_code, {"message": "retry later"}),
            FakeResponse(200, {"id": "page-1", "url": "https://notion.example/page-1"}),
        ]
    )
    client = notion_exporter.NotionClient("not-a-real-key", data_source_id="database-id", session=session, max_retries=2)

    result = client.create_page({"Name": {"title": [{"text": {"content": "Title"}}]}})

    assert result["success"] is True
    assert result["attempts"] == 2
    assert len(session.calls) == 2


def test_timeout_retries():
    session = FakeSession(
        [
            requests.exceptions.Timeout("timeout"),
            FakeResponse(200, {"id": "page-1", "url": "https://notion.example/page-1"}),
        ]
    )
    client = notion_exporter.NotionClient("not-a-real-key", data_source_id="database-id", session=session, max_retries=2)

    result = client.create_page({"Name": {"title": [{"text": {"content": "Title"}}]}})

    assert result["success"] is True
    assert result["attempts"] == 2


def test_append_blocks_batches_children_at_100():
    session = FakeSession(
        [
            FakeResponse(200, {"ok": True}),
            FakeResponse(200, {"ok": True}),
            FakeResponse(200, {"ok": True}),
        ]
    )
    client = notion_exporter.NotionClient("not-a-real-key", data_source_id="database-id", session=session, max_retries=0)
    blocks = [notion_exporter._paragraph(f"Block {index}") for index in range(250)]

    result = client.append_blocks("page-1", blocks)

    assert result["success"] is True
    assert [len(call["json"]["children"]) for call in session.calls] == [100, 100, 50]


def test_cli_dry_run_does_not_call_notion_or_write_db(monkeypatch, capsys):
    monkeypatch.setattr(notion_cli, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(notion_cli, "fetch_article_for_export", lambda dsn, article_id: _article(id=article_id))
    monkeypatch.setattr(notion_cli, "fetch_article_sources_for_export", lambda dsn, article_id: _article_sources())

    def fail_client(*args, **kwargs):
        raise AssertionError("dry-run must not build a live Notion client")

    def fail_record(*args, **kwargs):
        raise AssertionError("dry-run must not write article_exports")

    monkeypatch.setattr(notion_cli, "build_notion_client_from_env", fail_client)
    monkeypatch.setattr(notion_cli, "save_article_export_record_to_postgres", fail_record)

    exit_code = notion_cli.main(["--article-id", "1", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["dry_run"] is True
    assert payload["summary"]["would_write_export_record"] is False


def test_cli_export_writes_record_without_updating_article(monkeypatch, capsys):
    calls = {"records": 0}
    monkeypatch.setattr(notion_cli, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(notion_cli, "fetch_article_for_export", lambda dsn, article_id: _article(id=article_id))
    monkeypatch.setattr(notion_cli, "fetch_article_sources_for_export", lambda dsn, article_id: _article_sources())
    monkeypatch.setattr(
        notion_cli,
        "build_notion_client_from_env",
        lambda require_api_key=True: {
            "success": True,
            "config": {"success": True, "has_api_key": True},
            "client": FakeNotionClient(),
            "errors": [],
        },
    )

    def fake_record(dsn, export_result, dry_run=True):
        calls["records"] += 1
        return {"success": True, "dry_run": False, "inserted_count": 1, "export_id": 88, "status": "exported", "errors": []}

    monkeypatch.setattr(notion_cli, "save_article_export_record_to_postgres", fake_record)

    exit_code = notion_cli.main(["--article-id", "1", "--export"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["summary"]["would_publish"] is False
    assert calls["records"] == 1
    assert "published" not in json.dumps(payload["database"], ensure_ascii=False)


def test_cli_default_is_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(notion_cli, "get_postgres_dsn", lambda: "postgresql://example/db")
    monkeypatch.setattr(notion_cli, "fetch_article_for_export", lambda dsn, article_id: _article(id=article_id))
    monkeypatch.setattr(notion_cli, "fetch_article_sources_for_export", lambda dsn, article_id: _article_sources())

    exit_code = notion_cli.main(["--article-id", "1"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["dry_run"] is True


def test_cli_rejects_dry_run_and_export_together(capsys):
    exit_code = notion_cli.main(["--article-id", "1", "--dry-run", "--export"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["errors"][0]["type"] == "invalid_mode"


def test_output_is_json_serializable():
    result = notion_exporter.export_article_to_notion(_article(), _article_sources(), FakeNotionClient(), dry_run=True)

    _assert_json_serializable(result)
