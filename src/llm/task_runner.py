from __future__ import annotations

from typing import Any

from .result import LLMTaskError, LLMTaskResult
from .run_task import run_llm_task
from .types import LLMConfigError, LLMJSONParseError, LLMOutputSchemaError, LLMTaskError as RuntimeLLMTaskError


class LLMTaskRunner:
    def run(
        self,
        *,
        task: str,
        language: str,
        profile: str | None,
        input_data: dict,
        overrides: dict | None = None,
    ) -> LLMTaskResult:
        try:
            result = run_llm_task(task, input_data or {}, overrides=overrides)
        except Exception as exc:
            return LLMTaskResult(
                success=False,
                task=task,
                language=language,
                profile=profile,
                error=_error_from_exception(exc),
                metadata={"profile": profile},
            )

        output = result.get("output") if isinstance(result, dict) else None
        if output is not None and not isinstance(output, dict):
            return LLMTaskResult(
                success=False,
                task=task,
                language=language,
                profile=profile,
                model=result.get("model") if isinstance(result, dict) else None,
                prompt_version=result.get("prompt_version") if isinstance(result, dict) else None,
                raw_text=str(output),
                usage=result.get("usage") or {},
                latency_ms=result.get("latency_ms"),
                error=LLMTaskError(
                    type="llm_output_not_dict",
                    message="LLM task output must be a dict.",
                    raw={"output": output},
                ),
                metadata={"raw_result": _safe_result(result), "profile": profile},
            )

        return LLMTaskResult(
            success=bool(result.get("success")) if isinstance(result, dict) else False,
            task=str(result.get("task_name") or task) if isinstance(result, dict) else task,
            language=language,
            profile=profile,
            model=result.get("model") if isinstance(result, dict) else None,
            prompt_version=result.get("prompt_version") if isinstance(result, dict) else None,
            output=output,
            usage=result.get("usage") or {},
            latency_ms=result.get("latency_ms"),
            error=None,
            metadata={"raw_result": _safe_result(result), "profile": profile},
        )


def _error_from_exception(exc: Exception) -> LLMTaskError:
    if isinstance(exc, LLMConfigError):
        error_type = "llm_config_error"
    elif isinstance(exc, LLMJSONParseError):
        error_type = "llm_json_parse_error"
    elif isinstance(exc, LLMOutputSchemaError):
        error_type = "llm_schema_error"
    elif isinstance(exc, RuntimeLLMTaskError):
        error_type = getattr(exc, "error_type", None) or "llm_task_failed"
    else:
        error_type = "llm_task_failed"

    raw: dict[str, Any] = {}
    retryable = False
    if isinstance(exc, RuntimeLLMTaskError):
        raw = exc.to_dict()
        retryable = bool(exc.retryable)

    return LLMTaskError(
        type=error_type,
        message=str(exc),
        retryable=retryable,
        raw=raw,
    )


def _safe_result(result: Any) -> dict:
    if not isinstance(result, dict):
        return {"value": str(result)}
    return {key: value for key, value in result.items() if key not in {"raw_response"}}
