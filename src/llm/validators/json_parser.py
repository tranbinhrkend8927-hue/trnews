"""JSON parsing helpers for LLM task outputs."""

import json
from typing import Any, Optional

from ..types import LLMJSONParseError


def parse_llm_json(content: Any, *, task_name: str, prompt_version: str) -> Any:
    if isinstance(content, (dict, list)):
        return content
    if not isinstance(content, str):
        raise LLMJSONParseError(
            "LLM response content is not JSON-compatible.",
            task_name=task_name,
            prompt_version=prompt_version,
            details={"content_type": type(content).__name__},
        )
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        preview = content[:500]
        raise LLMJSONParseError(
            f"LLM returned invalid JSON for task '{task_name}' using prompt '{prompt_version}': {exc.msg}",
            task_name=task_name,
            prompt_version=prompt_version,
            details={"line": exc.lineno, "column": exc.colno, "content_preview": preview},
        ) from exc
