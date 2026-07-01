from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"]
    field: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class ValidationResult(BaseModel):
    passed: bool
    exportable: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


def passed(metadata: dict | None = None) -> ValidationResult:
    return ValidationResult(passed=True, exportable=True, metadata=metadata or {})


def failed(
    code: str,
    message: str,
    field: str | None = None,
    exportable: bool = False,
) -> ValidationResult:
    return ValidationResult(
        passed=False,
        exportable=exportable,
        issues=[
            ValidationIssue(
                code=code,
                message=message,
                severity="error",
                field=field,
            )
        ],
    )


def from_issues(issues: list[ValidationIssue], metadata: dict | None = None, exportable: bool = True) -> ValidationResult:
    has_errors = any(issue.severity == "error" for issue in issues)
    return ValidationResult(
        passed=not has_errors,
        exportable=exportable and not has_errors,
        issues=issues,
        metadata=metadata or {},
    )
