from tests.test_article_schema import valid_article

from src.content.validators.source_grounding import validate_source_grounding


def source_bundle():
    return {
        "bundle_id": "bundle-1",
        "market_id": "usd_idr_id",
        "symbol": "USDIDR",
        "language": "id",
        "sources": [
            {
                "source_id": "src-1",
                "news_id": "101",
                "title": "USD/IDR moves after Fed comments",
                "url": "https://example.com/a",
                "canonical_url": "https://example.com/a",
                "provider": "TradingView",
            }
        ],
    }


def test_valid_sources_used_passes():
    result = validate_source_grounding(valid_article(), source_bundle())

    assert result.passed is True
    assert result.exportable is True


def test_unknown_source_id_fails():
    article = valid_article(sources_used=[{"source_id": "src-x", "news_id": "101", "title": "Unknown"}])

    result = validate_source_grounding(article, source_bundle())

    assert result.passed is False
    assert result.exportable is False
    assert any(issue.code == "unknown_source_id" for issue in result.issues)


def test_unknown_news_id_fails():
    article = valid_article(sources_used=[{"source_id": "src-1", "news_id": "999", "title": "Known source"}])

    result = validate_source_grounding(article, source_bundle())

    assert result.passed is False
    assert any(issue.code == "unknown_news_id" for issue in result.issues)


def test_unknown_url_fails():
    article = valid_article(
        sources_used=[
            {
                "source_id": "src-1",
                "news_id": "101",
                "title": "Known source",
                "url": "https://example.com/unknown",
            }
        ]
    )

    result = validate_source_grounding(article, source_bundle())

    assert result.passed is False
    assert any(issue.code == "unknown_source_url" for issue in result.issues)


def test_body_unknown_url_fails():
    article = valid_article(body="Sumber\nhttps://example.com/not-in-bundle\n\nCatatan risiko\nRisiko.")

    result = validate_source_grounding(article, source_bundle())

    assert result.passed is False
    assert any(issue.code == "unknown_body_url" for issue in result.issues)


def test_empty_sources_used_fails():
    result = validate_source_grounding(valid_article(sources_used=[]), source_bundle())

    assert result.passed is False
    assert result.exportable is False
    assert any(issue.code == "missing_sources_used" for issue in result.issues)
