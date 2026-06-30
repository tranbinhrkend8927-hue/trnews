"""CLI for human review of generated article drafts."""

import argparse
import json
from typing import List, Optional

from dotenv import load_dotenv

from .article_review import (
    build_article_review_report,
    fetch_article_for_review,
    fetch_article_sources_for_review,
    json_safe,
    save_article_review_to_postgres,
)
from .fetch_forex_news_json import get_postgres_dsn


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review a generated article draft.")
    parser.add_argument("--article-id", type=int, required=True, help="generated_articles.id to review.")
    parser.add_argument("--report", action="store_true", help="Build a review report without writing to Postgres.")
    parser.add_argument("--decision", choices=["approved", "rejected", "needs_changes"], help="Human review decision.")
    parser.add_argument("--reviewer", help="Reviewer name or identifier.")
    parser.add_argument("--notes", help="Reviewer notes.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate decision without writing to Postgres.")
    mode.add_argument("--save-db", action="store_true", help="Insert review record and update generated_articles.status.")
    return parser


def _error_result(article_id: int, error: dict) -> dict:
    return json_safe(
        {
            "success": False,
            "article_id": article_id,
            "report": {},
            "review": {},
            "errors": [error],
        }
    )


def _report_result(article_id: int, report: dict) -> dict:
    return json_safe(
        {
            "success": True,
            "article_id": article_id,
            "report": report,
            "review": {},
            "errors": [],
        }
    )


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.report and args.decision:
        result = _error_result(
            args.article_id,
            {
                "code": "ambiguous_mode",
                "message": "--report cannot be combined with --decision.",
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    if not args.report and not args.decision:
        result = _error_result(
            args.article_id,
            {
                "code": "missing_mode",
                "message": "Use --report or provide --decision.",
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    try:
        dsn = get_postgres_dsn()
        if args.report:
            article = fetch_article_for_review(dsn, args.article_id)
            if not article:
                result = _error_result(
                    args.article_id,
                    {
                        "code": "article_not_found",
                        "message": f"Article not found: {args.article_id}",
                    },
                )
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
            article_sources = fetch_article_sources_for_review(dsn, args.article_id)
            report = build_article_review_report(article, article_sources)
            result = _report_result(args.article_id, report)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        dry_run = args.dry_run or not args.save_db
        review_result = save_article_review_to_postgres(
            dsn,
            args.article_id,
            args.decision,
            reviewer=args.reviewer,
            reviewer_notes=args.notes,
            dry_run=dry_run,
        )
        result = json_safe(
            {
                "success": bool(review_result.get("success")),
                "article_id": args.article_id,
                "report": review_result.get("review_report") or {},
                "review": review_result,
                "errors": review_result.get("errors") or [],
            }
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["success"] else 1
    except Exception as exc:
        result = _error_result(
            args.article_id,
            {
                "code": "review_cli_failed",
                "message": str(exc),
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
