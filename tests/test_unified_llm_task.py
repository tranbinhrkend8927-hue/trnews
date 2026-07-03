import json

import pytest

from src.llm.build_messages import build_messages
from src.llm.client import OpenAICompatibleClient
from src.llm.model_policies import get_model_policy
from src.llm.run_task import generate_article, generate_article_stream, run_llm_task
from src.llm.types import LLMConfigError, LLMJSONParseError


class FakeResponsesClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def with_options(self, **kwargs):
        self.options = kwargs
        return self

    @property
    def responses(self):
        return self

    @responses.setter
    def responses(self, value):
        self._responses = value

    def create(self, **kwargs):
        self.calls.append({"json": kwargs, "timeout": getattr(self, "options", {}).get("timeout")})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def stream(self, **kwargs):
        self.calls.append({"json": kwargs, "stream": True})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeStream:
    def __init__(self, deltas, final_response=None):
        self.deltas = list(deltas)
        self.final_response = final_response or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        for delta in self.deltas:
            yield {"type": "response.output_text.delta", "delta": delta}
        yield {"type": "response.completed", "response": self.final_response}

    def get_final_response(self):
        return self.final_response


class FakeBadRequest(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.status_code = 400


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


def _article_draft_input_data():
    return {
        "language": "id",
        "article_brief": (
            "language: id\n"
            "risk_disclaimer: Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.\n"
            "SOURCE 1\n"
            "source_id: source-10\n"
            "news_id: 10\n"
            "title: USD/IDR dan CPI menjadi perhatian\n"
            "url: https://example.com/source-10\n"
            "provider: Example\n"
            "published_at: 2026-07-01T00:00:00Z\n"
            "content: Pasar mencermati data AS dan pergerakan Rupiah."
        ),
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
            "faq": [{"question": "Apa yang perlu dipantau pembaca?", "answer": "Pembaca perlu memantau data AS dan pergerakan Rupiah sesuai sumber."}],
            "sources_used": [
                {
                    "source_id": "source-10",
                    "news_id": "10",
                    "title": "USD/IDR dan CPI menjadi perhatian",
                    "url": "https://example.com/source-10",
                    "provider": "Example",
                    "published_at": "2026-07-01T00:00:00Z",
                }
            ],
            "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
            "uncertain_claims": [],
            "language": "id",
            "market": "forex",
            "symbol": "USDIDR",
            "article_type": "fx_news_explainer",
            "region": "Indonesia",
            "search_intent": "Memahami faktor yang memengaruhi USD/IDR",
            "primary_keyword": "USDIDR berita forex",
            "secondary_keywords": ["Rupiah", "dolar AS"],
            "candidate_titles": ["USD/IDR dan Rupiah: Faktor yang Perlu Dipantau"],
            "editorial_angle": "Menjelaskan faktor sumber tanpa saran transaksi.",
            "key_takeaways": ["Pasar mencermati data AS.", "Rupiah tetap menjadi fokus pembaca Indonesia."],
            "evergreen_context": "USD/IDR mencerminkan hubungan dolar AS dan Rupiah.",
            "editor_notes": [],
        },
        ensure_ascii=False,
    )


def _ai_review_json():
    return json.dumps(
        {
            "publish_readiness": "needs_edit",
            "scores": {
                "grounding": 70,
                "depth": 68,
                "readability": 82,
                "headline_quality": 80,
                "financial_safety": 90,
                "source_usefulness": 75,
            },
            "issues": [],
            "unsupported_claims": [],
            "overstatements": [],
            "missing_context": ["Needs more context."],
            "rewrite_suggestions": ["Add source-backed context."],
            "recommended_editor_action": "Send to editor with highlighted issues.",
        },
        ensure_ascii=False,
    )


def _review_input_data():
    return {
        "language": "id",
        "language_profile": {"language": "id"},
        "article": {
            "title": "USD/IDR bergerak setelah komentar bank sentral",
            "summary": "Ringkasan sumber.",
            "body": "Ikhtisar peristiwa\nBerita bersumber.\n\nSumber\nhttps://example.com/source-1\n\nCatatan risiko\nRisiko.",
            "sources_used": [{"source_id": "source-1", "url": "https://example.com/source-1"}],
        },
        "editorial_brief": {
            "event_summary": "USD/IDR source event.",
            "primary_angle": "Explain source event without trading advice.",
            "content_type": "deep_article",
            "confidence_level": "high",
        },
        "source_bundle": {
            "sources": [
                {
                    "source_id": "source-1",
                    "title": "Bank central update moves FX market",
                    "url": "https://example.com/source-1",
                }
            ],
        },
        "source_quality_report": {
            "overall_source_quality": "strong",
            "recommended_action": "write_article",
            "usable_source_count": 2,
        },
        "validation": {"article_schema": {"passed": True, "issues": []}},
    }


