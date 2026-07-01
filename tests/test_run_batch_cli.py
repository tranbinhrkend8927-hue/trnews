import json
from types import SimpleNamespace

from src.jobs import run_batch


def market(market_id, enabled=True):
    return SimpleNamespace(id=market_id, enabled=enabled)


class FakeRegistry:
    def __init__(self):
        self.pipeline = SimpleNamespace(
            markets=[
                market("usd_idr_id", True),
                market("usd_jpy_ja", True),
                market("disabled_market", False),
            ]
        )

    def enabled_markets(self):
        return [item for item in self.pipeline.markets if item.enabled]


class FakePipeline:
    def __init__(self, results=None, exc_for=None):
        self.results = results or {}
        self.exc_for = set(exc_for or [])
        self.calls = []

    def run_market(self, market_id, *, dry_run=True):
        self.calls.append({"market_id": market_id, "dry_run": dry_run})
        if market_id in self.exc_for:
            raise RuntimeError("boom")
        return self.results.get(market_id, {"success": True, "status": "DRY_RUN_SUCCESS"})


def install(monkeypatch, pipeline=None, build_calls=None):
    registry = FakeRegistry()
    fake_pipeline = pipeline or FakePipeline()
    calls = build_calls if build_calls is not None else []
    monkeypatch.setattr(run_batch, "load_config_registry", lambda: registry)

    def fake_build_pipeline(**kwargs):
        calls.append(kwargs)
        return fake_pipeline

    monkeypatch.setattr(run_batch, "build_pipeline", fake_build_pipeline)
    return registry, fake_pipeline, calls


def test_default_selects_enabled_markets():
    selected = run_batch.select_markets(FakeRegistry())

    assert [market.id for market in selected] == ["usd_idr_id", "usd_jpy_ja"]


def test_enabled_only_selects_enabled_markets():
    selected = run_batch.select_markets(FakeRegistry(), enabled_only=True)

    assert [market.id for market in selected] == ["usd_idr_id", "usd_jpy_ja"]


def test_markets_selects_specific_markets():
    selected = run_batch.select_markets(FakeRegistry(), market_ids=["usd_jpy_ja"])

    assert [market.id for market in selected] == ["usd_jpy_ja"]


def test_limit_restricts_count():
    selected = run_batch.select_markets(FakeRegistry(), limit=1)

    assert [market.id for market in selected] == ["usd_idr_id"]


