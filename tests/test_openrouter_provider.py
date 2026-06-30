import json

import pytest
import requests

from news_pipeline.llm_config import load_openrouter_config
from news_pipeline.llm_gateway import LLMGateway
from news_pipeline.llm_providers.openrouter import OpenRouterProvider
from news_pipeline.llm_schemas import BASIC_JSON_SCHEMA


def _messages():
    return [
        {"role": "system", "content": "Return JSON."},
        {"role": "user", "content": "Say ok."},
    ]


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


def _success_response(content='{"message": "ok"}'):
    return FakeResponse(
        200,
        {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def test_missing_openrouter_api_key_returns_config_error(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    provider = OpenRouterProvider(session=FakeSession([]))

    result = LLMGateway(provider=provider).generate_json("test_task", _messages(), BASIC_JSON_SCHEMA)

    assert result["success"] is False
    assert result["provider"] == "openrouter"
    assert result["error"]["type"] == "config_error"


def test_config_output_does_not_include_api_key(monkeypatch):
    key = "unit-key-value"
    monkeypatch.setenv("LLM_API_KEY", key)
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    result = load_openrouter_config()
    dumped = json.dumps(result, ensure_ascii=False)

    assert result["success"] is True
    assert result["config"]["has_api_key"] is True
    assert result["config"]["base_url"] == "https://openrouter.ai/api/v1"
    assert "api_key" not in result["config"]
    assert key not in dumped


def test_config_reads_generic_llm_base_url(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm-gateway.example/v1/")

    result = load_openrouter_config()

    assert result["success"] is True
    assert result["config"]["base_url"] == "https://llm-gateway.example/v1"


def test_legacy_openrouter_env_vars_still_work_as_fallback(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "legacy-unit-key")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "legacy-unit-model")

    result = load_openrouter_config()

    assert result["success"] is True
    assert result["config"]["model"] == "legacy-unit-model"
    assert result["config"]["has_api_key"] is True


def test_missing_model_returns_config_error(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_DEFAULT_MODEL", raising=False)
    provider = OpenRouterProvider(session=FakeSession([]))

    result = LLMGateway(provider=provider).generate_json("test_task", _messages(), BASIC_JSON_SCHEMA)

    assert result["success"] is False
    assert result["error"]["type"] == "config_error"


def test_mock_http_success_parses_structured_json_and_uses_timeout(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeSession([_success_response()])
    provider = OpenRouterProvider(session=session)

    result = LLMGateway(provider=provider).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
        config={"timeout_seconds": 3, "max_retries": 0},
    )

    assert result["success"] is True
    assert result["provider"] == "openrouter"
    assert result["model"] == "unit-model"
    assert result["output"] == {"message": "ok"}
    assert result["usage"]["total_tokens"] == 2
    assert session.calls[0]["timeout"] == 3
    assert session.calls[0]["json"]["response_format"]["type"] == "json_schema"


def test_request_key_is_not_copied_into_result(monkeypatch):
    key = "unit-key-value"
    monkeypatch.setenv("LLM_API_KEY", key)
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeSession([_success_response()])

    result = LLMGateway(provider=OpenRouterProvider(session=session)).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )
    dumped = json.dumps(result, ensure_ascii=False)

    assert key not in dumped
    assert "Authorization" in session.calls[0]["headers"]


def test_mock_http_content_non_json_returns_invalid_json(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")

    result = LLMGateway(provider=OpenRouterProvider(session=FakeSession([_success_response("not json")]))).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is False
    assert result["error"]["type"] == "invalid_json"


def test_mock_http_body_non_json_returns_invalid_json(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    response = FakeResponse(200, ValueError("not json"), text="not json")

    result = LLMGateway(provider=OpenRouterProvider(session=FakeSession([response]))).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is False
    assert result["error"]["type"] == "invalid_json"


def test_mock_http_timeout_returns_timeout(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeSession([requests.exceptions.Timeout("timeout"), requests.exceptions.Timeout("timeout")])

    result = LLMGateway(provider=OpenRouterProvider(session=session)).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
        config={"max_retries": 1},
    )

    assert result["success"] is False
    assert result["error"]["type"] == "timeout"
    assert len(session.calls) == 2


@pytest.mark.parametrize("status_code", [401, 403])
def test_http_auth_errors_do_not_retry(monkeypatch, status_code):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeSession([FakeResponse(status_code, {"error": {"message": "auth failed"}})])

    result = LLMGateway(provider=OpenRouterProvider(session=session)).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
        config={"max_retries": 2},
    )

    assert result["success"] is False
    assert result["error"]["type"] == "api_error"
    assert len(session.calls) == 1


@pytest.mark.parametrize("status_code", [429, 500])
def test_transient_errors_retry(monkeypatch, status_code):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    session = FakeSession(
        [
            FakeResponse(status_code, {"error": {"message": "temporary"}}),
            _success_response(),
        ]
    )

    result = LLMGateway(provider=OpenRouterProvider(session=session)).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
        config={"max_retries": 1},
    )

    assert result["success"] is True
    assert len(session.calls) == 2


def test_schema_validation_failure_returns_structured_error(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")

    result = LLMGateway(provider=OpenRouterProvider(session=FakeSession([_success_response('{"other": "value"}')]))).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is False
    assert result["error"]["type"] == "schema_validation_error"


def test_openrouter_result_is_json_serializable(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")

    result = LLMGateway(provider=OpenRouterProvider(session=FakeSession([_success_response()]))).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )
    dumped = json.dumps(result, ensure_ascii=False)

    assert "openrouter" in dumped


def test_mock_provider_does_not_call_real_openrouter(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    session = FakeSession([_success_response()])

    LLMGateway(provider=OpenRouterProvider(session=session)).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert session.calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"


def test_provider_uses_generic_llm_base_url(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm-gateway.example/v1")
    session = FakeSession([_success_response()])

    result = LLMGateway(provider=OpenRouterProvider(session=session)).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is True
    assert session.calls[0]["url"] == "https://llm-gateway.example/v1/chat/completions"


def test_provider_allows_explicit_endpoint_override(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm-gateway.example/v1")
    session = FakeSession([_success_response()])

    result = LLMGateway(
        provider=OpenRouterProvider(
            session=session,
            endpoint="https://direct-endpoint.example/custom/chat/completions",
        )
    ).generate_json("test_task", _messages(), BASIC_JSON_SCHEMA)

    assert result["success"] is True
    assert session.calls[0]["url"] == "https://direct-endpoint.example/custom/chat/completions"


def test_provider_accepts_base_url_that_already_includes_chat_completions(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unit-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "unit-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm-gateway.example/v1/chat/completions")
    session = FakeSession([_success_response()])

    result = LLMGateway(provider=OpenRouterProvider(session=session)).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is True
    assert session.calls[0]["url"] == "https://llm-gateway.example/v1/chat/completions"
