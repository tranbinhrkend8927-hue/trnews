from __future__ import annotations

from src.observability.events import BATCH_COMPLETED, BATCH_FAILED, PIPELINE_COMPLETED, PIPELINE_FAILED, ObservationEvent


def summarize_events(events: list[ObservationEvent]) -> dict:
    summary = {
        "total_events": len(events),
        "pipelines": {"total": 0, "succeeded": 0, "failed": 0, "success_rate": 0.0},
        "batches": {"total": 0, "succeeded": 0, "failed": 0},
        "by_market": {},
        "by_language": {},
        "by_status": {},
        "llm": {"total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "by_model": {}},
        "notion": {"created": 0, "updated": 0, "failed": 0},
        "validators": {"failed_by_code": {}},
        "quality": {"avg_source_count": 0.0, "avg_body_length": 0.0},
    }
    source_counts: list[int] = []
    body_lengths: list[int] = []
    for event in events:
        if event.event_type in {PIPELINE_COMPLETED, PIPELINE_FAILED}:
            summary["pipelines"]["total"] += 1
            if event.success:
                summary["pipelines"]["succeeded"] += 1
            else:
                summary["pipelines"]["failed"] += 1
            _count_success(summary["by_market"], event.market_id, event.success)
            _count_success(summary["by_language"], event.language, event.success)
            if event.source_count is not None:
                source_counts.append(event.source_count)
            body_length = event.quality_summary.get("body_length")
            if isinstance(body_length, int):
                body_lengths.append(body_length)
        if event.event_type in {BATCH_COMPLETED, BATCH_FAILED}:
            summary["batches"]["total"] += 1
            if event.success:
                summary["batches"]["succeeded"] += 1
            else:
                summary["batches"]["failed"] += 1
        if event.status:
            summary["by_status"][event.status] = summary["by_status"].get(event.status, 0) + 1
        _add_llm_usage(summary["llm"], event)
        _add_notion(summary["notion"], event)
        _add_validator_codes(summary["validators"]["failed_by_code"], event)

    total = summary["pipelines"]["total"]
    summary["pipelines"]["success_rate"] = round(summary["pipelines"]["succeeded"] / total, 4) if total else 0.0
    summary["quality"]["avg_source_count"] = round(sum(source_counts) / len(source_counts), 4) if source_counts else 0.0
    summary["quality"]["avg_body_length"] = round(sum(body_lengths) / len(body_lengths), 4) if body_lengths else 0.0
    return summary


def _count_success(bucket: dict, key: str | None, success: bool | None) -> None:
    if not key:
        return
    item = bucket.setdefault(key, {"total": 0, "succeeded": 0, "failed": 0})
    item["total"] += 1
    if success:
        item["succeeded"] += 1
    else:
        item["failed"] += 1


def _add_llm_usage(llm: dict, event: ObservationEvent) -> None:
    prompt_tokens = int(event.usage.get("prompt_tokens") or event.usage.get("input_tokens") or 0)
    completion_tokens = int(event.usage.get("completion_tokens") or event.usage.get("output_tokens") or 0)
    total_tokens = int(event.usage.get("total_tokens") or prompt_tokens + completion_tokens)
    llm["total_prompt_tokens"] += prompt_tokens
    llm["total_completion_tokens"] += completion_tokens
    llm["total_tokens"] += total_tokens
    if event.model:
        model = llm["by_model"].setdefault(event.model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        model["calls"] += 1
        model["prompt_tokens"] += prompt_tokens
        model["completion_tokens"] += completion_tokens
        model["total_tokens"] += total_tokens


def _add_notion(notion: dict, event: ObservationEvent) -> None:
    action = event.notion_summary.get("action")
    if action == "created":
        notion["created"] += 1
    elif action == "updated":
        notion["updated"] += 1
    elif event.status == "NOTION_EXPORT_FAILED":
        notion["failed"] += 1


def _add_validator_codes(failed_by_code: dict, event: ObservationEvent) -> None:
    for code in event.validator_summary.get("failed_codes") or event.quality_summary.get("validator_codes") or []:
        failed_by_code[code] = failed_by_code.get(code, 0) + 1
