from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from .assets import MediaType
from .common import (
    ImmutableList,
    Language,
    StrictModel,
    ensure_utc,
    ensure_uuid4,
)
from .dish import GameplaySpec, PresentationSpec

CANONICAL_REGISTRY_SCHEMA_VERSION = 1
CANONICAL_MIN_VALID_COUNT = 2
CANONICAL_CANDIDATE_LIMIT = 5
CANONICAL_MATCH_THRESHOLD = 0.90
CANONICAL_REUSE_CONTRACT_VERSION = "canonical-reuse-v1"
CANONICAL_MATCH_PROMPT_VERSION = "canonical-match-v1"


class _FrozenCanonicalModel(StrictModel):
    model_config = ConfigDict(frozen=True)


class CanonicalIconKind(str, Enum):
    SOURCE = "SOURCE"
    ICON_16 = "ICON_16"


class RecallDecision(str, Enum):
    NOT_ATTEMPTED_BELOW_MINIMUM = "NOT_ATTEMPTED_BELOW_MINIMUM"
    NO_CANDIDATES = "NO_CANDIDATES"
    MATCH_MISS = "MATCH_MISS"
    MATCH_HIT = "MATCH_HIT"
    FALLBACK_ERROR = "FALLBACK_ERROR"
    BYPASSED_FULL_REGENERATE = "BYPASSED_FULL_REGENERATE"


