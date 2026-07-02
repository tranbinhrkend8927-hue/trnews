import pytest
from pydantic import ValidationError

from src.content.article_schema import ArticleDraft, article_draft_json_schema
from src.content.validators.article_schema import validate_article_schema


def valid_article(**overrides):
    data = {
        "title": "USD/IDR bergerak hati-hati",
        "slug": "usd-idr-bergerak-hati-hati",
        "summary": "Ringkasan berdasarkan sumber.",
        "body": "Pembuka.\n\nSumber\nhttps://example.com/a\n\nCatatan risiko\nArtikel ini hanya untuk informasi dan edukasi.",
        "seo_title": "USD/IDR bergerak hati-hati",
        "seo_description": "Konteks USD/IDR berdasarkan sumber.",
        "language": "id",
        "market": "Indonesia",
        "symbol": "USDIDR",
        "article_type": "fx_news_explainer",
        "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi.",
        "region": "id-ID",
        "search_intent": "Memahami berita USD/IDR dan faktor yang perlu dipantau.",
        "primary_keyword": "USDIDR berita forex",
        "secondary_keywords": ["USDIDR", "rupiah", "dolar AS"],
        "candidate_titles": ["USD/IDR bergerak hati-hati", "Apa arti berita terbaru bagi USD/IDR?"],
        "editorial_angle": "Menjelaskan konteks pasar untuk pembaca ritel.",
        "key_takeaways": ["Pasar mencermati komentar bank sentral."],
        "evergreen_context": "USD/IDR dipengaruhi data ekonomi, kebijakan moneter, dan sentimen risiko.",
        "editor_notes": [{"type": "readability", "text": "Periksa kejelasan pembuka."}],
        "faq": [{"question": "Apa yang terjadi?", "answer": "Pasar mencermati sumber."}],
        "sources_used": [
            {
                "source_id": "src-1",
                "news_id": "101",
                "title": "USD/IDR moves after Fed comments",
                "url": "https://example.com/a",
            }
        ],
        "uncertain_claims": [{"claim": "Arah pasar belum pasti", "reason": "Data terbatas", "severity": "low"}],
    }
    data.update(overrides)
    return data


def test_valid_article_draft_can_be_created():
    article = ArticleDraft(**valid_article())

    assert article.title == "USD/IDR bergerak hati-hati"
    assert article.sources_used[0].source_id == "src-1"
    assert article.primary_keyword == "USDIDR berita forex"
    assert article.editor_notes[0].type == "readability"
    assert validate_article_schema(valid_article()).passed is True


def test_missing_title_fails():
    data = valid_article()
    data.pop("title")

    with pytest.raises(ValidationError):
        ArticleDraft(**data)
    result = validate_article_schema(data)
    assert result.passed is False
    assert result.exportable is False
    assert any(issue.field == "title" for issue in result.issues)


def test_faq_item_missing_question_fails():
    data = valid_article(faq=[{"answer": "Jawaban tanpa pertanyaan."}])

    result = validate_article_schema(data)

    assert result.passed is False
    assert any(issue.field == "faq.0.question" for issue in result.issues)


def test_sources_used_item_missing_source_id_fails():
    data = valid_article(sources_used=[{"title": "Missing source id"}])

    result = validate_article_schema(data)

    assert result.passed is False
    assert any(issue.field == "sources_used.0.source_id" for issue in result.issues)


def test_article_draft_json_schema_contains_required_fields():
    schema = article_draft_json_schema()

    assert isinstance(schema, dict)
    assert "title" in schema["required"]
    assert "sources_used" not in schema["required"]
    assert "search_intent" in schema["properties"]
