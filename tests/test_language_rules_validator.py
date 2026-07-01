from tests.test_article_schema import valid_article

from src.content.validators.language_rules import validate_language_rules


def language_profile(**overrides):
    data = {
        "language": "id",
        "required_sections": ["Sumber", "Catatan risiko"],
        "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi.",
        "seo": {
            "title_max_length": 70,
            "description_max_length": 170,
        },
    }
    data.update(overrides)
    return data


def test_valid_indonesian_article_passes():
    result = validate_language_rules(valid_article(), language_profile())

    assert result.passed is True
    assert result.exportable is True


def test_language_mismatch_fails():
    result = validate_language_rules(valid_article(language="ja"), language_profile())

    assert result.passed is False
    assert any(issue.code == "language_mismatch" for issue in result.issues)


def test_missing_required_section_fails():
    article = valid_article(body="Sumber\nhttps://example.com/a\n\nTanpa bagian risiko.")

    result = validate_language_rules(article, language_profile())

    assert result.passed is False
    assert any(issue.code == "missing_required_section" for issue in result.issues)


def test_risk_disclaimer_mismatch_fails():
    article = valid_article(risk_disclaimer="Disclaimer lain.")

    result = validate_language_rules(article, language_profile())

    assert result.passed is False
    assert any(issue.code == "risk_disclaimer_mismatch" for issue in result.issues)


def test_seo_title_too_long_fails():
    article = valid_article(seo_title="x" * 71)

    result = validate_language_rules(article, language_profile())

    assert result.passed is False
    assert any(issue.code == "seo_title_too_long" for issue in result.issues)


def test_seo_description_too_long_fails():
    article = valid_article(seo_description="x" * 171)

    result = validate_language_rules(article, language_profile())

    assert result.passed is False
    assert any(issue.code == "seo_description_too_long" for issue in result.issues)
