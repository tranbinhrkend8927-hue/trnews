import pytest

from src.llm.build_messages import build_messages
from src.llm.prompt_renderer import PromptRenderer
from src.llm.types import LLMConfigError


def _input_data(language="id"):
    required_sections = ["Sumber", "Catatan risiko"] if language == "id" else ["情報源", "リスクに関する注記"]
    risk_disclaimer = (
        "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi."
        if language == "id"
        else "本記事は情報提供のみを目的としており、投資助言ではありません。"
    )
    return {
        "article_brief": "\n".join(
            [
                "TASK: Write a short grounded ArticleDraft for this market.",
                f"language: {language}",
                "MERGED_SOURCES:",
                "SOURCE 1",
                "source_id: source-1",
                "title: Bank central update moves FX market",
            ]
        ),
        "market": {
            "market_id": f"unit_{language}",
            "symbol": "USDIDR" if language == "id" else "USDJPY",
            "market": "Indonesia" if language == "id" else "Japan",
        },
        "language_profile": {
            "language": language,
            "required_sections": required_sections,
            "risk_disclaimer": risk_disclaimer,
        },
        "source_bundle": {
            "source_bundle_hash": "unit-hash",
            "sources": [
                {
                    "source_id": "source-1",
                    "title": "Bank central update moves FX market",
                    "url": "https://example.com/source-1",
                }
            ],
        },
    }


def test_article_draft_id_loads_indonesian_system_prompt():
    rendered = PromptRenderer().render("article_draft", "id", _input_data("id"))

    assert rendered.task == "article_draft"
    assert rendered.language == "id"
    assert "Bahasa Indonesia" in rendered.messages[0]["content"]
    assert "不要给投资建议" in rendered.messages[0]["content"]


def test_article_draft_ja_loads_japanese_system_prompt():
    rendered = PromptRenderer().render("article_draft", "ja", _input_data("ja"))

    assert rendered.task == "article_draft"
    assert rendered.language == "ja"
    assert "日本語の金融編集者" in rendered.messages[0]["content"]
    assert "情報源" in rendered.messages[0]["content"]


def test_rendered_prompt_has_system_and_user_messages_with_source_data():
    rendered = PromptRenderer().render("article_draft", "id", _input_data("id"))

    assert [message["role"] for message in rendered.messages] == ["system", "user"]
    assert "MERGED_SOURCES" in rendered.messages[1]["content"]
    assert "Bank central update moves FX market" in rendered.messages[1]["content"]
    assert "source-1" in rendered.messages[1]["content"]


def test_prompt_version_is_non_empty():
    rendered = PromptRenderer().render("article_draft", "id", _input_data("id"))

    assert rendered.prompt_version == "article_draft@2026-06-30+id"


def test_missing_required_input_field_raises_clear_error():
    input_data = _input_data("id")
    input_data.pop("article_brief")

    with pytest.raises(LLMConfigError) as exc_info:
        PromptRenderer().render("article_draft", "id", input_data)

    assert "article_brief" in str(exc_info.value)
    assert exc_info.value.details["missing_fields"] == ["article_brief"]


def test_unknown_language_raises_clear_error():
    with pytest.raises(LLMConfigError) as exc_info:
        PromptRenderer().render("article_draft", "zz", _input_data("id"))

    assert "language system prompt file is missing" in str(exc_info.value)
    assert "zz.system.md" in str(exc_info.value)


def test_unknown_task_raises_clear_error():
    with pytest.raises(LLMConfigError) as exc_info:
        PromptRenderer().render("unknown_task", "id", _input_data("id"))

    assert "Prompt task does not exist" in str(exc_info.value)


def test_build_messages_supports_article_draft_and_keeps_legacy_alias():
    rendered = build_messages("article_draft", _input_data("id"))
    legacy = build_messages("japan_fx_content", _legacy_input_data())

    assert rendered.task_name == "article_draft"
    assert rendered.prompt_version == "article_draft@2026-06-30+id"
    assert [message["role"] for message in rendered.messages] == ["system", "user"]
    assert legacy.task_name == "fx_article_id"


def _legacy_input_data():
    return {
        "source_bundle": {
            "sources": [
                {
                    "news_id": 10,
                    "symbol": "USDIDR",
                    "title": "USD/IDR source",
                    "url": "https://example.com/source-10",
                }
            ]
        },
        "language_profile": {
            "language": "id",
            "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi.",
        },
    }
