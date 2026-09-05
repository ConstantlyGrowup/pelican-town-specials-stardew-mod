from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from math import ceil, floor, isfinite
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from .common import DraftMode, StrictModel, ensure_uuid4


class _FrozenStrictModel(StrictModel):
    model_config = ConfigDict(frozen=True)

class FieldAuthority(str, Enum):
    AGENT_ASSIGNED = "AGENT_ASSIGNED"
    USER_ASSIGNED = "USER_ASSIGNED"
    SYSTEM_GENERATED = "SYSTEM_GENERATED"
    TEMPLATE_DEFAULT = "TEMPLATE_DEFAULT"
    CACHE_REUSED = "CACHE_REUSED"


class GenerationSource(str, Enum):
    FRESH_GENERATION = "FRESH_GENERATION"
    USER_AUTHORED = "USER_AUTHORED"
    CANONICAL_REUSED = "CANONICAL_REUSED"


class IconReuseDecision(str, Enum):
    """M13 Task 58: how a canonical-hit attempt obtained its pixel icon.

    A canonical hit always reuses the matched text; the ICON step may either
    reuse the canonical shared icon source (REUSED), generate a fresh icon
    from the current photo (GENERATED), or be skipped because the canonical
    icon assets are missing or damaged (UNAVAILABLE). Records written before
    M13 carry no decision (None).
    """

    REUSED = "REUSED"
    GENERATED = "GENERATED"
    UNAVAILABLE = "UNAVAILABLE"


class RecipeUnlock(str, Enum):
    DEFAULT = "DEFAULT"


