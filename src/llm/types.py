"""Shared types and exceptions for unified LLM tasks."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


ALLOWED_OVERRIDE_FIELDS = {
    "model",
    "temperature",
    "max_tokens",
    "top_p",
    "reasoning",
    "stream",
    "text_format",
    "text_verbosity",
}


class LLMTaskError(RuntimeError):
    """Base error raised by the LLM task runner."""

    def __init__(
        self,
        message: str,
        *,
        task_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
        error_type: str = "llm_task_error",
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.task_name = task_name
        self.prompt_version = prompt_version
        self.error_type = error_type
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.error_type,
            "message": str(self),
            "retryable": bool(self.retryable),
            "task_name": self.task_name,
            "prompt_version": self.prompt_version,
            "details": self.details,
        }


class LLMConfigError(LLMTaskError):
    """Raised when required LLM runtime configuration is missing."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_type="config_error", retryable=False, **kwargs)


class LLMAPIError(LLMTaskError):
    """Raised when the OpenAI-compatible API returns or raises an error."""

    def __init__(self, message: str, *, retryable: bool = False, **kwargs: Any) -> None:
        super().__init__(message, error_type="api_error", retryable=retryable, **kwargs)


class LLMJSONParseError(LLMTaskError):
    """Raised when a JSON-output task returns invalid JSON."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_type="invalid_json", retryable=False, **kwargs)


class LLMOutputSchemaError(LLMTaskError):
    """Raised when parsed JSON does not satisfy the task schema."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_type="schema_validation_error", retryable=False, **kwargs)


@dataclass(frozen=True)
class PromptBuildResult:
    task_name: str
    prompt_version: str
    messages: List[Dict[str, str]]


@dataclass(frozen=True)
class LLMTaskPolicy:
    task_name: str
    model: str
    temperature: float
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    reasoning: Optional[Dict[str, Any]] = None
    text_format: Optional[Dict[str, Any]] = None
    text_verbosity: Optional[str] = None
    stream: bool = False
    json_output: bool = False
    json_schema: Optional[Dict[str, Any]] = None
    timeout_seconds: float = 60.0
    max_retries: int = 2

    def with_overrides(self, overrides: Dict[str, Any]) -> "LLMTaskPolicy":
        blocked = sorted(set(overrides) - ALLOWED_OVERRIDE_FIELDS)
        if blocked:
            raise LLMConfigError(
                "Unsupported LLM override field(s): " + ", ".join(blocked),
                details={"blocked_fields": blocked, "allowed_fields": sorted(ALLOWED_OVERRIDE_FIELDS)},
            )
        values = {
            "task_name": self.task_name,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "reasoning": self.reasoning,
            "text_format": self.text_format,
            "text_verbosity": self.text_verbosity,
            "stream": self.stream,
            "json_output": self.json_output,
            "json_schema": self.json_schema,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }
        values.update(overrides)
        return LLMTaskPolicy(**values)
