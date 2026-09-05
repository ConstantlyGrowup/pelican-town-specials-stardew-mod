"""Strict internal Provider request/result/capability DTOs."""

from __future__ import annotations

from enum import Enum
from math import isfinite
from typing import Protocol
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from pelican_town_specials.domain.canonical import RecallDocument
from pelican_town_specials.domain.common import Language, StrictModel, ensure_uuid4
from pelican_town_specials.domain.dish import (
    BuffSpec,
    DishAnalysis,
    PresentationSpec,
    RecoverySpec,
)


class ModelGateway(Protocol):
    """Structured provider gateway used by the generation orchestrator."""

    async def analyze_dish(
        self, request: DishAnalysisRequest, *, json_only: bool = False
    ) -> DishAnalysis: ...

    async def design_ask_gus(
        self, request: AskGusDesignRequest, *, json_only: bool = False
    ) -> GeneratedDishCore: ...

    async def match_canonical(
        self,
        request: CanonicalMatchRequest,
        *,
        json_only: bool = False,
    ) -> CanonicalMatchResponse: ...

    async def compare_canonical_icon(
        self,
        request: CanonicalIconComparisonRequest,
        *,
        json_only: bool = False,
    ) -> CanonicalIconComparisonResponse: ...

    async def generate_image(self, request: ImageGenerationRequest) -> GeneratedImage: ...


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
    # M13 Task 59: this round's user-written regeneration instruction, kept
    # separate from the original contextText.
    regeneration_instructions: str | None = Field(
        default=None,
        alias="regenerationInstructions",
        max_length=500,
    )


class AskGusDesignRequest(StrictModel):
    analysis: DishAnalysis
    context_text: str | None = Field(default=None, max_length=500)
    language: Language
    request_id: UUID
    # M13 Task 59: this round's user-written regeneration instruction, kept
    # separate from the original contextText.
    regeneration_instructions: str | None = Field(
        default=None,
        alias="regenerationInstructions",
        max_length=500,
    )


class CanonicalMatchCandidate(StrictModel):
    canonical_id: UUID = Field(alias="canonicalId")
    display_name: str = Field(alias="displayName", min_length=1, max_length=60)
    recall_document: RecallDocument = Field(alias="recallDocument")

    @field_validator("canonical_id", mode="before")
    @classmethod
    def _validate_uuid4(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        if isinstance(value, str):
            return ensure_uuid4(UUID(value))
        return value


class CanonicalMatchRequest(StrictModel):
    analysis: DishAnalysis
    context_text: str | None = Field(default=None, alias="contextText", max_length=500)
    language: Language
    candidates: list[CanonicalMatchCandidate] = Field(min_length=1, max_length=5)
    request_id: UUID = Field(alias="requestId")


class CanonicalMatchResponse(StrictModel):
    candidate_id: UUID | None = Field(alias="candidateId")
    confidence: float = Field(ge=0, le=1)

    @field_validator("candidate_id", mode="before")
    @classmethod
    def _validate_optional_uuid4(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        if isinstance(value, str):
            return ensure_uuid4(UUID(value))
        return value

    @field_validator("confidence")
    @classmethod
    def _validate_finite_confidence(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("confidence must be finite")
        return value


class CanonicalIconComparisonRequest(StrictModel):
    """Ask the vision model whether the current dish photo matches the
    canonical item's recorded icon source well enough to reuse it (M13
    Task 58). The two images have explicit, ordered roles and both are always
    present; the response is a single finite 0..1 visual similarity score."""

    current_original: ProviderImageInput = Field(alias="currentOriginal")
    canonical_icon_source: ProviderImageInput = Field(alias="canonicalIconSource")
    language: Language
    request_id: UUID = Field(alias="requestId")


class CanonicalIconComparisonResponse(StrictModel):
    visual_similarity: float = Field(
        alias="visualSimilarity",
        ge=0,
        le=1,
    )

    @field_validator("visual_similarity")
    @classmethod
    def _validate_finite_similarity(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("visualSimilarity must be finite")
        return value


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
