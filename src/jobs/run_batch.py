from __future__ import annotations

import argparse
import json
import sys

from src.config.loader import load_config_registry
from src.jobs.job_store import FileJobStore, record_from_pipeline_result
from src.jobs.run_market import build_pipeline
from src.observability.event_store import JsonlEventStore
from src.observability.events import build_batch_event, build_pipeline_event


class BatchArgumentError(ValueError):
    pass


def select_markets(
    registry,
    *,
    enabled_only: bool = False,
    market_ids: list[str] | None = None,
    limit: int | None = None,
) -> list:
    if limit is not None and limit <= 0:
        raise BatchArgumentError("limit must be greater than 0.")

    markets_by_id = {market.id: market for market in registry.pipeline.markets}
    if market_ids:
        missing = [market_id for market_id in market_ids if market_id not in markets_by_id]
        if missing:
            raise BatchArgumentError("Unknown market id(s): " + ", ".join(missing))
        selected = [markets_by_id[market_id] for market_id in market_ids]
    elif enabled_only:
        selected = registry.enabled_markets()
    else:
        selected = registry.enabled_markets()

    return selected[:limit] if limit is not None else selected


def run_batch(
    *,
    registry,
    pipeline,
    markets: list,
    dry_run: bool,
    use_real_llm: bool,
    include_notion_preview: bool,
    export_notion: bool,
    continue_on_error: bool,
    fail_fast: bool,
    upsert_notion: bool = False,
    append_update_note: bool = False,
    job_store: FileJobStore | None = None,
    event_store: JsonlEventStore | None = None,
    skip_existing_success: bool = False,
    force: bool = False,
) -> dict:
    results = []
    errors = []
    for market in markets:
        if job_store is not None and skip_existing_success and not force:
            previous_success = _latest_success_for_market(job_store, market.id)
            if previous_success is not None:
                entry = {
                    "market_id": market.id,
                    "success": True,
                    "status": "SKIPPED_EXISTING_SUCCESS",
                    "skipped": True,
                    "job_key": previous_success.job_key,
                    "warning": {"type": "skip_existing_success_not_fully_prechecked"},
                }
                results.append(entry)
                continue
        try:
            result = pipeline.run_market(market.id, dry_run=dry_run)
            if job_store is not None:
                job_store.append(record_from_pipeline_result(result, fallback_market_id=market.id))
            if event_store is not None:
                event_store.append(build_pipeline_event(result))
            entry = {
                "market_id": market.id,
                "success": bool(result.get("success")),
                "status": result.get("status"),
                "result": result,
            }
        except Exception as exc:
            entry = {
                "market_id": market.id,
                "success": False,
                "status": "MARKET_FAILED",
                "error": {"type": "exception", "message": str(exc)},
            }
            if job_store is not None:
                job_store.append(record_from_pipeline_result(entry, fallback_market_id=market.id))
            if event_store is not None:
                event_store.append(build_pipeline_event(entry))
        results.append(entry)
        if not entry["success"]:
            errors.append({"market_id": market.id, "status": entry["status"], "error": entry.get("error")})
            if fail_fast:
                break
            if not continue_on_error:
                break

    succeeded = sum(1 for item in results if item["success"] and not item.get("skipped"))
    failed = sum(1 for item in results if not item["success"])
    skipped = sum(1 for item in results if item.get("skipped")) + max(0, len(markets) - len(results))
    if failed and fail_fast:
        status = "BATCH_ABORTED"
    elif failed:
        status = "BATCH_COMPLETED_WITH_ERRORS"
    else:
        status = "BATCH_COMPLETED"

    return {
        "success": failed == 0,
        "status": status,
        "summary": {
            "total": len(markets),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        },
        "options": {
            "dry_run": dry_run,
            "use_real_llm": use_real_llm,
            "include_notion_preview": include_notion_preview,
            "export_notion": export_notion,
            "upsert_notion": upsert_notion,
            "append_update_note": append_update_note,
            "continue_on_error": continue_on_error,
            "fail_fast": fail_fast,
            "skip_existing_success": skip_existing_success,
            "force": force,
        },
        "results": results,
        "errors": errors,
    }


