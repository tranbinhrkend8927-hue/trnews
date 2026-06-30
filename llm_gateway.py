"""Provider-agnostic LLM gateway for structured JSON outputs."""

import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from llm_schemas import validate_json_schema


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
        return {str(key): json_safe(item) for key, item in value.items() if str(key).lower() != "authorization"}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def llm_error(error_type: str, message: str, *, retryable: bool = False) -> Dict[str, Any]:
    return {"type": error_type, "message": str(message), "retryable": bool(retryable)}


def _latency_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def _provider_name(provider: Any) -> str:
    return str(getattr(provider, "provider_name", None) or getattr(provider, "provider", None) or "unknown")


def _provider_model(provider: Any, config: Optional[Dict[str, Any]] = None) -> str:
    config = config or {}
    return str(config.get("model") or getattr(provider, "model", None) or "")


def _scrub_secret(value: Any, secret: Optional[str]) -> Any:
    safe = json_safe(value)
    if not secret:
        return safe
    if isinstance(safe, str):
        return safe.replace(secret, "[REDACTED]")
    if isinstance(safe, dict):
        return {key: _scrub_secret(item, secret) for key, item in safe.items() if key != "api_key"}
    if isinstance(safe, list):
        return [_scrub_secret(item, secret) for item in safe]
    return safe


class MockLLMProvider:
    """Deterministic provider used by tests; it never performs network calls."""

    provider_name = "mock"

    def __init__(
        self,
        responses: Optional[List[Dict[str, Any]]] = None,
        *,
        mode: str = "success",
        model: str = "mock-model",
    ):
        self.responses = list(responses or [])
        self.mode = mode
        self.model = model
        self.call_count = 0

    def _response_for_mode(self) -> Dict[str, Any]:
        if self.mode == "invalid_json":
            return {"success": True, "content": "not json", "raw_response": {"content": "not json"}, "usage": {}}
        if self.mode == "timeout":
            return {"success": False, "error": llm_error("timeout", "Mock timeout.", retryable=True)}
        if self.mode == "api_error":
            return {"success": False, "error": llm_error("api_error", "Mock API error.", retryable=False)}
        if self.mode == "config_error":
            return {"success": False, "error": llm_error("config_error", "Mock config error.", retryable=False)}
        if self.mode == "schema_validation_error":
            return {"success": True, "content": {}, "raw_response": {"content": {}}, "usage": {}}
        return {
            "success": True,
            "content": {"message": "ok"},
            "raw_response": {"choices": [{"message": {"content": "{\"message\":\"ok\"}"}}]},
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    def generate(self, task_name: str, messages: List[Dict[str, Any]], schema: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.call_count += 1
        if self.responses:
            response = self.responses.pop(0)
        else:
            response = self._response_for_mode()
        response.setdefault("provider", self.provider_name)
        response.setdefault("model", self.model)
        response.setdefault("task_name", task_name)
        response.setdefault("latency_ms", 0)
        return json_safe(response)


class LLMGateway:
    def __init__(self, provider: Optional[Any] = None, *, max_retries: int = 0):
        self.provider = provider if provider is not None else MockLLMProvider()
        self.max_retries = max(0, int(max_retries or 0))

    def _result(
        self,
        *,
        success: bool,
        provider: str,
        model: str,
        task_name: str,
        output: Any,
        raw_response: Any,
        usage: Optional[Dict[str, Any]],
        latency_ms: int,
        error: Optional[Dict[str, Any]],
        secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        return _scrub_secret(
            {
                "success": bool(success),
                "provider": provider,
                "model": model,
                "task_name": task_name,
                "output": output,
                "raw_response": raw_response,
                "usage": usage or {},
                "latency_ms": latency_ms,
                "error": error,
            },
            secret,
        )

    def _failure(
        self,
        error_type: str,
        message: str,
        *,
        provider: str,
        model: str,
        task_name: str,
        latency_ms: int,
        raw_response: Any = None,
        usage: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
        secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._result(
            success=False,
            provider=provider,
            model=model,
            task_name=task_name,
            output=None,
            raw_response=raw_response,
            usage=usage or {},
            latency_ms=latency_ms,
            error=llm_error(error_type, message, retryable=retryable),
            secret=secret,
        )

    def generate_json(
        self,
        task_name: str,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        started_at = time.monotonic()
        config = dict(config or {})
        provider = self.provider
        provider_name = _provider_name(provider)
        model = _provider_model(provider, config)
        secret = config.get("api_key")
        max_retries = max(0, int(config.get("max_retries", self.max_retries) or 0))
        if getattr(provider, "handles_retries", False):
            max_retries = 0

        if provider is None or not hasattr(provider, "generate"):
            return self._failure(
                "config_error",
                "LLM provider is not configured.",
                provider=provider_name,
                model=model,
                task_name=task_name,
                latency_ms=_latency_ms(started_at),
                secret=secret,
            )

        attempts = 0
        last_result = None
        while attempts <= max_retries:
            attempts += 1
            try:
                provider_result = provider.generate(task_name, messages, schema, config)
            except TimeoutError as exc:
                provider_result = {"success": False, "error": llm_error("timeout", str(exc), retryable=True)}
            except Exception as exc:
                provider_result = {"success": False, "error": llm_error("unknown_error", str(exc), retryable=False)}

            last_result = json_safe(provider_result)
            provider_name = str(last_result.get("provider") or provider_name)
            model = str(last_result.get("model") or model)
            error = last_result.get("error") or {}
            if last_result.get("success") or not error.get("retryable") or attempts > max_retries:
                break

        latency = _latency_ms(started_at)
        if not last_result or not last_result.get("success"):
            error = (last_result or {}).get("error") or llm_error("unknown_error", "LLM provider failed.", retryable=False)
            return self._failure(
                error.get("type") or "unknown_error",
                error.get("message") or "LLM provider failed.",
                provider=provider_name,
                model=model,
                task_name=task_name,
                latency_ms=latency,
                raw_response=(last_result or {}).get("raw_response"),
                usage=(last_result or {}).get("usage") or {},
                retryable=bool(error.get("retryable", False)),
                secret=secret,
            )

        content = last_result.get("content")
        if isinstance(content, str):
            try:
                output = json.loads(content)
            except json.JSONDecodeError:
                return self._failure(
                    "invalid_json",
                    "LLM response content is not valid JSON.",
                    provider=provider_name,
                    model=model,
                    task_name=task_name,
                    latency_ms=latency,
                    raw_response=last_result.get("raw_response"),
                    usage=last_result.get("usage") or {},
                    secret=secret,
                )
        elif isinstance(content, (dict, list)):
            output = content
        else:
            return self._failure(
                "invalid_json",
                "LLM response content is not JSON-compatible.",
                provider=provider_name,
                model=model,
                task_name=task_name,
                latency_ms=latency,
                raw_response=last_result.get("raw_response"),
                usage=last_result.get("usage") or {},
                secret=secret,
            )

        validation = validate_json_schema(output, schema)
        if not validation.get("valid"):
            return self._failure(
                "schema_validation_error",
                "LLM output failed schema validation.",
                provider=provider_name,
                model=model,
                task_name=task_name,
                latency_ms=latency,
                raw_response=last_result.get("raw_response"),
                usage=last_result.get("usage") or {},
                retryable=False,
                secret=secret,
            )

        return self._result(
            success=True,
            provider=provider_name,
            model=model,
            task_name=task_name,
            output=output,
            raw_response=last_result.get("raw_response") or {},
            usage=last_result.get("usage") or {},
            latency_ms=latency,
            error=None,
            secret=secret,
        )
