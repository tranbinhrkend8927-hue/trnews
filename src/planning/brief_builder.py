from __future__ import annotations

from typing import Any

from src.models.brief import EditorialBrief


def build_editorial_brief(
    *,
    market: Any,
    language_profile: dict[str, Any],
    source_bundle: dict[str, Any],
) -> EditorialBrief:
    """Build a conservative deterministic brief from sources and quality metadata."""
    compact_sources = [source for source in list(source_bundle.get("sources") or []) if isinstance(source, dict)]
    source_quality = source_bundle.get("source_quality_report") if isinstance(source_bundle.get("source_quality_report"), dict) else {}
    symbol = str(source_bundle.get("symbol") or getattr(market, "symbol", "") or "").strip()
    market_name = _market_name(market, source_bundle)
    content_type = _content_type(source_bundle, source_quality)
    confidence_level = _confidence_level(source_quality, compact_sources)
    source_gaps = _source_gaps(source_quality, compact_sources)
    lead_source = compact_sources[0] if compact_sources else {}
    lead_title = _source_title(lead_source)
    target_reader = language_profile.get("audience") or "Retail FX readers who need context before interpreting market news."

    return EditorialBrief(
        event_summary=_event_summary(symbol, lead_title, compact_sources),
        why_it_matters=_why_it_matters(symbol, market_name, content_type),
        market_context=_market_context(symbol, market_name),
        primary_angle=_primary_angle(symbol, lead_title, content_type),
        reader_questions=_reader_questions(symbol, content_type),
        must_cover=_must_cover(symbol, compact_sources, source_quality, content_type),
        avoid_claims=_avoid_claims(source_gaps),
        source_gaps=source_gaps,
        recommended_structure=_recommended_structure(content_type),
        target_reader=target_reader,
        content_type=content_type,
        confidence_level=confidence_level,
        editorial_notes=_editorial_notes(source_quality, source_gaps, content_type),
    )


def format_editorial_brief_for_prompt(brief: EditorialBrief) -> str:
    """Render a structured EditorialBrief into the legacy article_brief string format."""
    lines = [
        "EDITORIAL_BRIEF:",
        f"content_type: {brief.content_type}",
        f"confidence_level: {brief.confidence_level}",
        f"target_reader: {brief.target_reader}",
        f"event_summary: {brief.event_summary}",
        f"why_it_matters: {brief.why_it_matters}",
        f"market_context: {brief.market_context}",
        f"primary_angle: {brief.primary_angle}",
        _list_section("reader_questions", brief.reader_questions),
        _list_section("must_cover", brief.must_cover),
        _list_section("avoid_claims", brief.avoid_claims),
        _list_section("source_gaps", brief.source_gaps),
        _list_section("recommended_structure", brief.recommended_structure),
        _list_section("editorial_notes", brief.editorial_notes),
    ]
    return "\n".join(line for line in lines if line).strip()


def _content_type(source_bundle: dict[str, Any], source_quality: dict[str, Any]) -> str:
    override = source_bundle.get("content_type_override")
    if override == "market_brief":
        return "market_brief"
    action = source_quality.get("recommended_action")
    if action == "write_brief_only":
        return "market_brief"
    if action == "skip_or_manual_review":
        return "news_update"
    return "deep_article"


