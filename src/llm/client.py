"""OpenAI-compatible chat completions client."""

import os
import time
from typing import Any, Dict, Optional

import requests

from .types import LLMAPIError, LLMConfigError, LLMTaskError


CHAT_COMPLETIONS_PATH = "/chat/completions"
DEFAULT_LLM_BASE_URL = "https://openrouter.ai/api/v1"
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRY_STATUS_CODES = {400, 401, 403, 404}


def chat_completions_url(base_url: str) -> str:
    normalized = str(base_url or DEFAULT_LLM_BASE_URL).strip().rstrip("/")
    if normalized.endswith(CHAT_COMPLETIONS_PATH):
        return normalized
    return f"{normalized}{CHAT_COMPLETIONS_PATH}"


class OpenAICompatibleClient:
    """Small client that only knows how to call OpenAI-compatible chat completions."""

    def __init__(
        self,
        *,
        session: Optional[Any] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.session = session or requests
        self.base_url = str(base_url or os.getenv("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL).strip()
        self.api_key = str(api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()

    @property
    def endpoint(self) -> str:
        return chat_completions_url(self.base_url)

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise LLMConfigError("LLM_API_KEY is required for OpenAI-compatible LLM calls.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def create_chat_completion(
        self,
        payload: Dict[str, Any],
        *,
        timeout_seconds: float = 60,
        max_retries: int = 2,
        task_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = self._headers()
        attempts = 0
        max_retries = max(0, int(max_retries or 0))
        started_at = time.monotonic()

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
                raise LLMTaskError(
                    str(exc),
                    task_name=task_name,
                    prompt_version=prompt_version,
                    error_type="timeout",
                    retryable=True,
                    details={"attempts": attempts},
                ) from exc
            except requests.exceptions.RequestException as exc:
                raise LLMAPIError(
                    str(exc),
                    task_name=task_name,
                    prompt_version=prompt_version,
                    retryable=False,
                    details={"attempts": attempts},
                ) from exc

            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code >= 400:
                retryable = status_code in TRANSIENT_STATUS_CODES
                if retryable and attempts <= max_retries:
                    continue
                message = f"OpenAI-compatible API returned HTTP {status_code}."
                response_data: Any
                try:
                    response_data = response.json()
                    provider_message = response_data.get("error", {}).get("message") if isinstance(response_data, dict) and isinstance(response_data.get("error"), dict) else None
                    if provider_message:
                        message = f"{message} {provider_message}"
                except Exception:
                    response_data = {"text": str(getattr(response, "text", ""))[:1000]}
                raise LLMAPIError(
                    message,
                    task_name=task_name,
                    prompt_version=prompt_version,
                    retryable=retryable and status_code not in NON_RETRY_STATUS_CODES,
                    details={"status_code": status_code, "attempts": attempts, "response": response_data},
                )

            try:
                data = response.json()
            except Exception as exc:
                raise LLMTaskError(
                    "OpenAI-compatible API response is not valid JSON.",
                    task_name=task_name,
                    prompt_version=prompt_version,
                    error_type="invalid_json",
                    retryable=False,
                    details={"attempts": attempts, "text": str(getattr(response, "text", ""))[:1000]},
                ) from exc
            data["_client"] = {"attempts": attempts, "latency_ms": max(0, int((time.monotonic() - started_at) * 1000))}
            return data

        raise LLMAPIError(
            "OpenAI-compatible API request did not complete.",
            task_name=task_name,
            prompt_version=prompt_version,
            retryable=False,
            details={"attempts": attempts},
        )
