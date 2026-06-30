import json

import llm_article_prompts
from language_profiles import get_language_profile


def _topic():
    return {
        "id": 1,
        "symbol": "USDIDR",
        "topic_type": "macro_event_watch",
        "title": "USD/IDR Bergerak Menjelang Data AS",
        "status": "candidate",
    }


def _source_bundle(**overrides):
    bundle = {
        "topic_id": 1,
        "topic_type": "macro_event_watch",
        "symbol": "USDIDR",
        "source_news_ids": [10],
        "sources": [
            {
                "news_id": 10,
                "title": "USD/IDR dan CPI menjadi perhatian",
                "summary": "Pasar mencermati data AS.",
                "url": "https://example.com/source-10",
                "source": "Example",
                "published_at": None,
            }
        ],
        "missing_source_news_ids": [],
        "warnings": [],
        "errors": [],
    }
    bundle.update(overrides)
    return bundle


def _messages_text(result):
    return "\n".join(message["content"] for message in result["messages"])


def test_build_messages_with_sources():
    profile = get_language_profile("id")["profile"]

    result = llm_article_prompts.build_llm_article_messages(_topic(), _source_bundle(), profile)

    assert result["success"] is True
    assert [message["role"] for message in result["messages"]] == ["system", "user"]
    assert result["error"] is None


def test_build_messages_without_sources_returns_structured_error():
    profile = get_language_profile("id")["profile"]

    result = llm_article_prompts.build_llm_article_messages(_topic(), _source_bundle(sources=[]), profile)

    assert result["success"] is False
    assert result["messages"] == []
    assert result["error"]["type"] == "missing_sources"


def test_system_message_contains_financial_safety_rules():
    profile = get_language_profile("id")["profile"]
    text = _messages_text(llm_article_prompts.build_llm_article_messages(_topic(), _source_bundle(), profile))

    assert "Gunakan hanya informasi dari source_bundle." in text
    assert "Jangan membuat angka, harga, kurs, tingkat suku bunga, CPI, NFP, FOMC, atau tanggal yang tidak tersedia di source_bundle." in text
    assert "Jangan memberikan rekomendasi beli/jual, target profit, stop loss, atau janji keuntungan." in text
    assert "Dilarang memberikan instruksi beli atau jual." in text
    assert "Dilarang menulis take profit atau stop loss." in text
    assert "Dilarang menjanjikan keuntungan" in text


def test_prompt_requires_bahasa_indonesia_json_sources_and_risk_sections():
    profile = get_language_profile("id")["profile"]
    text = _messages_text(llm_article_prompts.build_llm_article_messages(_topic(), _source_bundle(), profile))

    assert "Bahasa artikel harus Bahasa Indonesia." in text
    assert "Output harus berupa JSON valid saja." in text
    assert "Jangan output Markdown." in text
    assert "Body harus memuat paragraf atau bagian berjudul Sumber." in text
    assert "Body harus memuat paragraf atau bagian berjudul Catatan risiko." in text
    assert profile["risk_disclaimer"] in text


def test_user_message_contains_topic_source_bundle_and_template_hint():
    profile = get_language_profile("id")["profile"]
    result = llm_article_prompts.build_llm_article_messages(
        _topic(),
        _source_bundle(),
        profile,
        template_hint="daily_usdidr_update",
    )
    payload = json.loads(result["messages"][1]["content"])

    assert payload["topic"]["id"] == 1
    assert payload["source_bundle"]["sources"][0]["title"] == "USD/IDR dan CPI menjadi perhatian"
    assert payload["template_hint"] == "daily_usdidr_update"


def test_prompt_output_is_json_serializable():
    profile = get_language_profile("id")["profile"]
    result = llm_article_prompts.build_llm_article_messages(_topic(), _source_bundle(), profile)

    dumped = json.dumps(result, ensure_ascii=False)

    assert "source_bundle" in dumped
