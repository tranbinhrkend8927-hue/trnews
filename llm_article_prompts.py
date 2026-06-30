"""Prompt builders for LLM article draft candidates."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional


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

    system_content = "\n".join(
        [
            "Anda adalah asisten penulis artikel penjelasan berita finansial berbahasa Indonesia.",
            "Tulis dengan gaya jelas, hati-hati, edukatif, dan tidak sensasional.",
            "Gunakan hanya informasi dari source_bundle.",
            "Jangan membuat source title, URL, published_at, source_name, atau metadata sumber yang tidak tersedia di source_bundle.",
            "Jangan membuat angka, harga, kurs, tingkat suku bunga, CPI, NFP, FOMC, atau tanggal yang tidak tersedia di source_bundle.",
            "Jangan memberikan rekomendasi beli/jual, target profit, stop loss, atau janji keuntungan.",
            "Dilarang memberikan instruksi beli atau jual.",
            "Dilarang menulis take profit atau stop loss.",
            "Dilarang menjanjikan keuntungan atau membuat prediksi pasti.",
            "Output harus berupa JSON valid saja.",
            "Jangan output Markdown.",
            "Bahasa artikel harus Bahasa Indonesia.",
            "Body harus memuat paragraf atau bagian berjudul Sumber.",
            "Body harus memuat paragraf atau bagian berjudul Catatan risiko.",
            f"Catatan risiko wajib: {profile.get('risk_disclaimer') or REQUIRED_RISK_DISCLAIMER}",
            "JSON wajib memiliki field: title, slug, summary, body, seo_title, seo_description, faq, sources_used, risk_disclaimer, uncertain_claims, language.",
            "faq, sources_used, dan uncertain_claims wajib berupa array.",
        ]
    )
    user_payload = {
        "task": "Buat kandidat draft artikel edukatif berbahasa Indonesia untuk pembaca Indonesia.",
        "template_hint": template_hint,
        "topic": topic,
        "source_bundle": source_bundle,
        "language_profile": profile,
        "output_constraints": {
            "language": "id",
            "use_only_source_bundle": True,
            "do_not_fabricate_source_metadata": True,
            "do_not_fabricate_financial_numbers": True,
            "no_buy_sell_instruction": True,
            "no_take_profit_stop_loss": True,
            "no_profit_promise": True,
            "required_sections": ["Sumber", "Catatan risiko"],
            "required_risk_disclaimer": profile.get("risk_disclaimer") or REQUIRED_RISK_DISCLAIMER,
        },
    }
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True)},
    ]
    return json_safe({"success": True, "messages": messages, "error": None})
