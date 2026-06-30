"""Bahasa Indonesia prompt for FX article generation."""

from typing import Any, Dict, Optional


PROMPT_VERSION = "fx_article_id@2026-06-30"
TASK_NAME = "fx_article_id"

REQUIRED_RISK_DISCLAIMER = (
    "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi "
    "atau ajakan membeli/menjual aset keuangan."
)

TASK_SYSTEM_PROMPT = "\n".join(
    [
        "Tugas: buat kandidat draft artikel edukatif berbahasa Indonesia untuk pembaca Indonesia.",
        "Bahasa artikel harus Bahasa Indonesia.",
        "Output harus berupa JSON valid saja.",
        "Jangan output Markdown.",
        "Body harus memuat paragraf atau bagian berjudul Sumber.",
        "Body harus memuat paragraf atau bagian berjudul Catatan risiko.",
        "JSON wajib memiliki field: title, slug, summary, body, seo_title, seo_description, faq, sources_used, risk_disclaimer, uncertain_claims, language.",
        "faq, sources_used, dan uncertain_claims wajib berupa array.",
    ]
)


def validate_input(input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source_bundle = input_data.get("source_bundle") or {}
    profile = input_data.get("language_profile") or {}
    if not source_bundle.get("sources"):
        return {
            "type": "missing_sources",
            "message": "source_bundle.sources is required before calling the LLM.",
            "retryable": False,
        }
    if str(profile.get("language") or "").lower() != "id":
        return {
            "type": "unsupported_language",
            "message": "Only Bahasa Indonesia profile is supported.",
            "retryable": False,
        }
    return None


def build_user_payload(input_data: Dict[str, Any]) -> Dict[str, Any]:
    profile = input_data.get("language_profile") or {}
    risk_disclaimer = profile.get("risk_disclaimer") or REQUIRED_RISK_DISCLAIMER
    return {
        "task": "Buat kandidat draft artikel edukatif berbahasa Indonesia untuk pembaca Indonesia.",
        "template_hint": input_data.get("template_hint"),
        "topic": input_data.get("topic") or {},
        "source_bundle": input_data.get("source_bundle") or {},
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
            "required_risk_disclaimer": risk_disclaimer,
        },
    }
