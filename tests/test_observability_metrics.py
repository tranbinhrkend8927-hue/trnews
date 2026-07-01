from src.observability.events import ObservationEvent
from src.observability.metrics import summarize_events


def event(**overrides):
    data = {
        "event_id": "evt",
        "event_type": "pipeline.completed",
        "timestamp": "2026-07-01T00:00:00Z",
        "success": True,
        "status": "DRY_RUN_SUCCESS",
    }
    data.update(overrides)
    return ObservationEvent(**data)


def test_empty_events_summary():
    summary = summarize_events([])

    assert summary["total_events"] == 0
    assert summary["pipelines"]["success_rate"] == 0.0


def test_pipeline_success_failure_and_status():
    summary = summarize_events([event(success=True), event(event_type="pipeline.failed", success=False, status="VALIDATION_FAILED")])

    assert summary["pipelines"]["total"] == 2
    assert summary["pipelines"]["succeeded"] == 1
    assert summary["pipelines"]["failed"] == 1
    assert summary["by_status"]["VALIDATION_FAILED"] == 1


def test_batch_success_failure():
    summary = summarize_events([event(event_type="batch.completed", success=True), event(event_type="batch.failed", success=False)])

    assert summary["batches"]["succeeded"] == 1
    assert summary["batches"]["failed"] == 1


def test_by_market_and_language():
    summary = summarize_events([event(market_id="usd_idr_id", language="id"), event(event_type="pipeline.failed", success=False, market_id="usd_idr_id", language="id")])

    assert summary["by_market"]["usd_idr_id"]["total"] == 2
    assert summary["by_language"]["id"]["failed"] == 1


def test_token_usage_and_by_model():
    summary = summarize_events(
        [
            event(model="m1", usage={"prompt_tokens": 10, "completion_tokens": 5}),
            event(model="m1", usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 6}),
        ]
    )

    assert summary["llm"]["total_prompt_tokens"] == 12
    assert summary["llm"]["total_completion_tokens"] == 8
    assert summary["llm"]["total_tokens"] == 21
    assert summary["llm"]["by_model"]["m1"]["calls"] == 2


def test_notion_created_updated_and_failed():
    summary = summarize_events(
        [
            event(notion_summary={"action": "created"}),
            event(notion_summary={"action": "updated"}),
            event(event_type="pipeline.failed", success=False, status="NOTION_EXPORT_FAILED"),
        ]
    )

    assert summary["notion"]["created"] == 1
    assert summary["notion"]["updated"] == 1
    assert summary["notion"]["failed"] == 1


def test_validator_failed_by_code_and_quality_averages():
    summary = summarize_events(
        [
            event(source_count=2, quality_summary={"body_length": 100}, validator_summary={"failed_codes": ["a"]}),
            event(source_count=4, quality_summary={"body_length": 200, "validator_codes": ["b"]}),
        ]
    )

    assert summary["validators"]["failed_by_code"]["a"] == 1
    assert summary["validators"]["failed_by_code"]["b"] == 1
    assert summary["quality"]["avg_source_count"] == 3.0
    assert summary["quality"]["avg_body_length"] == 150.0
