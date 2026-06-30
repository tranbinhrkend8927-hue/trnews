"""Dry-run LLM article draft candidate generation."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from .draft_quality import evaluate_draft_quality
from .language_profiles import get_language_profile
from .llm_schemas import LLM_ARTICLE_DRAFT_SCHEMA
from .safety_validation import apply_fact_check_status, validate_financial_safety

from src.llm.build_messages import build_messages
from src.llm.run_task import run_llm_task
from src.llm.types import ALLOWED_OVERRIDE_FIELDS, LLMTaskError


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


def _base_result(
    *,
    topic_id: Any,
    language: str,
    provider: str,
    source_bundle: Optional[Dict[str, Any]] = None,
    llm_result: Optional[Dict[str, Any]] = None,
    draft_candidate: Optional[Dict[str, Any]] = None,
    safety_result: Optional[Dict[str, Any]] = None,
    quality_result: Optional[Dict[str, Any]] = None,
    errors: Optional[list] = None,
) -> Dict[str, Any]:
    errors = errors or []
    return json_safe(
        {
            "success": not errors,
            "topic_id": topic_id,
            "language": language,
            "provider": provider,
            "dry_run": True,
            "source_bundle": source_bundle or {},
            "llm_result": llm_result or {},
            "draft_candidate": draft_candidate or {},
            "safety_result": safety_result or {},
            "quality_result": quality_result or {},
            "summary": {
                "would_write_db": False,
                "would_publish": False,
                "llm_called": bool(llm_result),
                "candidate_generated": bool(draft_candidate),
            },
            "errors": errors,
        }
    )


def _provider_name(llm_runner: Any, model_config: Optional[Dict[str, Any]]) -> str:
    model_config = model_config or {}
    provider = getattr(llm_runner, "provider", None)
    return str(model_config.get("provider") or getattr(provider, "provider_name", None) or "openai-compatible")


def _task_error_result(exc: LLMTaskError) -> Dict[str, Any]:
    return {
        "success": False,
        "provider": "openai-compatible",
        "model": None,
        "task_name": exc.task_name,
        "prompt_version": exc.prompt_version,
        "output": None,
        "raw_response": {},
        "usage": {},
        "latency_ms": 0,
        "error": exc.to_dict(),
    }


def _legacy_gateway_runner(gateway: Any, task_name: str, input_data: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    messages_result = build_messages(task_name, input_data)
    return gateway.generate_json(
        messages_result.task_name,
        messages_result.messages,
        LLM_ARTICLE_DRAFT_SCHEMA,
        config=overrides or {},
    )


def _run_task(
    llm_runner: Any,
    task_name: str,
    input_data: Dict[str, Any],
    overrides: Optional[Dict[str, Any]],
    legacy_provider_label: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        if llm_runner is not None and hasattr(llm_runner, "generate_json"):
            legacy_overrides = dict(overrides or {})
            if legacy_provider_label:
                legacy_overrides.setdefault("provider", legacy_provider_label)
            return _legacy_gateway_runner(llm_runner, task_name, input_data, legacy_overrides)
        runner: Callable[..., Dict[str, Any]] = llm_runner or run_llm_task
        safe_overrides = {key: value for key, value in dict(overrides or {}).items() if key in ALLOWED_OVERRIDE_FIELDS}
        return runner(task_name, input_data, overrides=safe_overrides)
    except LLMTaskError as exc:
        return _task_error_result(exc)


def _normalize_candidate(
    llm_output: Dict[str, Any],
    *,
    topic: Dict[str, Any],
    source_bundle: Dict[str, Any],
    language: str,
) -> Dict[str, Any]:
    output = json_safe(llm_output or {})
    candidate = {
        "topic_id": topic.get("id"),
        "symbol": str(topic.get("symbol") or source_bundle.get("symbol") or "").upper(),
        "title": output.get("title") or "",
        "slug": output.get("slug") or "",
        "summary": output.get("summary") or "",
        "body": output.get("body") or "",
        "seo_title": output.get("seo_title") or "",
        "seo_description": output.get("seo_description") or "",
        "faq": output.get("faq") if isinstance(output.get("faq"), list) else [],
        "sources_used": output.get("sources_used") if isinstance(output.get("sources_used"), list) else [],
        "risk_disclaimer": output.get("risk_disclaimer") or "",
        "uncertain_claims": output.get("uncertain_claims") if isinstance(output.get("uncertain_claims"), list) else [],
        "language": language,
        "status": "pending_review",
        "fact_check_status": "pending",
        "published_at": None,
        "risk_disclaimer_included": True,
        "sources_json": source_bundle,
    }
    return json_safe(candidate)


def generate_llm_article_draft_candidate(
    topic: Dict[str, Any],
    source_bundle: Dict[str, Any],
    llm_runner: Any = None,
    language: str = "id",
    template_hint: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
    provider_label: Optional[str] = None,
    model_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    topic = json_safe(topic or {})
    source_bundle = json_safe(source_bundle or {})
    runtime_overrides = dict(overrides if overrides is not None else model_config or {})
    provider = str(provider_label or _provider_name(llm_runner, runtime_overrides))
    topic_id = topic.get("id") or source_bundle.get("topic_id")

    if not source_bundle.get("sources"):
        return _base_result(
            topic_id=topic_id,
            language=language,
            provider=provider,
            source_bundle=source_bundle,
            errors=[_error("missing_sources", "source_bundle.sources is required before calling the LLM.", retryable=False)],
        )

    profile_result = get_language_profile(language)
    if not profile_result.get("success"):
        return _base_result(
            topic_id=topic_id,
            language=language,
            provider=provider,
            source_bundle=source_bundle,
            errors=[profile_result.get("error")],
        )

    input_data = {
        "topic": topic,
        "source_bundle": source_bundle,
        "language_profile": profile_result["profile"],
        "template_hint": template_hint,
    }
    llm_result = _run_task(
        llm_runner,
        "fx_article_id",
        input_data,
        runtime_overrides,
        legacy_provider_label=provider,
    )
    provider = str(llm_result.get("provider") or provider)
    if not llm_result.get("success"):
        return _base_result(
            topic_id=topic_id,
            language=language,
            provider=provider,
            source_bundle=source_bundle,
            llm_result=llm_result,
            errors=[llm_result.get("error")],
        )

    draft_candidate = _normalize_candidate(
        llm_result.get("output") or {},
        topic=topic,
        source_bundle=source_bundle,
        language=language,
    )
    safety_result = validate_financial_safety(draft_candidate)
    draft_candidate = apply_fact_check_status(draft_candidate, safety_result)
    draft_candidate["status"] = "pending_review"
    draft_candidate["published_at"] = None
    quality_result = evaluate_draft_quality(
        draft_candidate,
        source_bundle=source_bundle,
        safety_result=safety_result,
    )

    return _base_result(
        topic_id=topic_id,
        language=language,
        provider=provider,
        source_bundle=source_bundle,
        llm_result=llm_result,
        draft_candidate=draft_candidate,
        safety_result=safety_result,
        quality_result=quality_result,
    )
