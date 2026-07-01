from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from src.observability.quality import summarize_article_quality


PIPELINE_COMPLETED = "pipeline.completed"
PIPELINE_FAILED = "pipeline.failed"
BATCH_COMPLETED = "batch.completed"
BATCH_FAILED = "batch.failed"
NOTION_CREATED = "notion.created"
NOTION_UPDATED = "notion.updated"
LLM_COMPLETED = "llm.completed"
LLM_FAILED = "llm.failed"
VALIDATION_FAILED = "validation.failed"


class ObservationEvent(BaseModel):
    event_id: str
    event_type: str
    timestamp: str

    pipeline_run_id: Optional[str] = None
    content_job_key: Optional[str] = None
    source_bundle_hash: Optional[str] = None

    market_id: Optional[str] = None
    symbol: Optional[str] = None
    language: Optional[str] = None
    task: Optional[str] = None

    status: Optional[str] = None
    success: Optional[bool] = None

    model: Optional[str] = None
    prompt_version: Optional[str] = None
    llm_profile: Optional[str] = None
    usage: dict = Field(default_factory=dict)
    latency_ms: Optional[int] = None

    source_count: Optional[int] = None
    validator_summary: dict = Field(default_factory=dict)
    quality_summary: dict = Field(default_factory=dict)
    notion_summary: dict = Field(default_factory=dict)

    error: Optional[dict] = None
    metadata: dict = Field(default_factory=dict)


def build_pipeline_event(result: dict) -> ObservationEvent:
    data = result if isinstance(result, dict) else {}
    timestamp = _utc_now()
    llm = data.get("llm") if isinstance(data.get("llm"), dict) else {}
    validation = data.get("validation") if isinstance(data.get("validation"), dict) else {}
    source_bundle = data.get("source_bundle") if isinstance(data.get("source_bundle"), dict) else {}
    notion = data.get("notion") if isinstance(data.get("notion"), dict) else {}
    if not notion and isinstance(data.get("notion_preview"), dict):
        notion = data.get("notion_preview") or {}
    quality = summarize_article_quality(data.get("article"), source_bundle, validation)
    return ObservationEvent(
        event_id=_event_id("pipeline", timestamp, data),
        event_type=PIPELINE_COMPLETED if bool(data.get("success")) else PIPELINE_FAILED,
        timestamp=timestamp,
        pipeline_run_id=data.get("pipeline_run_id"),
        content_job_key=data.get("content_job_key"),
        source_bundle_hash=data.get("source_bundle_hash") or source_bundle.get("source_bundle_hash"),
        market_id=data.get("market_id"),
        symbol=data.get("symbol"),
        language=data.get("language"),
        task=data.get("task"),
        status=data.get("status"),
        success=bool(data.get("success")),
        model=llm.get("model"),
        prompt_version=llm.get("prompt_version"),
        llm_profile=llm.get("profile"),
        usage=llm.get("usage") or {},
        latency_ms=llm.get("latency_ms"),
        source_count=_source_count(source_bundle),
        validator_summary=_validator_summary(validation),
        quality_summary=quality,
        notion_summary=_notion_summary(notion),
        error=_extract_error(data),
        metadata={"dry_run": data.get("dry_run")},
    )


def build_batch_event(result: dict) -> ObservationEvent:
    data = result if isinstance(result, dict) else {}
    timestamp = _utc_now()
    failed_market_ids = [
        item.get("market_id")
        for item in data.get("results", [])
        if isinstance(item, dict) and not item.get("success") and item.get("market_id")
    ]
    return ObservationEvent(
        event_id=_event_id("batch", timestamp, data),
        event_type=BATCH_COMPLETED if bool(data.get("success")) else BATCH_FAILED,
        timestamp=timestamp,
        status=data.get("status"),
        success=bool(data.get("success")),
        error={"errors": data.get("errors")} if data.get("errors") else None,
        metadata={
            "summary": data.get("summary") or {},
            "options": data.get("options") or {},
            "failed_market_ids": failed_market_ids,
        },
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _event_id(prefix: str, timestamp: str, data: dict) -> str:
    basis = {
        "timestamp": timestamp,
        "pipeline_run_id": data.get("pipeline_run_id"),
        "content_job_key": data.get("content_job_key"),
        "status": data.get("status"),
        "success": data.get("success"),
        "summary": data.get("summary"),
    }
    digest = hashlib.sha256(json.dumps(basis, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _source_count(source_bundle: dict) -> int | None:
    trace_count = (source_bundle.get("source_trace") or {}).get("source_count")
    if isinstance(trace_count, int):
        return trace_count
    sources = source_bundle.get("sources")
    if isinstance(sources, list):
        return len(sources)
    return None


def _validator_summary(validation: dict) -> dict:
    summary = {"total": 0, "passed": 0, "failed": 0, "issues": 0, "failed_codes": []}
    codes: set[str] = set()
    for result in validation.values():
        if not isinstance(result, dict):
            continue
        summary["total"] += 1
        if result.get("passed"):
            summary["passed"] += 1
        else:
            summary["failed"] += 1
        for issue in result.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            summary["issues"] += 1
            if issue.get("code"):
                codes.add(str(issue["code"]))
    summary["failed_codes"] = sorted(codes)
    return summary


def _notion_summary(notion: dict) -> dict:
    payload = notion.get("payload") if isinstance(notion.get("payload"), dict) else {}
    metadata = notion.get("metadata") if isinstance(notion.get("metadata"), dict) else {}
    return {
        "action": metadata.get("action"),
        "page_id": notion.get("page_id"),
        "url": notion.get("url"),
        "success": notion.get("success"),
        "dry_run": notion.get("dry_run"),
        "warnings": payload.get("warnings") or notion.get("warnings") or [],
    }


def _extract_error(result: dict) -> dict | None:
    if result.get("errors"):
        return {"errors": result.get("errors")}
    notion = result.get("notion") if isinstance(result.get("notion"), dict) else {}
    if notion.get("error"):
        return notion["error"]
    return None
