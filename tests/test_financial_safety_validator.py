from tests.test_article_schema import valid_article
from tests.test_language_rules_validator import language_profile

from src.content.validators.financial_safety import validate_financial_safety


def test_plain_risk_disclaimer_article_passes():
    result = validate_financial_safety(valid_article(), language_profile())

    assert result.passed is True
    assert result.exportable is True


def test_guaranteed_profit_phrases_fail():
    article = valid_article(body="Sumber\nhttps://example.com/a\n\nCatatan risiko\npasti untung dan 利益保証.")

    result = validate_financial_safety(article, language_profile())

    assert result.passed is False
    assert result.exportable is False
    assert any(issue.code == "profit_promise" for issue in result.issues)


def test_buy_sell_instruction_phrases_fail():
    article = valid_article(body="Sumber\nhttps://example.com/a\n\nCatatan risiko\nbuy now atau beli sekarang.")

    result = validate_financial_safety(article, language_profile())

    assert result.passed is False
    assert any(issue.code == "buy_sell_instruction" for issue in result.issues)


def test_missing_risk_disclaimer_fails_not_exportable():
    article = valid_article(risk_disclaimer="")

    result = validate_financial_safety(article, language_profile())

    assert result.passed is False
    assert result.exportable is False
    assert any(issue.code == "missing_risk_disclaimer" for issue in result.issues)
