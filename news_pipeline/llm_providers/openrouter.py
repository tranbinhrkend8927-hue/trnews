"""Compatibility OpenRouter provider backed by the unified LLM client."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from ..llm_config import load_openrouter_config
from ..llm_gateway import llm_error
from src.llm.client import OpenAICompatibleClient
from src.llm.model_policies import json_schema_chat_payload
from src.llm.types import LLMTaskError


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
        return {
            str(key): json_safe(item)
            for key, item in value.items()
            if str(key).lower() not in {"authorization", "api_key"}
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _provider_result(
    *,
    success: bool,
    model: str,
    task_name: str,
    content: Any = None,
    raw_response: Any = None,
    usage: Optional[Dict[str, Any]] = None,
    latency_ms: int = 0,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return json_safe(
        {
            "success": bool(success),
            "provider": "openrouter",
            "model": model,
            "task_name": task_name,
            "content": content,
            "raw_response": raw_response,
            "usage": usage or {},
            "latency_ms": latency_ms,
            "error": error,
        }
    )


class OpenRouterProvider:
    provider_name = "openrouter"
    handles_retries = True

    def __init__(self, *, session: Optional[Any] = None, endpoint: Optional[str] = None):
        self.session = session or requests
        self.endpoint = endpoint
        self.model = ""

    def _payload(self, task_name: str, messages: List[Dict[str, Any]], schema: Dict[str, Any], model: str) -> Dict[str, Any]:
        return json_schema_chat_payload(task_name, model=model, messages=messages, schema=schema)

    def generate(
        self,
        task_name: str,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        loaded = load_openrouter_config(overrides=config or {})
        config_data = loaded.get("config") or {}
        model = str(config_data.get("model") or "")
        self.model = model
        if not loaded.get("success"):
            first_error = (loaded.get("errors") or [llm_error("config_error", "OpenRouter config is invalid.")])[0]
            return _provider_result(
                success=False,
                model=model,
                task_name=task_name,
                latency_ms=0,
                error=llm_error("config_error", first_error.get("message", "OpenRouter config is invalid."), retryable=False),
            )

        timeout_seconds = config_data.get("timeout_seconds") or 60
        max_retries = min(int(config_data.get("max_retries") or 0), 2)
        base_url = self.endpoint or str(config_data.get("base_url") or "")
        try:
            payload = self._payload(task_name, messages, schema, model)
        except Exception as exc:
            return _provider_result(
                success=False,
                model=model,
                task_name=task_name,
                latency_ms=0,
                error=llm_error("api_error", f"Failed to build structured output request: {exc}", retryable=False),
            )

        client = OpenAICompatibleClient(session=self.session, base_url=base_url)
        try:
            raw_response = client.create_chat_completion(
                payload,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                task_name=task_name,
            )
            content = raw_response["choices"][0]["message"]["content"]
        except LLMTaskError as exc:
            error = exc.to_dict()
            return _provider_result(
                success=False,
                model=model,
                task_name=task_name,
                raw_response=error.get("details", {}).get("response"),
                latency_ms=0,
                error=llm_error(error.get("type") or "api_error", error.get("message") or str(exc), retryable=bool(error.get("retryable"))),
            )
        except (KeyError, IndexError, TypeError):
            return _provider_result(
                success=False,
                model=model,
                task_name=task_name,
                raw_response=raw_response,
                latency_ms=(raw_response.get("_client") or {}).get("latency_ms", 0) if isinstance(raw_response, dict) else 0,
                error=llm_error("invalid_json", "OpenRouter response does not contain choices[0].message.content.", retryable=False),
            )

        latency_ms = (raw_response.get("_client") or {}).get("latency_ms", 0) if isinstance(raw_response, dict) else 0
        raw_response = {key: value for key, value in raw_response.items() if key != "_client"}
        usage = raw_response.get("usage") if isinstance(raw_response, dict) else {}
        if isinstance(raw_response, dict):
            return _provider_result(
                success=True,
                model=model,
                task_name=task_name,
                content=content,
                raw_response=raw_response,
                usage=usage,
                latency_ms=latency_ms,
                error=None,
            )

        return _provider_result(
            success=False,
            model=model,
            task_name=task_name,
            latency_ms=latency_ms,
            error=llm_error("unknown_error", "OpenRouter request did not complete.", retryable=False),
        )
