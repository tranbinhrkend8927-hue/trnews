import json

import pytest

from src.jobs import smoke_test


def test_default_smoke_test_success(capsys):
    exit_code = smoke_test.smoke_test_command(["--market", "usd_idr_id"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "SMOKE_TEST_PASSED"
    assert payload["steps"]


def test_smoke_test_does_not_call_real_llm(monkeypatch, capsys):
    called = []

    class GuardLLM:
        def __init__(self):
            called.append("init")

    monkeypatch.setattr(smoke_test, "LLMTaskRunner", GuardLLM)

    exit_code = smoke_test.smoke_test_command(["--market", "usd_idr_id"])

    assert exit_code == 0
    assert called == []


def test_smoke_test_does_not_write_notion(monkeypatch, capsys):
    class GuardExporter(smoke_test.NotionDryRunExporter):
        def export(self, **kwargs):
            raise AssertionError("smoke test must not write Notion")

    monkeypatch.setattr(smoke_test, "NotionDryRunExporter", GuardExporter)

    assert smoke_test.smoke_test_command(["--market", "usd_idr_id"]) == 0


def test_include_notion_preview(capsys):
    smoke_test.smoke_test_command(["--market", "usd_idr_id", "--include-notion-preview"])
    payload = json.loads(capsys.readouterr().out)

    assert any(step["name"] == "notion_preview" and step["success"] for step in payload["steps"])


def test_use_real_tradingview_parameter_selects_adapter(monkeypatch, capsys):
    called = []

    class FakeRealAdapter:
        def fetch(self, market):
            called.append(market.id)
            return smoke_test._FakeTradingViewAdapter().fetch(market)

    monkeypatch.setattr(smoke_test, "TradingViewNewsAdapter", FakeRealAdapter)

    exit_code = smoke_test.smoke_test_command(["--market", "usd_idr_id", "--use-real-tradingview"])

    assert exit_code == 0
    assert called == ["usd_idr_id"]


def test_use_real_llm_parameter_selects_runner(monkeypatch, capsys):
    called = []

    class FakeLLM:
        def __init__(self):
            called.append("init")

        def run(self, **kwargs):
            from src.llm.result import LLMTaskResult

            return LLMTaskResult(success=False, task=kwargs["task"], language=kwargs["language"], output=None, error={"type": "fake", "message": "fake failure"})

    monkeypatch.setattr(smoke_test, "LLMTaskRunner", FakeLLM)

    exit_code = smoke_test.smoke_test_command(["--market", "usd_idr_id", "--use-real-llm"])

    assert exit_code == 1
    assert called == ["init"]


def test_output_steps(capsys):
    smoke_test.smoke_test_command(["--market", "usd_idr_id"])
    payload = json.loads(capsys.readouterr().out)

    assert [step["name"] for step in payload["steps"]]


def test_failure_exit_code_1(monkeypatch, capsys):
    monkeypatch.setattr(smoke_test, "validate_config_registry", lambda registry: type("Result", (), {"success": False, "errors": ["bad"], "warnings": []})())

    exit_code = smoke_test.smoke_test_command(["--market", "usd_idr_id"])

    assert exit_code == 1


def test_argument_error_exit_code_2(capsys):
    exit_code = smoke_test.smoke_test_command(["--market", "missing"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "SMOKE_TEST_ARGUMENT_ERROR"