def _confidence_level(source_quality: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    quality = source_quality.get("overall_source_quality")
    if quality == "strong":
        return "high"
    if quality == "acceptable":
        return "medium"
    if quality in ("weak", "insufficient"):
        return "low"
    return "medium" if sources else "low"


def _source_gaps(source_quality: dict[str, Any], sources: list[dict[str, Any]]) -> list[str]:
    gaps = [str(item) for item in source_quality.get("source_gaps") or []]
    if not sources:
        gaps.append("no_sources_available")
    if source_quality.get("duplicate_count", 0):
        gaps.append("duplicate_sources_present")
    return _unique(gaps)


def _event_summary(symbol: str, lead_title: str, sources: list[dict[str, Any]]) -> str:
    if lead_title:
        return f"{symbol} coverage is based on the latest source headline: {lead_title}."
    if sources:
        return f"{symbol} coverage is based on the available market news sources."
    return f"No usable source event is available for {symbol}."


def _why_it_matters(symbol: str, market_name: str, content_type: str) -> str:
    if content_type == "market_brief":
        return f"The item may help readers track {symbol}, but source depth is limited, so the article should stay brief."
    return f"The event may affect how readers interpret {symbol} within {market_name}, but implications must stay source-grounded."


def _market_context(symbol: str, market_name: str) -> str:
    return f"{symbol} should be explained within {market_name} context, including macro data, central-bank signals, risk sentiment, and source limitations when relevant."


def _primary_angle(symbol: str, lead_title: str, content_type: str) -> str:
    if content_type == "market_brief":
        return f"Summarize what is known about {symbol} and clearly state what cannot be concluded from the current sources."
    if lead_title:
        return f"Use the latest headline as the entry point, then explain why it matters for {symbol} without giving trading advice."
    return f"Explain the available {symbol} news cautiously and flag missing source detail."


def _reader_questions(symbol: str, content_type: str) -> list[str]:
    if content_type == "market_brief":
        return [
            f"What happened in the latest {symbol} source?",
            "What information is still missing?",
            "What should readers monitor next without treating it as a trade signal?",
        ]
    return [
        f"What happened in the latest {symbol} news?",
        "Why does it matter for FX readers?",
        "What market context helps readers interpret the event?",
        "What risks or uncertainties should readers keep in mind?",
    ]


def _must_cover(symbol: str, sources: list[dict[str, Any]], source_quality: dict[str, Any], content_type: str) -> list[str]:
    items = [
        f"The concrete source event for {symbol}.",
        "Source attribution and publication context.",
        "Risk disclaimer and no investment advice.",
    ]
    if content_type == "deep_article":
        items.extend(
            [
                "Relevant macro or market background supported by sources.",
                "Potential implications stated as possibilities, not certainty.",
                "Reader-focused questions and FAQ.",
            ]
        )
    if source_quality.get("overall_source_quality") in ("weak", "insufficient"):
        items.append("Source limitations and missing context.")
    if not sources:
        items.append("Manual review requirement before writing.")
    return items


def _avoid_claims(source_gaps: list[str]) -> list[str]:
    claims = [
        "Do not give buy, sell, long, or short recommendations.",
        "Do not state price targets or guaranteed outcomes.",
        "Do not turn correlation into causation.",
        "Do not add unsourced macro background as fact.",
    ]
    if source_gaps:
        claims.append("Do not present the article as deep analysis when source gaps are material.")
    return claims


def _recommended_structure(content_type: str) -> list[str]:
    if content_type == "market_brief":
        return ["Ikhtisar singkat", "Konteks pembaca", "Batasan informasi", "Sumber", "Catatan risiko"]
    if content_type == "news_update":
        return ["Apa yang diketahui", "Apa yang belum jelas", "Sumber", "Catatan risiko"]
    return ["Ikhtisar peristiwa", "Latar belakang", "Dampak pasar", "Hal yang perlu dipantau", "FAQ", "Sumber", "Catatan risiko"]


def _editorial_notes(source_quality: dict[str, Any], source_gaps: list[str], content_type: str) -> list[str]:
    notes = []
    if content_type == "market_brief":
        notes.append("Keep the article brief because source quality does not support a deep article.")
    if source_gaps:
        notes.append("Make source gaps visible to the editor and avoid unsupported expansion.")
    if source_quality:
        notes.append(f"Source quality: {source_quality.get('overall_source_quality', 'unknown')}; action: {source_quality.get('recommended_action', 'unknown')}.")
    return notes


def _market_name(market: Any, source_bundle: dict[str, Any]) -> str:
    content = getattr(market, "content", None)
    return str(source_bundle.get("market") or getattr(content, "market", "") or "the relevant FX market")


def _source_title(source: dict[str, Any]) -> str:
    return str(source.get("title") or source.get("original_title") or "").strip()


def _list_section(name: str, values: list[str]) -> str:
    if not values:
        return f"{name}:"
    return "\n".join([f"{name}:"] + [f"- {value}" for value in values])


def _unique(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