class RecallTrace(_FrozenCanonicalModel):
    outcome: RecallDecision
    candidate_count: int = Field(alias="candidateCount", ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    canonical_dish_id: UUID | None = Field(default=None, alias="canonicalDishId")
    elapsed_ms: int = Field(alias="elapsedMs", ge=0)

    @field_validator("confidence")
    @classmethod
    def _validate_finite_confidence(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("confidence must be finite")
        return value

    @field_validator("canonical_dish_id", mode="before")
    @classmethod
    def _validate_optional_uuid4(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        return value


class RecallIngredient(_FrozenCanonicalModel):
    name: str = Field(min_length=1, max_length=80)
    normalized_name: str = Field(alias="normalizedName", min_length=1, max_length=80)
    visible_confidence: float = Field(alias="visibleConfidence", ge=0, le=1)
    quantity_hint: str | None = Field(
        default=None,
        alias="quantityHint",
        min_length=1,
        max_length=120,
    )


class RecallDocument(_FrozenCanonicalModel):
    recognized_dish: str = Field(alias="recognizedDish", min_length=1, max_length=80)
    normalized_name: str = Field(alias="normalizedName", min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=300)
    cuisine: str | None = Field(default=None, min_length=1, max_length=60)
    semantic_ingredients: list[RecallIngredient] = Field(
        alias="semanticIngredients",
        min_length=1,
        max_length=12,
    )
    cooking_methods: list[str] = Field(
        default_factory=list,
        alias="cookingMethods",
        max_length=6,
    )
    flavor_profile: list[str] = Field(
        default_factory=list,
        alias="flavorProfile",
        max_length=8,
    )

    @field_validator(
        "semantic_ingredients",
        "cooking_methods",
        "flavor_profile",
        mode="before",
    )
    @classmethod
    def _copy_lists(cls, value: Any) -> Any:
        return list(value) if isinstance(value, (list, tuple)) else value

    @model_validator(mode="after")
    def _freeze_values(self) -> RecallDocument:
        semantic_ingredients = ImmutableList(
            ingredient.model_copy(deep=True) for ingredient in self.semantic_ingredients
        )
        cooking_methods = ImmutableList(self.cooking_methods)
        flavor_profile = ImmutableList(self.flavor_profile)
        for label, values, limit in (
            ("cooking_methods", cooking_methods, 40),
            ("flavor_profile", flavor_profile, 40),
        ):
            for value in values:
                if not 1 <= len(value) <= limit:
                    raise ValueError(f"{label} values must be 1 to 40 characters")
        object.__setattr__(self, "semantic_ingredients", semantic_ingredients)
        object.__setattr__(self, "cooking_methods", cooking_methods)
        object.__setattr__(self, "flavor_profile", flavor_profile)
        return self


class CanonicalIconMetadata(_FrozenCanonicalModel):
    relative_path: str = Field(alias="relativePath", min_length=1, max_length=240)
    media_type: MediaType = Field(alias="mediaType")
    sha256: str
    byte_size: int = Field(alias="byteSize", gt=0, le=20 * 1024 * 1024)
    width: int = Field(ge=1, le=8192)
    height: int = Field(ge=1, le=8192)

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        if (
            value.strip() != value
            or value.startswith(("/", "\\"))
            or "\\" in value
            or ":" in value
            or ".." in value.split("/")
            or any(not part for part in value.split("/"))
        ):
            raise ValueError("relative_path must be a safe relative path")
        return value

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def _validate_media_type(self) -> CanonicalIconMetadata:
        if self.media_type not in {MediaType.PNG, MediaType.JPEG, MediaType.WEBP}:
            raise ValueError("canonical icons must use PNG, JPEG, or WEBP")
        return self


class CanonicalIconInput(_FrozenCanonicalModel):
    data: bytes = Field(min_length=1, max_length=20 * 1024 * 1024)
    media_type: MediaType = Field(alias="mediaType")
    sha256: str
    byte_size: int = Field(alias="byteSize", gt=0, le=20 * 1024 * 1024)
    width: int = Field(ge=1, le=8192)
    height: int = Field(ge=1, le=8192)

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def _validate_media_type(self) -> CanonicalIconInput:
        if self.media_type not in {MediaType.PNG, MediaType.JPEG, MediaType.WEBP}:
            raise ValueError("canonical icons must use PNG, JPEG, or WEBP")
        return self


def _validate_catalog_version(gameplay: GameplaySpec, catalog_version: str) -> None:
    if any(
        ingredient.catalog_version != catalog_version
        for ingredient in gameplay.ingredients
    ):
        raise ValueError(
            "all gameplay ingredient catalog_version values must match catalog_version"
        )


def _freeze_canonical_content(
    instance: CanonicalDishRegistration | CanonicalDish,
) -> None:
    recall_document = instance.recall_document.model_copy(deep=True)
    presentation = instance.presentation.model_copy(deep=True)
    gameplay = instance.gameplay.model_copy(deep=True)
    object.__setattr__(
        presentation,
        "tags",
        ImmutableList(presentation.tags),
    )
    object.__setattr__(
        gameplay,
        "ingredients",
        ImmutableList(
            ingredient.model_copy(deep=True) for ingredient in gameplay.ingredients
        ),
    )
    object.__setattr__(instance, "recall_document", recall_document)
    object.__setattr__(instance, "presentation", presentation)
    object.__setattr__(instance, "gameplay", gameplay)


class CanonicalDishRegistration(_FrozenCanonicalModel):
    canonical_id: UUID = Field(alias="canonicalId")
    source_archive_id: UUID = Field(alias="sourceArchiveId")
    dish_signature: str = Field(alias="dishSignature")
    language: Language
    reuse_contract_version: str = Field(
        default=CANONICAL_REUSE_CONTRACT_VERSION,
        alias="reuseContractVersion",
    )
    recall_document: RecallDocument = Field(alias="recallDocument")
    presentation: PresentationSpec
    gameplay: GameplaySpec
    visual_brief: str = Field(alias="visualBrief", min_length=1, max_length=1500)
    catalog_version: str = Field(alias="catalogVersion", min_length=1, max_length=80)

    @field_validator("canonical_id", "source_archive_id", mode="before")
    @classmethod
    def _validate_uuid4(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        return value

    @field_validator("dish_signature")
    @classmethod
    def _validate_dish_signature(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(
                "dish_signature must be 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("reuse_contract_version")
    @classmethod
    def _validate_reuse_contract_version(cls, value: str) -> str:
        if value != CANONICAL_REUSE_CONTRACT_VERSION:
            raise ValueError(
                "reuse_contract_version must be canonical-reuse-v1"
            )
        return value

    @model_validator(mode="after")
    def _validate_and_freeze(self) -> CanonicalDishRegistration:
        _validate_catalog_version(self.gameplay, self.catalog_version)
        _freeze_canonical_content(self)
        return self


class CanonicalDish(CanonicalDishRegistration):
    schema_version: int = Field(default=CANONICAL_REGISTRY_SCHEMA_VERSION)
    icon_source: CanonicalIconMetadata = Field(alias="iconSource")
    icon_16: CanonicalIconMetadata = Field(alias="icon16")
    registered_at: datetime = Field(alias="registeredAt")
    last_used_at: datetime | None = Field(default=None, alias="lastUsedAt")
    use_count: int = Field(default=0, alias="useCount", ge=0)

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> CanonicalDish:
        if update:
            raise ValueError(
                "CanonicalDish is immutable; model_copy(update=...) is not supported"
            )
        return super().model_copy(update=None, deep=deep)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != CANONICAL_REGISTRY_SCHEMA_VERSION:
            raise ValueError("schema_version must be 1")
        return value

    @field_validator("registered_at", "last_used_at", mode="before")
    @classmethod
    def _validate_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)


class CanonicalRecallCandidate(_FrozenCanonicalModel):
    canonical_id: UUID = Field(alias="canonicalId")
    dish_signature: str = Field(alias="dishSignature")
    language: Language
    catalog_version: str = Field(alias="catalogVersion", min_length=1, max_length=80)
    recall_document: RecallDocument = Field(alias="recallDocument")
    display_name: str = Field(alias="displayName", min_length=1, max_length=60)
    registered_at: datetime = Field(alias="registeredAt")
    use_count: int = Field(alias="useCount", ge=0)
    last_used_at: datetime | None = Field(default=None, alias="lastUsedAt")

    @field_validator("canonical_id", mode="before")
    @classmethod
    def _validate_uuid4(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        return value

    @field_validator("dish_signature")
    @classmethod
    def _validate_dish_signature(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(
                "dish_signature must be 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("last_used_at", mode="before")
    @classmethod
    def _validate_last_used_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)

    @field_validator("registered_at", mode="before")
    @classmethod
    def _validate_registered_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


@runtime_checkable
class CanonicalRepository(Protocol):
    def register(
        self,
        registration: CanonicalDishRegistration,
        *,
        icon_source: CanonicalIconInput,
        icon_16: CanonicalIconInput,
    ) -> CanonicalDish: ...

    def get_by_source_archive_id(
        self,
        source_archive_id: UUID,
    ) -> CanonicalDish | None: ...

    def get_valid(self, canonical_id: UUID) -> CanonicalDish | None: ...

    def count_valid(self) -> int: ...

    def list_recall_candidates(
        self,
        *,
        language: Language,
        catalog_version: str,
        limit: int = CANONICAL_CANDIDATE_LIMIT,
    ) -> list[CanonicalRecallCandidate]: ...

    def list_recall_candidate_pool(
        self,
        *,
        language: Language,
        catalog_version: str,
    ) -> list[CanonicalRecallCandidate]: ...

    def record_usage(
        self,
        canonical_id: UUID,
        *,
        source_archive_id: UUID,
        used_at: datetime | None = None,
    ) -> CanonicalDish: ...

    def load_owned_icon(
        self,
        canonical_id: UUID,
        kind: CanonicalIconKind,
    ) -> bytes: ...
