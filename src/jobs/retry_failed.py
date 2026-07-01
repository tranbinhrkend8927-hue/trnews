from __future__ import annotations

import argparse
import json
import sys

from src.jobs.job_store import FileJobStore
from src.jobs.run_batch import run_batch
from src.jobs.run_market import build_pipeline
from src.config.loader import load_config_registry


def retry_failed_command(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retry failed content jobs from a local JSONL job store.")
    parser.add_argument("--job-store-path", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--use-real-llm", action="store_true")
    parser.add_argument("--include-notion-preview", action="store_true")
    parser.add_argument("--export-notion", action="store_true")
    namespace = parser.parse_args(args)

    store = FileJobStore(namespace.job_store_path)
    failed = store.list_failed(limit=namespace.limit)
    if not failed:
        result = {
            "success": True,
            "status": "NO_FAILED_JOBS",
            "summary": {"total": 0, "succeeded": 0, "failed": 0, "skipped": 0},
            "results": [],
            "errors": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    registry = load_config_registry()
    markets_by_id = {market.id: market for market in registry.pipeline.markets}
    markets = [markets_by_id[record.market_id] for record in failed if record.market_id in markets_by_id]
    pipeline = build_pipeline(
        use_real_llm=namespace.use_real_llm,
        include_notion_preview=namespace.include_notion_preview,
        export_notion=namespace.export_notion,
    )
    result = run_batch(
        registry=registry,
        pipeline=pipeline,
        markets=markets,
        dry_run=not namespace.export_notion,
        use_real_llm=namespace.use_real_llm,
        include_notion_preview=namespace.include_notion_preview,
        export_notion=namespace.export_notion,
        continue_on_error=True,
        fail_fast=False,
        job_store=store,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("success") else 1


def main() -> int:
    return retry_failed_command()


if __name__ == "__main__":
    sys.exit(main())
