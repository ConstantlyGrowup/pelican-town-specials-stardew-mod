from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import Field, field_validator, model_validator

from .common import (
    DraftMode,
    SafeScalar,
    StrictModel,
    ensure_safe_details,
    ensure_utc,
    utc_now,
)

if TYPE_CHECKING:
    from .draft import DraftRecord


class ValidationSeverity(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"


class ValidationIssue(StrictModel):
    code: str
    severity: ValidationSeverity
    path: str | None = None
    message: str
    details: dict[str, SafeScalar] = Field(default_factory=dict)

    @field_validator("details", mode="before")
    @classmethod
    def _validate_details(cls, value: object) -> dict[str, SafeScalar]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("details must be a mapping")
        return ensure_safe_details(value)


class ValidationReport(StrictModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    validated_at: datetime
    validator_version: str

    @field_validator("validated_at", mode="before")
    @classmethod
    def _validate_validated_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def _validate_consistency(self) -> ValidationReport:
        has_error = any(issue.severity is ValidationSeverity.ERROR for issue in self.issues)
        if self.valid != (not has_error):
            raise ValueError("valid must match the presence of ERROR issues")
        return self


def validate_draft(draft: DraftRecord) -> ValidationReport:
    issues: list[ValidationIssue] = []

    provenance = draft.provenance
    if provenance.mode is DraftMode.BLUEPRINT and provenance.cache_eligibility:
        issues.append(
            ValidationIssue(
                code="PTS_VALIDATION_BLUEPRINT_CACHE_ELIGIBILITY",
                severity=ValidationSeverity.ERROR,
                path="provenance.cacheEligibility",
                message="Blueprint drafts must not be cache eligible.",
                details={},
            )
        )

    if draft.visuals is not None and draft.visuals.source_revision != draft.revision:
        issues.append(
            ValidationIssue(
                code="PTS_VALIDATION_SOURCE_REVISION_MISMATCH",
                severity=ValidationSeverity.ERROR,
                path="visuals.sourceRevision",
                message="Visual source revision must match the draft revision.",
                details={
                    "draftRevision": draft.revision,
                    "visualSourceRevision": draft.visuals.source_revision,
                },
            )
        )

    status_name = getattr(draft.status, "value", draft.status)
    needs_core_fields = {
        "READY",
        "GENERATING",
        "REGENERATING",
        "REVIEWABLE",
        "STALE_PREVIEW",
        "ARCHIVED",
    }
    needs_visuals = {"REVIEWABLE", "STALE_PREVIEW", "ARCHIVED"}

    if status_name in needs_core_fields:
        required_fields = {
            "analysis": draft.analysis,
            "presentation": draft.presentation,
            "gameplay": draft.gameplay,
        }
        for field_name, value in required_fields.items():
            if value is None:
                issues.append(
                    ValidationIssue(
                        code="PTS_VALIDATION_REQUIRED_FIELD_MISSING",
                        severity=ValidationSeverity.ERROR,
                        path=field_name,
                        message=f"{field_name} is required for status {status_name}.",
                        details={"status": status_name},
                    )
                )

    if status_name in needs_visuals and draft.visuals is None:
        issues.append(
            ValidationIssue(
                code="PTS_VALIDATION_REQUIRED_FIELD_MISSING",
                severity=ValidationSeverity.ERROR,
                path="visuals",
                message=f"visuals is required for status {status_name}.",
                details={"status": status_name},
            )
        )

    return ValidationReport(
        valid=not any(issue.severity is ValidationSeverity.ERROR for issue in issues),
        issues=issues,
        validated_at=utc_now(),
        validator_version="task4-draft-validator-v1",
    )
