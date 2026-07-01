from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .types import LLMConfigError


DEFAULT_PROMPT_ROOT = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class RenderedPrompt:
    task: str
    language: str
    prompt_version: str
    messages: list[dict[str, str]]


class PromptRenderer:
    def __init__(self, prompt_root: str | Path | None = None):
        self.prompt_root = Path(prompt_root) if prompt_root is not None else DEFAULT_PROMPT_ROOT

    def render(self, task: str, language: str, input_data: dict[str, Any]) -> RenderedPrompt:
        task_name = str(task or "").strip()
        language_code = str(language or "").strip().lower()
        input_payload = dict(input_data or {})

        task_dir = self.prompt_root / task_name
        if not task_dir.exists() or not task_dir.is_dir():
            raise LLMConfigError(
                f"Prompt task does not exist: {task_name}",
                task_name=task_name,
                details={"prompt_dir": str(task_dir)},
            )

        spec_path = task_dir / "spec.yaml"
        system_path = task_dir / f"{language_code}.system.md"
        user_template_path = task_dir / "user_payload.jinja.md"
        for path, label in [
            (spec_path, "spec"),
            (system_path, "language system prompt"),
            (user_template_path, "user payload template"),
        ]:
            if not path.exists():
                raise LLMConfigError(
                    f"Prompt {label} file is missing: {path}",
                    task_name=task_name,
                    details={"path": str(path), "language": language_code},
                )

        spec = _parse_spec(spec_path, task_name=task_name)
        required_fields = spec.get("input_required") or []
        missing_fields = [field for field in required_fields if field not in input_payload]
        if missing_fields:
            raise LLMConfigError(
                "Prompt input is missing required field(s): " + ", ".join(missing_fields),
                task_name=task_name,
                prompt_version=str(spec.get("version") or ""),
                details={"missing_fields": missing_fields},
            )

        system_content = system_path.read_text(encoding="utf-8").strip()
        user_template = user_template_path.read_text(encoding="utf-8")
        user_content = _render_template(user_template, input_payload).strip()
        spec_version = str(spec.get("version") or task_name)

        return RenderedPrompt(
            task=task_name,
            language=language_code,
            prompt_version=f"{spec_version}+{language_code}",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
        )


def _parse_spec(path: Path, *, task_name: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        yaml = None

    try:
        data = yaml.safe_load(raw) if yaml is not None else json.loads(raw)
    except Exception as exc:  # pragma: no cover - parser exception depends on optional yaml.
        raise LLMConfigError(
            f"Unable to parse prompt spec: {path}",
            task_name=task_name,
            details={"path": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(data, dict):
        raise LLMConfigError(
            f"Prompt spec must contain a mapping: {path}",
            task_name=task_name,
            details={"path": str(path)},
        )
    return data


def _render_template(template: str, input_data: dict[str, Any]) -> str:
    json_pattern = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\|\s*tojson\s*}}")

    def replace_json(match: re.Match[str]) -> str:
        name = match.group(1)
        value = input_data.get(name)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)

    rendered = json_pattern.sub(replace_json, template)
    raw_pattern = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")

    def replace_raw(match: re.Match[str]) -> str:
        name = match.group(1)
        value = input_data.get(name)
        return "" if value is None else str(value)

    return raw_pattern.sub(replace_raw, rendered)
