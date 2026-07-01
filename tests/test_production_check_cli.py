import json

from src.jobs import production_check


def test_market_check_success(capsys):
    exit_code = production_check.production_check_command(["--market", "usd_idr_id"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "PRODUCTION_CHECK_PASSED"
    assert payload["checked_markets"] == ["usd_idr_id"]


def test_enabled_only_check_success(capsys):
    exit_code = production_check.production_check_command(["--enabled-only"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checked_markets"]


def test_missing_market_exit_code_2(capsys):
    exit_code = production_check.production_check_command(["--market", "missing"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "PRODUCTION_CHECK_ARGUMENT_ERROR"


def test_require_real_llm_missing_env_fails(monkeypatch, capsys):
    monkeypatch.setattr(production_check, "load_local_env", lambda: {})
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_WRITER_MODEL", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)

    exit_code = production_check.production_check_command(["--market", "usd_idr_id", "--require-real-llm"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "PRODUCTION_CHECK_FAILED"


def test_require_notion_missing_env_fails(monkeypatch, capsys):
    monkeypatch.setattr(production_check, "load_local_env", lambda: {})
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.delenv("NOTION_DATA_SOURCE_ID_ID", raising=False)

    exit_code = production_check.production_check_command(["--market", "usd_idr_id", "--require-notion"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert any(error["type"] == "missing_env" for error in payload["errors"])


def test_prompt_and_notion_payload_are_checked(capsys):
    production_check.production_check_command(["--market", "usd_idr_id", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["checks"]["prompt"]["items"][0]["success"] is True
    assert payload["checks"]["notion_payload"]["items"][0]["success"] is True
    assert payload["checks"]["notion_payload"]["items"][0]["block_count"] > 0


def test_output_json_and_no_real_services(monkeypatch, capsys):
    calls = []

    class GuardRenderer(production_check.PromptRenderer):
        def render(self, *args, **kwargs):
            calls.append("prompt")
            return super().render(*args, **kwargs)

    monkeypatch.setattr(production_check, "PromptRenderer", GuardRenderer)

    exit_code = production_check.production_check_command(["--market", "usd_idr_id"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert isinstance(payload, dict)
    assert calls == ["prompt"]
