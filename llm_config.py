"""Configuration helpers for provider-agnostic LLM gateway."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional


DEFAULT_OPENROUTER_TIMEOUT_SECONDS = 60
DEFAULT_OPENROUTER_MAX_RETRIES = 2


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
        return {str(key): json_safe(item) for key, item in value.items() if str(key) != "api_key"}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _parse_positive_int(value: Any, default: int, name: str, warnings: list) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        warnings.append({"type": "invalid_config_value", "name": name, "message": f"Using default {default}."})
        return default
    if parsed < 0:
        warnings.append({"type": "invalid_config_value", "name": name, "message": f"Using default {default}."})
        return default
    return parsed


def _parse_positive_float(value: Any, default: float, name: str, warnings: list) -> float:
    if value in (None, ""):
        return float(default)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        warnings.append({"type": "invalid_config_value", "name": name, "message": f"Using default {default}."})
        return float(default)
    if parsed <= 0:
        warnings.append({"type": "invalid_config_value", "name": name, "message": f"Using default {default}."})
        return float(default)
    return parsed


def _env_value(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name, "") or "").strip()


def load_openrouter_config(
    env: Optional[Mapping[str, str]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    env = env or os.environ
    overrides = overrides or {}
    warnings = []
    errors = []

    api_key = str(overrides.get("api_key") or _env_value(env, "OPENROUTER_API_KEY")).strip()
    model = str(
        overrides.get("model")
        or overrides.get("default_model")
        or _env_value(env, "OPENROUTER_DEFAULT_MODEL")
    ).strip()
    writer_model = str(overrides.get("writer_model") or _env_value(env, "OPENROUTER_WRITER_MODEL")).strip()
    review_model = str(overrides.get("review_model") or _env_value(env, "OPENROUTER_REVIEW_MODEL")).strip()
    timeout_seconds = _parse_positive_float(
        overrides.get("timeout_seconds", _env_value(env, "OPENROUTER_TIMEOUT_SECONDS")),
        DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
        "OPENROUTER_TIMEOUT_SECONDS",
        warnings,
    )
    max_retries = _parse_positive_int(
        overrides.get("max_retries", _env_value(env, "OPENROUTER_MAX_RETRIES")),
        DEFAULT_OPENROUTER_MAX_RETRIES,
        "OPENROUTER_MAX_RETRIES",
        warnings,
    )
    max_retries = min(max_retries, DEFAULT_OPENROUTER_MAX_RETRIES)

    if not api_key:
        errors.append(
            {
                "type": "config_error",
                "message": "OPENROUTER_API_KEY is required.",
                "retryable": False,
            }
        )
    if not model:
        errors.append(
            {
                "type": "config_error",
                "message": "OPENROUTER_DEFAULT_MODEL or config.model is required.",
                "retryable": False,
            }
        )

    config = {
        "provider": "openrouter",
        "model": model,
        "writer_model": writer_model or None,
        "review_model": review_model or None,
        "timeout_seconds": timeout_seconds,
        "max_retries": max_retries,
        "has_api_key": bool(api_key),
    }

    return json_safe(
        {
            "success": not errors,
            "config": config,
            "errors": errors,
            "warnings": warnings,
        }
    )


def get_openrouter_api_key(
    env: Optional[Mapping[str, str]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> str:
    env = env or os.environ
    overrides = overrides or {}
    return str(overrides.get("api_key") or _env_value(env, "OPENROUTER_API_KEY")).strip()
