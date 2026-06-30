"""Create article draft shells from content topics."""

import argparse
import json
from typing import List, Optional

from dotenv import load_dotenv

from .article_drafts import (
    build_article_draft_from_template,
    fetch_topic_for_draft,
    json_safe,
    save_article_sources_to_postgres,
    save_article_draft_to_postgres,
    utc_now_iso,
)
from .draft_quality import evaluate_draft_quality
from .fetch_forex_news_json import get_postgres_dsn
from .safety_validation import apply_fact_check_status, validate_financial_safety
from .source_grounding import (
    build_article_sources_from_bundle,
    build_source_bundle,
    fetch_source_news_for_topic,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a generated_articles draft from one content topic.")
    parser.add_argument("--topic-id", type=int, required=True, help="content_topics.id to create a draft for.")
    parser.add_argument("--template", help="Optional article template override. Only supported P5 templates are allowed.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Build and validate the draft without inserting it.")
    mode.add_argument("--save-db", action="store_true", help="Insert the draft shell into Postgres.")
    return parser


def build_result(
    topic_id: int,
    dry_run=True,
    draft=None,
    validation=None,
    quality_result=None,
    save_result=None,
    source_bundle=None,
    article_sources_result=None,
    errors=None,
) -> dict:
    save_result = save_result or {}
    article_sources_result = article_sources_result or {}
    errors = errors or []
    inserted_count = int(save_result.get("inserted_count", 0) or 0)
    skipped_count = int(save_result.get("skipped_count", 0) or 0)
    failed_count = int(save_result.get("failed_count", 0) or 0)
    article_sources_inserted = int(article_sources_result.get("inserted_count", 0) or 0)
    article_sources_failed = int(article_sources_result.get("failed_count", 0) or 0)
    article_sources_skipped = int(article_sources_result.get("skipped_count", 0) or 0)
    return json_safe(
        {
            "success": not errors and failed_count == 0 and article_sources_failed == 0,
            "generated_at": utc_now_iso(),
            "topic_id": topic_id,
            "dry_run": bool(dry_run),
            "summary": {
                "drafts_generated": 1 if draft else 0,
                "drafts_inserted": inserted_count,
                "drafts_skipped": skipped_count,
                "drafts_failed": failed_count,
                "inserted": 0 if dry_run else inserted_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "would_insert": inserted_count if dry_run else 0,
                "article_sources_inserted": article_sources_inserted,
                "article_sources_failed": article_sources_failed,
                "article_sources_skipped": article_sources_skipped,
            },
            "source_bundle": source_bundle or {},
            "draft": draft,
            "safety": validation,
            "safety_result": validation,
            "quality_result": quality_result or {},
            "database": {
                "save": save_result,
                "article_sources": article_sources_result,
            } if save_result or article_sources_result else {},
            "errors": errors,
        }
    )


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    dry_run = args.dry_run or not args.save_db

    try:
        dsn = get_postgres_dsn()
        topic = fetch_topic_for_draft(dsn, args.topic_id)
        if not topic:
            result = build_result(
                args.topic_id,
                dry_run=dry_run,
                errors=[{"topic_id": args.topic_id, "error": f"Topic not found: {args.topic_id}"}],
            )
        else:
            source_news_result = fetch_source_news_for_topic(dsn, topic)
            source_bundle = build_source_bundle(topic, source_news_result)
            draft_result = build_article_draft_from_template(topic, template=args.template, source_bundle=source_bundle)
            if not draft_result.get("success"):
                result = build_result(
                    args.topic_id,
                    dry_run=dry_run,
                    source_bundle=source_bundle,
                    errors=[draft_result.get("error")],
                )
                print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
                return 1
            draft = draft_result["draft"]
            validation = validate_financial_safety(draft)
            draft = apply_fact_check_status(draft, validation)
            quality_result = evaluate_draft_quality(draft, source_bundle=source_bundle, safety_result=validation)
            save_result = save_article_draft_to_postgres(draft, dsn, dry_run=dry_run)
            article_sources_result = {}
            if not dry_run and save_result.get("inserted_count") == 1 and save_result.get("article_id"):
                article_sources = build_article_sources_from_bundle(source_bundle)
                article_sources_result = save_article_sources_to_postgres(
                    save_result["article_id"],
                    article_sources,
                    dsn,
                    dry_run=False,
                )
            result = build_result(
                args.topic_id,
                dry_run=dry_run,
                draft=draft,
                validation=validation,
                quality_result=quality_result,
                save_result=save_result,
                source_bundle=source_bundle,
                article_sources_result=article_sources_result,
            )
    except Exception as exc:
        result = build_result(args.topic_id, dry_run=args.dry_run or not args.save_db, errors=[{"topic_id": args.topic_id, "error": str(exc)}])

    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
