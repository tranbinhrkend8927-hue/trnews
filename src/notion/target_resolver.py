from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel, Field


class ResolvedNotionTarget(BaseModel):
    name: str
    language: str
    market: str
    parent_type: str
    parent_id: Optional[str] = None
    status_default: str = "AI Draft"
    reviewer_status: str = "Needs Review"
    resolved_from_env: Optional[str] = None
    warnings: list[dict] = Field(default_factory=list)


class NotionTargetResolver:
    def __init__(self, config_registry):
        self.config_registry = config_registry

    def resolve(self, target_name: str) -> ResolvedNotionTarget:
        target = self.config_registry.notion_targets.targets.get(target_name)
        if target is None:
            raise ValueError(f"Unknown Notion target: {target_name}")

        parent_id, resolved_from_env, warnings = _resolve_parent_id(target)
        return ResolvedNotionTarget(
            name=target_name,
            language=target.language,
            market=target.market,
            parent_type=target.parent_type,
            parent_id=parent_id,
            status_default=target.status_default,
            reviewer_status=target.reviewer_status,
            resolved_from_env=resolved_from_env,
            warnings=warnings,
        )


def build_notion_parent_payload(target: ResolvedNotionTarget) -> dict:
    if target.parent_type == "data_source":
        return {"data_source_id": target.parent_id}
    if target.parent_type == "database":
        return {"database_id": target.parent_id}
    if target.parent_type == "page":
        return {"page_id": target.parent_id}
    raise ValueError(f"Unsupported Notion parent_type: {target.parent_type}")


def _resolve_parent_id(target) -> tuple[str | None, str | None, list[dict]]:
    primary_env, fallback_env = _env_names_for_parent(target)
    warnings: list[dict] = []
    primary_value = _env_value(primary_env)
    fallback_value = _env_value(fallback_env)
    if primary_env and primary_value:
        return primary_value, primary_env, warnings
    if fallback_env and fallback_value:
        warnings.append(
            {
                "type": "notion_parent_fallback_env",
                "missing_env": primary_env,
                "fallback_env": fallback_env,
            }
        )
        return fallback_value, fallback_env, warnings
    warnings.append(
        {
            "type": "missing_notion_parent_id",
            "parent_type": target.parent_type,
            "primary_env": primary_env,
            "fallback_env": fallback_env,
        }
    )
    return None, None, warnings


def _env_names_for_parent(target) -> tuple[str | None, str | None]:
    if target.parent_type == "data_source":
        return target.data_source_id_env, target.fallback_data_source_id_env
    if target.parent_type == "database":
        return target.database_id_env, target.fallback_database_id_env
    if target.parent_type == "page":
        return target.page_id_env, target.fallback_page_id_env
    return None, None


def _env_value(name: str | None) -> str:
    if not name:
        return ""
    value = os.getenv(name)
    if value:
        return value
    try:
        from src.config.loader import load_local_env
    except Exception:
        return ""
    return str(load_local_env().get(name) or "")
