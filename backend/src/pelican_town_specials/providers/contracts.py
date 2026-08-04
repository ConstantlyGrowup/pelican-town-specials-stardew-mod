"""Strict internal Provider request/result/capability DTOs."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import Field, model_validator

from pelican_town_specials.domain.common import Language, StrictModel
from pelican_town_specials.domain.dish import (
    BuffSpec,
    DishAnalysis,
    PresentationSpec,
    RecoverySpec,
)


class ImageOperation(str, Enum):
    GENERATION = "GENERATION"
    EDIT = "EDIT"


class ImageMediaType(str, Enum):
    PNG = "image/png"
    JPEG = "image/jpeg"
    WEBP = "image/webp"


class ProviderImageInput(StrictModel):
    data: bytes
    media_type: ImageMediaType


class DishAnalysisRequest(StrictModel):
    image: ProviderImageInput
    context_text: str | None = Field(default=None, max_length=500)
    language: Language
    request_id: UUID


class AskGusDesignRequest(StrictModel):
    analysis: DishAnalysis
    context_text: str | None = Field(default=None, max_length=500)
    language: Language
    request_id: UUID


class SemanticRecipeIngredient(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    normalized_name: str = Field(alias="normalizedName", min_length=1, max_length=80)
    quantity_hint: str | None = Field(default=None, alias="quantityHint", max_length=120)


class GeneratedDishCore(StrictModel):
    """Model-suggested design; ingredient mapping stays with Task 13."""

    presentation: PresentationSpec
    ingredients: list[SemanticRecipeIngredient] = Field(min_length=1, max_length=8)
    recovery: RecoverySpec
    buff: BuffSpec | None = None
    sell_price: int = Field(alias="sellPrice", ge=0, le=50000)
    is_drink: bool = Field(alias="isDrink")
    visual_brief: str = Field(alias="visualBrief", min_length=1, max_length=1500)


class ImageGenerationRequest(StrictModel):
    operation: ImageOperation
    prompt: str = Field(min_length=1, max_length=1500)
    source_images: list[ProviderImageInput] = Field(default_factory=list, max_length=10)
    size: str | None = Field(default=None, max_length=20)
    quality: str | None = Field(default=None, max_length=20)
    request_id: UUID

    @model_validator(mode="after")
    def _validate_operation(self) -> ImageGenerationRequest:
        if self.operation is ImageOperation.GENERATION and self.source_images:
            raise ValueError("GENERATION must not include source images")
        if self.operation is ImageOperation.EDIT and not 1 <= len(self.source_images) <= 10:
            raise ValueError("EDIT requires 1..10 source images")
        return self


class GeneratedImage(StrictModel):
    data: bytes
    media_type: ImageMediaType
    revised_prompt: str | None = Field(default=None, max_length=1500)


class CapabilityResult(StrictModel):
    supported: bool
    elapsed_ms: int = Field(alias="elapsedMs", ge=0)
    note: str | None = Field(default=None, max_length=400)


class ProviderCapabilities(StrictModel):
    chat_multimodal: CapabilityResult = Field(alias="chatMultimodal")
    chat_json_schema: CapabilityResult = Field(alias="chatJsonSchema")
    chat_json_only: CapabilityResult = Field(alias="chatJsonOnly")
    image_edits: CapabilityResult = Field(alias="imageEdits")
    image_generations: CapabilityResult = Field(alias="imageGenerations")
    image_response_formats: list[str] = Field(
        alias="imageResponseFormats", default_factory=list
    )
    observed_timeouts: list[str] = Field(alias="observedTimeouts", default_factory=list)
    observed_rate_limits: list[str] = Field(alias="observedRateLimits", default_factory=list)
