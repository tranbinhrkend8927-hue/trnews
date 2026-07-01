import json

import pytest

from src.jobs import run_market
from src.ingest.postgres_news import PostgresNewsAdapter, RefreshingPostgresNewsAdapter
from src.ingest.tradingview import TradingViewNewsAdapter


class FakePipeline:
    def __init__(self, result):
        self.result = result

    def run_market(self, market_id, *, dry_run=True):
        payload = dict(self.result)
        payload.setdefault("market_id", market_id)
        payload.setdefault("dry_run", dry_run)
        return payload


def test_missing_market_argument_fails():
    with pytest.raises(SystemExit):
        run_market.run_market_command([])


def test_build_pipeline_defaults_to_postgres_source_adapter():
    pipeline = run_market.build_pipeline()

    assert isinstance(pipeline.tradingview_adapter, PostgresNewsAdapter)


def test_build_pipeline_live_source_uses_tradingview_adapter():
    pipeline = run_market.build_pipeline(source_mode="live")

    assert isinstance(pipeline.tradingview_adapter, TradingViewNewsAdapter)


def test_build_pipeline_refresh_sources_wraps_postgres_adapter():
    pipeline = run_market.build_pipeline(refresh_sources=True)

    assert isinstance(pipeline.tradingview_adapter, RefreshingPostgresNewsAdapter)


def test_dry_run_success_exit_code_zero(monkeypatch, capsys):
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"}))

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["status"] == "DRY_RUN_SUCCESS"


def test_pipeline_failure_exit_code_one(monkeypatch, capsys):
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": False, "status": "SOURCE_BUNDLE_FAILED"}))

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["status"] == "SOURCE_BUNDLE_FAILED"


def test_cli_outputs_json(monkeypatch, capsys):
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"}))

    run_market.run_market_command(["--market", "usd_idr_id"])
    payload = json.loads(capsys.readouterr().out)

    assert isinstance(payload, dict)
    assert payload["market_id"] == "usd_idr_id"


