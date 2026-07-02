from dataclasses import dataclass, field

from src.planning.brief_builder import build_editorial_brief, format_editorial_brief_for_prompt


@dataclass
class _Content:
    market: str = "forex_idr"


@dataclass
class _Market:
    symbol: str = "USDIDR"
    content: _Content = field(default_factory=_Content)


def _source_bundle(**overrides):
    bundle = {
        "symbol": "USDIDR",
        "sources": [
            {
                "source_id": "s1",
                "title": "USD/IDR moves after Fed comments",
                "url": "https://example.com/s1",
                "provider": "Example",
            }
        ],
        "source_quality_report": {
            "overall_source_quality": "strong",
            "recommended_action": "write_article",
            "usable_source_count": 2,
            "source_gaps": [],
        },
    }
    bundle.update(overrides)
    return bundle


def test_build_editorial_brief_for_strong_sources():
    brief = build_editorial_brief(
        market=_Market(),
        language_profile={"audience": "Indonesian retail FX readers"},
        source_bundle=_source_bundle(),
    )

    assert brief.content_type == "deep_article"
    assert brief.confidence_level == "high"
    assert "USD/IDR moves after Fed comments" in brief.event_summary
    assert brief.target_reader == "Indonesian retail FX readers"
    assert "Do not give buy, sell, long, or short recommendations." in brief.avoid_claims
    assert "FAQ" in brief.recommended_structure


def test_build_editorial_brief_downgrades_weak_sources_to_market_brief():
    brief = build_editorial_brief(
        market=_Market(),
        language_profile={},
        source_bundle=_source_bundle(
            source_quality_report={
                "overall_source_quality": "weak",
                "recommended_action": "write_brief_only",
                "source_gaps": ["not_enough_usable_sources_for_deep_article"],
            }
        ),
    )

    assert brief.content_type == "market_brief"
    assert brief.confidence_level == "low"
    assert "not_enough_usable_sources_for_deep_article" in brief.source_gaps
    assert any("brief" in note.lower() for note in brief.editorial_notes)
    assert "Batasan informasi" in brief.recommended_structure


def test_build_editorial_brief_handles_no_sources():
    brief = build_editorial_brief(
        market=_Market(),
        language_profile={},
        source_bundle=_source_bundle(
            sources=[],
            source_quality_report={
                "overall_source_quality": "insufficient",
                "recommended_action": "skip_or_manual_review",
                "source_gaps": ["no_usable_source_content"],
            },
        ),
    )

    assert brief.content_type == "news_update"
    assert brief.confidence_level == "low"
    assert "no_sources_available" in brief.source_gaps
    assert "No usable source event" in brief.event_summary


def test_format_editorial_brief_for_prompt_contains_structured_fields():
    brief = build_editorial_brief(market=_Market(), language_profile={}, source_bundle=_source_bundle())
    text = format_editorial_brief_for_prompt(brief)

    assert "EDITORIAL_BRIEF:" in text
    assert "content_type: deep_article" in text
    assert "event_summary:" in text
    assert "reader_questions:" in text
    assert "recommended_structure:" in text