def run_batch_command(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run configured market pipelines in batch.")
    parser.add_argument("--enabled-only", action="store_true", help="Run enabled markets only.")
    parser.add_argument("--markets", nargs="+", help="Specific market ids to run.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Run without exporting to Notion.")
    parser.add_argument("--use-real-llm", action="store_true", help="Call configured LLM runner.")
    parser.add_argument("--include-notion-preview", action="store_true", help="Include dry-run Notion payload preview.")
    parser.add_argument("--export-notion", action="store_true", help="Export each validated article to Notion.")
    parser.add_argument("--upsert-notion", action="store_true", help="Upsert each validated article to Notion.")
    parser.add_argument("--yes", action="store_true", help="Confirm real Notion writes for --export-notion or --upsert-notion.")
    parser.add_argument("--append-update-note", action="store_true", help="Append an update note when upsert updates an existing page.")
    parser.add_argument("--continue-on-error", action="store_true", default=True, help="Continue after a market fails.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop at the first failed market.")
    parser.add_argument("--limit", type=int, help="Maximum number of markets to run.")
    parser.add_argument("--job-store-path", help="Append market results to a local JSONL job store.")
    parser.add_argument("--event-store-path", help="Append local observation events for markets and batch summary.")
    parser.add_argument("--skip-existing-success", action="store_true", help="Skip markets with previous successful records.")
    parser.add_argument("--force", action="store_true", help="Run even if previous successful records exist.")
    namespace = parser.parse_args(args)
    if (namespace.export_notion or namespace.upsert_notion) and not namespace.yes:
        print(
            json.dumps(
                {
                    "success": False,
                    "status": "CONFIRMATION_REQUIRED",
                    "errors": [{"message": "Real Notion writes require --yes."}],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    try:
        registry = load_config_registry()
        markets = select_markets(
            registry,
            enabled_only=namespace.enabled_only,
            market_ids=namespace.markets,
            limit=namespace.limit,
        )
    except BatchArgumentError as exc:
        print(json.dumps({"success": False, "status": "BATCH_ARGUMENT_ERROR", "errors": [{"message": str(exc)}]}, indent=2))
        return 2

    pipeline = build_pipeline(
        use_real_llm=namespace.use_real_llm,
        include_notion_preview=namespace.include_notion_preview,
        export_notion=namespace.export_notion,
        upsert_notion=namespace.upsert_notion,
        append_update_note=namespace.append_update_note,
    )
    job_store = FileJobStore(namespace.job_store_path) if namespace.job_store_path else None
    event_store = JsonlEventStore(namespace.event_store_path) if namespace.event_store_path else None
    result = run_batch(
        registry=registry,
        pipeline=pipeline,
        markets=markets,
        dry_run=not (namespace.export_notion or namespace.upsert_notion),
        use_real_llm=namespace.use_real_llm,
        include_notion_preview=namespace.include_notion_preview,
        export_notion=namespace.export_notion,
        upsert_notion=namespace.upsert_notion,
        append_update_note=namespace.append_update_note,
        continue_on_error=True if not namespace.fail_fast else False,
        fail_fast=namespace.fail_fast,
        job_store=job_store,
        event_store=event_store,
        skip_existing_success=namespace.skip_existing_success,
        force=namespace.force,
    )
    if event_store is not None:
        event_store.append(build_batch_event(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("success") else 1


def main() -> int:
    return run_batch_command()


def _latest_success_for_market(job_store: FileJobStore, market_id: str):
    records = [record for record in job_store.list_records() if record.market_id == market_id and record.success]
    return records[-1] if records else None


if __name__ == "__main__":
    sys.exit(main())