def test_default_does_not_create_real_llm_runner(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--dry-run"])

    assert exit_code == 0
    assert calls == [{"use_real_llm": False, "include_notion_preview": False, "export_notion": False, "upsert_notion": False, "append_update_note": False}]


def test_use_real_llm_creates_real_llm_runner(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--dry-run", "--use-real-llm"])

    assert exit_code == 0
    assert calls == [{"use_real_llm": True, "include_notion_preview": False, "export_notion": False, "upsert_notion": False, "append_update_note": False}]


def test_source_mode_live_is_passed_to_pipeline(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--source-mode", "live"])

    assert exit_code == 0
    assert calls[0]["source_mode"] == "live"


def test_refresh_sources_is_passed_to_pipeline(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--refresh-sources"])

    assert exit_code == 0
    assert calls[0]["refresh_sources"] is True


def test_refresh_sources_conflicts_with_live_source_mode(capsys):
    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--source-mode", "live", "--refresh-sources"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "ARGUMENT_ERROR"


def test_llm_failure_exit_code_one(monkeypatch, capsys):
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": False, "status": "LLM_FAILED"}))

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--dry-run", "--use-real-llm"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "LLM_FAILED"


def test_default_does_not_create_notion_exporter(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    run_market.run_market_command(["--market", "usd_idr_id", "--dry-run"])

    assert calls == [{"use_real_llm": False, "include_notion_preview": False, "export_notion": False, "upsert_notion": False, "append_update_note": False}]


def test_include_notion_preview_creates_dry_run_exporter(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline(
            {
                "success": True,
                "status": "DRY_RUN_SUCCESS",
                "notion_preview": {"payload": {"warnings": [{"type": "missing_notion_parent_id"}]}},
            }
        )

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--dry-run", "--include-notion-preview"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [{"use_real_llm": False, "include_notion_preview": True, "export_notion": False, "upsert_notion": False, "append_update_note": False}]
    assert "notion_preview" in payload


def test_missing_notion_env_warning_does_not_fail_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(
        run_market,
        "build_pipeline",
        lambda **kwargs: FakePipeline(
            {
                "success": True,
                "status": "DRY_RUN_SUCCESS",
                "notion_preview": {"payload": {"warnings": [{"type": "missing_notion_parent_id"}]}},
            }
        ),
    )

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--dry-run", "--include-notion-preview"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["notion_preview"]["payload"]["warnings"][0]["type"] == "missing_notion_parent_id"


def test_default_does_not_create_real_notion_exporter(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    run_market.run_market_command(["--market", "usd_idr_id"])

    assert calls == [{"use_real_llm": False, "include_notion_preview": False, "export_notion": False, "upsert_notion": False, "append_update_note": False}]


def test_export_notion_creates_real_exporter_and_sets_dry_run_false(monkeypatch, capsys):
    calls = []
    dry_run_values = []

    class ExportPipeline(FakePipeline):
        def run_market(self, market_id, *, dry_run=True):
            dry_run_values.append(dry_run)
            return {"success": True, "status": "NOTION_EXPORTED", "notion": {"page_id": "page"}}

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return ExportPipeline({})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--export-notion", "--yes"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [{"use_real_llm": False, "include_notion_preview": False, "export_notion": True, "upsert_notion": False, "append_update_note": False}]
    assert dry_run_values == [False]
    assert payload["status"] == "NOTION_EXPORTED"


def test_export_notion_without_yes_fails_without_running(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: calls.append(kwargs) or FakePipeline({}))

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--export-notion"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "CONFIRMATION_REQUIRED"
    assert calls == []


def test_upsert_notion_without_yes_fails_without_running(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: calls.append(kwargs) or FakePipeline({}))

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--upsert-notion"])

    assert exit_code == 2
    assert calls == []


def test_export_success_exit_code_zero(monkeypatch, capsys):
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": True, "status": "NOTION_EXPORTED", "notion": {"page_id": "page"}}))

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--export-notion", "--yes"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["notion"]["page_id"] == "page"


def test_export_failure_exit_code_one(monkeypatch, capsys):
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": False, "status": "NOTION_EXPORT_FAILED", "notion": {"error": {"type": "bad"}}}))

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--export-notion", "--yes"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "NOTION_EXPORT_FAILED"


def test_export_output_contains_notion(monkeypatch, capsys):
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": True, "status": "NOTION_EXPORTED", "notion": {"page_id": "page"}}))

    run_market.run_market_command(["--market", "usd_idr_id", "--export-notion", "--yes"])
    payload = json.loads(capsys.readouterr().out)

    assert "notion" in payload


def test_job_store_path_writes_record(monkeypatch, capsys, tmp_path):
    path = tmp_path / "jobs.jsonl"
    monkeypatch.setattr(
        run_market,
        "build_pipeline",
        lambda **kwargs: FakePipeline(
            {
                "success": True,
                "status": "DRY_RUN_SUCCESS",
                "market_id": "usd_idr_id",
                "symbol": "USDIDR",
                "language": "id",
                "source_bundle_hash": "hash",
                "content_job_key": "job",
                "pipeline_run_id": "run",
            }
        ),
    )

    run_market.run_market_command(["--market", "usd_idr_id", "--job-store-path", str(path)])

    assert path.exists()


def test_job_store_success_result_written(monkeypatch, capsys, tmp_path):
    from src.jobs.job_store import FileJobStore

    path = tmp_path / "jobs.jsonl"
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS", "market_id": "usd_idr_id", "symbol": "USDIDR", "language": "id", "source_bundle_hash": "hash", "content_job_key": "job", "pipeline_run_id": "run"}))

    run_market.run_market_command(["--market", "usd_idr_id", "--job-store-path", str(path)])

    assert FileJobStore(str(path)).list_records()[0].success is True


def test_job_store_failed_result_written(monkeypatch, capsys, tmp_path):
    from src.jobs.job_store import FileJobStore

    path = tmp_path / "jobs.jsonl"
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": False, "status": "FAILED", "market_id": "usd_idr_id", "symbol": "USDIDR", "language": "id", "source_bundle_hash": "hash", "content_job_key": "job", "pipeline_run_id": "run"}))

    run_market.run_market_command(["--market", "usd_idr_id", "--job-store-path", str(path)])

    assert FileJobStore(str(path)).list_records()[0].success is False


def test_force_does_not_block_execution(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        return FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS"})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--force"])

    assert exit_code == 0


def test_output_contains_job_metadata(monkeypatch, capsys):
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": True, "status": "DRY_RUN_SUCCESS", "pipeline_run_id": "run", "source_bundle_hash": "hash", "content_job_key": "job"}))

    run_market.run_market_command(["--market", "usd_idr_id"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["pipeline_run_id"] == "run"


def test_event_store_path_writes_success_event(monkeypatch, capsys, tmp_path):
    from src.observability.event_store import JsonlEventStore

    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(
        run_market,
        "build_pipeline",
        lambda **kwargs: FakePipeline(
            {
                "success": True,
                "status": "DRY_RUN_SUCCESS",
                "market_id": "usd_idr_id",
                "symbol": "USDIDR",
                "language": "id",
                "pipeline_run_id": "run",
                "source_bundle_hash": "hash",
                "content_job_key": "job",
            }
        ),
    )

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--event-store-path", str(path)])

    events = JsonlEventStore(str(path)).list_events()
    assert exit_code == 0
    assert events[0].event_type == "pipeline.completed"
    assert events[0].market_id == "usd_idr_id"


def test_event_store_path_writes_failed_event(monkeypatch, capsys, tmp_path):
    from src.observability.event_store import JsonlEventStore

    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(run_market, "build_pipeline", lambda **kwargs: FakePipeline({"success": False, "status": "LLM_FAILED", "market_id": "usd_idr_id"}))

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--event-store-path", str(path)])

    events = JsonlEventStore(str(path)).list_events()
    assert exit_code == 1
    assert events[0].event_type == "pipeline.failed"
    assert events[0].status == "LLM_FAILED"


def test_event_store_does_not_include_api_key(monkeypatch, capsys, tmp_path):
    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(
        run_market,
        "build_pipeline",
        lambda **kwargs: FakePipeline(
            {
                "success": True,
                "status": "DRY_RUN_SUCCESS",
                "market_id": "usd_idr_id",
                "llm": {"model": "m", "usage": {}, "metadata": {"api_key": "secret-key"}},
            }
        ),
    )

    run_market.run_market_command(["--market", "usd_idr_id", "--event-store-path", str(path)])

    assert "secret-key" not in path.read_text(encoding="utf-8")


def test_upsert_notion_creates_upsert_exporter_and_sets_dry_run_false(monkeypatch, capsys):
    calls = []
    dry_run_values = []

    class UpsertPipeline(FakePipeline):
        def run_market(self, market_id, *, dry_run=True):
            dry_run_values.append(dry_run)
            return {"success": True, "status": "NOTION_EXPORTED", "notion": {"metadata": {"action": "updated"}}}

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return UpsertPipeline({})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--upsert-notion", "--yes"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [{"use_real_llm": False, "include_notion_preview": False, "export_notion": False, "upsert_notion": True, "append_update_note": False}]
    assert dry_run_values == [False]
    assert payload["notion"]["metadata"]["action"] == "updated"


def test_export_and_upsert_together_passes_both_flags_with_upsert_priority(monkeypatch, capsys):
    calls = []
    dry_run_values = []

    class UpsertPipeline(FakePipeline):
        def run_market(self, market_id, *, dry_run=True):
            dry_run_values.append(dry_run)
            return {"success": True, "status": "NOTION_EXPORTED", "notion": {"metadata": {"action": "created"}}}

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return UpsertPipeline({})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--export-notion", "--upsert-notion", "--yes"])

    assert exit_code == 0
    assert calls == [{"use_real_llm": False, "include_notion_preview": False, "export_notion": True, "upsert_notion": True, "append_update_note": False}]
    assert dry_run_values == [False]


def test_append_update_note_is_passed(monkeypatch, capsys):
    calls = []

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline({"success": True, "status": "NOTION_EXPORTED", "notion": {"metadata": {"action": "updated"}}})

    monkeypatch.setattr(run_market, "build_pipeline", fake_build_pipeline)

    exit_code = run_market.run_market_command(["--market", "usd_idr_id", "--upsert-notion", "--append-update-note", "--yes"])

    assert exit_code == 0
    assert calls == [{"use_real_llm": False, "include_notion_preview": False, "export_notion": False, "upsert_notion": True, "append_update_note": True}]
