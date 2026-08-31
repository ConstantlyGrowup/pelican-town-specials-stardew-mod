"""Ask Gus synchronous generation orchestrator."""

from __future__ import annotations

import asyncio
import hashlib
import io
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import suppress
from time import monotonic
from typing import Protocol
from uuid import UUID, uuid4

from PIL import Image
from pydantic import Field

from pelican_town_specials.application.canonical_memory import RecallService
from pelican_town_specials.application.telemetry import (
    NoopTelemetryRecorder,
    TelemetryRecorder,
)
from pelican_town_specials.application.trial import TrialProviderPreference
from pelican_town_specials.catalog.gameplay_rules import validate_gameplay
from pelican_town_specials.catalog.mapping import ensure_main_protein, map_ingredient
from pelican_town_specials.catalog.models import CatalogCandidate
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.canonical import (
    CanonicalDish,
    CanonicalIconKind,
    CanonicalIconMetadata,
    CanonicalRepository,
    RecallDecision,
)
from pelican_town_specials.domain.common import (
    DraftMode,
    GenerationStage,
    Language,
    StrictModel,
    utc_now,
)
from pelican_town_specials.domain.dish import (
    DishAnalysis,
    FieldAuthority,
    GameIngredient,
    GameplaySpec,
    GenerationSource,
    PresentationSpec,
    Provenance,
    RecipeUnlock,
    VisualSpec,
)
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    DraftRecord,
    DraftStatus,
    GenerationAttempt,
    GenerationAttemptKind,
    StageAttempt,
    StageStatus,
)
from pelican_town_specials.domain.errors import (
    AppError,
    ErrorPayload,
    ErrorSummary,
    trial_limit_error,
    trial_service_unavailable_error,
)
from pelican_town_specials.domain.state_machine import DraftAction, transition
from pelican_town_specials.domain.telemetry import (
    MAX_DURATION_MS,
    ErrorCategory,
    GenerationKind,
    GenerationOutcome,
    MemoryOutcome,
    RejectionReason,
    TelemetryEvent,
    TelemetryMode,
)
from pelican_town_specials.domain.validation import ValidationSeverity, validate_draft
from pelican_town_specials.images import (
    build_icon_16,
    downscale_for_vision,
)
from pelican_town_specials.images.background_keying import key_icon_background
from pelican_town_specials.images.vision_input import (
    EDIT_MIN_PIXELS,
    VISION_MIN_PIXELS,
)
from pelican_town_specials.persistence.asset_store import AssetMetadata, FileAssetStore
from pelican_town_specials.persistence.repositories import (
    AttemptMismatchError,
    DraftRepository,
    GenerationAttemptRepository,
    RevisionConflictError,
)
from pelican_town_specials.providers.contracts import (
    AskGusDesignRequest,
    DishAnalysisRequest,
    GeneratedDishCore,
    GeneratedImage,
    ImageGenerationRequest,
    ImageMediaType,
    ImageOperation,
    ModelGateway,
    ProviderImageInput,
)

from .attempt_registry import MAX_CONCURRENT_GENERATIONS, AttemptRegistry
from .blueprint import (
    BLUEPRINT_STAGE_ORDER,
    blueprint_icon_prompt,
    blueprint_preview_prompt,
    build_blueprint_visual_brief,
    build_full_tooltip_prompt,
    enforce_preview_prompt_budget,
)
from .events import (
    GenerationEvent,
    attempt_failed,
    attempt_started,
    attempt_succeeded,
    stage_started,
    stage_succeeded,
)

STAGE_ORDER = tuple(GenerationStage)

_ASK_GUS_PROMPT_VERSION = "ask-gus-v3"
_ANALYSIS_PROMPT_VERSION = "analysis-v1"
_VISUAL_PROMPT_VERSION = "visual-v3-multi-image-edit"
_ICON_SIZE = "1024x1024"

_CANONICAL_REUSED_AUTHORITY = {
    "presentation.display_name": FieldAuthority.CACHE_REUSED,
    "presentation.category_label": FieldAuthority.CACHE_REUSED,
    "presentation.description": FieldAuthority.CACHE_REUSED,
    "presentation.gus_comment": FieldAuthority.CACHE_REUSED,
    "presentation.tags": FieldAuthority.CACHE_REUSED,
    "presentation.internal_name": FieldAuthority.SYSTEM_GENERATED,
    "gameplay.ingredients": FieldAuthority.CACHE_REUSED,
    "gameplay.recovery": FieldAuthority.CACHE_REUSED,
    "gameplay.sell_price": FieldAuthority.CACHE_REUSED,
    "gameplay.is_drink": FieldAuthority.CACHE_REUSED,
    "gameplay.buff": FieldAuthority.CACHE_REUSED,
    "gameplay.recipe_unlock": FieldAuthority.CACHE_REUSED,
    "visuals.visual_brief": FieldAuthority.CACHE_REUSED,
    "visuals.icon_source_asset_id": FieldAuthority.CACHE_REUSED,
    "visuals.icon_16_asset_id": FieldAuthority.CACHE_REUSED,
    "visuals.preview_asset_id": FieldAuthority.SYSTEM_GENERATED,
    "visuals.source_revision": FieldAuthority.SYSTEM_GENERATED,
}


def _language_suffix(language: Language) -> str:
    return "en" if language is Language.EN_US else "zh"


class _RunState:
    __slots__ = (
        "analysis",
        "attempt",
        "attempt_id",
        "candidate",
        "canonical",
        "command",
        "core",
        "draft",
        "gameplay",
        "gateway",
        "icon_16",
        "icon_source",
        "icon_source_asset_id",
        "presentation",
        "preview",
        "provider_started",
        "recall_confidence",
        "recall_decision",
        "recall_elapsed_ms",
        "staged",
        "started_monotonic",
        "telemetry_finished",
        "telemetry_started",
        "trial_remaining",
        "trial_reserved",
        "trial_used",
        "visual_brief",
    )

    attempt_id: UUID
    command: GenerationCommand
    draft: DraftRecord
    candidate: DraftRecord
    canonical: CanonicalDish | None
    gateway: ModelGateway | None
    attempt: GenerationAttempt
    staged: DraftRecord
    analysis: DishAnalysis | None
    core: GeneratedDishCore | None
    gameplay: GameplaySpec | None
    presentation: PresentationSpec | None
    visual_brief: str | None
    icon_source: GeneratedImage | None
    icon_source_asset_id: UUID | None
    icon_16: AssetRef | None
    preview: AssetRef | None
    recall_confidence: float | None
    recall_decision: MemoryOutcome
    recall_elapsed_ms: int | None
    started_monotonic: float | None
    telemetry_started: bool
    telemetry_finished: bool
    provider_started: bool
    trial_reserved: bool
    trial_used: bool
    trial_remaining: int | None

    def __init__(
        self,
        *,
        attempt_id: UUID,
        command: GenerationCommand,
        draft: DraftRecord,
        candidate: DraftRecord,
        gateway: ModelGateway | None = None,
        attempt: GenerationAttempt,
        staged: DraftRecord,
        started_monotonic: float | None,
    ) -> None:
        self.attempt_id = attempt_id
        self.command = command
        self.draft = draft
        self.candidate = candidate
        self.gateway = gateway
        self.attempt = attempt
        self.staged = staged
        self.analysis = None
        self.core = None
        self.canonical = None
        self.gameplay = None
        self.presentation = None
        self.visual_brief = None
        self.icon_source = None
        self.icon_source_asset_id = None
        self.icon_16 = None
        self.preview = None
        self.recall_confidence = None
        self.recall_elapsed_ms = None
        self.recall_decision = (
            MemoryOutcome.NOT_ELIGIBLE
            if command.kind is not GenerationAttemptKind.INITIAL
            or draft.mode is not DraftMode.ASK_GUS
            else MemoryOutcome.UNAVAILABLE
        )
        self.started_monotonic = started_monotonic
        self.telemetry_started = False
        self.telemetry_finished = False
        self.provider_started = False
        self.trial_reserved = False
        self.trial_used = False
        self.trial_remaining = None