def test_invalid_market_returns_exit_code_2(monkeypatch, capsys):
    install(monkeypatch)

    exit_code = run_batch.run_batch_command(["--markets", "missing"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "BATCH_ARGUMENT_ERROR"


def test_invalid_limit_returns_exit_code_2(monkeypatch, capsys):
    install(monkeypatch)

    exit_code = run_batch.run_batch_command(["--limit", "0"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "BATCH_ARGUMENT_ERROR"


def test_default_does_not_create_real_llm_runner(monkeypatch, capsys):
    _, _, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--enabled-only", "--dry-run"])

    assert calls[0]["use_real_llm"] is False


def test_use_real_llm_creates_runner(monkeypatch, capsys):
    _, _, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--enabled-only", "--use-real-llm"])

    assert calls[0]["use_real_llm"] is True


def test_default_does_not_create_notion_real_exporter(monkeypatch, capsys):
    _, _, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--enabled-only"])

    assert calls[0]["export_notion"] is False


def test_include_notion_preview_creates_dry_run_exporter(monkeypatch, capsys):
    _, _, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--enabled-only", "--include-notion-preview"])

    assert calls[0]["include_notion_preview"] is True
    assert calls[0]["export_notion"] is False


def test_export_notion_creates_real_exporter(monkeypatch, capsys):
    _, _, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--enabled-only", "--export-notion", "--yes"])

    assert calls[0]["export_notion"] is True
    assert calls[0]["upsert_notion"] is False


def test_export_notion_without_yes_fails_without_running(monkeypatch, capsys):
    _, pipeline, calls = install(monkeypatch, build_calls=[])

    exit_code = run_batch.run_batch_command(["--enabled-only", "--export-notion"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "CONFIRMATION_REQUIRED"
    assert calls == []
    assert pipeline.calls == []


def test_export_notion_sets_dry_run_false(monkeypatch, capsys):
    _, pipeline, _ = install(monkeypatch)

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--export-notion", "--yes"])

    assert pipeline.calls == [{"market_id": "usd_idr_id", "dry_run": False}]


def test_upsert_notion_creates_upsert_exporter(monkeypatch, capsys):
    _, _, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--enabled-only", "--upsert-notion", "--yes"])

    assert calls[0]["upsert_notion"] is True
    assert calls[0]["export_notion"] is False


def test_upsert_notion_without_yes_fails_without_running(monkeypatch, capsys):
    _, pipeline, calls = install(monkeypatch, build_calls=[])

    exit_code = run_batch.run_batch_command(["--enabled-only", "--upsert-notion"])

    assert exit_code == 2
    assert calls == []
    assert pipeline.calls == []


def test_upsert_notion_sets_dry_run_false(monkeypatch, capsys):
    _, pipeline, _ = install(monkeypatch)

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--upsert-notion", "--yes"])

    assert pipeline.calls == [{"market_id": "usd_idr_id", "dry_run": False}]


def test_export_and_upsert_together_passes_both_flags_with_upsert_priority(monkeypatch, capsys):
    _, pipeline, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--export-notion", "--upsert-notion", "--yes"])

    assert calls[0]["export_notion"] is True
    assert calls[0]["upsert_notion"] is True
    assert pipeline.calls == [{"market_id": "usd_idr_id", "dry_run": False}]


def test_append_update_note_is_passed(monkeypatch, capsys):
    _, _, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--upsert-notion", "--append-update-note", "--yes"])

    assert calls[0]["append_update_note"] is True


def test_all_success_exit_code_zero(monkeypatch, capsys):
    install(monkeypatch)

    exit_code = run_batch.run_batch_command(["--enabled-only", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "BATCH_COMPLETED"
    assert payload["summary"]["succeeded"] == 2


def test_failure_continue_on_error_exit_code_one(monkeypatch, capsys):
    pipeline = FakePipeline(results={"usd_jpy_ja": {"success": False, "status": "SOURCE_BUNDLE_FAILED"}})
    install(monkeypatch, pipeline=pipeline)

    exit_code = run_batch.run_batch_command(["--enabled-only", "--continue-on-error"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "BATCH_COMPLETED_WITH_ERRORS"
    assert len(payload["results"]) == 2


def test_fail_fast_stops_after_first_failure(monkeypatch, capsys):
    pipeline = FakePipeline(results={"usd_idr_id": {"success": False, "status": "SOURCE_BUNDLE_FAILED"}})
    install(monkeypatch, pipeline=pipeline)

    exit_code = run_batch.run_batch_command(["--enabled-only", "--fail-fast"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "BATCH_ABORTED"
    assert len(payload["results"]) == 1


def test_output_json_contains_summary(monkeypatch, capsys):
    install(monkeypatch)

    run_batch.run_batch_command(["--markets", "usd_idr_id"])
    payload = json.loads(capsys.readouterr().out)

    assert "summary" in payload


def test_market_exception_is_structured(monkeypatch, capsys):
    pipeline = FakePipeline(exc_for={"usd_idr_id"})
    install(monkeypatch, pipeline=pipeline)

    exit_code = run_batch.run_batch_command(["--markets", "usd_idr_id"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["results"][0]["status"] == "MARKET_FAILED"
    assert payload["results"][0]["error"]["type"] == "exception"


def test_no_real_external_services_are_used(monkeypatch, capsys):
    _, pipeline, calls = install(monkeypatch, build_calls=[])

    run_batch.run_batch_command(["--markets", "usd_idr_id"])

    assert pipeline.calls == [{"market_id": "usd_idr_id", "dry_run": True}]
    assert calls[0] == {"use_real_llm": False, "include_notion_preview": False, "export_notion": False, "upsert_notion": False, "append_update_note": False}


def _result_for(market_id, success=True):
    return {
        "success": success,
        "status": "DRY_RUN_SUCCESS" if success else "FAILED",
        "market_id": market_id,
        "symbol": "USDIDR",
        "language": "id",
        "source_bundle_hash": f"hash-{market_id}",
        "content_job_key": f"job-{market_id}",
        "pipeline_run_id": f"run-{market_id}",
    }


def test_job_store_path_writes_each_market(monkeypatch, capsys, tmp_path):
    from src.jobs.job_store import FileJobStore

    path = tmp_path / "jobs.jsonl"
    pipeline = FakePipeline(results={"usd_idr_id": _result_for("usd_idr_id"), "usd_jpy_ja": _result_for("usd_jpy_ja")})
    install(monkeypatch, pipeline=pipeline)

    run_batch.run_batch_command(["--enabled-only", "--job-store-path", str(path)])

    assert len(FileJobStore(str(path)).list_records()) == 2


def test_summary_includes_skipped(monkeypatch, capsys, tmp_path):
    from src.jobs.job_store import FileJobStore
    from tests.test_job_store import record

    path = tmp_path / "jobs.jsonl"
    FileJobStore(str(path)).append(record(success=True))
    install(monkeypatch)

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--job-store-path", str(path), "--skip-existing-success"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["skipped"] == 1


def test_skip_existing_success_skips(monkeypatch, capsys, tmp_path):
    from src.jobs.job_store import FileJobStore
    from tests.test_job_store import record

    path = tmp_path / "jobs.jsonl"
    FileJobStore(str(path)).append(record(success=True))
    _, pipeline, _ = install(monkeypatch)

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--job-store-path", str(path), "--skip-existing-success"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["results"][0]["status"] == "SKIPPED_EXISTING_SUCCESS"
    assert pipeline.calls == []


def test_force_overrides_skip(monkeypatch, capsys, tmp_path):
    from src.jobs.job_store import FileJobStore
    from tests.test_job_store import record

    path = tmp_path / "jobs.jsonl"
    FileJobStore(str(path)).append(record(success=True))
    _, pipeline, _ = install(monkeypatch)

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--job-store-path", str(path), "--skip-existing-success", "--force"])

    assert pipeline.calls == [{"market_id": "usd_idr_id", "dry_run": True}]


def test_skipped_not_failed(monkeypatch, capsys, tmp_path):
    from src.jobs.job_store import FileJobStore
    from tests.test_job_store import record

    path = tmp_path / "jobs.jsonl"
    FileJobStore(str(path)).append(record(success=True))
    install(monkeypatch)

    exit_code = run_batch.run_batch_command(["--markets", "usd_idr_id", "--job-store-path", str(path), "--skip-existing-success"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["summary"]["failed"] == 0


def test_failed_records_queryable(monkeypatch, capsys, tmp_path):
    from src.jobs.job_store import FileJobStore

    path = tmp_path / "jobs.jsonl"
    pipeline = FakePipeline(results={"usd_idr_id": _result_for("usd_idr_id", success=False)})
    install(monkeypatch, pipeline=pipeline)

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--job-store-path", str(path)])

    assert FileJobStore(str(path)).list_failed()[0].market_id == "usd_idr_id"


def test_event_store_path_writes_pipeline_and_batch_events(monkeypatch, capsys, tmp_path):
    from src.observability.event_store import JsonlEventStore

    path = tmp_path / "events.jsonl"
    pipeline = FakePipeline(results={"usd_idr_id": _result_for("usd_idr_id")})
    install(monkeypatch, pipeline=pipeline)

    exit_code = run_batch.run_batch_command(["--markets", "usd_idr_id", "--event-store-path", str(path)])
    payload = json.loads(capsys.readouterr().out)
    events = JsonlEventStore(str(path)).list_events()

    assert exit_code == 0
    assert payload["summary"]["succeeded"] == 1
    assert [event.event_type for event in events] == ["pipeline.completed", "batch.completed"]


def test_event_store_writes_batch_failed_event(monkeypatch, capsys, tmp_path):
    from src.observability.event_store import JsonlEventStore

    path = tmp_path / "events.jsonl"
    pipeline = FakePipeline(results={"usd_idr_id": _result_for("usd_idr_id", success=False)})
    install(monkeypatch, pipeline=pipeline)

    exit_code = run_batch.run_batch_command(["--markets", "usd_idr_id", "--event-store-path", str(path)])
    events = JsonlEventStore(str(path)).list_events()

    assert exit_code == 1
    assert events[-1].event_type == "batch.failed"
    assert events[-1].metadata["summary"]["failed"] == 1


def test_event_store_does_not_duplicate_batch_pipeline_events(monkeypatch, capsys, tmp_path):
    from src.observability.event_store import JsonlEventStore

    path = tmp_path / "events.jsonl"
    install(monkeypatch)

    run_batch.run_batch_command(["--markets", "usd_idr_id", "--event-store-path", str(path)])

    events = JsonlEventStore(str(path)).list_events()
    assert len(events) == 2
