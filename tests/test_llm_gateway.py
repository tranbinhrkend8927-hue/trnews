import json

from llm_gateway import LLMGateway, MockLLMProvider
from llm_schemas import BASIC_JSON_SCHEMA, validate_json_schema


def _messages():
    return [
        {"role": "system", "content": "Return JSON."},
        {"role": "user", "content": "Say ok."},
    ]


def test_lightweight_schema_validation_supports_required_and_types():
    valid = validate_json_schema({"message": "ok"}, BASIC_JSON_SCHEMA)
    missing = validate_json_schema({}, BASIC_JSON_SCHEMA)
    wrong_type = validate_json_schema({"message": 123}, BASIC_JSON_SCHEMA)

    assert valid == {"valid": True, "errors": []}
    assert missing["valid"] is False
    assert missing["errors"][0]["path"] == "message"
    assert wrong_type["valid"] is False
    assert wrong_type["errors"][0]["message"] == "Expected string, got integer"


def test_mock_provider_success_returns_json():
    gateway = LLMGateway(provider=MockLLMProvider())

    result = gateway.generate_json("test_task", _messages(), BASIC_JSON_SCHEMA)

    assert result["success"] is True
    assert result["provider"] == "mock"
    assert result["model"] == "mock-model"
    assert result["task_name"] == "test_task"
    assert result["output"] == {"message": "ok"}
    assert result["error"] is None
    assert "latency_ms" in result


def test_gateway_result_is_json_serializable():
    result = LLMGateway(provider=MockLLMProvider()).generate_json("test_task", _messages(), BASIC_JSON_SCHEMA)

    dumped = json.dumps(result, ensure_ascii=False)

    assert "mock-model" in dumped


def test_invalid_json_returns_invalid_json_error():
    result = LLMGateway(provider=MockLLMProvider(mode="invalid_json")).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is False
    assert result["error"]["type"] == "invalid_json"


def test_schema_validation_failure_returns_structured_error():
    result = LLMGateway(provider=MockLLMProvider(mode="schema_validation_error")).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is False
    assert result["error"]["type"] == "schema_validation_error"


def test_timeout_returns_timeout_error():
    result = LLMGateway(provider=MockLLMProvider(mode="timeout")).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is False
    assert result["error"]["type"] == "timeout"


def test_api_error_returns_api_error():
    result = LLMGateway(provider=MockLLMProvider(mode="api_error")).generate_json(
        "test_task",
        _messages(),
        BASIC_JSON_SCHEMA,
    )

    assert result["success"] is False
    assert result["error"]["type"] == "api_error"


def test_retry_count_is_controlled():
    provider = MockLLMProvider(
        responses=[
            {"success": False, "error": {"type": "timeout", "message": "first", "retryable": True}},
            {"success": True, "content": {"message": "after retry"}, "raw_response": {}, "usage": {}},
        ]
    )
    gateway = LLMGateway(provider=provider, max_retries=1)

    result = gateway.generate_json("retry_task", _messages(), BASIC_JSON_SCHEMA)

    assert result["success"] is True
    assert result["output"] == {"message": "after retry"}
    assert provider.call_count == 2


def test_retry_stops_when_limit_is_reached():
    provider = MockLLMProvider(
        responses=[
            {"success": False, "error": {"type": "timeout", "message": "first", "retryable": True}},
            {"success": True, "content": {"message": "should not run"}, "raw_response": {}, "usage": {}},
        ]
    )

    result = LLMGateway(provider=provider, max_retries=0).generate_json("retry_task", _messages(), BASIC_JSON_SCHEMA)

    assert result["success"] is False
    assert result["error"]["type"] == "timeout"
    assert provider.call_count == 1


def test_missing_provider_returns_config_error():
    result = LLMGateway(provider=object()).generate_json("test_task", _messages(), BASIC_JSON_SCHEMA)

    assert result["success"] is False
    assert result["error"]["type"] == "config_error"


def test_gateway_does_not_leak_api_key_from_config_or_raw_response():
    secret = "unit-secret-value"
    provider = MockLLMProvider(
        responses=[
            {
                "success": True,
                "content": {"message": "ok"},
                "raw_response": {"debug": secret, "headers": {"authorization": "Bearer " + secret}},
                "usage": {},
            }
        ]
    )

    result = LLMGateway(provider=provider).generate_json(
        "secret_task",
        _messages(),
        BASIC_JSON_SCHEMA,
        config={"api_key": secret},
    )
    dumped = json.dumps(result, ensure_ascii=False)

    assert secret not in dumped
    assert "authorization" not in dumped.lower()


def test_gateway_does_not_call_openrouter_by_default():
    result = LLMGateway(provider=MockLLMProvider()).generate_json("test_task", _messages(), BASIC_JSON_SCHEMA)

    assert result["provider"] == "mock"
