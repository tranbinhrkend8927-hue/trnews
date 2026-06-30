"""Language profiles for LLM-assisted draft candidates."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict


INDONESIAN_PROFILE = {
    "language": "id",
    "market": "Indonesia",
    "audience": "Indonesian retail readers interested in Rupiah, USD/IDR, Bank Indonesia, Fed, inflation, and macro events.",
    "tone": "clear, careful, explanatory, not sensational",
    "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
    "forbidden_claims": [
        "profit guarantee",
        "buy/sell instruction",
        "take profit",
        "stop loss",
        "certain prediction",
    ],
}


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


def get_language_profile(language: str) -> Dict[str, Any]:
    normalized = str(language or "").strip().lower()
    if normalized == "id":
        return json_safe(
            {
                "success": True,
                "language": "id",
                "profile": INDONESIAN_PROFILE,
                "error": None,
            }
        )
    return json_safe(
        {
            "success": False,
            "language": normalized,
            "profile": None,
            "error": _error("unsupported_language", f"Unsupported language: {normalized}", retryable=False),
        }
    )
