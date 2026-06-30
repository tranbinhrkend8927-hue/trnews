"""Unified LLM task execution entrypoint."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from news_pipeline.llm_schemas import validate_json_schema

from .build_messages import build_messages
from .client import OpenAICompatibleClient
from .model_policies import get_model_policy
from .types import LLMOutputSchemaError, LLMTaskError
from .validators.json_parser import parse_llm_json


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items() if str(key).lower() not in {"authorization", "api_key"}}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _payload_from_policy(policy: Any, messages: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": policy.model,
        "messages": messages,
        "temperature": policy.temperature,
        "stream": bool(policy.stream),
    }
    if policy.max_tokens is not None:
        payload["max_tokens"] = policy.max_tokens
    if policy.top_p is not None:
        payload["top_p"] = policy.top_p
    if policy.response_format is not None:
        payload["response_format"] = policy.response_format
    return payload


def _extract_content(raw_response: Dict[str, Any], *, task_name: str, prompt_version: str) -> Any:
    try:
        return raw_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMTaskError(
            "OpenAI-compatible response does not contain choices[0].message.content.",
            task_name=task_name,
            prompt_version=prompt_version,
            error_type="invalid_response",
            retryable=False,
            details={"raw_response": json_safe(raw_response)},
        ) from exc


def run_llm_task(task_name: str, input_data: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None, *, client: Optional[OpenAICompatibleClient] = None) -> Dict[str, Any]:
    """Run one configured LLM task.

    Business code should pass only the task name, task input, and optional safe
    generation overrides. Endpoint, key, prompts, and model defaults are owned
    by this module and its siblings.
    """

    messages_result = build_messages(task_name, input_data or {})
    policy = get_model_policy(messages_result.task_name, overrides or {})
    payload = _payload_from_policy(policy, messages_result.messages)
    client = client or OpenAICompatibleClient()
    raw_response = client.create_chat_completion(
        payload,
        timeout_seconds=policy.timeout_seconds,
        max_retries=policy.max_retries,
        task_name=messages_result.task_name,
        prompt_version=messages_result.prompt_version,
    )
    content = _extract_content(raw_response, task_name=messages_result.task_name, prompt_version=messages_result.prompt_version)
    if policy.json_output or policy.response_format:
        output = parse_llm_json(
            content,
            task_name=messages_result.task_name,
            prompt_version=messages_result.prompt_version,
        )
        if policy.json_schema:
            validation = validate_json_schema(output, policy.json_schema)
            if not validation.get("valid"):
                raise LLMOutputSchemaError(
                    "LLM JSON output failed schema validation.",
                    task_name=messages_result.task_name,
                    prompt_version=messages_result.prompt_version,
                    details={"validation_errors": validation.get("errors") or []},
                )
    else:
        output = content

    client_meta = raw_response.get("_client") if isinstance(raw_response, dict) else {}
    return json_safe(
        {
            "success": True,
            "provider": "openai-compatible",
            "model": policy.model,
            "task_name": messages_result.task_name,
            "prompt_version": messages_result.prompt_version,
            "output": output,
            "raw_response": {key: value for key, value in raw_response.items() if key != "_client"},
            "usage": raw_response.get("usage") if isinstance(raw_response, dict) else {},
            "latency_ms": (client_meta or {}).get("latency_ms", 0),
            "error": None,
        }
    )
