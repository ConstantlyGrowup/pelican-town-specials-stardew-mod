"""Typed, private checkpoints for resumable Ask Gus generation.

Checkpoint documents are deliberately kept in the per-attempt staging
directory.  They contain only validated generation results and opaque local
asset identifiers; provider configuration, credentials, request URLs, and
raw provider request bodies are never part of this model.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from pelican_town_specials.domain.canonical import CanonicalDish
from pelican_town_specials.domain.common import (
    DraftMode,
    GenerationStage,
    Language,
    StrictModel,
    ensure_utc,
    ensure_uuid4,
)
from pelican_town_specials.domain.dish import (
    DishAnalysis,
    GameplaySpec,
    PresentationSpec,
)
from pelican_town_specials.domain.draft import DraftRecord, GenerationAttemptKind
from pelican_town_specials.providers.contracts import GeneratedDishCore

CHECKPOINT_SCHEMA_VERSION: Literal[1] = 1
CHECKPOINT_PROTOCOL_VERSION = "task56-gus-generation-resume-v1"


class GenerationCheckpoint(StrictModel):
    """Private checkpoint state for one resumable generation attempt."""

    schema_version: Literal[1] = Field(
        default=CHECKPOINT_SCHEMA_VERSION,
        alias="schemaVersion",
    )
    attempt_id: UUID = Field(alias="attemptId")
    draft_id: UUID = Field(alias="draftId")
    kind: GenerationAttemptKind
    source_revision: int = Field(alias="sourceRevision", ge=1)
    input_fingerprint: str = Field(
        alias="inputFingerprint",
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    language: Language
    catalog_version: str = Field(alias="catalogVersion", min_length=1, max_length=80)
    protocol_version: str = Field(
        alias="protocolVersion",
        min_length=1,
        max_length=120,
    )
    completed_stages: list[GenerationStage] = Field(
        default_factory=list,
        alias="completedStages",
    )
    candidate: DraftRecord
    analysis: DishAnalysis | None = None
    core: GeneratedDishCore | None = None
    gameplay: GameplaySpec | None = None
    presentation: PresentationSpec | None = None
    visual_brief: str | None = Field(default=None, alias="visualBrief")
    canonical: CanonicalDish | None = None
    recall_confidence: float | None = Field(
        default=None,
        alias="recallConfidence",
        ge=0.0,
        le=1.0,
    )
    recall_elapsed_ms: int | None = Field(
        default=None,
        alias="recallElapsedMs",
        ge=0,
    )
    icon_source_asset_id: UUID | None = Field(
        default=None,
        alias="iconSourceAssetId",
    )
    icon_16_asset_id: UUID | None = Field(default=None, alias="icon16AssetId")
    preview_asset_id: UUID | None = Field(default=None, alias="previewAssetId")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("attempt_id", "draft_id", mode="before")
    @classmethod
    def _validate_uuid4(cls, value: UUID) -> UUID:
        return ensure_uuid4(value)

    @field_validator(
        "icon_source_asset_id",
        "icon_16_asset_id",
        "preview_asset_id",
        mode="before",
    )
    @classmethod
    def _validate_optional_uuid4(cls, value: UUID | None) -> UUID | None:
        if value is None:
            return None
        return ensure_uuid4(value)

    @field_validator("updated_at", mode="before")
    @classmethod
    def _validate_updated_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def _validate_checkpoint_invariants(self) -> GenerationCheckpoint:
        if self.kind not in {
            GenerationAttemptKind.INITIAL,
            GenerationAttemptKind.FULL_REGENERATE,
        }:
            raise ValueError("only Ask Gus checkpoints are resumable")
        if self.candidate.draft_id != self.draft_id:
            raise ValueError("checkpoint candidate must belong to the checkpoint draft")
        positions = [list(GenerationStage).index(stage) for stage in self.completed_stages]
        if positions != sorted(set(positions)):
            raise ValueError("checkpoint completed stages must be ordered and unique")
        return self


def input_fingerprint(
    *,
    draft_id: UUID,
    mode: DraftMode,
    original_asset_id: UUID,
    original_asset_sha256: str,
    context_text: str | None,
    language: Language,
) -> str:
    """Return a stable identity for the user input used by a checkpoint."""

    payload = {
        "draftId": str(draft_id),
        "mode": mode.value,
        "originalAssetId": str(original_asset_id),
        "originalAssetSha256": original_asset_sha256,
        "contextText": context_text,
        "language": language.value,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
