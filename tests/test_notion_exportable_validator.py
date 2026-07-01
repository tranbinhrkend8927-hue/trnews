from tests.test_article_schema import valid_article

from src.content.validators.notion_exportable import validate_notion_exportable


def test_valid_article_is_notion_exportable():
    result = validate_notion_exportable(valid_article())

    assert result.passed is True
    assert result.exportable is True


def test_empty_title_fails():
    result = validate_notion_exportable(valid_article(title=""))

    assert result.passed is False
    assert result.exportable is False
    assert any(issue.field == "title" for issue in result.issues)


def test_empty_body_fails():
    result = validate_notion_exportable(valid_article(body=""))

    assert result.passed is False
    assert any(issue.field == "body" for issue in result.issues)


def test_empty_sources_used_fails():
    result = validate_notion_exportable(valid_article(sources_used=[]))

    assert result.passed is False
    assert any(issue.field == "sources_used" for issue in result.issues)


def test_empty_risk_disclaimer_fails():
    result = validate_notion_exportable(valid_article(risk_disclaimer=""))

    assert result.passed is False
    assert any(issue.field == "risk_disclaimer" for issue in result.issues)
