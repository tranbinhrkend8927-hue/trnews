from src.models.brief import EditorialBrief
from src.planning.brief_validator import validate_editorial_brief


def _brief(**overrides):
    data = {
        "event_summary": "USD/IDR moved after a source headline.",
        "why_it_matters": "It matters for FX readers.",
        "market_context": "Macro context should be explained carefully.",
        "primary_angle": "Explain what happened without trading advice.",
        "reader_questions": ["What happened?"],
        "must_cover": ["Source event", "Risk disclaimer"],
        "avoid_claims": ["No investment advice"],
        "recommended_structure": ["Ikhtisar peristiwa", "Sumber", "Catatan risiko"],
        "target_reader": "Retail FX readers",
        "content_type": "deep_article",
        "confidence_level": "high",
    }
    data.update(overrides)
    return EditorialBrief(**data)


def test_validate_complete_brief_passes():
    result = validate_editorial_brief(_brief())

    assert result.passed is True
    assert result.recommended_status == "ready"
    assert result.issues == []


def test_validate_missing_core_text_field_requires_rewrite():
    result = validate_editorial_brief(_brief(event_summary=""))

    assert result.passed is False
    assert result.recommended_status == "needs_brief_rewrite"
    assert any(issue.field == "event_summary" for issue in result.issues)


def test_validate_missing_list_field_requires_rewrite():
    result = validate_editorial_brief(_brief(reader_questions=[]))

    assert result.passed is False
    assert result.recommended_status == "needs_brief_rewrite"
    assert any(issue.field == "reader_questions" for issue in result.issues)


def test_validate_low_confidence_deep_article_needs_manual_review():
    result = validate_editorial_brief(_brief(confidence_level="low"))

    assert result.passed is True
    assert result.recommended_status == "needs_manual_review"
    assert any(issue.code == "low_confidence" for issue in result.issues)


def test_validate_market_brief_recommends_brief_only():
    result = validate_editorial_brief(_brief(content_type="market_brief", confidence_level="low"))

    assert result.passed is True
    assert result.recommended_status == "write_brief_only"


def test_validate_source_gaps_warn_for_deep_article():
    result = validate_editorial_brief(_brief(source_gaps=["not_enough_usable_sources_for_deep_article"]))

    assert result.passed is True
    assert result.recommended_status == "ready"
    assert any(issue.code == "source_gaps_for_deep_article" for issue in result.issues)
