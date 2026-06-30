"""OpenRouter provider for the provider-agnostic LLM gateway."""

import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from llm_config import get_openrouter_api_key, load_openrouter_config
from llm_gateway import llm_error


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


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


def _latency_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def _schema_name(task_name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(task_name or "llm_task")).strip("_")
    return name or "llm_task"


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


def _response_error(response: Any, model: str, task_name: str, latency_ms: int, retryable: bool) -> Dict[str, Any]:
    status_code = getattr(response, "status_code", None)
    raw_response = None
    message = f"OpenRouter API error: HTTP {status_code}"
    try:
        raw_response = response.json()
        if isinstance(raw_response, dict):
            provider_message = raw_response.get("error", {}).get("message") if isinstance(raw_response.get("error"), dict) else None
            if provider_message:
                message = f"OpenRouter API error: HTTP {status_code}: {provider_message}"
    except Exception:
        raw_response = {"status_code": status_code, "text": str(getattr(response, "text", ""))[:1000]}
    return _provider_result(
        success=False,
        model=model,
        task_name=task_name,
        raw_response=raw_response,
        latency_ms=latency_ms,
        error=llm_error("api_error", message, retryable=retryable),
    )


class OpenRouterProvider:
    provider_name = "openrouter"
    handles_retries = True

    def __init__(self, *, session: Optional[Any] = None, endpoint: str = OPENROUTER_CHAT_COMPLETIONS_URL):
        self.session = session or requests
        self.endpoint = endpoint
        self.model = ""

    def _payload(self, task_name: str, messages: List[Dict[str, Any]], schema: Dict[str, Any], model: str) -> Dict[str, Any]:
        return {
            "model": model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(task_name),
                    "strict": True,
                    "schema": schema,
                },
            },
        }

    def generate(
        self,
        task_name: str,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        started_at = time.monotonic()
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
                latency_ms=_latency_ms(started_at),
                error=llm_error("config_error", first_error.get("message", "OpenRouter config is invalid."), retryable=False),
            )

        api_key = get_openrouter_api_key(overrides=config or {})
        timeout_seconds = config_data.get("timeout_seconds") or 60
        max_retries = min(int(config_data.get("max_retries") or 0), 2)
        try:
            payload = self._payload(task_name, messages, schema, model)
        except Exception as exc:
            return _provider_result(
                success=False,
                model=model,
                task_name=task_name,
                latency_ms=_latency_ms(started_at),
                error=llm_error("api_error", f"Failed to build structured output request: {exc}", retryable=False),
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        attempts = 0
        while attempts <= max_retries:
            attempts += 1
            try:
                response = self.session.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=timeout_seconds,
                )
            except requests.exceptions.Timeout as exc:
                if attempts <= max_retries:
                    continue
                return _provider_result(
                    success=False,
                    model=model,
                    task_name=task_name,
                    latency_ms=_latency_ms(started_at),
                    error=llm_error("timeout", str(exc), retryable=True),
                )
            except requests.exceptions.RequestException as exc:
                return _provider_result(
                    success=False,
                    model=model,
                    task_name=task_name,
                    latency_ms=_latency_ms(started_at),
                    error=llm_error("api_error", str(exc), retryable=False),
                )

            status_code = getattr(response, "status_code", 200)
            if status_code >= 400:
                retryable = status_code == 429 or status_code >= 500
                if retryable and attempts <= max_retries:
                    continue
                return _response_error(response, model, task_name, _latency_ms(started_at), retryable)

            try:
                raw_response = response.json()
            except Exception:
                return _provider_result(
                    success=False,
                    model=model,
                    task_name=task_name,
                    raw_response={"text": str(getattr(response, "text", ""))[:1000]},
                    latency_ms=_latency_ms(started_at),
                    error=llm_error("invalid_json", "OpenRouter HTTP response is not valid JSON.", retryable=False),
                )

            try:
                content = raw_response["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                return _provider_result(
                    success=False,
                    model=model,
                    task_name=task_name,
                    raw_response=raw_response,
                    latency_ms=_latency_ms(started_at),
                    error=llm_error("invalid_json", "OpenRouter response does not contain choices[0].message.content.", retryable=False),
                )

            return _provider_result(
                success=True,
                model=model,
                task_name=task_name,
                content=content,
                raw_response=raw_response,
                usage=raw_response.get("usage") if isinstance(raw_response, dict) else {},
                latency_ms=_latency_ms(started_at),
                error=None,
            )

        return _provider_result(
            success=False,
            model=model,
            task_name=task_name,
            latency_ms=_latency_ms(started_at),
            error=llm_error("unknown_error", "OpenRouter request did not complete.", retryable=False),
        )
