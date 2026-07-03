"""OpenAI Responses API client wrapper."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, Optional

from .types import LLMAPIError, LLMConfigError, LLMTaskError


RESPONSES_PATH = "/responses"
DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRY_STATUS_CODES = {400, 401, 403, 404}


def responses_url(base_url: str) -> str:
    normalized = str(base_url or DEFAULT_LLM_BASE_URL).strip().rstrip("/")
    if normalized.endswith(RESPONSES_PATH):
        return normalized
    legacy_chat_path = "/" + "chat" + "/completions"
    if normalized.endswith(legacy_chat_path):
        normalized = normalized[: -len(legacy_chat_path)]
    return f"{normalized}{RESPONSES_PATH}"


class OpenAICompatibleClient:
    """Thin wrapper around the OpenAI SDK Responses API.

    The name is kept for compatibility with existing imports, but the runtime
    endpoint is Responses API, not Chat Completions.
    """

    def __init__(
        self,
        *,
        client: Optional[Any] = None,
        session: Optional[Any] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self._provided_client = client or session
        self.base_url = str(base_url or _env_value("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL).strip()
        self.api_key = str(api_key or _env_value("OPENAI_API_KEY") or _env_value("LLM_API_KEY") or _env_value("OPENROUTER_API_KEY") or "").strip()
        self._client = self._provided_client

    @property
    def endpoint(self) -> str:
        return responses_url(self.base_url)

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise LLMConfigError("OPENAI_API_KEY is required for OpenAI Responses API calls.")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMConfigError("The openai package is required for Responses API calls.") from exc
            self._client = OpenAI(api_key=self.api_key, base_url=self._base_url_for_sdk())
        return self._client

    def create_response(
        self,
        payload: Dict[str, Any],
        *,
        timeout_seconds: float = 60,
        max_retries: int = 2,
        task_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        started_at = time.monotonic()
        effective_payload = dict(payload)
        try:
            sdk_client = self._client_with_options(timeout_seconds=timeout_seconds, max_retries=max_retries)
            try:
                response = sdk_client.responses.create(**effective_payload)
            except Exception as exc:
                stripped = _payload_without_unsupported_response_params(effective_payload, exc)
                if stripped is None:
                    raise
                effective_payload = stripped
                response = sdk_client.responses.create(**effective_payload)
        except Exception as exc:
            raise _sdk_exception_to_task_error(exc, task_name=task_name, prompt_version=prompt_version) from None

        data = _response_to_dict(response)
        data["_client"] = {"attempts": 1, "latency_ms": max(0, int((time.monotonic() - started_at) * 1000))}
        return data

    def stream_response_text(
        self,
        payload: Dict[str, Any],
        *,
        timeout_seconds: float = 60,
        max_retries: int = 2,
        task_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        started_at = time.monotonic()
        chunks: list[str] = []
        final_response: Any = None
        effective_payload = dict(payload)
        try:
            sdk_client = self._client_with_options(timeout_seconds=timeout_seconds, max_retries=max_retries)
            try:
                stream_cm = sdk_client.responses.stream(**effective_payload)
            except Exception as exc:
                stripped = _payload_without_unsupported_response_params(effective_payload, exc)
                if stripped is None:
                    raise
                effective_payload = stripped
                stream_cm = sdk_client.responses.stream(**effective_payload)
            with stream_cm as stream:
                for event in stream:
                    event_type = getattr(event, "type", None) or (event.get("type") if isinstance(event, dict) else None)
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", None) if not isinstance(event, dict) else event.get("delta")
                        if delta:
                            chunks.append(str(delta))
                if hasattr(stream, "get_final_response"):
                    final_response = stream.get_final_response()
        except Exception as exc:
            raise _sdk_exception_to_task_error(exc, task_name=task_name, prompt_version=prompt_version) from None

        data = _response_to_dict(final_response) if final_response is not None else {}
        data["output_text"] = "".join(chunks)
        data["_client"] = {"attempts": 1, "latency_ms": max(0, int((time.monotonic() - started_at) * 1000))}
        return data

    def _client_with_options(self, *, timeout_seconds: float, max_retries: int) -> Any:
        client = self.client
        if hasattr(client, "with_options"):
            return client.with_options(timeout=timeout_seconds, max_retries=max(0, int(max_retries or 0)))
        return client

    def _base_url_for_sdk(self) -> str:
        endpoint = responses_url(self.base_url)
        if endpoint.endswith(RESPONSES_PATH):
            return endpoint[: -len(RESPONSES_PATH)]
        return str(self.base_url or DEFAULT_LLM_BASE_URL).rstrip("/")


def _env_value(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        from src.config.loader import load_local_env
    except Exception:
        return ""
    return str(load_local_env().get(name) or "")


def _response_to_dict(response: Any) -> Dict[str, Any]:
    if response is None:
        return {}
    if isinstance(response, dict):
        return dict(response)
    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif hasattr(response, "to_dict"):
        data = response.to_dict()
    else:
        data = {"value": str(response)}
    output_text = getattr(response, "output_text", None)
    if output_text is not None:
        data["output_text"] = output_text
    usage = getattr(response, "usage", None)
    if usage is not None:
        data["usage"] = _response_to_dict(usage) if not isinstance(usage, dict) else usage
    return data


def _payload_without_unsupported_response_params(payload: Dict[str, Any], exc: Exception) -> Optional[Dict[str, Any]]:
    message = str(exc).lower()
    status_code = getattr(exc, "status_code", None)
    if status_code not in (None, 400):
        return None
    unsupported_params = [
        key
        for key in ("temperature", "top_p")
        if key in payload and key in message and ("unsupported" in message or "not supported" in message)
    ]
    if not unsupported_params:
        return None
    stripped = dict(payload)
    for key in unsupported_params:
        stripped.pop(key, None)
    return stripped


def _sdk_exception_to_task_error(exc: Exception, *, task_name: Optional[str], prompt_version: Optional[str]) -> LLMTaskError:
    status_code = getattr(exc, "status_code", None)
    retryable = bool(status_code in TRANSIENT_STATUS_CODES) if status_code is not None else False
    error_type = "api_error"
    raw_message = str(exc)
    if exc.__class__.__name__.lower().endswith("timeout") or "timeout" in raw_message.lower() or "timed out" in raw_message.lower():
        error_type = "timeout"
        retryable = True
    details: Dict[str, Any] = {"exception_type": exc.__class__.__name__}
    if status_code is not None:
        details["status_code"] = status_code
        retryable = retryable and status_code not in NON_RETRY_STATUS_CODES
    response = getattr(exc, "response", None)
    if response is not None:
        details["response"] = _redact_secrets(str(response))[:1000]
    message = _redact_secrets(raw_message)
    return LLMAPIError(
        message,
        task_name=task_name,
        prompt_version=prompt_version,
        retryable=retryable,
        details=details,
    ) if error_type == "api_error" else LLMTaskError(
        message,
        task_name=task_name,
        prompt_version=prompt_version,
        error_type=error_type,
        retryable=retryable,
        details=details,
    )


def _redact_secrets(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"sk-[A-Za-z0-9_*.-]{8,}", "sk-[REDACTED]", text)
    text = re.sub(r"(api[_ -]?key[^:]*:\s*)['\"]?[^,'\"}\s]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    return text
