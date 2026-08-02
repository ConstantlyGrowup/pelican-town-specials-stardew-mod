from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .assets import SourceInput
from .common import DraftMode, GenerationStage, StrictModel, ensure_utc, ensure_uuid4
from .dish import DishAnalysis, GameplaySpec, PresentationSpec, Provenance, VisualSpec
from .errors import ErrorSummary


def _validate_uuid4_public_boundary(value: object) -> object:
    if isinstance(value, UUID):
        return ensure_uuid4(value)
    return value


class DraftStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    GENERATING = "GENERATING"
    REGENERATING = "REGENERATING"
    REVIEWABLE = "REVIEWABLE"
    STALE_PREVIEW = "STALE_PREVIEW"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"
    DISCARDED = "DISCARDED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class GenerationAttemptKind(str, Enum):
    INITIAL = "INITIAL"
    FULL_REGENERATE = "FULL_REGENERATE"
    BLUEPRINT_PREVIEW = "BLUEPRINT_PREVIEW"
    RETRY_FAILED_STAGE = "RETRY_FAILED_STAGE"


class AttemptStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class StageAttempt(StrictModel):
    stage: GenerationStage
    status: StageStatus
    retry_count: int = Field(ge=0, le=3)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: ErrorSummary | None = None

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def _validate_optional_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)


def _coerce_copy_mode(value: Any) -> DraftMode:
    if isinstance(value, DraftMode):
        return value
    try:
        return DraftMode(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("draft mode is immutable") from exc

class DraftRecord(StrictModel):
    schema_version: int = Field(ge=1)
    draft_id: UUID
    mode: DraftMode = Field(frozen=True)
    status: DraftStatus
    revision: int = Field(ge=1)
    source: SourceInput
    analysis: DishAnalysis | None = None
    presentation: PresentationSpec | None = None
    gameplay: GameplaySpec | None = None
    visuals: VisualSpec | None = None
    provenance: Provenance
    active_attempt_id: UUID | None = None
    last_attempt_id: UUID | None = None
    last_error: ErrorSummary | None = None
    created_at: datetime
    updated_at: datetime
    archived_dish_id: UUID | None = None

    @field_validator(
        "draft_id",
        "active_attempt_id",
        "last_attempt_id",
        "archived_dish_id",
        mode="before",
    )
    @classmethod
    def _validate_optional_uuid4(cls, value: UUID | None) -> UUID | None:
        if value is None:
            return None
        return ensure_uuid4(value)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _validate_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def _validate_mode_alignment(self) -> DraftRecord:
        if self.provenance.mode is not self.mode:
            raise ValueError("provenance.mode must match draft mode")
        return self


    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> DraftRecord:
        if update is None:
            return super().model_copy(update=None, deep=deep)

        safe_update = dict(update)
        if "mode" in safe_update:
            candidate_mode = _coerce_copy_mode(safe_update["mode"])
            if candidate_mode is not self.mode:
                raise ValueError("draft mode is immutable")
            safe_update["mode"] = candidate_mode

        if "provenance" in safe_update:
            candidate = safe_update["provenance"]
            if isinstance(candidate, Provenance):
                candidate_provenance = candidate
            elif isinstance(candidate, Mapping):
                candidate_provenance = Provenance.model_validate(candidate)
                safe_update["provenance"] = candidate_provenance
            else:
                raise ValueError("provenance mode must match draft mode")
            if candidate_provenance.mode is not self.mode:
                raise ValueError("draft mode and provenance mode must match")

        return super().model_copy(update=safe_update, deep=deep)

class GenerationAttempt(StrictModel):
    attempt_id: UUID
    draft_id: UUID
    kind: GenerationAttemptKind
    source_revision: int = Field(ge=1)
    status: AttemptStatus
    current_stage: GenerationStage | None = None
    stages: list[StageAttempt] = Field(min_length=1)
    candidate_record_path: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    error: ErrorSummary | None = None

    @field_validator("attempt_id", "draft_id", mode="before")
    @classmethod
    def _validate_uuid4(cls, value: UUID) -> UUID:
        return ensure_uuid4(value)

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def _validate_attempt_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)


class GenerationAttemptPublic(StrictModel):
    attempt_id: UUID
    draft_id: UUID
    kind: GenerationAttemptKind
    source_revision: int = Field(ge=1)
    status: AttemptStatus
    current_stage: GenerationStage | None = None
    stages: list[StageAttempt] = Field(min_length=1)
    started_at: datetime
    finished_at: datetime | None = None
    error: ErrorSummary | None = None

    @field_validator("attempt_id", "draft_id", mode="before")
    @classmethod
    def _validate_uuid4(cls, value: object) -> object:
        return _validate_uuid4_public_boundary(value)

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def _validate_public_attempt_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)

    @classmethod
    def from_attempt(cls, attempt: GenerationAttempt) -> GenerationAttemptPublic:
        return cls.model_validate(
            attempt.model_dump(exclude={"candidate_record_path"})
        )
