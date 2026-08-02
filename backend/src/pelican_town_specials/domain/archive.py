from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from .common import ImmutableDict, ImmutableList, StrictModel, ensure_utc, ensure_uuid4
from .dish import GameplaySpec, PresentationSpec, Provenance, VisualSpec


def _serialize_utc_datetime(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


def _validate_uuid4_public_boundary(value: object) -> object:
    if isinstance(value, UUID):
        return ensure_uuid4(value)
    return value


class ArchivedDish(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        alias_generator=to_camel,
        frozen=True,
    )

    schema_version: int = Field(ge=1)
    dish_id: UUID
    archive_revision: int = Field(default=1)
    archived_at: datetime
    presentation: PresentationSpec
    gameplay: GameplaySpec
    visuals: VisualSpec
    content_hash: str
    internal_provenance: Provenance
    source_draft_id: UUID

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> ArchivedDish:
        if update:
            raise ValueError(
                "ArchivedDish is immutable; model_copy(update=...) is not supported"
            )
        return super().model_copy(update=None, deep=deep)

    @field_validator("dish_id", "source_draft_id", mode="before")
    @classmethod
    def _validate_uuid4(cls, value: UUID) -> UUID:
        return ensure_uuid4(value)

    @field_validator("archived_at", mode="before")
    @classmethod
    def _validate_archived_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("archive_revision")
    @classmethod
    def _validate_archive_revision(cls, value: int) -> int:
        if value != 1:
            raise ValueError("archive_revision must be 1")
        return value

    @field_validator("content_hash")
    @classmethod
    def _validate_content_hash(cls, value: str) -> str:
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("content_hash must be a 64-character lowercase sha256")
        return value


    @model_validator(mode="after")
    def _freeze_nested_snapshot(self) -> ArchivedDish:
        presentation = self.presentation.model_copy(deep=True)
        gameplay = self.gameplay.model_copy(deep=True)
        visuals = self.visuals.model_copy(deep=True)
        provenance = self.internal_provenance.model_copy(deep=True)

        object.__setattr__(
            presentation,
            "tags",
            ImmutableList(presentation.tags),
        )
        object.__setattr__(
            gameplay,
            "ingredients",
            ImmutableList(gameplay.ingredients),
        )
        object.__setattr__(
            provenance,
            "authority_by_field",
            ImmutableDict(provenance.authority_by_field),
        )
        object.__setattr__(
            provenance,
            "prompt_versions",
            ImmutableDict(provenance.prompt_versions),
        )

        object.__setattr__(self, "presentation", presentation)
        object.__setattr__(self, "gameplay", gameplay)
        object.__setattr__(self, "visuals", visuals)
        object.__setattr__(self, "internal_provenance", provenance)
        return self


class CookbookVisuals(StrictModel):
    generated_art_asset_id: UUID | None = None
    preview_asset_id: UUID | None = None
    icon_source_asset_id: UUID | None = None
    icon_16_asset_id: UUID | None = None
    source_revision: int = Field(ge=1)
    prompt_version: str = Field(min_length=1, max_length=80)

    @field_validator(
        "generated_art_asset_id",
        "preview_asset_id",
        "icon_source_asset_id",
        "icon_16_asset_id",
        mode="before",
    )
    @classmethod
    def _validate_optional_uuid4(cls, value: object) -> object:
        if value is None:
            return None
        return _validate_uuid4_public_boundary(value)

    @classmethod
    def from_visuals(cls, visuals: VisualSpec) -> CookbookVisuals:
        return cls(
            generated_art_asset_id=visuals.generated_art_asset_id,
            preview_asset_id=visuals.preview_asset_id,
            icon_source_asset_id=visuals.icon_source_asset_id,
            icon_16_asset_id=visuals.icon_16_asset_id,
            source_revision=visuals.source_revision,
            prompt_version=visuals.prompt_version,
        )


class CookbookDishSummary(StrictModel):
    dish_id: UUID
    archived_at: datetime
    display_name: str = Field(min_length=1, max_length=60)
    category_label: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=400)
    tags: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("dish_id", mode="before")
    @classmethod
    def _validate_dish_id(cls, value: object) -> object:
        return _validate_uuid4_public_boundary(value)

    @field_validator("archived_at", mode="before")
    @classmethod
    def _validate_summary_archived_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_serializer("archived_at", when_used="json")
    def _serialize_archived_at(self, value: datetime) -> str:
        return _serialize_utc_datetime(value)

    @classmethod
    def from_archived_dish(cls, archive: ArchivedDish) -> CookbookDishSummary:
        return cls(
            dish_id=archive.dish_id,
            archived_at=archive.archived_at,
            display_name=archive.presentation.display_name,
            category_label=archive.presentation.category_label,
            description=archive.presentation.description,
            tags=list(archive.presentation.tags),
        )


class CookbookDishDetail(StrictModel):
    dish_id: UUID
    archived_at: datetime
    display_name: str = Field(min_length=1, max_length=60)
    internal_name: str = Field(min_length=3, max_length=48)
    category_label: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=400)
    tags: list[str] = Field(default_factory=list, max_length=12)
    gameplay: GameplaySpec
    visuals: CookbookVisuals

    @field_validator("dish_id", mode="before")
    @classmethod
    def _validate_dish_id(cls, value: object) -> object:
        return _validate_uuid4_public_boundary(value)

    @field_validator("archived_at", mode="before")
    @classmethod
    def _validate_detail_archived_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_serializer("archived_at", when_used="json")
    def _serialize_archived_at(self, value: datetime) -> str:
        return _serialize_utc_datetime(value)

    @classmethod
    def from_archived_dish(cls, archive: ArchivedDish) -> CookbookDishDetail:
        return cls(
            dish_id=archive.dish_id,
            archived_at=archive.archived_at,
            display_name=archive.presentation.display_name,
            internal_name=archive.presentation.internal_name,
            category_label=archive.presentation.category_label,
            description=archive.presentation.description,
            tags=list(archive.presentation.tags),
            gameplay=archive.gameplay,
            visuals=CookbookVisuals.from_visuals(archive.visuals),
        )
