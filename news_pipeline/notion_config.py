"""Configuration helpers for Notion exports."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional


DEFAULT_NOTION_TIMEOUT_SECONDS = 60
DEFAULT_NOTION_MAX_RETRIES = 2
MAX_NOTION_MAX_RETRIES = 2


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _error(error_type: str, message: str, *, retryable: bool = False) -> Dict[str, Any]:
    return {"type": error_type, "message": message, "retryable": bool(retryable)}


def _env_value(env: Optional[Dict[str, str]], name: str) -> Optional[str]:
    source = env if env is not None else os.environ
    value = source.get(name)
    if value is None:
        return None
    return str(value).strip()


def _int_setting(value: Optional[str], default: int, *, maximum: Optional[int] = None) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def load_notion_config(
    env: Optional[Dict[str, str]] = None,
    *,
    require_api_key: bool = False,
) -> Dict[str, Any]:
    api_key = _env_value(env, "NOTION_API_KEY") or ""
    data_source_id = _env_value(env, "NOTION_DATA_SOURCE_ID") or ""
    parent_page_id = _env_value(env, "NOTION_PARENT_PAGE_ID") or ""
    export_mode = _env_value(env, "NOTION_EXPORT_MODE") or "data_source"
    timeout_seconds = _int_setting(
        _env_value(env, "NOTION_TIMEOUT_SECONDS"),
        DEFAULT_NOTION_TIMEOUT_SECONDS,
    )
    max_retries = _int_setting(
        _env_value(env, "NOTION_MAX_RETRIES"),
        DEFAULT_NOTION_MAX_RETRIES,
        maximum=MAX_NOTION_MAX_RETRIES,
    )

    errors = []
    if require_api_key and not api_key:
        errors.append(_error("config_error", "NOTION_API_KEY is required for export."))
    if not data_source_id and not parent_page_id:
        errors.append(_error("config_error", "NOTION_DATA_SOURCE_ID or NOTION_PARENT_PAGE_ID is required."))

    parent_type = "data_source" if data_source_id else "page"
    return json_safe(
        {
            "success": not errors,
            "has_api_key": bool(api_key),
            "parent_type": parent_type,
            "has_data_source_id": bool(data_source_id),
            "has_parent_page_id": bool(parent_page_id),
            "export_mode": export_mode,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "errors": errors,
        }
    )


def get_notion_api_key(env: Optional[Dict[str, str]] = None) -> str:
    return _env_value(env, "NOTION_API_KEY") or ""


def get_notion_parent(env: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
    data_source_id = _env_value(env, "NOTION_DATA_SOURCE_ID") or ""
    parent_page_id = _env_value(env, "NOTION_PARENT_PAGE_ID") or ""
    if data_source_id:
        return {"type": "data_source", "id": data_source_id}
    return {"type": "page", "id": parent_page_id or None}
