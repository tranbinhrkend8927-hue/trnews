from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RewriteStatus = Literal["not_needed", "suggested", "blocked"]
RewritePriority = Literal["low", "medium", "high"]


class RewriteAction(BaseModel):
    action_type: str
    priority: RewritePriority = "medium"
    reason: str
    suggested_change: str
    source: str | None = None


class RewritePlan(BaseModel):
    enabled: bool = False
    status: RewriteStatus = "not_needed"
    should_rewrite: bool = False
    automatic_rewrite_performed: bool = False
    reason: str = ""
    actions: list[RewriteAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
