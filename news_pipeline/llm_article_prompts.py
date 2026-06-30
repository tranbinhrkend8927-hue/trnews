"""Compatibility prompt builder for LLM article draft candidates."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from src.llm.build_messages import build_messages


REQUIRED_RISK_DISCLAIMER = (
    "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi "
    "atau ajakan membeli/menjual aset keuangan."
)


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


def _has_sources(source_bundle: Dict[str, Any]) -> bool:
    return bool((source_bundle or {}).get("sources"))


def build_llm_article_messages(
    topic: Dict[str, Any],
    source_bundle: Dict[str, Any],
    language_profile: Dict[str, Any],
    template_hint: Optional[str] = None,
) -> Dict[str, Any]:
    topic = json_safe(topic or {})
    source_bundle = json_safe(source_bundle or {})
    profile = json_safe(language_profile or {})

    if not _has_sources(source_bundle):
        return json_safe(
            {
                "success": False,
                "messages": [],
                "error": _error("missing_sources", "source_bundle.sources is required before calling the LLM.", retryable=False),
            }
        )
    if (profile.get("language") or "").lower() != "id":
        return json_safe(
            {
                "success": False,
                "messages": [],
                "error": _error("unsupported_language", "Only Bahasa Indonesia profile is supported.", retryable=False),
            }
        )

    result = build_messages(
        "fx_article_id",
        {
            "topic": topic,
            "source_bundle": source_bundle,
            "language_profile": profile,
            "template_hint": template_hint,
        },
    )
    return json_safe({"success": True, "messages": result.messages, "prompt_version": result.prompt_version, "error": None})
