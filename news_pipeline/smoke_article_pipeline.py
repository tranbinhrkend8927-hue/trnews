"""Smoke runner for the article candidate and review pipeline."""

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .article_drafts import fetch_topic_for_draft
from .article_review import (
    build_article_review_report,
    fetch_article_for_review,
    fetch_article_sources_for_review,
    validate_review_decision,
)
from .fetch_forex_news_json import get_postgres_dsn
from .generate_llm_article_draft import build_gateway
from .selected_article_draft import (
    build_selected_candidate_save_payload,
    save_selected_candidate_to_postgres,
)
from .source_grounding import build_source_bundle, fetch_source_news_for_topic


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _error(error_type: str, message: str, *, retryable: bool = False) -> Dict[str, Any]:
    return {"type": error_type, "message": message, "retryable": bool(retryable)}


def _step(name: str, success: bool, summary: Optional[Dict[str, Any]] = None, errors: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return json_safe({"name": name, "success": bool(success), "summary": summary or {}, "errors": errors or []})


def _result(
    *,
    success: bool,
    mode: str,
    topic_id: Optional[int] = None,
    article_id: Optional[int] = None,
    candidate_type: Optional[str] = None,
    provider: str = "mock",
    steps: Optional[List[Dict[str, Any]]] = None,
    result: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return json_safe(
        {
            "success": bool(success),
            "mode": mode,
            "topic_id": topic_id,
            "article_id": article_id,
            "candidate_type": candidate_type,
            "provider": provider,
            "steps": steps or [],
            "result": result or {},
            "summary": summary
            or {
                "would_write_db": False,
                "would_publish": False,
                "status_after_save": "pending_review",
            },
            "errors": errors or [],
        }
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run article pipeline smoke checks without publishing.")
    parser.add_argument("--topic-id", type=int, help="content_topics.id for selected candidate smoke flow.")
    parser.add_argument("--article-id", type=int, help="generated_articles.id for review smoke flow.")
    parser.add_argument("--candidate", choices=["template", "llm"], help="Explicit candidate for topic flow.")
    parser.add_argument("--provider", choices=["mock", "openrouter"], default="mock", help="LLM provider for candidate=llm. Default is mock.")
    parser.add_argument("--template", help="Optional template hint.")
    parser.add_argument("--language", default="id", help="Language profile for candidate=llm.")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing. Required for review decision.")
    parser.add_argument("--save-selected-draft", action="store_true", help="Persist selected draft as pending_review.")
    parser.add_argument("--review-report", action="store_true", help="Build review report without writing.")
    parser.add_argument("--review-decision", choices=["approved", "rejected", "needs_changes"], help="Validate review decision in dry-run mode.")
    parser.add_argument("--reviewer", help="Reviewer name for decision dry-run.")
    parser.add_argument("--notes", help="Reviewer notes for decision dry-run.")
    return parser


def _validate_args(args: argparse.Namespace) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    topic_mode = args.topic_id is not None
    review_mode = args.article_id is not None
    if topic_mode and review_mode:
        errors.append(_error("ambiguous_mode", "Use either --topic-id or --article-id, not both."))
    if not topic_mode and not review_mode:
        errors.append(_error("missing_mode", "Use --topic-id for candidate smoke or --article-id for review smoke."))
    if args.dry_run and args.save_selected_draft:
        errors.append(_error("invalid_mode", "--dry-run and --save-selected-draft cannot be used together."))
    if topic_mode:
        if args.review_report or args.review_decision:
            errors.append(_error("invalid_topic_mode", "Review options require --article-id."))
        if not args.candidate:
            errors.append(_error("candidate_required", "--candidate template or --candidate llm is required for topic smoke."))
    if review_mode:
        if args.candidate or args.save_selected_draft:
            errors.append(_error("invalid_review_mode", "Candidate save options require --topic-id."))
        if args.review_report and args.review_decision:
            errors.append(_error("ambiguous_review_mode", "Use --review-report or --review-decision, not both."))
        if not args.review_report and not args.review_decision:
            errors.append(_error("review_mode_required", "Use --review-report or --review-decision with --article-id."))
        if args.review_decision and not args.dry_run:
            errors.append(_error("review_decision_dry_run_required", "P13 review decision smoke only supports --dry-run."))
    return errors


def run_topic_pipeline(args: argparse.Namespace, dsn: str) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    mode = "topic_pipeline_save_selected_draft" if args.save_selected_draft else "topic_pipeline_dry_run"
    dry_run = not args.save_selected_draft

    topic = fetch_topic_for_draft(dsn, args.topic_id)
    steps.append(_step("fetch_topic", bool(topic), {"topic_id": args.topic_id}))
    if not topic:
        return _result(
            success=False,
            mode=mode,
            topic_id=args.topic_id,
            candidate_type=args.candidate,
            provider=args.provider,
            steps=steps,
            errors=[_error("topic_not_found", f"Topic not found: {args.topic_id}")],
        )

    source_news_result = fetch_source_news_for_topic(dsn, topic)
    source_bundle = build_source_bundle(topic, source_news_result)
    steps.append(
        _step(
            "build_source_bundle",
            True,
            {
                "source_count": len(source_bundle.get("sources") or []),
                "missing_source_news_ids": source_bundle.get("missing_source_news_ids") or [],
            },
        )
    )

    gateway = build_gateway(args.provider, source_bundle) if args.candidate == "llm" else None
    selected_payload = build_selected_candidate_save_payload(
        topic,
        source_bundle,
        args.candidate,
        provider=args.provider,
        template_hint=args.template,
        language=args.language,
        gateway=gateway,
    )
    steps.append(
        _step(
            "build_selected_candidate",
            bool(selected_payload.get("selected_draft")) and not selected_payload.get("errors"),
            {
                "candidate_type": args.candidate,
                "llm_status": (selected_payload.get("comparison_result") or {}).get("llm_status"),
            },
            selected_payload.get("errors") or [],
        )
    )
    save_validation = selected_payload.get("save_validation") or {}
    steps.append(
        _step(
            "save_validation",
            bool(save_validation.get("can_save")),
            {
                "can_save": bool(save_validation.get("can_save")),
                "blocker_count": len(save_validation.get("blockers") or []),
                "warning_count": len(save_validation.get("warnings") or []),
            },
            save_validation.get("blockers") or [],
        )
    )

    if not selected_payload.get("success"):
        return _result(
            success=False,
            mode=mode,
            topic_id=args.topic_id,
            candidate_type=args.candidate,
            provider=args.provider,
            steps=steps,
            result=selected_payload,
            errors=selected_payload.get("errors") or [_error("selected_payload_failed", "Selected candidate payload failed.")],
        )

    save_result = {}
    if args.save_selected_draft:
        save_result = save_selected_candidate_to_postgres(dsn, selected_payload, dry_run=False)
        status = (save_result.get("selected_draft") or {}).get("status")
        steps.append(
            _step(
                "save_selected_draft",
                bool(save_result.get("success")) and status == "pending_review",
                {
                    "article_id": save_result.get("article_id"),
                    "status": status,
                    "inserted": (save_result.get("summary") or {}).get("inserted", 0),
                    "skipped": (save_result.get("summary") or {}).get("skipped", 0),
                },
                save_result.get("errors") or [],
            )
        )

    final_result = {"selected_payload": selected_payload, "save_result": save_result}
    errors = save_result.get("errors") if save_result else []
    return _result(
        success=not errors and bool(selected_payload.get("success")) and (not save_result or bool(save_result.get("success"))),
        mode=mode,
        topic_id=args.topic_id,
        article_id=save_result.get("article_id") if save_result else None,
        candidate_type=args.candidate,
        provider=args.provider,
        steps=steps,
        result=final_result,
        summary={
            "would_write_db": bool(args.save_selected_draft),
            "would_publish": False,
            "status_after_save": "pending_review",
            "inserted": (save_result.get("summary") or {}).get("inserted", 0) if save_result else 0,
            "skipped": (save_result.get("summary") or {}).get("skipped", 0) if save_result else 0,
            "article_sources_inserted": (save_result.get("summary") or {}).get("article_sources_inserted", 0) if save_result else 0,
        },
        errors=errors or [],
    )


def run_review_pipeline(args: argparse.Namespace, dsn: str) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    mode = "review_decision_dry_run" if args.review_decision else "review_report"
    article = fetch_article_for_review(dsn, args.article_id)
    steps.append(_step("fetch_article", bool(article), {"article_id": args.article_id}))
    if not article:
        return _result(
            success=False,
            mode=mode,
            article_id=args.article_id,
            steps=steps,
            errors=[_error("article_not_found", f"Article not found: {args.article_id}")],
        )

    article_sources = fetch_article_sources_for_review(dsn, args.article_id)
    steps.append(_step("fetch_article_sources", True, {"source_count": len(article_sources or [])}))
    report = build_article_review_report(article, article_sources)
    steps.append(
        _step(
            "build_review_report",
            True,
            {
                "can_approve": bool(report.get("can_approve")),
                "approval_blocker_count": len(report.get("approval_blockers") or []),
            },
        )
    )

    if args.review_report:
        return _result(
            success=True,
            mode=mode,
            article_id=args.article_id,
            steps=steps,
            result={"review_report": report},
        )

    validation = validate_review_decision(report, args.review_decision, reviewer_notes=args.notes)
    steps.append(
        _step(
            "validate_review_decision",
            bool(validation.get("valid")),
            {
                "decision": args.review_decision,
                "new_status": validation.get("new_status"),
                "would_insert_review": False,
                "would_update_article": False,
            },
            validation.get("errors") or [],
        )
    )
    return _result(
        success=bool(validation.get("valid")),
        mode=mode,
        article_id=args.article_id,
        steps=steps,
        result={"review_report": report, "validation": validation, "reviewer": args.reviewer, "notes": args.notes},
        errors=validation.get("errors") or [],
    )


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    arg_errors = _validate_args(args)
    if arg_errors:
        result = _result(
            success=False,
            mode="argument_error",
            topic_id=args.topic_id,
            article_id=args.article_id,
            candidate_type=args.candidate,
            provider=args.provider,
            errors=arg_errors,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    try:
        dsn = get_postgres_dsn()
        if args.topic_id is not None:
            result = run_topic_pipeline(args, dsn)
        else:
            result = run_review_pipeline(args, dsn)
    except Exception as exc:
        result = _result(
            success=False,
            mode="smoke_pipeline_error",
            topic_id=args.topic_id,
            article_id=args.article_id,
            candidate_type=args.candidate,
            provider=args.provider,
            errors=[_error("smoke_pipeline_failed", str(exc))],
        )

    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
