from __future__ import annotations

import argparse
import json
import sys

from src.config.loader import load_config_registry
from src.content.article_pipeline import ArticlePipeline
from src.content.source_bundle import SourceBundleBuilder
from src.ingest.postgres_news import PostgresNewsAdapter, RefreshingPostgresNewsAdapter
from src.ingest.tradingview import TradingViewNewsAdapter
from src.jobs.job_store import FileJobStore, record_from_pipeline_result
from src.llm.task_runner import LLMTaskRunner
from src.notion.exporter import NotionDryRunExporter, NotionRealExporter, NotionUpsertExporter
from src.notion.target_resolver import NotionTargetResolver
from src.observability.event_store import JsonlEventStore
from src.observability.events import build_pipeline_event


def build_pipeline(
    *,
    use_real_llm: bool = False,
    include_notion_preview: bool = False,
    export_notion: bool = False,
    upsert_notion: bool = False,
    append_update_note: bool = False,
    source_mode: str = "db",
    refresh_sources: bool = False,
) -> ArticlePipeline:
    registry = load_config_registry()
    target_resolver = NotionTargetResolver(registry)
    notion_exporter = None
    if upsert_notion:
        notion_exporter = NotionUpsertExporter(target_resolver)
    elif export_notion:
        notion_exporter = NotionRealExporter(target_resolver)
    elif include_notion_preview:
        notion_exporter = NotionDryRunExporter(target_resolver)
    if source_mode == "live":
        source_adapter = TradingViewNewsAdapter()
        content_job_key_mode = "source_hash"
    elif refresh_sources:
        source_adapter = RefreshingPostgresNewsAdapter()
        content_job_key_mode = "daily"
    else:
        source_adapter = PostgresNewsAdapter()
        content_job_key_mode = "daily"
    return ArticlePipeline(
        config_registry=registry,
        tradingview_adapter=source_adapter,
        source_bundle_builder=SourceBundleBuilder(),
        llm_runner=LLMTaskRunner() if use_real_llm else None,
        notion_exporter=notion_exporter,
        append_update_note=append_update_note,
        content_job_key_mode=content_job_key_mode,
    )


def run_market_command(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one configured market pipeline.")
    parser.add_argument("--market", required=True, help="Market id from config/pipeline.yaml.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Run without exporting to Notion.")
    parser.add_argument("--use-real-llm", action="store_true", help="Call the configured LLM task runner.")
    parser.add_argument("--include-notion-preview", action="store_true", help="Include dry-run Notion payload preview.")
    parser.add_argument("--export-notion", action="store_true", help="Export the validated article to Notion.")
    parser.add_argument("--upsert-notion", action="store_true", help="Upsert the validated article to Notion by Content Job Key.")
    parser.add_argument("--yes", action="store_true", help="Confirm real Notion write for --export-notion or --upsert-notion.")
    parser.add_argument("--append-update-note", action="store_true", help="Append a short note when upsert updates an existing page.")
    parser.add_argument("--job-store-path", help="Append the run result to a local JSONL job store.")
    parser.add_argument("--event-store-path", help="Append a local observation event after the run.")
    parser.add_argument("--source-mode", choices=["db", "live"], default="db", help="Use stored Postgres forex_news by default; live fetches TradingView directly.")
    parser.add_argument("--refresh-sources", action="store_true", help="Fetch TradingView into Postgres first, then generate from stored forex_news.")
    parser.add_argument("--skip-existing-success", action="store_true", help="Reserved for idempotent skip support.")
    parser.add_argument("--force", action="store_true", help="Force execution even if a previous successful job exists.")
    namespace = parser.parse_args(args)
    if namespace.source_mode == "live" and namespace.refresh_sources:
        print(
            json.dumps(
                {
                    "success": False,
                    "status": "ARGUMENT_ERROR",
                    "errors": [{"message": "--refresh-sources requires --source-mode db."}],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
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

    build_kwargs = {
        "use_real_llm": namespace.use_real_llm,
        "include_notion_preview": namespace.include_notion_preview,
        "export_notion": namespace.export_notion,
        "upsert_notion": namespace.upsert_notion,
        "append_update_note": namespace.append_update_note,
    }
    if namespace.source_mode != "db":
        build_kwargs["source_mode"] = namespace.source_mode
    if namespace.refresh_sources:
        build_kwargs["refresh_sources"] = namespace.refresh_sources
    pipeline = build_pipeline(**build_kwargs)
    result = pipeline.run_market(namespace.market, dry_run=not (namespace.export_notion or namespace.upsert_notion))
    if namespace.job_store_path:
        FileJobStore(namespace.job_store_path).append(record_from_pipeline_result(result, fallback_market_id=namespace.market))
    if namespace.event_store_path:
        JsonlEventStore(namespace.event_store_path).append(build_pipeline_event(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("success") else 1


def main() -> int:
    return run_market_command()


if __name__ == "__main__":
    sys.exit(main())
