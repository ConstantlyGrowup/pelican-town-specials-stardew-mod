"""Strict camelCase NDJSON generation events."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import Field

from pelican_town_specials.domain.common import GenerationStage, StrictModel
from pelican_town_specials.domain.errors import ErrorPayload


class GenerationEvent(StrictModel):
    type: str
    attempt_id: UUID | None = Field(default=None, alias="attemptId")
    stage: GenerationStage | None = None
    ordinal: int | None = Field(default=None, ge=1)
    total: int | None = Field(default=None, ge=1)
    draft_revision: int | None = Field(default=None, alias="draftRevision")
    error: ErrorPayload | None = None
    draft: dict[str, object] | None = None

    def to_ndjson(self) -> str:
        payload = self.model_dump(
            by_alias=True, mode="json", exclude_none=True
        )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def attempt_started(attempt_id: UUID) -> GenerationEvent:
    return GenerationEvent(type="attempt.started", attemptId=attempt_id)


def stage_started(
    attempt_id: UUID,
    stage: GenerationStage,
    ordinal: int,
    total: int,
) -> GenerationEvent:
    return GenerationEvent(
        type="stage.started",
        attemptId=attempt_id,
        stage=stage,
        ordinal=ordinal,
        total=total,
    )


def stage_succeeded(
    attempt_id: UUID,
    stage: GenerationStage,
    ordinal: int,
    total: int,
) -> GenerationEvent:
    return GenerationEvent(
        type="stage.succeeded",
        attemptId=attempt_id,
        stage=stage,
        ordinal=ordinal,
        total=total,
    )


def attempt_succeeded(
    attempt_id: UUID,
    draft_revision: int,
    draft: dict[str, Any],
) -> GenerationEvent:
    return GenerationEvent(
        type="attempt.succeeded",
        attemptId=attempt_id,
        draftRevision=draft_revision,
        draft=draft,
    )


def attempt_failed(
    attempt_id: UUID,
    error: ErrorPayload,
) -> GenerationEvent:
    return GenerationEvent(
        type="attempt.failed",
        attemptId=attempt_id,
        error=error,
    )
