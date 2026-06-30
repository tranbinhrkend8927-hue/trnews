"""Compatibility exports for legacy LLM configuration helpers."""

from src.llm.config import (
    get_openrouter_api_key,
    json_safe,
    load_openrouter_config,
)

__all__ = [
    "get_openrouter_api_key",
    "json_safe",
    "load_openrouter_config",
]