class SemanticIngredient(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    normalized_name: str = Field(alias="normalizedName", min_length=1, max_length=80)
    visible_confidence: float = Field(alias="visibleConfidence", ge=0.0, le=1.0)
    quantity_hint: str | None = Field(default=None, alias="quantityHint", max_length=120)


class GameIngredient(_FrozenStrictModel):
    item_id: str = Field(alias="itemId", min_length=1, max_length=80)
    display_name: str = Field(alias="displayName", min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=99)
    mapping_reason: str = Field(alias="mappingReason", min_length=1, max_length=200)
    catalog_version: str = Field(alias="catalogVersion", min_length=1, max_length=80)


class PresentationSpec(_FrozenStrictModel):
    display_name: str = Field(alias="displayName", min_length=1, max_length=60)
    internal_name: str = Field(
        alias="internalName",
        min_length=3,
        max_length=48,
        pattern=r"^[A-Za-z][A-Za-z0-9_]{2,47}$",
    )
    category_label: str = Field(alias="categoryLabel", min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=400)
    gus_comment: str | None = Field(default=None, alias="gusComment", max_length=400)
    tags: list[str] = Field(default_factory=list, min_length=0, max_length=12)

    @field_validator("tags", mode="before")
    @classmethod
    def _copy_tags(cls, value: Any) -> Any:
        return list(value) if isinstance(value, (list, tuple)) else value

    @model_validator(mode="after")
    def _validate_tags(self) -> PresentationSpec:
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("tags must be unique")
        for tag in self.tags:
            if not 1 <= len(tag) <= 30:
                raise ValueError("each tag must be 1 to 30 characters long")
        return self


class DishAnalysis(StrictModel):
    recognized_dish: str = Field(alias="recognizedDish", min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=300)
    cuisine: str | None = Field(default=None, max_length=60)
    cooking_methods: list[str] = Field(default_factory=list, alias="cookingMethods", max_length=6)
    flavor_profile: list[str] = Field(default_factory=list, alias="flavorProfile", max_length=8)
    semantic_ingredients: list[SemanticIngredient] = Field(
        alias="semanticIngredients",
        min_length=1,
        max_length=12,
    )
    confidence: float = Field(ge=0.0, le=1.0)
    safety_notes: list[str] = Field(default_factory=list, alias="safetyNotes")

    @model_validator(mode="after")
    def _validate_lengths(self) -> DishAnalysis:
        for label, values, limit in (
            ("cooking_methods", self.cooking_methods, 6),
            ("flavor_profile", self.flavor_profile, 8),
        ):
            if len(values) > limit:
                raise ValueError(f"{label} cannot exceed {limit} items")
            for value in values:
                if not 1 <= len(value) <= 40:
                    raise ValueError(f"{label} items must be 1 to 40 characters long")
        for note in self.safety_notes:
            if not 1 <= len(note) <= 200:
                raise ValueError("safety_notes items must be 1 to 200 characters long")
        return self


class RecoverySpec(_FrozenStrictModel):
    edibility: int = Field(ge=0, le=500)
    energy_restore: int = Field(default=0, alias="energyRestore", frozen=True)
    health_restore: int = Field(default=0, alias="healthRestore", frozen=True)
    calculation_version: str = Field(default="stardew-1.6", alias="calculationVersion", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _reject_derived_inputs(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            forbidden = {
                "energy_restore",
                "energyRestore",
                "health_restore",
                "healthRestore",
                "calculation_version",
                "calculationVersion",
            }
            overlap = forbidden.intersection(data.keys())
            if overlap:
                joined = ", ".join(sorted(overlap))
                raise ValueError(f"derived recovery fields are read-only: {joined}")
        return data

    @model_validator(mode="after")
    def _derive_fields(self) -> RecoverySpec:
        # Vanilla Stardew formula: energy = ceil(edibility * 2.5),
        # health = floor(energy * 0.45) (R14: replaces the previous
        # floor-based approximation that drifted from the in-game values).
        energy = ceil(self.edibility * 2.5)
        object.__setattr__(self, "energy_restore", energy)
        object.__setattr__(self, "health_restore", floor(energy * 0.45))
        object.__setattr__(self, "calculation_version", "stardew-1.6")
        return self


class BuffAttributes(_FrozenStrictModel):
    farming_level: int = Field(default=0, alias="farmingLevel")
    fishing_level: int = Field(default=0, alias="fishingLevel")
    mining_level: int = Field(default=0, alias="miningLevel")
    foraging_level: int = Field(default=0, alias="foragingLevel")
    combat_level: int = Field(default=0, alias="combatLevel")
    luck_level: int = Field(default=0, alias="luckLevel")
    attack: int = 0
    defense: int = 0
    immunity: int = 0
    magnetic_radius: int = Field(default=0, alias="magneticRadius")
    max_stamina: int = Field(default=0, alias="maxStamina")
    speed: int = 0

    @model_validator(mode="after")
    def _validate_nonzero(self) -> BuffAttributes:
        if not any(
            value != 0
            for value in (
                self.farming_level,
                self.fishing_level,
                self.mining_level,
                self.foraging_level,
                self.combat_level,
                self.luck_level,
                self.attack,
                self.defense,
                self.immunity,
                self.magnetic_radius,
                self.max_stamina,
                self.speed,
            )
        ):
            raise ValueError("buff attributes must contain at least one non-zero value")
        return self


class BuffSpec(_FrozenStrictModel):
    id: str = Field(min_length=1, max_length=80)
    duration_minutes: int = Field(alias="durationMinutes", ge=10, le=1440)
    is_debuff: bool = Field(default=False, alias="isDebuff")
    attributes: BuffAttributes

    @field_validator("duration_minutes")
    @classmethod
    def _validate_duration_multiple(cls, value: int) -> int:
        if value % 10 != 0:
            raise ValueError("duration_minutes must be a multiple of 10")
        return value


class GameplaySpec(_FrozenStrictModel):
    ingredients: list[GameIngredient] = Field(min_length=1, max_length=8)
    recovery: RecoverySpec
    buff: BuffSpec | None = None
    sell_price: int = Field(alias="sellPrice", ge=0, le=50000)
    is_drink: bool = Field(alias="isDrink")
    recipe_unlock: RecipeUnlock = Field(default=RecipeUnlock.DEFAULT, alias="recipeUnlock")

    @model_validator(mode="before")
    @classmethod
    def _coerce_recipe_unlock(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "recipeUnlock" in data and not isinstance(data["recipeUnlock"], RecipeUnlock):
            data = dict(data)
            data["recipeUnlock"] = RecipeUnlock(data["recipeUnlock"])
        return data

    @model_validator(mode="after")
    def _validate_unique_ingredients(self) -> GameplaySpec:
        item_ids = [ingredient.item_id for ingredient in self.ingredients]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("ingredients must have unique item_id values")
        return self


class VisualSpec(_FrozenStrictModel):
    visual_brief: str = Field(alias="visualBrief", min_length=1, max_length=1500)
    generated_art_asset_id: UUID | None = Field(default=None, alias="generatedArtAssetId")
    preview_asset_id: UUID | None = Field(default=None, alias="previewAssetId")
    icon_source_asset_id: UUID | None = Field(default=None, alias="iconSourceAssetId")
    icon_16_asset_id: UUID | None = Field(default=None, alias="icon16AssetId")
    source_revision: int = Field(alias="sourceRevision", ge=1)
    prompt_version: str = Field(alias="promptVersion", min_length=1, max_length=80)

    @field_validator(
        "generated_art_asset_id",
        "preview_asset_id",
        "icon_source_asset_id",
        "icon_16_asset_id",
        mode="before",
    )
    @classmethod
    def _validate_optional_uuid4(cls, value: UUID | None) -> UUID | None:
        if value is None:
            return None
        return ensure_uuid4(value)


class Provenance(_FrozenStrictModel):
    mode: DraftMode
    authority_by_field: dict[str, FieldAuthority] = Field(default_factory=dict, alias="authorityByField")
    vision_model: str | None = Field(default=None, alias="visionModel", min_length=1, max_length=120)
    text_model: str | None = Field(default=None, alias="textModel", min_length=1, max_length=120)
    image_model: str | None = Field(default=None, alias="imageModel", min_length=1, max_length=120)
    prompt_versions: dict[str, str] = Field(default_factory=dict, alias="promptVersions")
    generation_source: GenerationSource = Field(alias="generationSource")
    canonical_dish_signature: str | None = Field(
        default=None,
        alias="canonicalDishSignature",
        min_length=1,
        max_length=200,
    )
    canonical_dish_id: UUID | None = Field(default=None, alias="canonicalDishId")
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
    icon_reuse_decision: IconReuseDecision | None = Field(
        default=None,
        alias="iconReuseDecision",
    )
    icon_visual_similarity: float | None = Field(
        default=None,
        alias="iconVisualSimilarity",
        ge=0.0,
        le=1.0,
    )
    cache_eligibility: bool = Field(alias="cacheEligibility")

    @model_validator(mode="before")
    @classmethod
    def _coerce_enum_inputs(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        mutable = dict(data)
        if "mode" in mutable and not isinstance(mutable["mode"], DraftMode):
            mutable["mode"] = DraftMode(mutable["mode"])
        if "generationSource" in mutable and not isinstance(mutable["generationSource"], GenerationSource):
            mutable["generationSource"] = GenerationSource(mutable["generationSource"])
        if (
            "iconReuseDecision" in mutable
            and mutable["iconReuseDecision"] is not None
            and not isinstance(mutable["iconReuseDecision"], IconReuseDecision)
        ):
            mutable["iconReuseDecision"] = IconReuseDecision(
                mutable["iconReuseDecision"]
            )
        if "authorityByField" in mutable and isinstance(mutable["authorityByField"], Mapping):
            mutable["authorityByField"] = {
                key: value if isinstance(value, FieldAuthority) else FieldAuthority(value)
                for key, value in mutable["authorityByField"].items()
            }
        return mutable

    @field_validator("canonical_dish_id", mode="before")
    @classmethod
    def _validate_optional_canonical_uuid4(cls, value: object) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        try:
            return ensure_uuid4(UUID(str(value)))
        except (TypeError, ValueError) as exc:
            raise ValueError("canonical_dish_id must be a UUID v4") from exc

    @field_validator("recall_confidence", "icon_visual_similarity")
    @classmethod
    def _validate_finite_fraction(
        cls, value: float | None
    ) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("score must be finite")
        return value

    @model_validator(mode="after")
    def _validate_blueprint_cache(self) -> Provenance:
        if self.mode is DraftMode.BLUEPRINT and self.cache_eligibility:
            raise ValueError("blueprint provenance must not be cache eligible")
        return self
