from __future__ import annotations

import argparse
import json
import os
import sys

from src.config.loader import load_config_registry
from src.notion.client import NotionClient
from src.notion.target_resolver import NotionTargetResolver
from src.review.feedback_store import JsonlReviewFeedbackStore
from src.review.notion_sync import NotionReviewSyncer


def sync_notion_reviews_command(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read Notion review statuses into the local review feedback store.")
    parser.add_argument("--target", required=True)
    parser.add_argument("--feedback-store-path", default=".runs/review_feedback.jsonl")
    parser.add_argument("--reviewer")
    parser.add_argument("--status", action="append", default=[])
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Write feedback even when ENABLE_NOTION_FEEDBACK_SYNC is not enabled.")
    namespace = parser.parse_args(args)

    if namespace.page_size <= 0:
        print(json.dumps({"success": False, "status": "NOTION_REVIEW_SYNC_ARGUMENT_ERROR", "errors": [{"message": "page-size must be greater than 0."}]}, indent=2))
        return 2
    if namespace.limit is not None and namespace.limit <= 0:
        print(json.dumps({"success": False, "status": "NOTION_REVIEW_SYNC_ARGUMENT_ERROR", "errors": [{"message": "limit must be greater than 0."}]}, indent=2))
        return 2
    if not namespace.dry_run and not namespace.force and not _feedback_sync_enabled():
        print(
            json.dumps(
                {
                    "success": False,
                    "status": "NOTION_REVIEW_SYNC_DISABLED",
                    "errors": [
                        {
                            "message": "Set ENABLE_NOTION_FEEDBACK_SYNC=1 or pass --force to write Notion review feedback.",
                        }
                    ],
                },
                indent=2,
            )
        )
        return 2

    registry = load_config_registry()
    syncer = NotionReviewSyncer(
        target_resolver=NotionTargetResolver(registry),
        notion_client=NotionClient(),
        feedback_store=JsonlReviewFeedbackStore(namespace.feedback_store_path),
    )
    result = syncer.sync(
        target_name=namespace.target,
        reviewer=namespace.reviewer,
        status_filter=namespace.status or None,
        page_size=namespace.page_size,
        limit=namespace.limit,
        dry_run=namespace.dry_run,
    )
    payload = result.model_dump() if hasattr(result, "model_dump") else result.dict()
    payload = {
        "success": result.success,
        "status": "NOTION_REVIEWS_SYNCED" if result.success else "NOTION_REVIEW_SYNC_FAILED",
        "target": result.target_name,
        **payload,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if result.success else 1


def main() -> int:
    return sync_notion_reviews_command()


def _feedback_sync_enabled() -> bool:
    return os.getenv("ENABLE_NOTION_FEEDBACK_SYNC", "0").strip().lower() in ("1", "true", "yes")


if __name__ == "__main__":
    sys.exit(main())
