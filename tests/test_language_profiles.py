import json

import language_profiles


def test_indonesian_profile_success():
    result = language_profiles.get_language_profile("id")

    assert result["success"] is True
    assert result["language"] == "id"
    assert result["profile"]["market"] == "Indonesia"
    assert "risk_disclaimer" in result["profile"]
    assert result["error"] is None


def test_unsupported_language_returns_structured_error():
    result = language_profiles.get_language_profile("ja")

    assert result["success"] is False
    assert result["language"] == "ja"
    assert result["profile"] is None
    assert result["error"] == {
        "type": "unsupported_language",
        "message": "Unsupported language: ja",
        "retryable": False,
    }


def test_language_profile_output_is_json_serializable():
    result = language_profiles.get_language_profile("id")

    dumped = json.dumps(result, ensure_ascii=False)

    assert "Indonesia" in dumped
