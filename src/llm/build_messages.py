"""Build chat messages from central prompt definitions."""

import json
from typing import Any, Dict

from .model_policies import canonical_task_name
from .prompt_renderer import PromptRenderer
from .prompts import fx_article_id, market_alert, rss_summary
from .prompts.global_prompt import GLOBAL_SYSTEM_PROMPT, PROMPT_VERSION as GLOBAL_PROMPT_VERSION
from .types import LLMConfigError, PromptBuildResult


TASK_PROMPTS = {
    "fx_article_id": fx_article_id,
    "rss_summary": rss_summary,
    "market_alert": market_alert,
}


def build_messages(task_name: str, input_data: Dict[str, Any]) -> PromptBuildResult:
    canonical = canonical_task_name(task_name)
    if canonical in {"article_draft", "article_review"}:
        input_data = dict(input_data or {})
        language_profile = input_data.get("language_profile") or {}
        language = str(input_data.get("language") or language_profile.get("language") or "").strip()
        if not language:
            raise LLMConfigError(
                f"language or language_profile.language is required for {canonical}.",
                task_name=canonical,
            )
        rendered = PromptRenderer().render(canonical, language, input_data)
        return PromptBuildResult(
            task_name=rendered.task,
            prompt_version=rendered.prompt_version,
            messages=rendered.messages,
        )

    if canonical == "json_extract":
        module = rss_summary
    else:
        module = TASK_PROMPTS.get(canonical)
    if module is None:
        raise LLMConfigError(f"Unknown LLM prompt task: {task_name}", task_name=task_name)

    input_data = dict(input_data or {})
    validator = getattr(module, "validate_input", None)
    if validator:
        error = validator(input_data)
        if error:
            raise LLMConfigError(
                error.get("message") or "Invalid LLM task input.",
                task_name=canonical,
                prompt_version=getattr(module, "PROMPT_VERSION", None),
                details=error,
            )

    task_prompt = getattr(module, "TASK_SYSTEM_PROMPT", "")
    system_content = "\n".join(part for part in [GLOBAL_SYSTEM_PROMPT, task_prompt] if part)
    user_payload = module.build_user_payload(input_data)
    prompt_version = f"{GLOBAL_PROMPT_VERSION}+{module.PROMPT_VERSION}"
    return PromptBuildResult(
        task_name=canonical,
        prompt_version=prompt_version,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True)},
        ],
    )
