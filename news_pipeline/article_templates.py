"""Rule-based Indonesian article draft templates for USDIDR content topics."""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .source_grounding import build_source_bundle


SUPPORTED_ARTICLE_TEMPLATES = {
    "daily_usdidr_update",
    "rupiah_explainer",
    "macro_event_watch",
}

RISK_DISCLAIMER = (
    "Catatan risiko: Artikel ini bersifat informasi umum dan bukan rekomendasi "
    "investasi, ajakan beli atau jual, maupun saran trading. Keputusan finansial "
    "tetap memerlukan pertimbangan pribadi dan sumber resmi."
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


def normalize_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return json_safe(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        return json_safe(loaded if isinstance(loaded, dict) else {"value": loaded})
    return {}


def unsupported_template_error(topic_type: str) -> Dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": "unsupported_topic_type",
            "topic_type": topic_type,
            "message": f"Unsupported article template topic_type: {topic_type}",
        },
    }


def source_news_ids_from_topic(topic_row: Dict[str, Any]) -> List[int]:
    reason_json = normalize_json_object(topic_row.get("reason_json"))
    source_news_ids = topic_row.get("source_news_ids") or reason_json.get("source_news_ids") or []
    result = []
    for item in source_news_ids:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def source_urls_from_topic(topic_row: Dict[str, Any]) -> List[str]:
    reason_json = normalize_json_object(topic_row.get("reason_json"))
    candidates = []
    for key in ("source_url", "url", "canonical_url"):
        if topic_row.get(key):
            candidates.append(topic_row[key])
        if reason_json.get(key):
            candidates.append(reason_json[key])
    for key in ("source_urls", "urls", "canonical_urls"):
        value = reason_json.get(key) or topic_row.get(key)
        if isinstance(value, (list, tuple)):
            candidates.extend(value)

    urls = []
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text.startswith(("http://", "https://")) and text not in urls:
            urls.append(text)
    return urls


