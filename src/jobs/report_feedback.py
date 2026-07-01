from __future__ import annotations

import argparse
import json
import sys

from src.review.feedback_store import JsonlReviewFeedbackStore
from src.review.metrics import summarize_review_feedback


def report_feedback_command(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize local human review feedback.")
    parser.add_argument("--feedback-store-path", default=".runs/review_feedback.jsonl")
    parser.add_argument("--review-status")
    parser.add_argument("--market-id")
    parser.add_argument("--language")
    parser.add_argument("--model")
    parser.add_argument("--prompt-version")
    parser.add_argument("--content-job-key")
    parser.add_argument("--limit", type=int)
    namespace = parser.parse_args(args)

    if namespace.limit is not None and namespace.limit <= 0:
        print(json.dumps({"success": False, "status": "FEEDBACK_REPORT_ARGUMENT_ERROR", "errors": [{"message": "limit must be greater than 0."}]}, indent=2))
        return 2

    items = JsonlReviewFeedbackStore(namespace.feedback_store_path).filter_feedback(
        review_status=namespace.review_status,
        market_id=namespace.market_id,
        language=namespace.language,
        model=namespace.model,
        prompt_version=namespace.prompt_version,
        content_job_key=namespace.content_job_key,
        limit=namespace.limit,
    )
    payload = {
        "success": True,
        "status": "FEEDBACK_REPORT_GENERATED",
        "filters": {
            "feedback_store_path": namespace.feedback_store_path,
            "review_status": namespace.review_status,
            "market_id": namespace.market_id,
            "language": namespace.language,
            "model": namespace.model,
            "prompt_version": namespace.prompt_version,
            "content_job_key": namespace.content_job_key,
            "limit": namespace.limit,
        },
        "summary": summarize_review_feedback(items),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return report_feedback_command()


if __name__ == "__main__":
    sys.exit(main())
