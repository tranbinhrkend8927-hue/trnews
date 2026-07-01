from src.observability.events import BATCH_COMPLETED, BATCH_FAILED, PIPELINE_COMPLETED, PIPELINE_FAILED, build_batch_event, build_pipeline_event


def pipeline_result(success=True):
    return {
        "success": success,
        "status": "DRY_RUN_SUCCESS" if success else "VALIDATION_FAILED",
        "pipeline_run_id": "run-1",
        "content_job_key": "job-1",
        "source_bundle_hash": "hash-1",
        "market_id": "usd_idr_id",
        "symbol": "USDIDR",
        "language": "id",
        "task": "article_draft",
        "llm": {"model": "model-a", "prompt_version": "v1", "profile": "draft", "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "latency_ms": 123},
        "source_bundle": {"source_trace": {"source_count": 2}, "sources": [{}, {}]},
        "article": {"title": "T", "summary": "S", "body": "Body", "sources_used": [{}]},
        "validation": {"schema": {"passed": success, "issues": [] if success else [{"severity": "error", "code": "schema"}]}},
        "notion": {"success": True, "page_id": "page", "url": "url", "metadata": {"action": "updated"}},
    }


def test_build_pipeline_event_success_result():
    event = build_pipeline_event(pipeline_result(True))

    assert event.event_type == PIPELINE_COMPLETED
    assert event.success is True
    assert event.pipeline_run_id == "run-1"
    assert event.source_count == 2


def test_build_pipeline_event_failure_result():
    event = build_pipeline_event(pipeline_result(False))

    assert event.event_type == PIPELINE_FAILED
    assert event.success is False
    assert event.validator_summary["failed_codes"] == ["schema"]


def test_build_pipeline_event_missing_fields_does_not_crash():
    event = build_pipeline_event({})

    assert event.event_type == PIPELINE_FAILED
    assert event.event_id


def test_build_pipeline_event_extracts_llm_usage_and_notion_action():
    event = build_pipeline_event(pipeline_result(True))

    assert event.model == "model-a"
    assert event.prompt_version == "v1"
    assert event.usage["prompt_tokens"] == 10
    assert event.latency_ms == 123
    assert event.notion_summary["action"] == "updated"


def test_build_batch_event_success():
    event = build_batch_event({"success": True, "status": "BATCH_COMPLETED", "summary": {"total": 1}, "options": {"dry_run": True}, "results": []})

    assert event.event_type == BATCH_COMPLETED
    assert event.metadata["summary"]["total"] == 1


def test_build_batch_event_failure_and_failed_ids():
    event = build_batch_event(
        {
            "success": False,
            "status": "BATCH_COMPLETED_WITH_ERRORS",
            "summary": {"total": 2},
            "options": {},
            "results": [{"market_id": "bad", "success": False, "result": {"large": "x" * 1000}}],
        }
    )

    assert event.event_type == BATCH_FAILED
    assert event.metadata["failed_market_ids"] == ["bad"]
    assert "results" not in event.metadata
