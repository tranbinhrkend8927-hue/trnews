"""CLI for exporting approved generated articles to Notion."""

import argparse
import json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from fetch_forex_news_json import get_postgres_dsn
from notion_config import json_safe, load_notion_config
from notion_exporter import (
    build_notion_client_from_env,
    export_article_to_notion,
    fetch_article_for_export,
    fetch_article_sources_for_export,
    save_article_export_record_to_postgres,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export an approved generated article to Notion.")
    parser.add_argument("--article-id", type=int, required=True, help="generated_articles.id to export.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and build Notion payload without writing.")
    parser.add_argument("--export", action="store_true", help="Call Notion and record the export result.")
    return parser


def _error(error_type: str, message: str, *, retryable: bool = False) -> Dict[str, Any]:
    return {"type": error_type, "message": message, "retryable": bool(retryable)}


def _result(
    *,
    article_id: int,
    dry_run: bool,
    export_result: Optional[Dict[str, Any]] = None,
    record_result: Optional[Dict[str, Any]] = None,
    config_summary: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    export_result = export_result or {}
    record_result = record_result or {}
    errors = errors or export_result.get("errors") or record_result.get("errors") or []
    return json_safe(
        {
            "success": not errors and bool(export_result.get("success", False)),
            "article_id": article_id,
            "dry_run": bool(dry_run),
            "exportable": bool(export_result.get("exportable")),
            "validation": export_result.get("validation") or {},
            "notion": export_result.get("notion") or {},
            "config": config_summary or {},
            "database": {"export_record": record_result} if record_result else {},
            "summary": {
                "would_write_export_record": not dry_run,
                "export_record_status": (export_result.get("summary") or {}).get("export_record_status"),
                "would_publish": False,
            },
            "errors": errors,
        }
    )


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.export:
        result = _result(
            article_id=args.article_id,
            dry_run=True,
            export_result={
                "success": False,
                "exportable": False,
                "errors": [_error("invalid_mode", "--dry-run and --export cannot be used together.")],
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    dry_run = not args.export

    try:
        dsn = get_postgres_dsn()
        article = fetch_article_for_export(dsn, args.article_id)
        if not article:
            result = _result(
                article_id=args.article_id,
                dry_run=dry_run,
                export_result={"success": False, "exportable": False, "errors": [_error("article_not_found", "Article not found.")]},
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        article_sources = fetch_article_sources_for_export(dsn, args.article_id)
        if dry_run:
            config_summary = load_notion_config(require_api_key=False)
            export_result = export_article_to_notion(article, article_sources, notion_client=None, dry_run=True)
            result = _result(
                article_id=args.article_id,
                dry_run=True,
                export_result=export_result,
                config_summary=config_summary,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("success") else 1

        client_result = build_notion_client_from_env(require_api_key=True)
        config_summary = client_result.get("config") or {}
        if not client_result.get("success"):
            export_result = {
                "success": False,
                "article_id": args.article_id,
                "dry_run": False,
                "exportable": False,
                "validation": {},
                "notion": {},
                "summary": {"export_record_status": "failed", "would_publish": False},
                "errors": client_result.get("errors") or [_error("config_error", "Invalid Notion configuration.")],
            }
            record_result = save_article_export_record_to_postgres(dsn, export_result, dry_run=False)
            result = _result(
                article_id=args.article_id,
                dry_run=False,
                export_result=export_result,
                record_result=record_result,
                config_summary=config_summary,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        export_result = export_article_to_notion(article, article_sources, client_result.get("client"), dry_run=False)
        record_result = save_article_export_record_to_postgres(dsn, export_result, dry_run=False)
        result = _result(
            article_id=args.article_id,
            dry_run=False,
            export_result=export_result,
            record_result=record_result,
            config_summary=config_summary,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("success") else 1
    except Exception as exc:
        result = _result(
            article_id=args.article_id,
            dry_run=dry_run,
            export_result={"success": False, "exportable": False, "errors": [_error("notion_export_cli_failed", str(exc))]},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
