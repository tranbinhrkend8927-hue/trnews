from src.llm import task_runner
from src.llm.task_runner import LLMTaskRunner
from src.llm.types import LLMJSONParseError


def test_run_llm_task_success_returns_result(monkeypatch):
    def fake_run_llm_task(task, input_data, overrides=None):
        return {
            "success": True,
            "model": "unit-model",
            "task_name": task,
            "prompt_version": "article_draft@unit+id",
            "output": {"title": "Unit article"},
            "usage": {"total_tokens": 10},
            "latency_ms": 12,
        }

    monkeypatch.setattr(task_runner, "run_llm_task", fake_run_llm_task)

    result = LLMTaskRunner().run(
        task="article_draft",
        language="id",
        profile="article_writer_id",
        input_data={"source_bundle": {}},
    )

    assert result.success is True
    assert result.output == {"title": "Unit article"}
    assert result.task == "article_draft"
    assert result.language == "id"
    assert result.profile == "article_writer_id"
    assert result.model == "unit-model"


def test_run_llm_task_exception_returns_failure(monkeypatch):
    def fake_run_llm_task(task, input_data, overrides=None):
        raise LLMJSONParseError("bad json", task_name=task, prompt_version="unit")

    monkeypatch.setattr(task_runner, "run_llm_task", fake_run_llm_task)

    result = LLMTaskRunner().run(
        task="article_draft",
        language="id",
        profile="article_writer_id",
        input_data={},
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.type
    assert result.error.type == "llm_json_parse_error"