def build_source_trace(topic_row: Dict[str, Any], source_bundle: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if source_bundle is not None:
        return json_safe(source_bundle)

    reason_json = normalize_json_object(topic_row.get("reason_json"))
    fallback_bundle = build_source_bundle(topic_row, [])
    fallback_bundle["source_trace"]["matched_keywords"] = reason_json.get("matched_keywords", [])
    fallback_bundle["source_trace"]["source_urls"] = source_urls_from_topic(topic_row)
    return json_safe(fallback_bundle)


def template_title(topic_type: str) -> str:
    titles = {
        "daily_usdidr_update": "USD/IDR Hari Ini: Rupiah Bergerak, Ini Faktor yang Perlu Dipantau",
        "rupiah_explainer": "Mengapa Rupiah Bisa Melemah terhadap Dolar AS? Ini Faktor yang Perlu Dipahami",
        "macro_event_watch": "Data Makro AS dan USD/IDR: Faktor yang Perlu Dipantau Pasar",
    }
    return titles[topic_type]


def template_summary(topic_type: str) -> str:
    summaries = {
        "daily_usdidr_update": (
            "Ringkasan USD/IDR untuk pembaca Indonesia, dengan fokus pada Rupiah, "
            "Dolar AS, dan faktor pasar yang perlu dipantau."
        ),
        "rupiah_explainer": (
            "Penjelasan singkat mengenai hubungan Rupiah, Dolar AS, The Fed, dan "
            "Bank Indonesia tanpa memberikan rekomendasi investasi."
        ),
        "macro_event_watch": (
            "Panduan konteks mengenai CPI, NFP, FOMC, The Fed, dan dampaknya bagi "
            "perhatian pasar terhadap USD/IDR."
        ),
    }
    return summaries[topic_type]


def faq_for_template(topic_type: str) -> str:
    if topic_type == "rupiah_explainer":
        return "\n".join(
            [
                "FAQ",
                "Q: Mengapa Dolar AS dapat memengaruhi Rupiah?",
                "A: Dolar AS sering menjadi acuan global, sehingga perubahan sentimen terhadap Dolar AS dapat memengaruhi mata uang lain, termasuk Rupiah.",
                "Q: Apakah artikel ini memberi arahan transaksi?",
                "A: Tidak. Artikel ini hanya berisi informasi umum dan konteks yang perlu dipantau.",
            ]
        )
    if topic_type == "macro_event_watch":
        return "\n".join(
            [
                "FAQ",
                "Q: Mengapa CPI, NFP, atau FOMC diperhatikan pasar?",
                "A: Data dan agenda tersebut dapat memengaruhi ekspektasi terhadap kebijakan The Fed dan pergerakan Dolar AS.",
                "Q: Apakah dampaknya terhadap USD/IDR selalu sama?",
                "A: Tidak. Dampak pasar dapat berbeda bergantung pada konteks data, komunikasi bank sentral, dan sentimen global.",
            ]
        )
    return "\n".join(
        [
            "FAQ",
            "Q: Apa yang perlu dipantau dari USD/IDR hari ini?",
            "A: Pembaca dapat mencermati sentimen Dolar AS, berita Rupiah, Bank Indonesia, The Fed, dan agenda data ekonomi.",
            "Q: Apakah artikel ini merupakan saran trading?",
            "A: Tidak. Artikel ini disusun sebagai informasi umum untuk membantu memahami konteks pasar.",
        ]
    )


def source_section(topic_row: Dict[str, Any], source_bundle: Optional[Dict[str, Any]] = None) -> str:
    if source_bundle is not None and source_bundle.get("sources"):
        lines = ["Sumber"]
        for source in source_bundle.get("sources", []):
            news_id = source.get("news_id")
            title = source.get("title")
            url = source.get("url") or source.get("canonical_url") or source.get("source_url")
            if title:
                lines.append(f"Source news ID {news_id}: {title}" if news_id else f"Source: {title}")
            elif news_id:
                lines.append(f"Source news ID {news_id}")
            if url:
                lines.append(f"URL: {url}")
        missing = source_bundle.get("missing_source_news_ids") or []
        if missing:
            lines.append("Source news IDs belum ditemukan: " + ", ".join(str(item) for item in missing))
        return "\n".join(lines)

    source_ids = source_news_ids_from_topic(topic_row)
    urls = source_urls_from_topic(topic_row)
    lines = ["Sumber"]
    if source_ids:
        lines.append("Source news IDs: " + ", ".join(str(item) for item in source_ids))
    else:
        lines.append("Source news IDs: belum tersedia dalam topic.")
    if urls:
        lines.extend(f"URL: {url}" for url in urls)
    else:
        lines.append("URL sumber tidak tersedia; rujukan berasal dari catatan berita forex yang sudah tersimpan.")
    return "\n".join(lines)


def body_for_template(topic_type: str, topic_row: Dict[str, Any], source_bundle: Optional[Dict[str, Any]] = None) -> str:
    source_intro = "berdasarkan sumber berita yang tersedia"
    if source_bundle is not None and source_bundle.get("sources"):
        source_intro = "berdasarkan sumber berita yang tersimpan"
    if topic_type == "rupiah_explainer":
        opening = (
            "Pembuka singkat\n"
            "Rupiah dan Dolar AS sering menjadi perhatian pembaca Indonesia karena keduanya terkait dengan harga impor, sentimen pasar, dan arah kebijakan moneter."
        )
        what_happened = (
            "Apa yang terjadi?\n"
            f"{source_intro.capitalize()}, topik ini membahas faktor yang dapat memengaruhi hubungan Rupiah, Dolar AS, The Fed, dan Bank Indonesia."
        )
        why_important = (
            "Mengapa ini penting untuk Rupiah?\n"
            "Perubahan ekspektasi terhadap suku bunga, inflasi, dan permintaan Dolar AS dapat memengaruhi cara pasar menilai Rupiah."
        )
        factors = (
            "Faktor yang perlu dipantau\n"
            "- Komunikasi Bank Indonesia dan The Fed.\n"
            "- Data inflasi dan indikator ekonomi utama.\n"
            "- Sentimen global terhadap aset berisiko dan Dolar AS."
        )
        impact = (
            "Apa dampaknya bagi pembaca Indonesia?\n"
            "Konteks ini dapat membantu pembaca memahami mengapa berita global dapat terasa dekat dengan kebutuhan sehari-hari, terutama saat Rupiah menjadi perhatian pasar."
        )
    elif topic_type == "macro_event_watch":
        opening = (
            "Pembuka singkat\n"
            "Agenda makro seperti CPI, NFP, FOMC, dan komunikasi The Fed sering menjadi perhatian pasar valuta asing, termasuk pasangan USD/IDR."
        )
        what_happened = (
            "Apa yang terjadi?\n"
            f"{source_intro.capitalize()}, pasar mencermati agenda data dan kebijakan yang dapat memengaruhi Dolar AS serta sentimen terhadap Rupiah."
        )
        why_important = (
            "Mengapa ini penting untuk Rupiah?\n"
            "Ekspektasi terhadap kebijakan The Fed dapat memengaruhi permintaan Dolar AS, sementara Rupiah juga dipengaruhi oleh faktor domestik dan komunikasi Bank Indonesia."
        )
        factors = (
            "Faktor yang perlu dipantau\n"
            "- Rilis CPI, NFP, dan agenda FOMC dari sumber resmi.\n"
            "- Nada komunikasi The Fed dan respons pasar terhadap Dolar AS.\n"
            "- Kebijakan Bank Indonesia dan sentimen terhadap Rupiah."
        )
        impact = (
            "Apa dampaknya bagi pembaca Indonesia?\n"
            "Pembaca dapat menggunakan konteks ini untuk memahami mengapa berita ekonomi AS berpotensi menjadi perhatian dalam pembahasan Rupiah dan USD/IDR."
        )
    else:
        opening = (
            "Pembuka singkat\n"
            "USD/IDR kembali menjadi perhatian pembaca Indonesia seiring pasar mencermati Rupiah, Dolar AS, dan sentimen global."
        )
        what_happened = (
            "Apa yang terjadi?\n"
            f"{source_intro.capitalize()}, pergerakan Rupiah terhadap Dolar AS perlu dipantau bersama faktor domestik dan eksternal."
        )
        why_important = (
            "Mengapa ini penting untuk Rupiah?\n"
            "Perubahan sentimen terhadap Dolar AS, arah kebijakan Bank Indonesia, dan agenda ekonomi global dapat memengaruhi perhatian pasar terhadap Rupiah."
        )
        factors = (
            "Faktor yang perlu dipantau\n"
            "- Sentimen terhadap Dolar AS dan ekspektasi kebijakan The Fed.\n"
            "- Komunikasi Bank Indonesia dan data ekonomi domestik.\n"
            "- Berita global yang dapat memengaruhi arus modal dan minat risiko."
        )
        impact = (
            "Apa dampaknya bagi pembaca Indonesia?\n"
            "Informasi ini membantu pembaca mengikuti konteks USD/IDR tanpa menganggap arah pasar sebagai hal yang sudah tentu."
        )

    return "\n\n".join(
        [
            opening,
            what_happened,
            why_important,
            factors,
            impact,
            faq_for_template(topic_type),
            source_section(topic_row, source_bundle=source_bundle),
            RISK_DISCLAIMER,
        ]
    )


def render_article_template(
    topic_row: Dict[str, Any],
    template: Optional[str] = None,
    source_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    topic_type = str(template or topic_row.get("topic_type") or "").strip()
    if topic_type not in SUPPORTED_ARTICLE_TEMPLATES:
        return json_safe(unsupported_template_error(topic_type))

    title = template_title(topic_type)
    summary = template_summary(topic_type)
    body = body_for_template(topic_type, topic_row, source_bundle=source_bundle)
    seo_title = title
    seo_description = re.sub(r"\s+", " ", summary).strip()

    return json_safe(
        {
            "success": True,
            "template": topic_type,
            "title": title,
            "summary": summary,
            "body": body,
            "seo_title": seo_title,
            "seo_description": seo_description,
            "risk_disclaimer_included": True,
            "sources_json": build_source_trace(topic_row, source_bundle=source_bundle),
        }
    )
