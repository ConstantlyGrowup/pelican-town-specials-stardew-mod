from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .common import Language, StrictModel, ensure_utc, ensure_uuid4
from .errors import ErrorSummary
from .validation import ValidationReport

_SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_PACK_SLUG_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,47}$")


class ExportSpec(StrictModel):
    dish_ids: list[UUID] = Field(min_length=1, max_length=100)
    pack_display_name: str = Field(min_length=1, max_length=80)
    pack_slug: str = Field(min_length=3, max_length=48)
    version: str = Field(min_length=5, max_length=32)
    description: str = Field(min_length=1, max_length=200)
    language: Language

    @field_validator("dish_ids", mode="before")
    @classmethod
    def _coerce_dish_ids(cls, value: object) -> object:
        if isinstance(value, list):
            coerced: list[UUID] = []
            for item in value:
                if isinstance(item, UUID):
                    coerced.append(item)
                    continue
                try:
                    coerced.append(UUID(str(item)))
                except (ValueError, AttributeError, TypeError) as exc:
                    raise ValueError("dishIds must contain valid UUIDs") from exc
            return coerced
        return value

    @field_validator("dish_ids")
    @classmethod
    def _validate_uuid4_list(cls, value: list[UUID]) -> list[UUID]:
        return [ensure_uuid4(item) for item in value]

    @field_validator("language", mode="before")
    @classmethod
    def _coerce_language(cls, value: Language | str) -> Language:
        if isinstance(value, Language):
            return value
        return Language(value)

    @field_validator("pack_slug")
    @classmethod
    def _validate_pack_slug(cls, value: str) -> str:
        if not _PACK_SLUG_PATTERN.fullmatch(value):
            raise ValueError("pack_slug must match the required slug format")
        return value

    @field_validator("version")
    @classmethod
    def _validate_semver(cls, value: str) -> str:
        if not _SEMVER_PATTERN.fullmatch(value):
            raise ValueError("version must be canonical MAJOR.MINOR.PATCH")
        return value

    @model_validator(mode="after")
    def _validate_unique_dishes(self) -> ExportSpec:
        if len(set(self.dish_ids)) != len(self.dish_ids):
            raise ValueError("dish_ids must be unique")
        return self


class ExportStatus(str, Enum):
    VALIDATING = "VALIDATING"
    BUILDING = "BUILDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ExportRecord(StrictModel):
    """Persisted export record (design 9.17).

    ``artifact_asset_id`` is set only for SUCCEEDED exports; the staging ZIP
    is never registered and therefore never downloadable.
    """

    schema_version: int = Field(default=1)
    export_id: UUID = Field(alias="exportId")
    spec: ExportSpec
    author_name: str
    unique_id: str = Field(alias="uniqueId")
    status: ExportStatus
    dish_content_hashes: dict[str, str] = Field(alias="dishContentHashes")
    compiler_version: str = Field(alias="compilerVersion")
    game_version: str = Field(alias="gameVersion")
    content_patcher_format: str = Field(alias="contentPatcherFormat")
    validation: ValidationReport
    artifact_asset_id: UUID | None = Field(default=None, alias="artifactAssetId")
    created_at: datetime = Field(alias="createdAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    error: ErrorSummary | None = None

    @field_validator("export_id", mode="before")
    @classmethod
    def _validate_export_id(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        try:
            return ensure_uuid4(UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("exportId must be a valid UUID v4") from exc

    @field_validator("artifact_asset_id", mode="before")
    @classmethod
    def _validate_optional_asset_id(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        try:
            return ensure_uuid4(UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("artifactAssetId must be a valid UUID v4") from exc

    @field_validator("created_at", "finished_at", mode="before")
    @classmethod
    def _validate_datetimes(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, datetime):
            return ensure_utc(value)
        raise ValueError("export timestamps must be timezone-aware datetimes")


class ExportRecordView(StrictModel):
    """API DTO for an export record; never exposes internal provenance."""

    export_id: UUID = Field(alias="exportId")
    spec: ExportSpec
    author_name: str
    unique_id: str = Field(alias="uniqueId")
    status: ExportStatus
    dish_content_hashes: dict[str, str] = Field(alias="dishContentHashes")
    compiler_version: str = Field(alias="compilerVersion")
    game_version: str = Field(alias="gameVersion")
    content_patcher_format: str = Field(alias="contentPatcherFormat")
    validation: ValidationReport
    artifact_asset_id: UUID | None = Field(default=None, alias="artifactAssetId")
    created_at: datetime = Field(alias="createdAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    error: ErrorSummary | None = None

    @field_validator("export_id", mode="before")
    @classmethod
    def _validate_export_id(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        try:
            return ensure_uuid4(UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("exportId must be a valid UUID v4") from exc

    @field_validator("artifact_asset_id", mode="before")
    @classmethod
    def _validate_optional_asset_id(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        try:
            return ensure_uuid4(UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("artifactAssetId must be a valid UUID v4") from exc

    @field_validator("created_at", "finished_at", mode="before")
    @classmethod
    def _validate_datetimes(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, datetime):
            return ensure_utc(value)
        raise ValueError("export timestamps must be timezone-aware datetimes")

    @classmethod
    def from_record(cls, record: ExportRecord) -> ExportRecordView:
        return cls(
            exportId=record.export_id,
            spec=record.spec,
            author_name=record.author_name,
            uniqueId=record.unique_id,
            status=record.status,
            dishContentHashes=record.dish_content_hashes,
            compilerVersion=record.compiler_version,
            gameVersion=record.game_version,
            contentPatcherFormat=record.content_patcher_format,
            validation=record.validation,
            artifactAssetId=record.artifact_asset_id,
            createdAt=record.created_at,
            finishedAt=record.finished_at,
            error=record.error,
        )
