import json

import pytest

from src.llm.build_messages import build_messages
from src.llm.client import OpenAICompatibleClient
from src.llm.model_policies import get_model_policy
from src.llm.run_task import run_llm_task
from src.llm.types import LLMConfigError, LLMJSONParseError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _source_bundle():
    return {
        "topic_id": 1,
        "topic_type": "macro_event_watch",
        "symbol": "USDIDR",
        "source_news_ids": [10],
        "sources": [
            {
                "news_id": 10,
                "symbol": "USDIDR",
                "title": "USD/IDR dan CPI menjadi perhatian",
                "summary": "Pasar mencermati data AS.",
                "content": "Pasar mencermati data AS dan pergerakan Rupiah.",
                "url": "https://example.com/source-10",
                "source": "Example",
                "published_at": None,
                "locale": "id",
            }
        ],
        "missing_source_news_ids": [],
        "warnings": [],
        "errors": [],
    }


def _input_data():
    return {
        "topic": {
            "id": 1,
            "symbol": "USDIDR",
            "topic_type": "macro_event_watch",
            "title": "USD/IDR Bergerak Menjelang Data AS",
            "status": "candidate",
        },
        "source_bundle": _source_bundle(),
        "language_profile": {
            "language": "id",
            "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
        },
        "template_hint": "unit-test",
    }


def _article_json():
    return json.dumps(
        {
            "title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau",
            "slug": "usd-idr-rupiah-faktor",
            "summary": "Ringkasan edukatif berdasarkan sumber tersimpan.",
            "body": "Pembuka\n\nSumber\nURL: https://example.com/source-10\n\nCatatan risiko\nArtikel ini hanya untuk informasi dan edukasi.",
            "seo_title": "USD/IDR dan Rupiah",
            "seo_description": "Konteks USD/IDR untuk pembaca Indonesia.",
            "faq": [],
            "sources_used": [{"news_id": 10, "title": "USD/IDR dan CPI menjadi perhatian"}],
            "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
            "uncertain_claims": [],
            "language": "id",
        },
        ensure_ascii=False,
    )


def _success_response(content=None):
    return FakeResponse(
        200,
        {
            "choices": [{"message": {"content": content if content is not None else _article_json()}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def test_build_messages_has_versioned_prompts():
    result = build_messages("fx_article_id", _input_data())

    assert result.task_name == "fx_article_id"
    assert result.prompt_version == "global@2026-06-30+fx_article_id@2026-06-30"
    assert [message["role"] for message in result.messages] == ["system", "user"]
    assert "Gunakan hanya informasi dari source_bundle." in result.messages[0]["content"]


def test_legacy_japan_fx_content_aliases_to_indonesian_fx_article():
    result = build_messages("japan_fx_content", _input_data())

    assert result.task_name == "fx_article_id"
    assert result.prompt_version == "global@2026-06-30+fx_article_id@2026-06-30"


def test_model_policies_hold_task_temperatures(monkeypatch):
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")

    assert get_model_policy("fx_article_id").temperature == 0.35
    assert get_model_policy("japan_fx_content").task_name == "fx_article_id"
    assert get_model_policy("rss_summary").temperature == 0.2
    assert get_model_policy("market_alert").temperature == 0.1
    assert get_model_policy("json_extract").temperature == 0.0


def test_run_llm_task_uses_policy_and_allowed_overrides(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeSession([_success_response()])
    client = OpenAICompatibleClient(session=session)

    result = run_llm_task(
        "fx_article_id",
        _input_data(),
        overrides={"temperature": 0.11, "max_tokens": 321, "top_p": 0.7},
        client=client,
    )

    assert result["success"] is True
    assert result["task_name"] == "fx_article_id"
    assert result["prompt_version"] == "global@2026-06-30+fx_article_id@2026-06-30"
    assert result["output"]["language"] == "id"
    payload = session.calls[0]["json"]
    assert payload["model"] == "unit-model"
    assert payload["temperature"] == 0.11
    assert payload["max_tokens"] == 321
    assert payload["top_p"] == 0.7
    assert payload["response_format"]["type"] == "json_schema"


def test_run_llm_task_rejects_blocked_overrides(monkeypatch):
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")

    with pytest.raises(LLMConfigError) as exc_info:
        run_llm_task("fx_article_id", _input_data(), overrides={"api_key": "blocked"})

    assert exc_info.value.error_type == "config_error"
    assert "api_key" in exc_info.value.details["blocked_fields"]


def test_invalid_json_error_includes_task_and_prompt_version(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeSession([_success_response("not json")])
    client = OpenAICompatibleClient(session=session)

    with pytest.raises(LLMJSONParseError) as exc_info:
        run_llm_task("fx_article_id", _input_data(), client=client)

    assert exc_info.value.task_name == "fx_article_id"
    assert exc_info.value.prompt_version == "global@2026-06-30+fx_article_id@2026-06-30"
    assert exc_info.value.error_type == "invalid_json"
