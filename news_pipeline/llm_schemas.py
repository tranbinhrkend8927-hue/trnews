"""Lightweight JSON schema helpers for LLM structured outputs."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List


BASIC_JSON_SCHEMA = {
    "type": "object",
    "required": ["message"],
    "properties": {
        "message": {"type": "string"},
    },
}

ARTICLE_DRAFT_SCHEMA = {
    "type": "object",
    "required": ["title", "summary"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
    },
}

LLM_ARTICLE_DRAFT_SCHEMA = {
    "type": "object",
    "required": [
        "title",
        "slug",
        "summary",
        "body",
        "seo_title",
        "seo_description",
        "faq",
        "sources_used",
        "risk_disclaimer",
        "uncertain_claims",
        "language",
    ],
    "properties": {
        "title": {"type": "string"},
        "slug": {"type": "string"},
        "summary": {"type": "string"},
        "body": {"type": "string"},
        "seo_title": {"type": "string"},
        "seo_description": {"type": "string"},
        "faq": {"type": "array"},
        "sources_used": {"type": "array"},
        "risk_disclaimer": {"type": "string"},
        "uncertain_claims": {"type": "array"},
        "language": {"type": "string"},
    },
}


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
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _path(parent: str, child: str) -> str:
    return f"{parent}.{child}" if parent else child


def _validate(value: Any, schema: Dict[str, Any], path: str, errors: List[Dict[str, str]]) -> None:
    if not isinstance(schema, dict):
        return

    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, expected_type):
        errors.append(
            {
                "path": path or "$",
                "message": f"Expected {expected_type}, got {_type_name(value)}",
            }
        )
        return

    if expected_type == "object" or isinstance(value, dict):
        required = schema.get("required") or []
        properties = schema.get("properties") or {}
        if isinstance(required, list):
            for field in required:
                if not isinstance(value, dict) or field not in value:
                    errors.append({"path": _path(path, str(field)), "message": "Missing required field"})
        if isinstance(value, dict) and isinstance(properties, dict):
            for field, field_schema in properties.items():
                if field in value:
                    _validate(value[field], field_schema, _path(path, str(field)), errors)

    if expected_type == "array" or isinstance(value, list):
        item_schema = schema.get("items")
        if item_schema and isinstance(value, list):
            for index, item in enumerate(value):
                _validate(item, item_schema, f"{path}[{index}]" if path else f"[{index}]", errors)


def validate_json_schema(value: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    _validate(value, schema or {}, "", errors)
    return json_safe({"valid": not errors, "errors": errors})
