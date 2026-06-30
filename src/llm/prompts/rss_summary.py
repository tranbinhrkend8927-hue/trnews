"""Prompt for RSS item summarization."""

from typing import Any, Dict, Optional


PROMPT_VERSION = "rss_summary@2026-06-30"
TASK_NAME = "rss_summary"
TASK_SYSTEM_PROMPT = "Tugas: ringkas input RSS secara faktual, singkat, dan tidak menambahkan informasi baru."


def validate_input(input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not input_data:
        return {"type": "missing_input", "message": "input_data is required.", "retryable": False}
    return None


def build_user_payload(input_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task": "Ringkas item RSS.",
        "rss_item": input_data.get("rss_item") or input_data,
        "output_constraints": {"use_only_input": True, "concise": True},
    }
