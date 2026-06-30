"""Central model parameter policies for LLM tasks."""

import os
import re
from typing import Any, Dict, List

from news_pipeline.llm_schemas import LLM_ARTICLE_DRAFT_SCHEMA

from .types import LLMConfigError, LLMTaskPolicy


DEFAULT_MODEL_ENV = "LLM_DEFAULT_MODEL"


TASK_ALIASES = {
    "indonesia_fx_content": "fx_article_id",
    "japan_fx_content": "fx_article_id",
    "llm_article_draft_candidate": "fx_article_id",
}


def canonical_task_name(task_name: str) -> str:
    normalized = str(task_name or "").strip()
    return TASK_ALIASES.get(normalized, normalized)


def _schema_name(task_name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(task_name or "llm_task")).strip("_")
    return name or "llm_task"


def json_schema_response_format(task_name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _schema_name(task_name),
            "strict": True,
            "schema": schema,
        },
    }


def json_schema_chat_payload(
    task_name: str,
    *,
    model: str,
    messages: List[Dict[str, Any]],
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "response_format": json_schema_response_format(task_name, schema),
    }


def _default_model() -> str:
    return str(os.getenv(DEFAULT_MODEL_ENV, "") or os.getenv("OPENROUTER_DEFAULT_MODEL", "")).strip()


def _require_model(model: str, task_name: str) -> str:
    if not model:
        raise LLMConfigError(
            "LLM_DEFAULT_MODEL is required for real LLM tasks.",
            task_name=task_name,
            details={"env": DEFAULT_MODEL_ENV},
        )
    return model


def _base_policy(task_name: str, *, temperature: float, json_output: bool = False, json_schema: Dict[str, Any] = None) -> LLMTaskPolicy:
    model = _require_model(_default_model(), task_name)
    response_format = json_schema_response_format(task_name, json_schema) if json_schema else {"type": "json_object"} if json_output else None
    return LLMTaskPolicy(
        task_name=task_name,
        model=model,
        temperature=temperature,
        max_tokens=1800,
        top_p=1.0,
        response_format=response_format,
        stream=False,
        json_output=json_output,
        json_schema=json_schema,
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60") or 60),
        max_retries=min(int(os.getenv("LLM_MAX_RETRIES", "2") or 2), 2),
    )


def get_model_policy(task_name: str, overrides: Dict[str, Any] = None) -> LLMTaskPolicy:
    canonical = canonical_task_name(task_name)
    if canonical == "fx_article_id":
        policy = _base_policy(
            canonical,
            temperature=0.35,
            json_output=True,
            json_schema=LLM_ARTICLE_DRAFT_SCHEMA,
        )
    elif canonical == "rss_summary":
        policy = _base_policy(canonical, temperature=0.2, json_output=True)
    elif canonical == "market_alert":
        policy = _base_policy(canonical, temperature=0.1, json_output=True)
    elif canonical == "json_extract":
        policy = _base_policy(canonical, temperature=0.0, json_output=True)
    else:
        raise LLMConfigError(
            f"Unknown LLM task: {task_name}",
            task_name=task_name,
            details={"known_tasks": ["fx_article_id", "rss_summary", "market_alert", "json_extract"]},
        )
    return policy.with_overrides(dict(overrides or {}))
