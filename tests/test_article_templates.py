import json
import re

import article_templates


def _topic(**overrides):
    row = {
        "id": 1,
        "symbol": "USDIDR",
        "topic_type": "daily_usdidr_update",
        "title": "USD/IDR Hari Ini",
        "status": "candidate",
        "reason_json": {
            "matched_keywords": ["USD/IDR", "rupiah", "dolar AS"],
            "source_news_ids": [10, 11],
        },
        "source_news_ids": [10, 11],
    }
    row.update(overrides)
    return row


def _render(topic_type):
    return article_templates.render_article_template(_topic(topic_type=topic_type))


def _source_bundle(**overrides):
    bundle = {
        "topic_id": 1,
        "topic_type": "daily_usdidr_update",
        "symbol": "USDIDR",
        "source_news_ids": [10],
        "sources": [
            {
                "news_id": 10,
                "symbol": "USDIDR",
                "title": "Rupiah bergerak terhadap Dolar AS",
                "summary": "Pasar mencermati Dolar AS dan Rupiah.",
                "content": None,
                "url": "https://example.com/rupiah",
                "canonical_url": None,
                "source": "Example News",
                "source_url": None,
                "published_at": None,
                "fetched_at": None,
                "locale": "id",
            }
        ],
        "missing_source_news_ids": [],
        "warnings": [],
        "errors": [],
        "reason_json": {"source_news_ids": [10]},
        "source_trace": {"topic_status": "candidate"},
    }
    bundle.update(overrides)
    return bundle


def assert_safe_template(result):
    body = result["body"].lower()

    assert result["success"] is True
    assert "faq" in body
    assert "sumber" in body
    assert "catatan risiko" in body
    assert result["risk_disclaimer_included"] is True
    assert "beli sekarang" not in body
    assert "jual sekarang" not in body
    assert "take profit" not in body
    assert "stop loss" not in body
    assert "dijamin profit" not in body
    assert "pasti untung" not in body
    assert "pasti" not in body
    assert "dijamin" not in body
    assert "wajib beli" not in body
    assert "segera jual" not in body
    assert not re.search(r"USD/IDR\s+\d", result["body"])
    assert not re.search(r"\d+(?:[.,]\d+)?\s*%", result["body"])
    assert json.loads(json.dumps(result, ensure_ascii=False))["success"] is True


def test_daily_usdidr_update_generates_indonesian_draft_content():
    result = _render("daily_usdidr_update")

    assert result["template"] == "daily_usdidr_update"
    assert "Rupiah" in result["title"]
    assert "Pembuka singkat" in result["body"]
    assert "Apa yang terjadi?" in result["body"]
    assert "Mengapa ini penting untuk Rupiah?" in result["body"]
    assert "Apa dampaknya bagi pembaca Indonesia?" in result["body"]
    assert_safe_template(result)


def test_rupiah_explainer_generates_indonesian_draft_content():
    result = _render("rupiah_explainer")

    assert result["template"] == "rupiah_explainer"
    assert "Mengapa Rupiah" in result["title"]
    assert "Dolar AS" in result["body"]
    assert_safe_template(result)


def test_macro_event_watch_generates_indonesian_draft_content():
    result = _render("macro_event_watch")

    assert result["template"] == "macro_event_watch"
    assert "CPI" in result["body"]
    assert "FOMC" in result["body"]
    assert "The Fed" in result["body"]
    assert_safe_template(result)


def test_bank_indonesia_watch_returns_structured_unsupported_error():
    result = article_templates.render_article_template(_topic(topic_type="bank_indonesia_watch"))

    assert result["success"] is False
    assert result["error"]["code"] == "unsupported_topic_type"
    assert result["error"]["topic_type"] == "bank_indonesia_watch"


def test_unknown_topic_type_returns_structured_unsupported_error():
    result = article_templates.render_article_template(_topic(topic_type="unknown_topic"))

    assert result["success"] is False
    assert result["error"]["code"] == "unsupported_topic_type"
    assert result["error"]["topic_type"] == "unknown_topic"


def test_sources_json_tracks_source_news_ids_reason_json_and_source_trace():
    result = article_templates.render_article_template(
        _topic(reason_json={"source_news_ids": [22], "source_urls": ["https://example.com/news"]}, source_news_ids=[])
    )

    assert result["sources_json"]["topic_id"] == 1
    assert result["sources_json"]["topic_type"] == "daily_usdidr_update"
    assert result["sources_json"]["source_news_ids"] == [22]
    assert result["sources_json"]["reason_json"]["source_news_ids"] == [22]
    assert result["sources_json"]["source_trace"]["source_urls"] == ["https://example.com/news"]
    assert "URL: https://example.com/news" in result["body"]


def test_source_section_does_not_fabricate_urls():
    result = article_templates.render_article_template(_topic(reason_json={"source_news_ids": [7]}, source_news_ids=[]))

    assert "Source news IDs: 7" in result["body"]
    assert "URL sumber tidak tersedia" in result["body"]
    assert "https://" not in result["body"]


def test_source_section_uses_source_bundle_title_and_url():
    result = article_templates.render_article_template(_topic(), source_bundle=_source_bundle())

    assert "Source news ID 10: Rupiah bergerak terhadap Dolar AS" in result["body"]
    assert "URL: https://example.com/rupiah" in result["body"]
    assert result["sources_json"]["sources"][0]["title"] == "Rupiah bergerak terhadap Dolar AS"
    assert result["sources_json"]["sources"][0]["url"] == "https://example.com/rupiah"


def test_source_section_with_only_news_id_does_not_fabricate_metadata():
    bundle = _source_bundle(
        sources=[
            {
                "news_id": 12,
                "symbol": "USDIDR",
                "title": None,
                "summary": None,
                "content": None,
                "url": None,
                "canonical_url": None,
                "source": None,
                "source_url": None,
                "published_at": None,
                "fetched_at": None,
                "locale": "id",
            }
        ],
        source_news_ids=[12],
    )

    result = article_templates.render_article_template(_topic(source_news_ids=[12]), source_bundle=bundle)

    assert "Source news ID 12" in result["body"]
    assert "URL:" not in result["body"]