def _map_gameplay(
    core: GeneratedDishCore,
    catalog: VanillaCatalog,
    *,
    language: Language,
) -> GameplaySpec:
    ingredients: list[GameIngredient] = []
    used_item_ids: set[str] = set()
    for semantic in core.ingredients:
        candidates = _build_candidates(semantic, catalog)
        mapped = map_ingredient(
            semantic,
            candidates,
            catalog,
            used_item_ids=frozenset(used_item_ids),
            language=language,
        )
        used_item_ids.add(mapped.item_id)
        ingredients.append(mapped)
    ingredients = ensure_main_protein(
        _dish_text(core), ingredients, catalog, language=language
    )
    return GameplaySpec(
        ingredients=ingredients,
        recovery=core.recovery,
        sellPrice=core.sell_price,
        isDrink=core.is_drink,
        recipeUnlock=RecipeUnlock.DEFAULT,
        buff=core.buff,
    )


def _dish_text(core: GeneratedDishCore) -> str:
    """Concatenate the human-facing dish text used by consistency guards."""
    presentation = core.presentation
    parts = [
        presentation.display_name,
        presentation.category_label,
        presentation.description,
        *presentation.tags,
    ]
    if presentation.gus_comment:
        parts.append(presentation.gus_comment)
    return " ".join(parts)


def _build_candidates(
    semantic: object, catalog: VanillaCatalog
) -> list[CatalogCandidate]:
    name = getattr(semantic, "normalized_name", None) or getattr(semantic, "name", "")
    items = catalog.search_ingredients(str(name), limit=5)
    total = sum(item.edibility or 0 for item in items) or 1
    candidates = []
    for index, item in enumerate(items):
        score = 1.0 - (index / max(len(items), 1))
        if item.edibility is not None:
            score = score * (1.0 + (item.edibility / total))
        candidates.append(CatalogCandidate(item_id=item.item_id, score=score))
    return candidates


def _read_source_image(asset_store: FileAssetStore, draft: DraftRecord) -> bytes:
    ref = asset_store.stat(draft.source.original_image_asset_id)
    with asset_store.open(ref) as handle:
        return handle.read()


def _image_input_error(min_pixels: int = VISION_MIN_PIXELS) -> AppError:
    return AppError(
        code="PTS_IMAGE_INPUT_UNSUPPORTED",
        message="图片无法被图像服务接受：分辨率过低或格式不受支持。请上传更高分辨率的照片。",
        http_status=422,
        details={"minPixels": min_pixels},
        retryable=False,
    )


def _prepare_vision_input(
    data: bytes, *, min_pixels: int = VISION_MIN_PIXELS
) -> tuple[bytes, ImageMediaType]:
    """Shape source bytes for vision/EDIT providers; unsupported inputs (bad
    format, or aspect ratio that cannot meet the provider minimum pixel count
    within the max side) fail as a controlled non-retryable error instead of a
    raw ValueError surfacing as a 500."""
    try:
        return downscale_for_vision(data, min_pixels=min_pixels)
    except ValueError as exc:
        raise _image_input_error(min_pixels=min_pixels) from exc


def _domain_media_type(value: ImageMediaType) -> MediaType:
    return MediaType(value.value)


def _extension_for_media_type(value: ImageMediaType) -> str:
    if value is ImageMediaType.JPEG:
        return ".jpg"
    if value is ImageMediaType.WEBP:
        return ".webp"
    return ".png"


def _canonical_internal_name(canonical_internal_name: str, draft_id: UUID) -> str:
    """Keep a reused dish's readable ID while making each draft unique."""
    suffix = f"_{draft_id.hex[:8]}"
    prefix_length = 48 - len(suffix)
    return f"{canonical_internal_name[:prefix_length]}{suffix}"


def _expected_image_format(media_type: MediaType) -> str:
    if media_type is MediaType.PNG:
        return "PNG"
    if media_type is MediaType.JPEG:
        return "JPEG"
    if media_type is MediaType.WEBP:
        return "WEBP"
    raise ValueError("canonical icon media type is unsupported")


def _validate_canonical_icon_data(
    data: bytes,
    metadata: CanonicalIconMetadata,
    *,
    icon_16: bool,
) -> None:
    if len(data) != metadata.byte_size:
        raise ValueError("canonical icon byte size does not match metadata")
    if hashlib.sha256(data).hexdigest() != metadata.sha256:
        raise ValueError("canonical icon hash does not match metadata")
    if icon_16 and (
        metadata.media_type is not MediaType.PNG
        or (metadata.width, metadata.height) != (16, 16)
    ):
        raise ValueError("canonical icon16 must be PNG and exactly 16x16")
    try:
        with Image.open(io.BytesIO(data)) as image:
            actual_format = image.format
            actual_size = image.size
            image.verify()
    except Exception as exc:
        raise ValueError("canonical icon bytes are not a valid image") from exc
    if actual_format != _expected_image_format(metadata.media_type):
        raise ValueError("canonical icon media type does not match its bytes")
    if actual_size != (metadata.width, metadata.height):
        raise ValueError("canonical icon dimensions do not match metadata")


def _image_dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def _preview_size(data: bytes) -> str:
    width, height = _image_dimensions(data)
    return f"{width}x{height}"


def _icon_prompt(
    core: GeneratedDishCore,
    *,
    language: Language = Language.ZH_CN,
) -> str:
    if language is Language.EN_US:
        return (
            f"Stardew Valley-style 16×16 game icon: {core.presentation.display_name}"
            ". Use the source photo as the visual reference for the dish. Preserve the "
            "recognizable silhouette, main colors, plating, and key ingredient features; "
            "Do not make the table or photo background the subject. Convert only the "
            "dish into one Stardew Valley-style pixel item icon. Single item centered, "
            "use a removable solid magenta background (#FF00FF), no shadows, "
            "no reflections, no text, no borders"
        )
    return (
        f"星露谷风格的 16×16 游戏图标：{core.presentation.display_name}"
        "。参考输入图中的菜品主体，保留可辨识的轮廓、主要配色、摆盘形态和关键食材特征；"
        "不要把桌面或照片背景作为主体。将菜品转为单个星露谷风格的像素物品图标。"
        "单个物品居中，使用便于抠图的纯洋红色背景（#FF00FF），无阴影、无反光、无文字、无边框"
    )


def _preview_prompt(
    presentation: PresentationSpec,
    gameplay: GameplaySpec,
    *,
    language: Language = Language.ZH_CN,
) -> str:
    """Build the shared hard-anchor full tooltip edit prompt from validated
    fields (Ask Gus consumes the same prompt language as Blueprint)."""
    return build_full_tooltip_prompt(presentation, gameplay, language=language)


def _to_summary(error: AppError) -> ErrorSummary:
    from uuid import uuid4 as _uuid4

    return ErrorSummary(
        code=error.code,
        message=error.message,
        retryable=error.retryable,
        request_id=_uuid4(),
        occurred_at=utc_now(),
    )


def _generated_provenance(draft: DraftRecord) -> Provenance:
    base = draft.provenance
    authority: dict[str, FieldAuthority] = {
        **base.authority_by_field,
        "presentation.display_name": FieldAuthority.AGENT_ASSIGNED,
        "presentation.internal_name": FieldAuthority.AGENT_ASSIGNED,
        "presentation.category_label": FieldAuthority.AGENT_ASSIGNED,
        "presentation.description": FieldAuthority.AGENT_ASSIGNED,
        "presentation.gus_comment": FieldAuthority.AGENT_ASSIGNED,
        "presentation.tags": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.ingredients": FieldAuthority.SYSTEM_GENERATED,
        "gameplay.recovery": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.sell_price": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.is_drink": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.buff": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.recipe_unlock": FieldAuthority.AGENT_ASSIGNED,
        "visuals.visual_brief": FieldAuthority.AGENT_ASSIGNED,
        "visuals.icon_source_asset_id": FieldAuthority.SYSTEM_GENERATED,
        "visuals.icon_16_asset_id": FieldAuthority.SYSTEM_GENERATED,
        "visuals.preview_asset_id": FieldAuthority.SYSTEM_GENERATED,
        "visuals.source_revision": FieldAuthority.SYSTEM_GENERATED,
    }
    suffix = _language_suffix(draft.source.language)
    return base.model_copy(
        update={
            "authority_by_field": authority,
            "prompt_versions": {
                **base.prompt_versions,
                "analysis": f"{_ANALYSIS_PROMPT_VERSION}-{suffix}",
                "ask-gus": f"{_ASK_GUS_PROMPT_VERSION}-{suffix}",
                "visual": f"{_VISUAL_PROMPT_VERSION}-{suffix}",
            },
            "generation_source": GenerationSource.FRESH_GENERATION,
            "canonical_dish_id": None,
            "canonical_dish_signature": None,
            "recall_confidence": None,
            "recall_elapsed_ms": None,
        }
    )


