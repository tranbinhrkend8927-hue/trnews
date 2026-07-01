import json
from types import SimpleNamespace

from src.jobs import retry_failed
from src.jobs.job_store import FileJobStore
from tests.test_job_store import record
from tests.test_run_batch_cli import FakePipeline


class FakeRegistry:
    def __init__(self):
        self.pipeline = SimpleNamespace(markets=[SimpleNamespace(id="usd_idr_id")])


def install(monkeypatch, pipeline=None, calls=None):
    monkeypatch.setattr(retry_failed, "load_config_registry", lambda: FakeRegistry())
    fake_pipeline = pipeline or FakePipeline()
    build_calls = calls if calls is not None else []

    def fake_build_pipeline(**kwargs):
        build_calls.append(kwargs)
        return fake_pipeline

    monkeypatch.setattr(retry_failed, "build_pipeline", fake_build_pipeline)
    return fake_pipeline, build_calls


def test_no_failed_records_returns_no_failed_jobs(tmp_path, monkeypatch, capsys):
    install(monkeypatch)
    path = tmp_path / "jobs.jsonl"

    exit_code = retry_failed.retry_failed_command(["--job-store-path", str(path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "NO_FAILED_JOBS"


def test_failed_records_are_retried(tmp_path, monkeypatch, capsys):
    path = tmp_path / "jobs.jsonl"
    store = FileJobStore(str(path))
    store.append(record(success=False, status="FAILED"))
    pipeline, _ = install(monkeypatch)

    retry_failed.retry_failed_command(["--job-store-path", str(path)])

    assert pipeline.calls == [{"market_id": "usd_idr_id", "dry_run": True}]


def test_limit_is_applied(tmp_path, monkeypatch, capsys):
    path = tmp_path / "jobs.jsonl"
    store = FileJobStore(str(path))
    store.append(record(job_key="a", success=False))
    store.append(record(job_key="b", success=False))
    pipeline, _ = install(monkeypatch)

    retry_failed.retry_failed_command(["--job-store-path", str(path), "--limit", "1"])

    assert len(pipeline.calls) == 1


def test_default_dry_run(tmp_path, monkeypatch, capsys):
    path = tmp_path / "jobs.jsonl"
    FileJobStore(str(path)).append(record(success=False))
    pipeline, _ = install(monkeypatch)

    retry_failed.retry_failed_command(["--job-store-path", str(path)])

    assert pipeline.calls[0]["dry_run"] is True


def test_default_no_real_llm(tmp_path, monkeypatch, capsys):
    path = tmp_path / "jobs.jsonl"
    FileJobStore(str(path)).append(record(success=False))
    _, calls = install(monkeypatch, calls=[])

    retry_failed.retry_failed_command(["--job-store-path", str(path)])

    assert calls[0]["use_real_llm"] is False


def test_default_does_not_write_notion(tmp_path, monkeypatch, capsys):
    path = tmp_path / "jobs.jsonl"
    FileJobStore(str(path)).append(record(success=False))
    _, calls = install(monkeypatch, calls=[])

    retry_failed.retry_failed_command(["--job-store-path", str(path)])

    assert calls[0]["export_notion"] is False


def test_outputs_summary_json(tmp_path, monkeypatch, capsys):
    path = tmp_path / "jobs.jsonl"
    FileJobStore(str(path)).append(record(success=False))
    install(monkeypatch)

    retry_failed.retry_failed_command(["--job-store-path", str(path)])
    payload = json.loads(capsys.readouterr().out)

    assert "summary" in payload
