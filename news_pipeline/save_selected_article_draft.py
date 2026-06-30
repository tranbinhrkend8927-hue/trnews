"""Save an explicitly selected article draft candidate as pending_review."""

import argparse
import json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .article_drafts import fetch_topic_for_draft
from .fetch_forex_news_json import get_postgres_dsn
from .generate_llm_article_draft import build_gateway
from .selected_article_draft import (
    build_selected_candidate_save_payload,
    json_safe,
    save_selected_candidate_to_postgres,
)
from .source_grounding import build_source_bundle, fetch_source_news_for_topic


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Save an explicitly selected draft candidate as pending_review.")
    parser.add_argument("--topic-id", type=int, required=True, help="content_topics.id to use.")
    parser.add_argument("--candidate", help="Explicit candidate to save: template or llm.")
    parser.add_argument("--provider", choices=["mock", "openrouter"], default="mock", help="LLM provider for candidate=llm. Default is mock.")
    parser.add_argument("--language", default="id", help="Language profile for candidate=llm.")
    parser.add_argument("--template", help="Optional template hint/override.")
    parser.add_argument("--dry-run", action="store_true", help="Build payload without writing to DB.")
    parser.add_argument("--save-db", action="store_true", help="Write selected candidate to generated_articles and article_sources.")
    return parser


def _error(error_type: str, message: str, *, retryable: bool = False) -> Dict[str, Any]:
    return {"type": error_type, "message": message, "retryable": bool(retryable)}


def _result(
    *,
    topic_id: int,
    candidate_type: Optional[str],
    provider: str,
    dry_run: bool,
    source_bundle: Optional[Dict[str, Any]] = None,
    selected_payload: Optional[Dict[str, Any]] = None,
    save_result: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    errors = errors or []
    selected_payload = selected_payload or {}
    save_result = save_result or {}
    return json_safe(
        {
            "success": not errors and (not save_result or bool(save_result.get("success"))),
            "topic_id": topic_id,
            "candidate_type": candidate_type,
            "provider": provider,
            "dry_run": bool(dry_run),
            "source_bundle": source_bundle or selected_payload.get("source_bundle") or {},
            "selected": {
                "draft": selected_payload.get("selected_draft") or {},
                "safety_result": selected_payload.get("safety_result") or {},
                "quality_result": selected_payload.get("quality_result") or {},
            },
            "comparison_result": selected_payload.get("comparison_result") or {},
            "save_validation": selected_payload.get("save_validation") or {},
            "database": {"save": save_result} if save_result else {},
            "summary": {
                "would_write_db": bool(selected_payload.get("save_validation", {}).get("can_save")),
                "would_publish": False,
                "status_after_save": "pending_review",
                "inserted": (save_result.get("summary") or {}).get("inserted", 0),
                "skipped": (save_result.get("summary") or {}).get("skipped", 0),
                "article_sources_inserted": (save_result.get("summary") or {}).get("article_sources_inserted", 0),
                "article_sources_failed": (save_result.get("summary") or {}).get("article_sources_failed", 0),
            },
            "errors": errors or selected_payload.get("errors") or save_result.get("errors") or [],
        }
    )


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    candidate_type = str(args.candidate or "").strip()

    errors: List[Dict[str, Any]] = []
    if not candidate_type:
        errors.append(_error("candidate_required", "--candidate template or --candidate llm is required."))
    elif candidate_type not in {"template", "llm"}:
        errors.append(_error("invalid_candidate", "candidate must be template or llm."))
    if args.dry_run and args.save_db:
        errors.append(_error("invalid_mode", "--dry-run and --save-db cannot be used together."))
    if not args.dry_run and not args.save_db:
        errors.append(_error("mode_required", "Either --dry-run or --save-db is required."))

    if errors:
        result = _result(
            topic_id=args.topic_id,
            candidate_type=candidate_type or None,
            provider=args.provider,
            dry_run=bool(args.dry_run),
            errors=errors,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    try:
        dsn = get_postgres_dsn()
        topic = fetch_topic_for_draft(dsn, args.topic_id)
        if not topic:
            result = _result(
                topic_id=args.topic_id,
                candidate_type=candidate_type,
                provider=args.provider,
                dry_run=args.dry_run,
                errors=[_error("topic_not_found", f"Topic not found: {args.topic_id}")],
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        source_news_result = fetch_source_news_for_topic(dsn, topic)
        source_bundle = build_source_bundle(topic, source_news_result)
        gateway = build_gateway(args.provider, source_bundle) if candidate_type == "llm" else None
        selected_payload = build_selected_candidate_save_payload(
            topic,
            source_bundle,
            candidate_type,
            provider=args.provider,
            template_hint=args.template,
            language=args.language,
            gateway=gateway,
        )
        if not selected_payload.get("success"):
            result = _result(
                topic_id=args.topic_id,
                candidate_type=candidate_type,
                provider=args.provider,
                dry_run=args.dry_run,
                source_bundle=source_bundle,
                selected_payload=selected_payload,
                errors=selected_payload.get("errors") or [_error("selected_payload_failed", "Selected candidate cannot be saved.")],
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        save_result = save_selected_candidate_to_postgres(dsn, selected_payload, dry_run=args.dry_run)
        result = _result(
            topic_id=args.topic_id,
            candidate_type=candidate_type,
            provider=args.provider,
            dry_run=args.dry_run,
            source_bundle=source_bundle,
            selected_payload=selected_payload,
            save_result=save_result,
            errors=save_result.get("errors") or [],
        )
    except Exception as exc:
        result = _result(
            topic_id=args.topic_id,
            candidate_type=candidate_type,
            provider=args.provider,
            dry_run=args.dry_run,
            errors=[_error("save_selected_article_draft_error", str(exc))],
        )

    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