def _canonical_reused_provenance(state: _RunState) -> Provenance:
    assert state.canonical is not None
    base = state.draft.provenance
    suffix = _language_suffix(state.draft.source.language)
    prompt_versions = {
        key: value
        for key, value in base.prompt_versions.items()
        if key != "ask-gus"
    }
    prompt_versions.update(
        {
            "analysis": f"{_ANALYSIS_PROMPT_VERSION}-{suffix}",
            "visual": f"{_VISUAL_PROMPT_VERSION}-{suffix}",
        }
    )
    return base.model_copy(
        update={
            "authority_by_field": {
                **base.authority_by_field,
                **_CANONICAL_REUSED_AUTHORITY,
            },
            "prompt_versions": prompt_versions,
            "generation_source": GenerationSource.CANONICAL_REUSED,
            "canonical_dish_id": state.canonical.canonical_id,
            "canonical_dish_signature": state.canonical.dish_signature,
            "recall_confidence": state.recall_confidence,
            "recall_elapsed_ms": state.recall_elapsed_ms,
        }
    )


def _busy_error(registry: AttemptRegistry, draft_id: UUID) -> AppError:
    return AppError(
        code="PTS_GEN_BUSY",
        message="当前已有一个生成任务在运行，请稍后重试。",
        http_status=409,
        details={
            "activeCount": registry.active_count(),
            "maxConcurrent": MAX_CONCURRENT_GENERATIONS,
            "draftId": str(draft_id),
        },
        retryable=False,
    )


def _draft_not_found_error() -> AppError:
    return AppError(
        code="PTS_DRAFT_NOT_FOUND",
        message="草稿不存在或已删除。",
        http_status=404,
        details={},
        retryable=False,
    )


def _illegal_state_error() -> AppError:
    return AppError(
        code="PTS_STATE_ILLEGAL_TRANSITION",
        message="草稿当前状态不允许生成。",
        http_status=409,
        details={},
        retryable=False,
    )


def _low_confidence_error(confidence: float) -> AppError:
    return AppError(
        code="PTS_GEN_LOW_CONFIDENCE",
        message="图片识别置信度过低，请换一张更清晰的照片。",
        http_status=422,
        details={"confidence": confidence},
        retryable=False,
    )


def _validation_error() -> AppError:
    return AppError(
        code="PTS_GEN_VALIDATION_FAILED",
        message="生成结果未通过校验。",
        http_status=502,
        details={},
        retryable=False,
    )


def _image_edit_capability_error() -> AppError:
    return AppError(
        code="PTS_PROVIDER_IMAGE_EDIT_UNSUPPORTED",
        message="当前图像服务不支持双图编辑，无法生成词条卡预览。",
        http_status=502,
        details={"requiredCapability": "multi-image-edit"},
        retryable=False,
    )


def _ensure_image_edit_capability(gateway: ModelGateway) -> None:
    """Honor an explicitly reported capability without changing the gateway API.

    The current OpenAI-compatible gateway already exposes the EDIT transport
    path, so it has no capability property to consult. Probe-aware gateways may
    attach either ``image_edits_supported`` or ``capabilities.image_edits``;
    an explicit false stops the stage and never enables a local fallback.
    """
    if getattr(gateway, "image_edits_supported", None) is False:
        raise _image_edit_capability_error()
    capabilities = getattr(gateway, "capabilities", None)
    image_edits = getattr(capabilities, "image_edits", None)
    if image_edits is not None and getattr(image_edits, "supported", True) is False:
        raise _image_edit_capability_error()


def _stale_error() -> AppError:
    return AppError(
        code="PTS_STATE_REVISION_CONFLICT",
        message="生成结果已过期，请重试。",
        http_status=409,
        details={},
        retryable=False,
    )


def _cancelled_error() -> AppError:
    return AppError(
        code="PTS_GEN_CANCELLED",
        message="生成任务已取消。",
        http_status=202,
        details={},
        retryable=False,
    )


def _interrupted_error() -> AppError:
    return AppError(
        code="PTS_GEN_INTERRUPTED",
        message="生成任务已中断，请重新生成。",
        http_status=202,
        details={},
        retryable=True,
    )


def _unexpected_error(exc: Exception) -> AppError:
    return AppError(
        code="PTS_GEN_UNEXPECTED",
        message="生成过程出现意外错误。",
        http_status=500,
        details={"kind": type(exc).__name__},
        retryable=True,
    )


class GenerationCommand(StrictModel):
    draft_id: UUID = Field(alias="draftId")
    kind: GenerationAttemptKind
    request_id: UUID = Field(alias="requestId")


GatewayFactory = Callable[[], ModelGateway]


class TrialAccess(Protocol):
    """Trial enrollment hook consulted before the first provider call."""

    def is_active(self) -> bool: ...

    def preference(self) -> TrialProviderPreference: ...

    def trial_opportunity(self) -> bool: ...

    def reserve_attempt(self, attempt_id: UUID) -> bool: ...

    def commit_attempt(self, attempt_id: UUID) -> int | None: ...

    def release_attempt(self, attempt_id: UUID) -> bool: ...


_STREAM_END = object()


class _ServerOwnedStream:
    """Response-side view of a server-owned generation task.

    The generation stage loop runs in a background asyncio task owned by the
    server; this iterator reads its NDJSON events from an in-process queue.
    Closing this iterator (client disconnect / page nav / reload) only detaches
    this subscriber — the background task keeps running, owns the slot, and
    writes its terminal state. Only an explicit /cancel terminates it.
    """

    def __init__(
        self,
        orchestrator: GenerationOrchestrator,
        command: GenerationCommand,
        attempt_id: UUID,
        registry: AttemptRegistry,
    ) -> None:
        self._orchestrator = orchestrator
        self._command = command
        self._attempt_id = attempt_id
        self._registry = registry
        self._queue: asyncio.Queue[object] | None = None
        self._task: asyncio.Task[None] | None = None
        self._started = False

    def __aiter__(self) -> _ServerOwnedStream:
        return self

    def _ensure_started(self) -> None:
        if not self._started:
            self._started = True
            self._queue = asyncio.Queue()
            self._task = asyncio.create_task(
                self._orchestrator._run_server_owned(
                    self._command, self._attempt_id, self._queue
                )
            )
            # Track the task immediately so an /cancel that lands before the
            # background task runs its own register() still finds it.
            self._registry.register(self._attempt_id, self._task)

    async def __anext__(self) -> GenerationEvent:
        self._ensure_started()
        assert self._queue is not None
        item = await self._queue.get()
        if item is _STREAM_END:
            raise StopAsyncIteration
        if isinstance(item, AppError):
            # Re-surface a pre-stage AppError raised by the background task.
            raise item
        # The queue carries only GenerationEvent, _STREAM_END, or a re-raised
        # AppError; anything else would be a programming error.
        assert isinstance(item, GenerationEvent)
        return item

    async def aclose(self) -> None:
        # Detach this subscriber only: never cancel the server-owned task. If
        # the task was never started (stream dropped before its body began),
        # release the slot reserved in run(); otherwise the background task
        # owns the slot and releases it when the generation finishes.
        if not self._started:
            self._registry.release_slot(self._attempt_id)
            self._registry.unregister(self._attempt_id)

    def __del__(self) -> None:
        # GC safety for the never-started case (response abandoned before any
        # iteration): release the slot so a future generation is not blocked.
        try:
            if not self._started:
                self._registry.release_slot(self._attempt_id)
                self._registry.unregister(self._attempt_id)
        except Exception:  # noqa: BLE001, S110 - __del__ must never raise
            pass


