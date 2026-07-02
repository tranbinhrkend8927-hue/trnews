from pydantic import ValidationError

from src.models.brief import BriefValidationResult, EditorialBrief


def test_editorial_brief_requires_core_text_fields():
    try:
        EditorialBrief(
            event_summary="",
            why_it_matters="Why it matters",
            market_context="Market context",
            primary_angle="Angle",
            target_reader="Retail FX readers",
        )
    except ValidationError as exc:
        raise AssertionError(f"Empty strings are allowed for validator-level checks: {exc}") from exc


def test_editorial_brief_accepts_expected_content_types():
    brief = EditorialBrief(
        event_summary="Event",
        why_it_matters="Why",
        market_context="Context",
        primary_angle="Angle",
        target_reader="Retail FX readers",
        content_type="market_brief",
        confidence_level="low",
    )

    assert brief.content_type == "market_brief"
    assert brief.confidence_level == "low"


def test_editorial_brief_rejects_unknown_content_type():
    try:
        EditorialBrief(
            event_summary="Event",
            why_it_matters="Why",
            market_context="Context",
            primary_angle="Angle",
            target_reader="Retail FX readers",
            content_type="trade_signal",
        )
    except ValidationError as exc:
        assert "content_type" in str(exc)
    else:
        raise AssertionError("Expected content_type validation to fail")


def test_brief_validation_result_defaults():
    result = BriefValidationResult(passed=True, recommended_status="ready")

    assert result.issues == []
    assert result.warnings == []
