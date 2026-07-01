from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class JobRecord(BaseModel):
    job_key: str
    pipeline_run_id: str
    market_id: str
    symbol: str
    language: str
    task: str
    source_bundle_hash: str
    status: str
    success: bool
    notion_page_id: Optional[str] = None
    notion_url: Optional[str] = None
    error: Optional[dict] = None
    result_summary: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class FileJobStore:
    def __init__(self, path: str = ".runs/content_jobs.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: JobRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            payload = record.model_dump() if hasattr(record, "model_dump") else record.dict()
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def list_records(self) -> list[JobRecord]:
        if not self.path.exists():
            return []
        records: list[JobRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                records.append(JobRecord(**data))
            except Exception:
                continue
        return records

    def find_by_job_key(self, job_key: str) -> list[JobRecord]:
        return [record for record in self.list_records() if record.job_key == job_key]

    def latest_by_job_key(self, job_key: str) -> JobRecord | None:
        matches = self.find_by_job_key(job_key)
        return matches[-1] if matches else None

    def has_successful_job(self, job_key: str) -> bool:
        return any(record.success for record in self.find_by_job_key(job_key))

    def list_failed(self, limit: int | None = None) -> list[JobRecord]:
        failed = [record for record in self.list_records() if not record.success]
        return failed[:limit] if limit is not None else failed


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def record_from_pipeline_result(result: dict, *, fallback_market_id: str | None = None) -> JobRecord:
    now = utc_now_iso()
    market_id = str(result.get("market_id") or fallback_market_id or "unknown")
    symbol = str(result.get("symbol") or "unknown")
    language = str(result.get("language") or "unknown")
    source_bundle_hash = str(result.get("source_bundle_hash") or result.get("source_bundle", {}).get("source_bundle_hash") or "unknown")
    job_key = str(result.get("content_job_key") or f"{market_id}:{symbol}:{language}:unknown:{source_bundle_hash[:16]}")
    notion = result.get("notion") or {}
    error = _extract_error(result)
    return JobRecord(
        job_key=job_key,
        pipeline_run_id=str(result.get("pipeline_run_id") or f"run-{market_id}-unknown"),
        market_id=market_id,
        symbol=symbol,
        language=language,
        task=str(result.get("task") or result.get("article", {}).get("article_type") or "article_draft"),
        source_bundle_hash=source_bundle_hash,
        status=str(result.get("status") or "FAILED"),
        success=bool(result.get("success")),
        notion_page_id=notion.get("page_id"),
        notion_url=notion.get("url"),
        error=error,
        result_summary={
            "status": result.get("status"),
            "success": bool(result.get("success")),
            "source_count": result.get("source_bundle", {}).get("source_trace", {}).get("source_count"),
        },
        created_at=now,
        updated_at=now,
    )


def _extract_error(result: dict) -> dict | None:
    if result.get("errors"):
        return {"errors": result.get("errors")}
    if result.get("notion", {}).get("error"):
        return result["notion"]["error"]
    return None
