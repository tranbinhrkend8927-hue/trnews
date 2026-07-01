import json

from src.jobs.job_store import FileJobStore, JobRecord


def record(job_key="job", success=True, status="DRY_RUN_SUCCESS", created_at="2026-07-01T00:00:00Z"):
    return JobRecord(
        job_key=job_key,
        pipeline_run_id=f"run-{created_at}",
        market_id="usd_idr_id",
        symbol="USDIDR",
        language="id",
        task="article_draft",
        source_bundle_hash="hash",
        status=status,
        success=success,
        created_at=created_at,
        updated_at=created_at,
    )


def test_append_then_list_records(tmp_path):
    store = FileJobStore(str(tmp_path / "runs" / "jobs.jsonl"))

    store.append(record())

    assert store.list_records()[0].job_key == "job"


def test_missing_file_returns_empty(tmp_path):
    store = FileJobStore(str(tmp_path / "runs" / "jobs.jsonl"))

    assert store.list_records() == []


def test_latest_by_job_key_returns_latest(tmp_path):
    store = FileJobStore(str(tmp_path / "jobs.jsonl"))
    store.append(record(job_key="job", created_at="1"))
    store.append(record(job_key="job", created_at="2"))

    assert store.latest_by_job_key("job").created_at == "2"


def test_has_successful_job(tmp_path):
    store = FileJobStore(str(tmp_path / "jobs.jsonl"))
    store.append(record(job_key="job", success=False))
    store.append(record(job_key="job", success=True))

    assert store.has_successful_job("job") is True


def test_list_failed(tmp_path):
    store = FileJobStore(str(tmp_path / "jobs.jsonl"))
    store.append(record(job_key="ok", success=True))
    store.append(record(job_key="bad", success=False, status="FAILED"))

    assert [item.job_key for item in store.list_failed()] == ["bad"]


def test_list_failed_limit(tmp_path):
    store = FileJobStore(str(tmp_path / "jobs.jsonl"))
    store.append(record(job_key="bad1", success=False))
    store.append(record(job_key="bad2", success=False))

    assert len(store.list_failed(limit=1)) == 1


def test_bad_json_line_is_skipped(tmp_path):
    path = tmp_path / "jobs.jsonl"
    path.write_text("{bad json}\n" + json.dumps(record().model_dump()) + "\n", encoding="utf-8")
    store = FileJobStore(str(path))

    assert len(store.list_records()) == 1


def test_creates_directory(tmp_path):
    path = tmp_path / "new" / "jobs.jsonl"
    FileJobStore(str(path))

    assert path.parent.exists()