def _success_response(content=None):
    return {
        "output_text": content if content is not None else _article_json(),
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


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

    assert get_model_policy("fx_article_id").temperature == 0.2
    assert get_model_policy("article_draft").temperature == 0.2
    assert get_model_policy("article_draft").task_name == "article_draft"
    assert get_model_policy("article_review").temperature == 0.1
    assert get_model_policy("article_review").json_schema["required"][0] == "publish_readiness"
    assert get_model_policy("japan_fx_content").task_name == "fx_article_id"
    assert get_model_policy("rss_summary").temperature == 0.2
    assert get_model_policy("market_alert").temperature == 0.1
    assert get_model_policy("json_extract").temperature == 0.0


def test_run_llm_task_uses_policy_and_allowed_overrides(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeResponsesClient([_success_response()])
    client = OpenAICompatibleClient(client=session)

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
    assert payload["max_output_tokens"] == 321
    assert payload["top_p"] == 0.7
    assert payload["input"][0]["role"] == "system"
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["text"]["verbosity"] == "low"
    assert payload["text"]["format"]["type"] == "json_schema"


def test_run_llm_task_supports_article_review(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeResponsesClient([_success_response(_ai_review_json())])
    client = OpenAICompatibleClient(client=session)

    result = run_llm_task(
        "article_review",
        _review_input_data(),
        overrides={"temperature": 0.05, "max_tokens": 456},
        client=client,
    )

    assert result["success"] is True
    assert result["task_name"] == "article_review"
    assert result["prompt_version"] == "article_review@2026-07-02+id"
    assert result["output"]["publish_readiness"] == "needs_edit"
    payload = session.calls[0]["json"]
    assert payload["temperature"] == 0.05
    assert payload["max_output_tokens"] == 456
    assert payload["text"]["format"]["name"] == "article_review"


def test_generate_article_returns_parsed_dict(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeResponsesClient([_success_response()])
    client = OpenAICompatibleClient(client=session)

    result = generate_article(_article_draft_input_data(), client=client)

    assert result["title"] == "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau"
    payload = session.calls[0]["json"]
    assert "input" in payload
    assert "messages" not in payload
    assert payload["text"]["format"]["name"] == "article_draft"


def test_generate_article_stream_concatenates_output_text_deltas(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    article_text = _article_json()
    stream = FakeStream(
        [article_text[:40], article_text[40:]],
        final_response={"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    )
    session = FakeResponsesClient([stream])
    client = OpenAICompatibleClient(client=session)

    result = generate_article_stream(_article_draft_input_data(), client=client)

    assert result["language"] == "id"
    assert session.calls[0]["stream"] is True
    assert session.calls[0]["json"]["text"]["format"]["type"] == "json_schema"


def test_responses_client_retries_without_unsupported_sampling_params(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeResponsesClient(
        [
            FakeBadRequest("Unsupported parameter: 'temperature' is not supported with this model."),
            _success_response(),
        ]
    )
    client = OpenAICompatibleClient(client=session)

    result = run_llm_task("fx_article_id", _input_data(), client=client)

    assert result["success"] is True
    assert "temperature" in session.calls[0]["json"]
    assert "temperature" not in session.calls[1]["json"]


def test_api_errors_redact_api_key_fragments(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeResponsesClient([FakeBadRequest("Incorrect API key provided: sk-a3c88********aaf8.")])
    client = OpenAICompatibleClient(client=session)

    with pytest.raises(Exception) as exc_info:
        run_llm_task("fx_article_id", _input_data(), client=client)

    dumped = json.dumps(exc_info.value.to_dict(), ensure_ascii=False)
    assert "sk-a3c88" not in dumped
    assert "[REDACTED]" in dumped


def test_run_llm_task_article_review_schema_failure(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeResponsesClient([_success_response(json.dumps({"publish_readiness": "ready"}))])
    client = OpenAICompatibleClient(client=session)

    with pytest.raises(Exception) as exc_info:
        run_llm_task("article_review", _review_input_data(), client=client)

    assert getattr(exc_info.value, "error_type", "") == "schema_validation_error"


def test_run_llm_task_rejects_blocked_overrides(monkeypatch):
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")

    with pytest.raises(LLMConfigError) as exc_info:
        run_llm_task("fx_article_id", _input_data(), overrides={"api_key": "blocked"})

    assert exc_info.value.error_type == "config_error"
    assert "api_key" in exc_info.value.details["blocked_fields"]


def test_invalid_json_error_includes_task_and_prompt_version(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeResponsesClient([_success_response("not json")])
    client = OpenAICompatibleClient(client=session)

    with pytest.raises(LLMJSONParseError) as exc_info:
        run_llm_task("fx_article_id", _input_data(), client=client)

    assert exc_info.value.task_name == "fx_article_id"
    assert exc_info.value.prompt_version == "global@2026-06-30+fx_article_id@2026-06-30"
    assert exc_info.value.error_type == "invalid_json"
