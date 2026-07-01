import json

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
    }
    data.update(overrides)
    return ObservationEvent(**data)


def test_append_and_list(tmp_path):
    store = JsonlEventStore(str(tmp_path / "events.jsonl"))
    store.append(event())

    assert store.list_events()[0].event_id == "evt-1"


def test_missing_file_returns_empty(tmp_path):
    assert JsonlEventStore(str(tmp_path / "missing.jsonl")).list_events() == []


def test_filter_by_event_type_market_language_success_and_limit(tmp_path):
    store = JsonlEventStore(str(tmp_path / "events.jsonl"))
    store.append(event(event_id="a", event_type="pipeline.completed", market_id="usd_idr_id", language="id", success=True))
    store.append(event(event_id="b", event_type="pipeline.failed", market_id="usd_jpy_ja", language="ja", success=False))

    assert [item.event_id for item in store.filter_events(event_type="pipeline.failed")] == ["b"]
    assert [item.event_id for item in store.filter_events(market_id="usd_idr_id")] == ["a"]
    assert [item.event_id for item in store.filter_events(language="ja")] == ["b"]
    assert [item.event_id for item in store.filter_events(success=False)] == ["b"]
    assert len(store.filter_events(limit=1)) == 1


def test_bad_json_line_is_skipped(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("bad json\n" + json.dumps(event().model_dump()) + "\n", encoding="utf-8")

    assert len(JsonlEventStore(str(path)).list_events()) == 1


def test_auto_creates_directory(tmp_path):
    path = tmp_path / "nested" / "events.jsonl"
    store = JsonlEventStore(str(path))
    store.append(event())

    assert path.exists()
