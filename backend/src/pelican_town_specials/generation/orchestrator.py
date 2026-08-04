"""Ask Gus synchronous generation orchestrator."""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from time import monotonic
from uuid import UUID, uuid4

from PIL import Image
from pydantic import Field

from pelican_town_specials.catalog.mapping import map_ingredient
from pelican_town_specials.catalog.models import CatalogCandidate
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.common import (
    DraftMode,
    GenerationStage,
    StrictModel,
    utc_now,
)
from pelican_town_specials.domain.dish import (
    DishAnalysis,
    FieldAuthority,
    GameIngredient,
    GameplaySpec,
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
from pelican_town_specials.domain.errors import AppError, ErrorPayload, ErrorSummary
from pelican_town_specials.domain.state_machine import DraftAction, transition
from pelican_town_specials.domain.validation import ValidationSeverity, validate_draft
from pelican_town_specials.images import (
    PreviewSnapshot,
    build_icon_16,
    compose_preview,
    downscale_for_vision,
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

from .attempt_registry import AttemptRegistry
from .blueprint import (
    BLUEPRINT_STAGE_ORDER,
    blueprint_icon_prompt,
    blueprint_preview_prompt,
    build_blueprint_visual_brief,
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

_ASK_GUS_PROMPT_VERSION = "ask-gus-v1"
_VISUAL_PROMPT_VERSION = "visual-v1"
_ICON_SIZE = "1024x1024"
_PREVIEW_WIDTH = 960
_PREVIEW_HEIGHT = 540


class _RunState:
    __slots__ = (
        "analysis",
        "attempt",
        "attempt_id",
        "candidate",
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
        "preview_art",
        "preview_art_asset_id",
        "staged",
        "visual_brief",
    )

    attempt_id: UUID
    command: GenerationCommand
    draft: DraftRecord
    candidate: DraftRecord
    gateway: ModelGateway
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
    preview_art: GeneratedImage | None
    preview_art_asset_id: UUID | None
    preview: AssetRef | None

    def __init__(
        self,
        *,
        attempt_id: UUID,
        command: GenerationCommand,
        draft: DraftRecord,
        candidate: DraftRecord,
        gateway: ModelGateway,
        attempt: GenerationAttempt,
        staged: DraftRecord,
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
        self.gameplay = None
        self.presentation = None
        self.visual_brief = None
        self.icon_source = None
        self.icon_source_asset_id = None
        self.icon_16 = None
        self.preview_art = None
        self.preview_art_asset_id = None
        self.preview = None


def _map_gameplay(
    core: GeneratedDishCore,
    catalog: VanillaCatalog,
) -> GameplaySpec:
    ingredients: list[GameIngredient] = []
    for semantic in core.ingredients:
        candidates = _build_candidates(semantic, catalog)
        mapped = map_ingredient(semantic, candidates, catalog)
        ingredients.append(mapped)
    return GameplaySpec(
        ingredients=ingredients,
        recovery=core.recovery,
        sellPrice=core.sell_price,
        isDrink=core.is_drink,
        recipeUnlock=RecipeUnlock.DEFAULT,
        buff=core.buff,
    )


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


def _domain_media_type(value: ImageMediaType) -> MediaType:
    return MediaType(value.value)


def _extension_for_media_type(value: ImageMediaType) -> str:
    if value is ImageMediaType.JPEG:
        return ".jpg"
    if value is ImageMediaType.WEBP:
        return ".webp"
    return ".png"


def _image_dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def _icon_prompt(core: GeneratedDishCore) -> str:
    return f"星露谷风格的 16×16 游戏图标：{core.presentation.display_name}"


def _preview_prompt(core: GeneratedDishCore) -> str:
    return f"星露谷风格的菜品插画：{core.presentation.display_name}，{core.visual_brief}"


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
        "presentation.tags": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.ingredients": FieldAuthority.SYSTEM_GENERATED,
        "gameplay.recovery": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.sell_price": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.is_drink": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.buff": FieldAuthority.AGENT_ASSIGNED,
        "gameplay.recipe_unlock": FieldAuthority.AGENT_ASSIGNED,
    }
    return base.model_copy(
        update={
            "authority_by_field": authority,
            "prompt_versions": {
                **base.prompt_versions,
                "ask-gus": _ASK_GUS_PROMPT_VERSION,
                "visual": _VISUAL_PROMPT_VERSION,
            },
        }
    )


def _busy_error() -> AppError:
    return AppError(
        code="PTS_GEN_BUSY",
        message="当前已有一个生成任务在运行，请稍后重试。",
        http_status=409,
        details={},
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


class _SlotGuardedAsyncIterator:
    """Async iterator that releases the generation slot on any termination.

    The slot is reserved synchronously in ``run()`` so a busy condition can be
    returned before the NDJSON stream starts; this wrapper guarantees the slot
    is released when the generator finishes, raises, is cancelled, or is closed
    even before its body has started iterating.
    """

    def __init__(
        self,
        inner: AsyncGenerator[GenerationEvent],
        registry: AttemptRegistry,
    ) -> None:
        self._inner = inner
        self._registry = registry
        self._released = False

    def __aiter__(self) -> _SlotGuardedAsyncIterator:
        return self

    async def __anext__(self) -> GenerationEvent:
        try:
            return await self._inner.__anext__()
        except StopAsyncIteration:
            self._release()
            raise
        except BaseException:
            self._release()
            raise

    async def aclose(self) -> None:
        try:
            await self._inner.aclose()
        finally:
            self._release()

    def _release(self) -> None:
        if not self._released:
            self._released = True
            self._registry.release_slot()


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
    ) -> None:
        self._drafts = draft_repository
        self._attempts = attempt_repository
        self._assets = asset_store
        self._catalog = catalog
        self._gateway_factory = gateway_factory
        self._registry = registry
        self._min_confidence = min_confidence
        self._clock = clock

    def run(self, command: GenerationCommand) -> AsyncIterator[GenerationEvent]:
        if not self._registry.reserve_slot():
            raise _busy_error()
        return _SlotGuardedAsyncIterator(self._generate(command), self._registry)

    def cancel(self, attempt_id: UUID) -> bool:
        """Request cancellation of a running attempt; returns whether it was tracked."""
        return self._registry.request_cancel(attempt_id, "user requested cancellation")

    @property
    def drafts(self) -> DraftRepository:
        return self._drafts

    @property
    def attempts(self) -> GenerationAttemptRepository:
        return self._attempts

    @property
    def assets(self) -> FileAssetStore:
        return self._assets

    async def _generate(
        self, command: GenerationCommand
    ) -> AsyncGenerator[GenerationEvent]:
        attempt_id = uuid4()
        self._registry.register(
            attempt_id,
            asyncio.current_task() if asyncio.current_task() is not None else None,
        )
        async with self._registry.semaphore():
            try:
                yield attempt_started(attempt_id)
                async for event in self._run(command, attempt_id):
                    yield event
            finally:
                self._registry.unregister(attempt_id)

    async def _run(
        self, command: GenerationCommand, attempt_id: UUID
    ) -> AsyncIterator[GenerationEvent]:
        try:
            draft = self._drafts.get(command.draft_id)
        except (FileNotFoundError, OSError) as exc:
            raise _draft_not_found_error() from exc
        gateway = self._gateway_factory()
        if command.kind is GenerationAttemptKind.INITIAL:
            if draft.status is DraftStatus.DRAFT:
                ready = transition(draft, DraftAction.FIELDS_READY)
                staged = transition(ready, DraftAction.START_INITIAL_GENERATION)
            elif draft.status is DraftStatus.READY:
                staged = transition(draft, DraftAction.START_INITIAL_GENERATION)
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

        staged = staged.model_copy(update={"active_attempt_id": attempt_id})
        self._drafts.control_write(
            staged, expected_revision=draft.revision, expected_attempt_id=None
        )
        attempt = self._new_attempt(command, attempt_id, draft.revision)
        self._attempts.save(attempt)

        state = _RunState(
            attempt_id=attempt_id,
            command=command,
            draft=draft,
            candidate=draft.model_copy(),
            gateway=gateway,
            attempt=attempt,
            staged=staged,
        )
        stage_order = (
            BLUEPRINT_STAGE_ORDER
            if draft.mode is DraftMode.BLUEPRINT
            else STAGE_ORDER
        )
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

        try:
            promoted = self._drafts.promote(
                state.candidate,
                expected_revision=draft.revision,
                expected_attempt_id=attempt_id,
            )
        except (RevisionConflictError, AttemptMismatchError):
            yield await self._finish_failed(state, staged, _stale_error(), attempt_id)
            return
        finished = self._finish_success(state, promoted)
        self._attempts.save(finished)
        yield attempt_succeeded(
            attempt_id,
            promoted.revision,
            promoted.model_dump(by_alias=True, mode="json"),
        )

    async def _execute_stage(self, state: _RunState, stage: GenerationStage) -> None:
        gateway = state.gateway
        draft = state.draft
        if stage is GenerationStage.INPUT_VALIDATION:
            self._assets.stat(draft.source.original_image_asset_id)
        elif stage is GenerationStage.DISH_ANALYSIS:
            vision_data, vision_media = downscale_for_vision(
                _read_source_image(self._assets, draft)
            )
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
            assert state.core is not None
            state.gameplay = _map_gameplay(state.core, self._catalog)
            self._update_candidate(state, gameplay=state.gameplay)
        elif stage is GenerationStage.VISUAL_BRIEF:
            if draft.mode is DraftMode.BLUEPRINT:
                assert draft.presentation is not None
                assert draft.gameplay is not None
                state.visual_brief = build_blueprint_visual_brief(
                    draft.presentation, draft.gameplay
                )
            else:
                assert state.core is not None
                state.visual_brief = state.core.visual_brief
        elif stage is GenerationStage.ICON_GENERATION_AND_NORMALIZATION:
            if draft.mode is DraftMode.BLUEPRINT:
                assert draft.presentation is not None
                icon_prompt = blueprint_icon_prompt(draft.presentation)
            else:
                assert state.core is not None
                icon_prompt = _icon_prompt(state.core)
            state.icon_source = await gateway.generate_image(
                ImageGenerationRequest(
                    operation=ImageOperation.GENERATION,
                    prompt=icon_prompt,
                    size=_ICON_SIZE,
                    request_id=state.command.request_id,
                )
            )
            icon_w, icon_h = _image_dimensions(state.icon_source.data)
            icon_source_ref = self._assets.put(
                state.icon_source.data,
                AssetMetadata(
                    kind=AssetKind.ICON_SOURCE,
                    mediaType=_domain_media_type(state.icon_source.media_type),
                    fileExtension=_extension_for_media_type(
                        state.icon_source.media_type
                    ),
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
                assert state.visual_brief is not None
                preview_prompt = blueprint_preview_prompt(
                    draft.presentation, state.visual_brief
                )
                snapshot_presentation = draft.presentation
                snapshot_gameplay = draft.gameplay
            else:
                assert state.core is not None
                assert state.presentation is not None
                assert state.gameplay is not None
                preview_prompt = _preview_prompt(state.core)
                snapshot_presentation = state.presentation
                snapshot_gameplay = state.gameplay
            state.preview_art = await gateway.generate_image(
                ImageGenerationRequest(
                    operation=ImageOperation.GENERATION,
                    prompt=preview_prompt,
                    size=_ICON_SIZE,
                    request_id=state.command.request_id,
                )
            )
            art_w, art_h = _image_dimensions(state.preview_art.data)
            preview_art_ref = self._assets.put(
                state.preview_art.data,
                AssetMetadata(
                    kind=AssetKind.GENERATED_ART,
                    mediaType=_domain_media_type(state.preview_art.media_type),
                    fileExtension=_extension_for_media_type(
                        state.preview_art.media_type
                    ),
                    width=art_w,
                    height=art_h,
                ),
            )
            state.preview_art_asset_id = preview_art_ref.asset_id
            preview_bytes = compose_preview(
                PreviewSnapshot(
                    generated_art=state.preview_art.data,
                    presentation=snapshot_presentation,
                    gameplay=snapshot_gameplay,
                )
            )
            state.preview = self._assets.put(
                preview_bytes,
                AssetMetadata(
                    kind=AssetKind.PREVIEW,
                    mediaType=MediaType.PNG,
                    fileExtension=".png",
                    width=_PREVIEW_WIDTH,
                    height=_PREVIEW_HEIGHT,
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
        self, command: GenerationCommand, attempt_id: UUID, source_revision: int
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
            candidate_record_path=None,
            started_at=now,
            finished_at=None,
            error=None,
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
            # and never enables cache eligibility.
            provenance = state.draft.provenance
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
    ) -> GenerationEvent:
        if state.command.kind is GenerationAttemptKind.BLUEPRINT_PREVIEW:
            # A failed preview keeps the draft in STALE_PREVIEW: user fields and
            # the old visual assets remain, only the attempt state is cleared.
            rolled = staged.model_copy(
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
            rolled = transition(staged, action)
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
                expected_revision=staged.revision,
                expected_attempt_id=attempt_id,
            )
        except (RevisionConflictError, AttemptMismatchError):
            pass
        failed = state.attempt.model_copy(
            update={
                "status": AttemptStatus.FAILED,
                "finished_at": utc_now(),
                "error": _to_summary(error),
            }
        )
        self._attempts.save(failed)
        return attempt_failed(
            attempt_id,
            ErrorPayload.from_app_error(error, request_id=state.command.request_id),
        )

    async def _finish_cancelled(
        self,
        state: _RunState,
        staged: DraftRecord,
    ) -> GenerationEvent:
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
        cancelled = state.attempt.model_copy(
            update={
                "status": AttemptStatus.CANCELLED,
                "finished_at": utc_now(),
            }
        )
        self._attempts.save(cancelled)
        return attempt_failed(
            state.attempt_id,
            ErrorPayload.from_app_error(
                _cancelled_error(), request_id=state.command.request_id
            ),
        )


def _build_visual_spec(state: _RunState, source_revision: int) -> VisualSpec:
    assert state.visual_brief is not None
    assert state.icon_source_asset_id is not None
    assert state.icon_16 is not None
    assert state.preview_art_asset_id is not None
    assert state.preview is not None
    return VisualSpec(
        visualBrief=state.visual_brief,
        generatedArtAssetId=state.preview_art_asset_id,
        previewAssetId=state.preview.asset_id,
        iconSourceAssetId=state.icon_source_asset_id,
        icon16AssetId=state.icon_16.asset_id,
        sourceRevision=source_revision,
        promptVersion=_VISUAL_PROMPT_VERSION,
    )