class GenerationOrchestrator:
    def __init__(
        self,
        *,
        draft_repository: DraftRepository,
        attempt_repository: GenerationAttemptRepository,
        asset_store: FileAssetStore,
        catalog: VanillaCatalog,
        gateway_factory: GatewayFactory,
        registry: AttemptRegistry,
        min_confidence: float,
        clock: Callable[[], float] = monotonic,
        trial_access: TrialAccess | None = None,
        trial_gateway_factory: GatewayFactory | None = None,
        personal_configured: Callable[[], bool] = lambda: False,
        canonical_repository: CanonicalRepository | None = None,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self._drafts = draft_repository
        self._attempts = attempt_repository
        self._assets = asset_store
        self._catalog = catalog
        self._gateway_factory = gateway_factory
        self._trial_access = trial_access
        self._trial_gateway_factory = trial_gateway_factory
        self._personal_configured = personal_configured
        self._canonical_repository = canonical_repository
        self._registry = registry
        self._min_confidence = min_confidence
        self._clock = clock
        self._telemetry = (
            telemetry if telemetry is not None else NoopTelemetryRecorder()
        )

    def run(self, command: GenerationCommand) -> AsyncIterator[GenerationEvent]:
        # The attempt id is created up front so the slot can be attributed to
        # its owning draft and attempt before any stream begins.
        attempt_id = uuid4()
        if not self._registry.reserve_slot(command.draft_id, attempt_id):
            error = _busy_error(self._registry, command.draft_id)
            self._record_rejection_for_error(error)
            raise error
        return _ServerOwnedStream(self, command, attempt_id, self._registry)

    def cancel(self, attempt_id: UUID) -> bool:
        """Request cancellation of a running attempt; returns whether it was tracked."""
        return self._registry.request_cancel(attempt_id, "user requested cancellation")

    async def await_cancelled(self, attempt_id: UUID) -> None:
        """Wait for a cancelled attempt's rollback to finish (best-effort).

        The synchronous ``cancel`` only fires the cancellation; this awaits the
        tracked task so callers know the draft rollback and slot release have
        completed before returning (e.g. a 202 from the cancel route).
        """
        await self._registry.await_task(attempt_id)

    def recover_interrupted(self, draft_id: UUID) -> bool:
        """Roll a draft back out of a generating state whose attempt is no
        longer tracked in this process.

        Applies when the client disconnected and the stream task was dropped,
        or when the process restarted over a previously generating draft. The
        draft returns to its pre-generation status (READY for INITIAL,
        REVIEWABLE for regeneration, STALE_PREVIEW for a cancelled blueprint
        preview), the active attempt is cleared, and the persisted attempt is
        marked INTERRUPTED so a fresh generation can start. Returns whether a
        recovery was applied.
        """
        try:
            draft = self._drafts.get(draft_id)
        except (FileNotFoundError, OSError):
            return False
        attempt_id = draft.active_attempt_id
        if attempt_id is None:
            return False
        if draft.status is DraftStatus.GENERATING:
            action = DraftAction.GENERATION_CANCELLED
        elif draft.status is DraftStatus.REGENERATING:
            action = DraftAction.REGENERATION_CANCELLED
        elif draft.status is DraftStatus.STALE_PREVIEW:
            rolled = draft
        else:
            return False
        if draft.status in (DraftStatus.GENERATING, DraftStatus.REGENERATING):
            rolled = transition(draft, action)
        rolled = rolled.model_copy(
            update={
                "last_attempt_id": attempt_id,
                "last_error": _to_summary(_interrupted_error()),
                "active_attempt_id": None,
                "updated_at": utc_now(),
            }
        )
        try:
            self._drafts.control_write(
                rolled,
                expected_revision=draft.revision,
                expected_attempt_id=attempt_id,
            )
        except (RevisionConflictError, AttemptMismatchError):
            # State changed concurrently; someone else owns the recovery.
            return False
        try:
            attempt = self._attempts.get(attempt_id)
        except (FileNotFoundError, OSError):
            return True
        interrupted = attempt.model_copy(
            update={"status": AttemptStatus.INTERRUPTED, "finished_at": utc_now()}
        )
        self._attempts.save(interrupted)
        return True

    @property
    def drafts(self) -> DraftRepository:
        return self._drafts

    @property
    def attempts(self) -> GenerationAttemptRepository:
        return self._attempts

    @property
    def assets(self) -> FileAssetStore:
        return self._assets

    def _record_telemetry(self, event: TelemetryEvent) -> None:
        try:
            self._telemetry.record(event)
        except Exception:  # noqa: BLE001 - telemetry is explicitly fail-open
            return

    def _capture_monotonic(self) -> float | None:
        try:
            return self._clock()
        except Exception:  # noqa: BLE001 - telemetry clock is fail-open
            return None

    def _record_generation_started(self, state: _RunState) -> None:
        if state.telemetry_started:
            return
        state.telemetry_started = True
        if state.started_monotonic is None:
            state.started_monotonic = self._capture_monotonic()
        self._record_telemetry(
            TelemetryEvent.generation_started(
                mode=_telemetry_mode(state.draft.mode),
                trial_used=state.trial_used,
                generation_kind=_telemetry_generation_kind(state.command.kind),
            )
        )

    def _record_generation_finished(
        self,
        state: _RunState,
        *,
        outcome: GenerationOutcome,
        error_category: ErrorCategory,
        error: AppError | None = None,
    ) -> None:
        if state.telemetry_finished:
            return
        state.telemetry_finished = True
        self._record_generation_started(state)
        if error is not None:
            reason = _rejection_reason(error, provider_started=state.provider_started)
            if reason is not None:
                self._record_telemetry(
                    TelemetryEvent.generation_rejected(reason=reason)
                )
        self._record_telemetry(
            TelemetryEvent.generation_finished(
                mode=_telemetry_mode(state.draft.mode),
                outcome=outcome,
                duration_ms=_duration_ms(self._clock, state.started_monotonic),
                trial_used=state.trial_used,
                memory_outcome=state.recall_decision,
                error_category=error_category,
            )
        )

    def _record_rejection_for_error(self, error: AppError) -> None:
        reason = _rejection_reason(error, provider_started=False)
        if reason is not None:
            self._record_telemetry(TelemetryEvent.generation_rejected(reason=reason))

    async def _run_server_owned(
        self,
        command: GenerationCommand,
        attempt_id: UUID,
        queue: asyncio.Queue[object],
    ) -> None:
        """Run the generation stage loop to completion in the background.

        Task 19.2: the generation is owned by the server, not by any HTTP
        connection. The stage loop runs here to its terminal state and publishes
        each event into ``queue``; a subscriber that detaches (client disconnect
        / page nav / reload) simply stops reading. Only an explicit /cancel
        (CancelledError) terminates the attempt. The slot is released here on
        every termination path.
        """
        self._registry.register(attempt_id, asyncio.current_task())
        try:
            async with self._registry.semaphore():
                queue.put_nowait(attempt_started(attempt_id))
                inner = self._run(command, attempt_id)
                try:
                    async for event in inner:
                        queue.put_nowait(event)
                except AppError as exc:
                    # A pre-stage AppError (e.g. illegal state) is raised by
                    # _run before it yields any terminal event. Surface it to
                    # the subscriber exactly like the old stream contract did.
                    self._record_rejection_for_error(exc)
                    queue.put_nowait(exc)
                finally:
                    await inner.aclose()
        finally:
            self._registry.release_slot(attempt_id)
            self._registry.unregister(attempt_id)
            queue.put_nowait(_STREAM_END)

    async def _run(
        self, command: GenerationCommand, attempt_id: UUID
    ) -> AsyncGenerator[GenerationEvent]:
        try:
            draft = self._drafts.get(command.draft_id)
        except (FileNotFoundError, OSError) as exc:
            raise _draft_not_found_error() from exc
        if command.kind is GenerationAttemptKind.INITIAL:
            if draft.status is DraftStatus.DRAFT:
                ready = transition(draft, DraftAction.FIELDS_READY)
                staged = transition(ready, DraftAction.START_INITIAL_GENERATION)
            elif draft.status is DraftStatus.READY:
                staged = transition(draft, DraftAction.START_INITIAL_GENERATION)
            elif draft.status is DraftStatus.FAILED:
                staged = transition(draft, DraftAction.RETRY_FAILED_GENERATION)
            else:
                raise _illegal_state_error()
        elif command.kind is GenerationAttemptKind.FULL_REGENERATE:
            if draft.status is not DraftStatus.REVIEWABLE:
                raise _illegal_state_error()
            staged = transition(draft, DraftAction.START_FULL_REGENERATION)
        elif command.kind is GenerationAttemptKind.BLUEPRINT_PREVIEW:
            if draft.status is not DraftStatus.STALE_PREVIEW:
                raise _illegal_state_error()
            staged = draft
        else:
            raise _illegal_state_error()

        stage_order = (
            BLUEPRINT_STAGE_ORDER
            if draft.mode is DraftMode.BLUEPRINT
            else STAGE_ORDER
        )
        staged = staged.model_copy(update={"active_attempt_id": attempt_id})
        self._drafts.control_write(
            staged, expected_revision=draft.revision, expected_attempt_id=None
        )
        attempt = self._new_attempt(
            command,
            attempt_id,
            draft.revision,
            total_stages=len(stage_order),
        )
        self._attempts.save(attempt)
        started_monotonic = self._capture_monotonic()

        state = _RunState(
            attempt_id=attempt_id,
            command=command,
            draft=draft,
            candidate=draft.model_copy(),
            attempt=attempt,
            staged=staged,
            started_monotonic=started_monotonic,
        )
        try:
            for ordinal, stage in enumerate(stage_order, start=1):
                if self._registry.is_cancelled(attempt_id):
                    yield await self._finish_cancelled(state, staged)
                    return
                yield stage_started(attempt_id, stage, ordinal, len(stage_order))
                try:
                    await self._execute_stage(state, stage)
                except AppError as exc:
                    yield await self._finish_failed(state, staged, exc, attempt_id)
                    return
                except asyncio.CancelledError:
                    yield await self._finish_cancelled(state, staged)
                    return
                except Exception as exc:  # noqa: BLE001
                    yield await self._finish_failed(
                        state, staged, _unexpected_error(exc), attempt_id
                    )
                    return
                self._attempts.save(self._advance_stage(state, stage))
                yield stage_succeeded(attempt_id, stage, ordinal, len(stage_order))
        except asyncio.CancelledError:
            # Explicit /cancel (task.cancel) or a cancellation landing at a
            # yield boundary: roll back and emit the cancelled terminal event.
            yield await self._finish_cancelled(state, staged)
            return
        except GeneratorExit:
            # Task 19.2: a client disconnect (abort / close / page nav) only
            # detaches the response subscriber; the server-owned generation
            # continues and the draft/attempt state is preserved. This branch
            # only fires if the server task itself is torn down unexpectedly at
            # a yield; no event is yielded and nothing is rolled back.
            raise

        try:
            promoted = self._drafts.promote(
                state.candidate,
                expected_revision=draft.revision,
                expected_attempt_id=attempt_id,
            )
        except (RevisionConflictError, AttemptMismatchError):
            yield await self._finish_failed(state, staged, _stale_error(), attempt_id)
            return
        except Exception as exc:  # noqa: BLE001 - promotion failures must release trial reservations
            yield await self._finish_failed(
                state, staged, _unexpected_error(exc), attempt_id
            )
            return
        try:
            self._commit_trial_after_generation_success(state)
        except Exception as exc:  # noqa: BLE001 - quota commit must fail closed
            yield await self._finish_failed(
                state,
                staged,
                _unexpected_error(exc),
                attempt_id,
                promoted=promoted,
            )
            return
        finished = self._finish_success(state, promoted)
        self._attempts.save(finished)
        self._record_generation_finished(
            state,
            outcome=GenerationOutcome.SUCCEEDED,
            error_category=ErrorCategory.NONE,
        )
        yield attempt_succeeded(
            attempt_id,
            promoted.revision,
            promoted.model_dump(by_alias=True, mode="json"),
        )

    def _ensure_gateway(self, state: _RunState) -> ModelGateway:
        """Build the per-attempt gateway lazily at the first provider call.

        Idempotent: the first call caches the gateway on the run state so a
        single attempt reserves at most one trial generation. The persisted
        preference is read only at this boundary; once a gateway is selected,
        later preference changes cannot hot-switch the running attempt.

        ``PERSONAL`` bypasses trial reservation entirely. ``TRIAL_FIRST``
        preserves the existing Task 40 behavior: configured users consume an
        available trial first and fall back to their personal provider when it
        is exhausted, while users without a personal provider keep the opt-in
        trial flow.
        """
        if state.gateway is not None:
            return state.gateway
        if self._trial_access is not None and self._trial_gateway_factory is not None:
            if self._trial_preference() is TrialProviderPreference.PERSONAL:
                state.gateway = self._gateway_factory()
                self._record_generation_started(state)
                return state.gateway
            if self._personal_configured():
                if (
                    self._trial_access.trial_opportunity()
                    and self._trial_access.reserve_attempt(state.attempt_id)
                ):
                    state.trial_reserved = True
                    state.gateway = self._trial_gateway_factory()
                    return state.gateway
                state.gateway = self._gateway_factory()
                self._record_generation_started(state)
                return state.gateway
            # Users without a personal provider keep the opt-in trial flow.
            if self._trial_access.is_active():
                if not self._trial_access.reserve_attempt(state.attempt_id):
                    raise trial_limit_error()
                state.trial_reserved = True
                state.gateway = self._trial_gateway_factory()
                return state.gateway
        state.gateway = self._gateway_factory()
        self._record_generation_started(state)
        return state.gateway

    def _trial_preference(self) -> TrialProviderPreference:
        """Read the trial preference with compatibility-safe fail-open behavior."""
        if self._trial_access is None:
            return TrialProviderPreference.TRIAL_FIRST
        getter = getattr(self._trial_access, "preference", None)
        if getter is None:
            # Task 40 test doubles and older integrations did not expose the
            # optional preference hook; their historical behavior is trial-first.
            return TrialProviderPreference.TRIAL_FIRST
        try:
            value = getter()
            return (
                value
                if isinstance(value, TrialProviderPreference)
                else TrialProviderPreference(value)
            )
        except (TypeError, ValueError):
            # A malformed preference must never trigger a hot switch or expose
            # storage details. Keep the conservative historical route.
            return TrialProviderPreference.TRIAL_FIRST

    def _commit_trial_after_generation_success(self, state: _RunState) -> None:
        """Commit a trial only after complete generation and Draft promotion."""
        if (
            self._trial_access is None
            or not state.trial_reserved
            or state.trial_used
        ):
            return
        remaining = self._trial_access.commit_attempt(state.attempt_id)
        if remaining is None:
            # The real service returns a fixed snapshot for every reservation.
            # Treat a missing snapshot as an accounting failure rather than
            # silently claiming a quota unit without persisting its attempt
            # state. The reservation remains available for the failure path to
            # release because no successful attempt snapshot was written.
            raise RuntimeError("trial reservation disappeared before commit")
        state.trial_used = True
        state.trial_remaining = remaining
        state.trial_reserved = False
        state.attempt = state.attempt.model_copy(
            update={
                "trial_used": True,
                "trial_remaining": remaining,
            }
        )
        # Persist the immutable attempt snapshot before lifecycle telemetry.
        self._attempts.save(state.attempt)
        self._record_generation_started(state)

    def _release_trial_reservation(self, state: _RunState) -> None:
        """Release a reservation that has not reached terminal success."""
        if (
            self._trial_access is None
            or not state.trial_reserved
            or state.trial_used
        ):
            return
        with suppress(Exception):
            self._trial_access.release_attempt(state.attempt_id)
        state.trial_reserved = False

    def _trial_failure_error(
        self,
        state: _RunState,
        error: AppError,
    ) -> AppError:
        """Map a pre-success trial failure to the stable redacted contract."""
        if (
            self._trial_access is not None
            and state.trial_reserved
            and not state.trial_used
        ):
            self._release_trial_reservation(state)
            return trial_service_unavailable_error(
                personal_provider_configured=self._safe_personal_configured()
            )
        return error

    def _safe_personal_configured(self) -> bool:
        """Evaluate the local provider predicate without leaking read failures."""
        try:
            return bool(self._personal_configured())
        except Exception:  # noqa: BLE001 - a settings read must not mask trial error mapping
            return False

    def _import_canonical_icons(
        self,
        state: _RunState,
        canonical: CanonicalDish,
    ) -> tuple[GeneratedImage, AssetRef, AssetRef]:
        repository = self._canonical_repository
        if repository is None:
            raise ValueError("canonical Registry is unavailable")

        source_data = repository.load_owned_icon(
            canonical.canonical_id,
            CanonicalIconKind.SOURCE,
        )
        icon_16_data = repository.load_owned_icon(
            canonical.canonical_id,
            CanonicalIconKind.ICON_16,
        )
        _validate_canonical_icon_data(
            source_data,
            canonical.icon_source,
            icon_16=False,
        )
        _validate_canonical_icon_data(
            icon_16_data,
            canonical.icon_16,
            icon_16=True,
        )
        source_media_type = ImageMediaType(canonical.icon_source.media_type.value)
        icon_16_media_type = ImageMediaType(canonical.icon_16.media_type.value)
        source_revision = state.draft.revision + 1
        source_ref = self._assets.put(
            source_data,
            AssetMetadata(
                kind=AssetKind.ICON_SOURCE,
                mediaType=canonical.icon_source.media_type,
                fileExtension=_extension_for_media_type(source_media_type),
                width=canonical.icon_source.width,
                height=canonical.icon_source.height,
                sourceRevision=source_revision,
                attemptId=state.attempt_id,
            ),
        )
        icon_16_ref = self._assets.put(
            icon_16_data,
            AssetMetadata(
                kind=AssetKind.ICON_16,
                mediaType=canonical.icon_16.media_type,
                fileExtension=_extension_for_media_type(icon_16_media_type),
                width=canonical.icon_16.width,
                height=canonical.icon_16.height,
                sourceRevision=source_revision,
                attemptId=state.attempt_id,
            ),
        )
        return (
            GeneratedImage(data=source_data, media_type=source_media_type),
            source_ref,
            icon_16_ref,
        )

    async def _try_canonical_recall(self, state: _RunState) -> bool:
        if (
            self._canonical_repository is None
            or state.command.kind is not GenerationAttemptKind.INITIAL
            or state.draft.mode is not DraftMode.ASK_GUS
        ):
            return False
        assert state.analysis is not None
        # Keep _ensure_gateway outside the fail-open recall boundary: a trial
        # limit error is the existing generation error and must not cause a
        # second reservation attempt while falling back to design.
        gateway = self._ensure_gateway(state)
        try:
            state.provider_started = True
            result = await RecallService(
                registry=self._canonical_repository,
                gateway=gateway,
            ).recall(
                state.analysis,
                state.draft.source.context_text,
                state.draft.source.language,
                self._catalog.version,
                state.command.request_id,
            )
            state.recall_decision = _memory_outcome_for_recall(result.decision)
            if result.decision is not RecallDecision.MATCH_HIT:
                return False
            canonical = result.canonical_dish
            if canonical is None:
                state.recall_decision = MemoryOutcome.FALLBACK_ERROR
                return False
            gameplay_report = validate_gameplay(canonical.gameplay, self._catalog)
            if any(
                issue.severity is ValidationSeverity.ERROR
                for issue in gameplay_report.issues
            ):
                state.recall_decision = MemoryOutcome.FALLBACK_ERROR
                return False
            icon_source, icon_source_ref, icon_16_ref = self._import_canonical_icons(
                state,
                canonical,
            )
            state.canonical = canonical
            state.recall_confidence = result.trace.confidence
            state.recall_elapsed_ms = result.trace.elapsed_ms
            state.presentation = canonical.presentation.model_copy(
                update={
                    "internal_name": _canonical_internal_name(
                        canonical.presentation.internal_name,
                        state.draft.draft_id,
                    )
                }
            )
            state.gameplay = canonical.gameplay
            state.visual_brief = canonical.visual_brief
            state.icon_source = icon_source
            state.icon_source_asset_id = icon_source_ref.asset_id
            state.icon_16 = icon_16_ref
            return True
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - memory failures degrade to fresh
            state.recall_decision = MemoryOutcome.FALLBACK_ERROR
            return False

    async def _execute_stage(self, state: _RunState, stage: GenerationStage) -> None:
        draft = state.draft
        if stage is GenerationStage.INPUT_VALIDATION:
            self._assets.stat(draft.source.original_image_asset_id)
        elif stage is GenerationStage.DISH_ANALYSIS:
            vision_data, vision_media = _prepare_vision_input(
                _read_source_image(self._assets, draft)
            )
            gateway = self._ensure_gateway(state)
            state.provider_started = True
            state.analysis = await gateway.analyze_dish(
                DishAnalysisRequest(
                    image=ProviderImageInput(
                        data=vision_data,
                        media_type=vision_media,
                    ),
                    context_text=draft.source.context_text,
                    language=draft.source.language,
                    request_id=state.command.request_id,
                )
            )
            if state.analysis.confidence < self._min_confidence:
                raise _low_confidence_error(state.analysis.confidence)
            self._update_candidate(state, analysis=state.analysis)
        elif stage is GenerationStage.GAMEPLAY_DESIGN:
            assert state.analysis is not None
            if await self._try_canonical_recall(state):
                assert state.presentation is not None
                self._update_candidate(state, presentation=state.presentation)
            else:
                gateway = self._ensure_gateway(state)
                state.provider_started = True
                state.core = await gateway.design_ask_gus(
                    AskGusDesignRequest(
                        analysis=state.analysis,
                        context_text=draft.source.context_text,
                        language=draft.source.language,
                        request_id=state.command.request_id,
                    )
                )
                state.presentation = state.core.presentation
                self._update_candidate(state, presentation=state.presentation)
        elif stage is GenerationStage.INGREDIENT_MAPPING:
            if state.canonical is None:
                assert state.core is not None
                state.gameplay = _map_gameplay(
                    state.core, self._catalog, language=draft.source.language
                )
            else:
                assert state.gameplay is not None
            self._update_candidate(state, gameplay=state.gameplay)
        elif stage is GenerationStage.VISUAL_BRIEF:
            if state.canonical is not None:
                assert state.visual_brief is not None
            elif draft.mode is DraftMode.BLUEPRINT:
                assert draft.presentation is not None
                assert draft.gameplay is not None
                state.visual_brief = build_blueprint_visual_brief(
                    draft.presentation,
                    draft.gameplay,
                    language=draft.source.language,
                )
            else:
                assert state.core is not None
                state.visual_brief = state.core.visual_brief
        elif stage is GenerationStage.ICON_GENERATION_AND_NORMALIZATION:
            if state.canonical is not None:
                assert state.icon_source is not None
                assert state.icon_source_asset_id is not None
                assert state.icon_16 is not None
                return
            if draft.mode is DraftMode.BLUEPRINT:
                assert draft.presentation is not None
                icon_prompt = blueprint_icon_prompt(
                    draft.presentation, language=draft.source.language
                )
            else:
                assert state.core is not None
                icon_prompt = _icon_prompt(
                    state.core, language=draft.source.language
                )
            gateway = self._ensure_gateway(state)
            _ensure_image_edit_capability(gateway)
            icon_image, icon_media_type = _prepare_vision_input(
                _read_source_image(self._assets, draft), min_pixels=EDIT_MIN_PIXELS
            )
            state.provider_started = True
            generated_icon = await gateway.generate_image(
                ImageGenerationRequest(
                    operation=ImageOperation.EDIT,
                    prompt=icon_prompt,
                    source_images=[
                        ProviderImageInput(
                            data=icon_image,
                            media_type=icon_media_type,
                        )
                    ],
                    size=_ICON_SIZE,
                    request_id=state.command.request_id,
                )
            )
            # R12: models often return an opaque solid backdrop despite the
            # transparent-background instruction; key it out deterministically
            # so the stored icon source and the 16x16 icon are truly
            # transparent in game.
            keyed = key_icon_background(generated_icon.data)
            icon_media_type = (
                ImageMediaType.PNG if keyed.changed else generated_icon.media_type
            )
            state.icon_source = GeneratedImage(
                data=keyed.data, media_type=icon_media_type
            )
            icon_w, icon_h = _image_dimensions(state.icon_source.data)
            icon_source_ref = self._assets.put(
                state.icon_source.data,
                AssetMetadata(
                    kind=AssetKind.ICON_SOURCE,
                    mediaType=_domain_media_type(icon_media_type),
                    fileExtension=_extension_for_media_type(icon_media_type),
                    width=icon_w,
                    height=icon_h,
                ),
            )
            state.icon_source_asset_id = icon_source_ref.asset_id
            icon_bytes = build_icon_16(state.icon_source.data)
            state.icon_16 = self._assets.put(
                icon_bytes,
                AssetMetadata(
                    kind=AssetKind.ICON_16,
                    mediaType=MediaType.PNG,
                    fileExtension=".png",
                    width=16,
                    height=16,
                ),
            )
        elif stage is GenerationStage.PREVIEW_ART_GENERATION_AND_COMPOSITION:
            if draft.mode is DraftMode.BLUEPRINT:
                assert draft.presentation is not None
                assert draft.gameplay is not None
                snapshot_presentation = draft.presentation
                snapshot_gameplay = draft.gameplay
                prompt = blueprint_preview_prompt(
                    snapshot_presentation,
                    snapshot_gameplay,
                    language=draft.source.language,
                )
            elif state.canonical is not None:
                assert state.presentation is not None
                assert state.gameplay is not None
                snapshot_presentation = state.presentation
                snapshot_gameplay = state.gameplay
                prompt = _preview_prompt(
                    snapshot_presentation,
                    snapshot_gameplay,
                    language=draft.source.language,
                )
            else:
                assert state.core is not None
                assert state.presentation is not None
                assert state.gameplay is not None
                snapshot_presentation = state.presentation
                snapshot_gameplay = state.gameplay
                prompt = _preview_prompt(
                    snapshot_presentation,
                    snapshot_gameplay,
                    language=draft.source.language,
                )
            # Shared final budget gate for both modes: business fields stay
            # verbatim; an over-limit prompt fails controlled, pre-provider.
            enforce_preview_prompt_budget(prompt)
            assert state.icon_source_asset_id is not None
            assert state.icon_source is not None
            gateway = self._ensure_gateway(state)
            _ensure_image_edit_capability(gateway)
            original_image = _read_source_image(self._assets, draft)
            edit_image, edit_media_type = _prepare_vision_input(
                original_image, min_pixels=EDIT_MIN_PIXELS
            )
            icon_source_ref = self._assets.stat(state.icon_source_asset_id)
            with self._assets.open(icon_source_ref) as handle:
                icon_source = handle.read()
            state.provider_started = True
            generated_preview = await gateway.generate_image(
                ImageGenerationRequest(
                    operation=ImageOperation.EDIT,
                    prompt=prompt,
                    source_images=[
                        ProviderImageInput(
                            data=edit_image,
                            media_type=edit_media_type,
                        ),
                        ProviderImageInput(
                            data=icon_source,
                            media_type=state.icon_source.media_type,
                        ),
                    ],
                    size=_preview_size(edit_image),
                    quality="high",
                    request_id=state.command.request_id,
                )
            )
            preview_w, preview_h = _image_dimensions(generated_preview.data)
            state.preview = self._assets.put(
                generated_preview.data,
                AssetMetadata(
                    kind=AssetKind.PREVIEW,
                    mediaType=_domain_media_type(generated_preview.media_type),
                    fileExtension=_extension_for_media_type(
                        generated_preview.media_type
                    ),
                    width=preview_w,
                    height=preview_h,
                ),
            )
            next_revision = draft.revision + 1
            self._update_candidate(
                state,
                revision=next_revision,
                visuals=_build_visual_spec(state, next_revision),
            )
        elif stage is GenerationStage.RESULT_VALIDATION:
            report = validate_draft(state.candidate)
            if any(
                issue.severity is ValidationSeverity.ERROR for issue in report.issues
            ):
                raise _validation_error()
        elif stage is GenerationStage.ATOMIC_PROMOTION:
            state.candidate = self._finalize_candidate(state)

    def _advance_stage(self, state: _RunState, stage: GenerationStage) -> GenerationAttempt:
        stages = list(state.attempt.stages)
        for item in stages:
            if item.stage is stage:
                updated = item.model_copy(update={"status": StageStatus.SUCCEEDED})
                stages = [updated if s.stage is stage else s for s in stages]
                break
        else:
            stages.append(
                StageAttempt(
                    stage=stage,
                    status=StageStatus.SUCCEEDED,
                    retry_count=0,
                    started_at=utc_now(),
                    finished_at=utc_now(),
                )
            )
        state.attempt = state.attempt.model_copy(
            update={"stages": stages, "current_stage": stage}
        )
        return state.attempt

    def _update_candidate(
        self, state: _RunState, **updates: object
    ) -> None:
        state.candidate = state.candidate.model_copy(update=updates)

    def _new_attempt(
        self,
        command: GenerationCommand,
        attempt_id: UUID,
        source_revision: int,
        *,
        total_stages: int,
    ) -> GenerationAttempt:
        now = utc_now()
        return GenerationAttempt(
            attempt_id=attempt_id,
            draft_id=command.draft_id,
            kind=command.kind,
            source_revision=source_revision,
            status=AttemptStatus.RUNNING,
            current_stage=None,
            stages=[
                StageAttempt(
                    stage=GenerationStage.INPUT_VALIDATION,
                    status=StageStatus.RUNNING,
                    retry_count=0,
                    started_at=now,
                    finished_at=None,
                )
            ],
            total_stages=total_stages,
            candidate_record_path=None,
            started_at=now,
            finished_at=None,
            error=None,
            trial_used=False,
            trial_remaining=None,
        )

    def _finalize_candidate(self, state: _RunState) -> DraftRecord:
        if state.command.kind is GenerationAttemptKind.INITIAL:
            action = DraftAction.GENERATION_SUCCEEDED
        elif state.command.kind is GenerationAttemptKind.BLUEPRINT_PREVIEW:
            action = DraftAction.PREVIEW_UPDATED
        else:
            action = DraftAction.REGENERATION_SUCCEEDED
        target_status = transition(state.staged, action).status
        if state.draft.mode is DraftMode.BLUEPRINT:
            # Blueprint generation never rewrites user provenance to AGENT_ASSIGNED
            # and never enables cache eligibility; it records which visual prompt
            # template produced the preview so provenance stays traceable (R-03).
            base = state.draft.provenance
            suffix = _language_suffix(state.draft.source.language)
            provenance = base.model_copy(
                update={
                    "prompt_versions": {
                        **base.prompt_versions,
                        "visual": f"{_VISUAL_PROMPT_VERSION}-{suffix}",
                    },
                }
            )
        elif state.canonical is not None:
            provenance = _canonical_reused_provenance(state)
        else:
            provenance = _generated_provenance(state.draft)
        return state.candidate.model_copy(
            update={
                "status": target_status,
                "provenance": provenance,
                "active_attempt_id": None,
                "last_attempt_id": state.attempt_id,
                "last_error": None,
                "updated_at": utc_now(),
            }
        )

    def _finish_success(
        self, state: _RunState, promoted: DraftRecord
    ) -> GenerationAttempt:
        return state.attempt.model_copy(
            update={
                "status": AttemptStatus.SUCCEEDED,
                "finished_at": utc_now(),
                "current_stage": None,
            }
        )

    async def _finish_failed(
        self,
        state: _RunState,
        staged: DraftRecord,
        error: AppError,
        attempt_id: UUID,
        *,
        promoted: DraftRecord | None = None,
    ) -> GenerationEvent:
        error = self._trial_failure_error(state, error)
        # Trial accounting is committed only after Draft promotion. If that
        # final accounting step fails, the persisted Draft already owns the
        # promoted revision and has no active attempt. Reuse the normal
        # generation-kind rollback record at that exact revision instead of
        # trying to write through the stale pre-promotion owner boundary.
        rollback_source = (
            staged.model_copy(update={"revision": promoted.revision})
            if promoted is not None
            else staged
        )
        if state.command.kind is GenerationAttemptKind.BLUEPRINT_PREVIEW:
            # A failed preview keeps the draft in STALE_PREVIEW: user fields and
            # the old visual assets remain, only the attempt state is cleared.
            rolled = rollback_source.model_copy(
                update={
                    "last_attempt_id": attempt_id,
                    "last_error": _to_summary(error),
                    "active_attempt_id": None,
                    "updated_at": utc_now(),
                }
            )
        else:
            if state.command.kind is GenerationAttemptKind.INITIAL:
                action = DraftAction.GENERATION_FAILED
            else:
                action = DraftAction.REGENERATION_FAILED
            rolled = transition(rollback_source, action)
            rolled = rolled.model_copy(
                update={
                    "last_attempt_id": attempt_id,
                    "last_error": _to_summary(error),
                    "active_attempt_id": None,
                    "updated_at": utc_now(),
                }
            )
        try:
            self._drafts.control_write(
                rolled,
                expected_revision=rollback_source.revision,
                expected_attempt_id=None if promoted is not None else attempt_id,
            )
        except (RevisionConflictError, AttemptMismatchError):
            pass
        except (FileNotFoundError, OSError):
            # Task 19.4: the draft was deleted mid-generation; keep the attempt
            # terminal and return without trying to roll the record back.
            failed = state.attempt.model_copy(
                update={
                    "status": AttemptStatus.FAILED,
                    "finished_at": utc_now(),
                    "error": _to_summary(error),
                }
            )
            self._attempts.save(failed)
            self._record_generation_finished(
                state,
                outcome=GenerationOutcome.FAILED,
                error_category=_error_category(error),
                error=error,
            )
            return attempt_failed(
                attempt_id,
                ErrorPayload.from_app_error(
                    error, request_id=state.command.request_id
                ),
            )
        failed = state.attempt.model_copy(
            update={
                "status": AttemptStatus.FAILED,
                "finished_at": utc_now(),
                "error": _to_summary(error),
            }
        )
        self._attempts.save(failed)
        self._record_generation_finished(
            state,
            outcome=GenerationOutcome.FAILED,
            error_category=_error_category(error),
            error=error,
        )
        return attempt_failed(
            attempt_id,
            ErrorPayload.from_app_error(error, request_id=state.command.request_id),
        )

    def _rollback_cancelled(
        self,
        state: _RunState,
        staged: DraftRecord,
    ) -> None:
        """Side-effect rollback shared by explicit /cancel and client disconnect.

        Clears the active attempt and moves the draft back to its pre-generation
        status. Synchronous so the GeneratorExit path can run it without
        yielding an event.
        """
        self._release_trial_reservation(state)
        if state.command.kind is GenerationAttemptKind.BLUEPRINT_PREVIEW:
            # A cancelled preview keeps the draft in STALE_PREVIEW.
            rolled = staged.model_copy(
                update={
                    "last_attempt_id": state.attempt_id,
                    "last_error": _to_summary(_cancelled_error()),
                    "active_attempt_id": None,
                    "updated_at": utc_now(),
                }
            )
        else:
            if state.command.kind is GenerationAttemptKind.INITIAL:
                action = DraftAction.GENERATION_CANCELLED
            else:
                action = DraftAction.REGENERATION_CANCELLED
            rolled = transition(staged, action)
            rolled = rolled.model_copy(
                update={
                    "last_attempt_id": state.attempt_id,
                    "active_attempt_id": None,
                    "updated_at": utc_now(),
                }
            )
        try:
            self._drafts.control_write(
                rolled,
                expected_revision=staged.revision,
                expected_attempt_id=state.attempt_id,
            )
        except (RevisionConflictError, AttemptMismatchError):
            pass
        except (FileNotFoundError, OSError):
            # Task 19.4: the draft was deleted while the attempt ran; there is
            # nothing to roll back. Keep the attempt terminal and return.
            cancelled = state.attempt.model_copy(
                update={
                    "status": AttemptStatus.CANCELLED,
                    "finished_at": utc_now(),
                }
            )
            self._attempts.save(cancelled)
            return
        cancelled = state.attempt.model_copy(
            update={
                "status": AttemptStatus.CANCELLED,
                "finished_at": utc_now(),
            }
        )
        self._attempts.save(cancelled)

    async def _finish_cancelled(
        self,
        state: _RunState,
        staged: DraftRecord,
    ) -> GenerationEvent:
        self._rollback_cancelled(state, staged)
        self._record_generation_finished(
            state,
            outcome=GenerationOutcome.CANCELLED,
            error_category=ErrorCategory.CANCELLED,
        )
        return attempt_failed(
            state.attempt_id,
            ErrorPayload.from_app_error(
                _cancelled_error(), request_id=state.command.request_id
            ),
        )


def _telemetry_mode(mode: DraftMode) -> TelemetryMode:
    return (
        TelemetryMode.BLUEPRINT
        if mode is DraftMode.BLUEPRINT
        else TelemetryMode.ASK_GUS
    )


def _telemetry_generation_kind(
    kind: GenerationAttemptKind,
) -> GenerationKind:
    return {
        GenerationAttemptKind.INITIAL: GenerationKind.INITIAL,
        GenerationAttemptKind.FULL_REGENERATE: GenerationKind.FULL_REGENERATE,
        GenerationAttemptKind.BLUEPRINT_PREVIEW: GenerationKind.BLUEPRINT_PREVIEW,
    }.get(kind, GenerationKind.RETRY_FAILED_STAGE)


def _default_memory_outcome(
    mode: DraftMode,
    kind: GenerationAttemptKind,
) -> MemoryOutcome:
    if mode is DraftMode.ASK_GUS and kind is GenerationAttemptKind.INITIAL:
        return MemoryOutcome.UNAVAILABLE
    return MemoryOutcome.NOT_ELIGIBLE


def _memory_outcome_for_recall(decision: RecallDecision) -> MemoryOutcome:
    if decision is RecallDecision.MATCH_HIT:
        return MemoryOutcome.HIT
    if decision in {
        RecallDecision.NOT_ATTEMPTED_BELOW_MINIMUM,
        RecallDecision.NO_CANDIDATES,
        RecallDecision.MATCH_MISS,
    }:
        return MemoryOutcome.MISS
    if decision is RecallDecision.FALLBACK_ERROR:
        return MemoryOutcome.FALLBACK_ERROR
    return MemoryOutcome.UNAVAILABLE


def _error_category(error: AppError) -> ErrorCategory:
    """Map stable error codes without inspecting messages or details."""

    code = error.code
    if code == "PTS_GEN_CANCELLED":
        return ErrorCategory.CANCELLED
    if code == "PTS_GEN_INTERRUPTED":
        return ErrorCategory.INTERRUPTED
    if code == "PTS_GEN_BUSY":
        return ErrorCategory.BUSY
    if code == "PTS_TRIAL_LIMIT_REACHED":
        return ErrorCategory.TRIAL_LIMIT
    if code in {
        "PTS_PROVIDER_NOT_CONFIGURED",
        "PTS_PROVIDER_AUTH_FAILED",
        "PTS_INPUT_API_KEY_INVALID",
        "PTS_WORKSPACE_SETTINGS_INVALID",
        "PTS_WORKSPACE_SETTINGS_UNAVAILABLE",
        "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE",
    }:
        return ErrorCategory.SETTINGS
    if code in {"PTS_PROVIDER_UNAVAILABLE", "PTS_TRIAL_SERVICE_UNAVAILABLE"}:
        return ErrorCategory.NETWORK
    if code in {
        "PTS_GEN_LOW_CONFIDENCE",
        "PTS_GEN_VALIDATION_FAILED",
        "PTS_IMAGE_INPUT_UNSUPPORTED",
        "PTS_PROVIDER_IMAGE_EDIT_UNSUPPORTED",
        "PTS_PREVIEW_PROMPT_TOO_LONG",
    } or code.startswith(("PTS_INPUT_", "PTS_STATE_")):
        return ErrorCategory.VALIDATION
    if code.startswith("PTS_PROVIDER_"):
        return ErrorCategory.PROVIDER
    return ErrorCategory.INTERNAL


def _rejection_reason(
    error: AppError,
    *,
    provider_started: bool,
) -> RejectionReason | None:
    if provider_started:
        return None
    category = _error_category(error)
    if category is ErrorCategory.BUSY:
        return RejectionReason.BUSY
    if category is ErrorCategory.TRIAL_LIMIT:
        return RejectionReason.TRIAL_LIMIT
    if category is ErrorCategory.SETTINGS:
        return RejectionReason.SETTINGS
    if category is ErrorCategory.VALIDATION:
        return RejectionReason.VALIDATION
    return None


def _duration_ms(
    clock: Callable[[], float],
    started_monotonic: float | None,
) -> int:
    try:
        elapsed = 0.0 if started_monotonic is None else clock() - started_monotonic
        return min(MAX_DURATION_MS, max(0, round(max(0.0, elapsed) * 1000)))
    except Exception:  # noqa: BLE001 - telemetry timing is fail-open
        return 0


def _build_visual_spec(state: _RunState, source_revision: int) -> VisualSpec:
    assert state.visual_brief is not None
    assert state.icon_source_asset_id is not None
    assert state.icon_16 is not None
    assert state.preview is not None
    return VisualSpec(
        visualBrief=state.visual_brief,
        previewAssetId=state.preview.asset_id,
        iconSourceAssetId=state.icon_source_asset_id,
        icon16AssetId=state.icon_16.asset_id,
        sourceRevision=source_revision,
        promptVersion=(
            f"{_VISUAL_PROMPT_VERSION}-{_language_suffix(state.draft.source.language)}"
        ),
    )
