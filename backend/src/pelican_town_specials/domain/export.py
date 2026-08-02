from __future__ import annotations

import re
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .common import Language, StrictModel, ensure_uuid4

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
