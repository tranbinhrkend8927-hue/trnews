"""Compare template and LLM article draft candidates in dry-run mode."""

import argparse
import json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .article_drafts import build_article_draft_from_template, fetch_topic_for_draft
from .draft_comparison import compare_draft_candidates, json_safe
from .draft_quality import evaluate_draft_quality
from .fetch_forex_news_json import get_postgres_dsn
from .generate_llm_article_draft import build_gateway
from .llm_article_drafts import generate_llm_article_draft_candidate
from .safety_validation import apply_fact_check_status, validate_financial_safety
from .source_grounding import build_source_bundle, fetch_source_news_for_topic


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare template and LLM article draft candidates without writing to DB.")
    parser.add_argument("--topic-id", type=int, required=True, help="content_topics.id to compare.")
    parser.add_argument("--provider", choices=["mock", "openrouter"], default="mock", help="LLM provider. Default is mock.")
    parser.add_argument("--template", help="Optional template hint/override.")
    parser.add_argument("--dry-run", action="store_true", help="Required. P11 never writes generated articles.")
    return parser


def _error(error_type: str, message: str, *, retryable: bool = False) -> Dict[str, Any]:
    return {"type": error_type, "message": message, "retryable": bool(retryable)}


def _empty_result(topic_id: int, provider: str, errors: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    errors = errors or []
    return json_safe(
        {
            "success": not errors,
            "topic_id": topic_id,
            "dry_run": True,
            "provider": provider,
            "source_bundle": {},
            "template": {"draft": {}, "safety_result": {}, "quality_result": {}, "errors": []},
            "llm": {"llm_result": {}, "draft_candidate": {}, "safety_result": {}, "quality_result": {}, "errors": []},
            "comparison_result": {},
            "summary": {
                "would_write_db": False,
                "would_publish": False,
                "recommended_candidate": None,
            },
            "errors": errors,
        }
    )


def build_result(
    *,
    topic_id: int,
    provider: str,
    source_bundle: Dict[str, Any],
    template_section: Dict[str, Any],
    llm_section: Dict[str, Any],
    comparison_result: Dict[str, Any],
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    errors = errors or []
    return json_safe(
        {
            "success": not errors and bool(comparison_result),
            "topic_id": topic_id,
            "dry_run": True,
            "provider": provider,
            "source_bundle": source_bundle or {},
            "template": template_section,
            "llm": llm_section,
            "comparison_result": comparison_result or {},
            "summary": {
                "would_write_db": False,
                "would_publish": False,
                "recommended_candidate": (comparison_result or {}).get("recommendation"),
            },
            "errors": errors,
        }
    )


def build_template_section(topic: Dict[str, Any], source_bundle: Dict[str, Any], template: Optional[str] = None) -> Dict[str, Any]:
    draft_result = build_article_draft_from_template(topic, template=template, source_bundle=source_bundle)
    if not draft_result.get("success"):
        return json_safe({"draft": {}, "safety_result": {}, "quality_result": {}, "errors": [draft_result.get("error")]})
    draft = draft_result["draft"]
    safety_result = validate_financial_safety(draft)
    draft = apply_fact_check_status(draft, safety_result)
    draft["status"] = "pending_review"
    draft["published_at"] = None
    quality_result = evaluate_draft_quality(draft, source_bundle=source_bundle, safety_result=safety_result)
    return json_safe({"draft": draft, "safety_result": safety_result, "quality_result": quality_result, "errors": []})


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.dry_run:
        result = _empty_result(
            args.topic_id,
            args.provider,
            errors=[_error("dry_run_required", "P11 only supports --dry-run and never writes to the database.", retryable=False)],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    try:
        dsn = get_postgres_dsn()
        topic = fetch_topic_for_draft(dsn, args.topic_id)
        if not topic:
            result = _empty_result(
                args.topic_id,
                args.provider,
                errors=[_error("topic_not_found", f"Topic not found: {args.topic_id}", retryable=False)],
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        source_news_result = fetch_source_news_for_topic(dsn, topic)
        source_bundle = build_source_bundle(topic, source_news_result)
        template_section = build_template_section(topic, source_bundle, template=args.template)
        gateway = build_gateway(args.provider, source_bundle)
        llm_result = generate_llm_article_draft_candidate(
            topic,
            source_bundle,
            gateway,
            template_hint=args.template,
            provider_label=args.provider,
        )
        llm_section = {
            "llm_result": llm_result.get("llm_result") or {},
            "draft_candidate": llm_result.get("draft_candidate") or {},
            "safety_result": llm_result.get("safety_result") or {},
            "quality_result": llm_result.get("quality_result") or {},
            "errors": llm_result.get("errors") or [],
        }
        comparison_result = compare_draft_candidates(
            template_section.get("draft") or {},
            llm_section.get("draft_candidate") or {},
            source_bundle=source_bundle,
            template_safety_result=template_section.get("safety_result") or None,
            template_quality_result=template_section.get("quality_result") or None,
            llm_safety_result=llm_section.get("safety_result") or None,
            llm_quality_result=llm_section.get("quality_result") or None,
        )
        result = build_result(
            topic_id=args.topic_id,
            provider=args.provider,
            source_bundle=source_bundle,
            template_section=template_section,
            llm_section=llm_section,
            comparison_result=comparison_result,
        )
    except Exception as exc:
        result = _empty_result(
            args.topic_id,
            args.provider,
            errors=[_error("compare_article_drafts_error", str(exc), retryable=False)],
        )

    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
