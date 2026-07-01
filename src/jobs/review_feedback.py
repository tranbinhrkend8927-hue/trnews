from __future__ import annotations

import argparse
import json
import sys

from pydantic import ValidationError

from src.review.feedback import create_review_feedback
from src.review.feedback_store import JsonlReviewFeedbackStore


def review_feedback_command(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one local human review feedback item.")
    parser.add_argument("--feedback-store-path", default=".runs/review_feedback.jsonl")
    parser.add_argument("--review-status", required=True)
    parser.add_argument("--pipeline-run-id")
    parser.add_argument("--content-job-key")
    parser.add_argument("--notion-page-id")
    parser.add_argument("--notion-url")
    parser.add_argument("--market-id")
    parser.add_argument("--symbol")
    parser.add_argument("--language")
    parser.add_argument("--task")
    parser.add_argument("--model")
    parser.add_argument("--prompt-version")
    parser.add_argument("--reviewer")
    parser.add_argument("--quality-score", type=int)
    parser.add_argument("--factuality-score", type=int)
    parser.add_argument("--language-score", type=int)
    parser.add_argument("--seo-score", type=int)
    parser.add_argument("--compliance-score", type=int)
    parser.add_argument("--issue", action="append", default=[])
    parser.add_argument("--notes")
    namespace = parser.parse_args(args)

    try:
        feedback = create_review_feedback(
            review_status=namespace.review_status,
            pipeline_run_id=namespace.pipeline_run_id,
            content_job_key=namespace.content_job_key,
            notion_page_id=namespace.notion_page_id,
            notion_url=namespace.notion_url,
            market_id=namespace.market_id,
            symbol=namespace.symbol,
            language=namespace.language,
            task=namespace.task,
            model=namespace.model,
            prompt_version=namespace.prompt_version,
            reviewer=namespace.reviewer,
            quality_score=namespace.quality_score,
            factuality_score=namespace.factuality_score,
            language_score=namespace.language_score,
            seo_score=namespace.seo_score,
            compliance_score=namespace.compliance_score,
            issues=namespace.issue,
            notes=namespace.notes,
        )
        JsonlReviewFeedbackStore(namespace.feedback_store_path).append(feedback)
        print(json.dumps({"success": True, "status": "FEEDBACK_RECORDED", "feedback": feedback.model_dump()}, ensure_ascii=False, indent=2))
        return 0
    except ValidationError as exc:
        print(json.dumps({"success": False, "status": "FEEDBACK_ARGUMENT_ERROR", "errors": json.loads(exc.json())}, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        print(json.dumps({"success": False, "status": "FEEDBACK_ARGUMENT_ERROR", "errors": [{"message": str(exc)}]}, ensure_ascii=False, indent=2))
        return 2


def main() -> int:
    return review_feedback_command()


if __name__ == "__main__":
    sys.exit(main())
