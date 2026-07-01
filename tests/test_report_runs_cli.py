import json

from src.jobs import report_runs
from src.observability.event_store import JsonlEventStore
from src.observability.events import ObservationEvent


def event(**overrides):
    data = {
        "event_id": "evt-1",
        "event_type": "pipeline.completed",
        "timestamp": "2026-07-01T00:00:00Z",
        "market_id": "usd_idr_id",
        "language": "id",
        "success": True,
        "status": "DRY_RUN_SUCCESS",
    }
    data.update(overrides)
    return ObservationEvent(**data)


def test_empty_event_store_returns_report_generated(tmp_path, capsys):
    exit_code = report_runs.report_runs_command(["--event-store-path", str(tmp_path / "events.jsonl")])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "REPORT_GENERATED"
    assert payload["summary"]["total_events"] == 0


def test_events_output_summary(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    JsonlEventStore(str(path)).append(event())

    exit_code = report_runs.report_runs_command(["--event-store-path", str(path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["summary"]["pipelines"]["total"] == 1


def test_filter_market_language_event_type_success_and_limit(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    store = JsonlEventStore(str(path))
    store.append(event(event_id="a", market_id="usd_idr_id", language="id", success=True))
    store.append(event(event_id="b", market_id="usd_jpy_ja", language="ja", success=False, event_type="pipeline.failed"))

    report_runs.report_runs_command(
        [
            "--event-store-path",
            str(path),
            "--market",
            "usd_idr_id",
            "--language",
            "id",
            "--event-type",
            "pipeline.completed",
            "--success",
            "true",
            "--limit",
            "1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["total_events"] == 1
    assert payload["filters"]["success"] is True


def test_argument_error_exit_code_2(tmp_path, capsys):
    exit_code = report_runs.report_runs_command(["--event-store-path", str(tmp_path / "events.jsonl"), "--limit", "0"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "REPORT_ARGUMENT_ERROR"
