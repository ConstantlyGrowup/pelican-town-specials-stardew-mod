"""Ask Gus initial generation: stage order, low-confidence stop, illegal state."""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from backend.tests.domain.factories import make_draft as make_domain_draft
from PIL import Image

from pelican_town_specials.domain.assets import AssetRef, MediaType
from pelican_town_specials.domain.canonical import (
    CanonicalDish,
    CanonicalIconKind,
    CanonicalIconMetadata,
    CanonicalRecallCandidate,
)
from pelican_town_specials.domain.common import DraftMode, GenerationStage
from pelican_town_specials.domain.dish import (
    GenerationSource,
    IconReuseDecision,
)
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    DraftStatus,
    GenerationAttemptKind,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import (
    GenerationCommand,
    GenerationOrchestrator,
)
from pelican_town_specials.images import downscale_for_vision
from pelican_town_specials.images.vision_input import EDIT_MIN_PIXELS
from pelican_town_specials.persistence.asset_store import FileAssetStore
from pelican_town_specials.providers.contracts import (
    CanonicalMatchResponse,
    ImageMediaType,
    ImageOperation,
    SemanticRecipeIngredient,
)
from tests.domain.factories import canonical_registration_fixture

from .conftest import (
    EXPECTED_ASK_GUS_STAGES,
    FakeGateway,
    GenerationHarness,
    core_fixture,
    full_regen_command,
    initial_command,
    put_original_image,
)


def _read_asset(asset_store: FileAssetStore, ref: AssetRef) -> bytes:
    with asset_store.open(ref) as handle:
        return handle.read()


def _icon_bytes(size: int, color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (size, size), color).save(output, format="PNG")
    return output.getvalue()


def _canonical_dish(canonical_id: UUID) -> tuple[CanonicalDish, bytes, bytes]:
    registration = canonical_registration_fixture(canonical_id=canonical_id)
    source = _icon_bytes(32, "gold")
    icon_16 = _icon_bytes(16, "orange")
    registration_payload = registration.model_dump(by_alias=True)
    recovery = registration_payload["gameplay"]["recovery"]
    for field in ("calculationVersion", "energyRestore", "healthRestore"):
        recovery.pop(field, None)
    canonical = CanonicalDish(
        **registration_payload,
        iconSource=CanonicalIconMetadata(
            relativePath=f"{canonical_id}/icon-source.png",
            mediaType=MediaType.PNG,
            sha256=hashlib.sha256(source).hexdigest(),
            byteSize=len(source),
            width=32,
            height=32,
        ),
        icon16=CanonicalIconMetadata(
            relativePath=f"{canonical_id}/icon-16.png",
            mediaType=MediaType.PNG,
            sha256=hashlib.sha256(icon_16).hexdigest(),
            byteSize=len(icon_16),
            width=16,
            height=16,
        ),
        registeredAt=datetime.now(UTC),
    )
    return canonical, source, icon_16


class _RecallRegistry:
    def __init__(
        self,
        canonical: CanonicalDish,
        source: bytes,
        icon_16: bytes,
        *,
        second: CanonicalDish | None = None,
    ) -> None:
        self.canonical = canonical
        self.source = source
        self.icon_16 = icon_16
        self.second = second
        self.calls: list[str] = []

    def count_valid(self) -> int:
        self.calls.append("count")
        return 2

    def list_recall_candidate_pool(self, **_kwargs):
        self.calls.append("pool")
        candidates = [self.canonical, self.second or self.canonical]
        return [
            CanonicalRecallCandidate(
                canonicalId=item.canonical_id,
                dishSignature=item.dish_signature,
                language=item.language,
                catalogVersion=item.catalog_version,
                recallDocument=item.recall_document,
                displayName=item.presentation.display_name,
                registeredAt=item.registered_at,
                useCount=item.use_count,
                lastUsedAt=item.last_used_at,
            )
            for item in candidates
        ]

    def get_valid(self, canonical_id: UUID) -> CanonicalDish | None:
        self.calls.append("get")
        if canonical_id == self.canonical.canonical_id:
            return self.canonical
        if self.second is not None and canonical_id == self.second.canonical_id:
            return self.second
        return None

    def load_owned_icon(self, canonical_id: UUID, kind: CanonicalIconKind) -> bytes:
        self.calls.append(f"icon:{kind.value}")
        if canonical_id != self.canonical.canonical_id:
            raise FileNotFoundError(canonical_id)
        return self.source if kind is CanonicalIconKind.SOURCE else self.icon_16


def _canonical_orchestrator(harness: GenerationHarness, registry: object):
    return GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=lambda: harness.gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
        canonical_repository=registry,
    )


async def test_canonical_hit_uses_one_trial_reservation_for_analysis_match_and_preview(
    harness: GenerationHarness,
) -> None:
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    second, _, _ = _canonical_dish(uuid4())
    registry = _RecallRegistry(
        canonical,
        source_icon,
        icon_16,
        second=second,
    )
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.94,
    )

    class _Trial:
        def __init__(self) -> None:
            self.reserved_attempts: list[UUID] = []
            self.committed_attempts: list[UUID] = []
            self.released_attempts: list[UUID] = []

        def is_active(self) -> bool:
            return True

        def trial_opportunity(self) -> bool:
            return True

        def reserve_attempt(self, attempt_id: UUID) -> bool:
            self.reserved_attempts.append(attempt_id)
            return True

        def commit_attempt(self, attempt_id: UUID) -> int | None:
            self.committed_attempts.append(attempt_id)
            return 1

        def release_attempt(self, attempt_id: UUID) -> bool:
            self.released_attempts.append(attempt_id)
            return True

    trial = _Trial()
    local = GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=lambda: harness.gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
        trial_access=trial,
        trial_gateway_factory=lambda: harness.gateway,
        canonical_repository=registry,
    )
    original = put_original_image(harness)
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in local.run(initial_command(saved))]

    assert events[-1].type == "attempt.succeeded"
    started = [event for event in events if event.type == "attempt.started"]
    assert len(started) == 1
    attempt_id = started[0].attempt_id
    assert attempt_id is not None
    assert trial.reserved_attempts == [attempt_id]
    assert trial.committed_attempts == [attempt_id]
    assert trial.released_attempts == []
    assert harness.gateway.calls == ["analyze", "match", "compare_icon", "image"]


async def test_ask_gus_stage_order(
    harness: GenerationHarness, ready_draft
) -> None:
    events = [
        event
        async for event in harness.orchestrator.run(initial_command(ready_draft))
    ]
    succeeded = [
        event.stage for event in events if event.type == "stage.succeeded"
    ]
    assert succeeded == EXPECTED_ASK_GUS_STAGES
    assert events[-1].type == "attempt.succeeded"
    assert events[-1].draft_revision == ready_draft.revision + 1
    assert harness.gateway.calls == ["analyze", "design", "image", "image"]
    assert len(harness.gateway.image_requests) == 2
    icon_request, preview_request = harness.gateway.image_requests
    assert icon_request.operation is ImageOperation.EDIT
    assert len(icon_request.source_images) == 1
    assert preview_request.operation is ImageOperation.EDIT
    assert preview_request.quality == "high"
    assert len(preview_request.source_images) == 2
    # The edit `size` mirrors the shaped input and must never fall below the
    # provider's 921,600 px floor (a small source is upscaled to meet it).
    size_w, size_h = (int(part) for part in preview_request.size.split("x"))
    assert size_w * size_h >= EDIT_MIN_PIXELS
    for required_text in (
        "春日面碗",
        "主菜",
        "一碗带着春天气息的热汤面。",
        "能量：+200",
        "生命：+90",
        "售价：220g",
        "item hover tooltip",
        "不是海报",
        "无 Buff：不要生成增益行和持续时间行",
    ):
        assert required_text in preview_request.prompt
    assert "持续时间：" not in preview_request.prompt
    saved = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert saved.provenance.prompt_versions["analysis"] == "analysis-v1-zh"
    assert saved.provenance.prompt_versions["ask-gus"] == "ask-gus-v3-zh"
    assert saved.provenance.prompt_versions["visual"] == "visual-v3-multi-image-edit-zh"
    assert saved.visuals is not None
    assert saved.visuals.prompt_version == "visual-v3-multi-image-edit-zh"
    assert saved.visuals is not None
    assert saved.visuals.generated_art_asset_id is None
    assert saved.visuals.preview_asset_id is not None
    assert saved.visuals.icon_source_asset_id is not None
    assert saved.visuals.icon_16_asset_id is not None
    original_ref = harness.asset_store.stat(saved.source.original_image_asset_id)
    icon_source_ref = harness.asset_store.stat(saved.visuals.icon_source_asset_id)
    preview_ref = harness.asset_store.stat(saved.visuals.preview_asset_id)
    original_data = _read_asset(harness.asset_store, original_ref)
    icon_source_data = _read_asset(harness.asset_store, icon_source_ref)
    downscaled, media_type = downscale_for_vision(
        original_data, min_pixels=EDIT_MIN_PIXELS
    )
    assert icon_request.source_images[0].data == downscaled
    assert icon_request.source_images[0].media_type is media_type
    assert icon_request.size == "1024x1024"
    for required_text in (
        "参考输入图中的菜品主体",
        "可辨识的轮廓、主要配色、摆盘形态和关键食材特征",
        "不要把桌面或照片背景作为主体",
        "单个星露谷风格的像素物品图标",
    ):
        assert required_text in icon_request.prompt
    assert preview_request.source_images[0].data == downscaled
    assert preview_request.source_images[0].media_type is media_type
    assert preview_request.source_images[1].data == icon_source_data
    assert preview_request.source_images[1].data != _read_asset(
        harness.asset_store,
        harness.asset_store.stat(saved.visuals.icon_16_asset_id),
    )
    original = Image.open(io.BytesIO(original_data)).convert("RGBA")
    preview = Image.open(
        io.BytesIO(_read_asset(harness.asset_store, preview_ref))
    ).convert("RGBA")
    icon_source = Image.open(io.BytesIO(icon_source_data)).convert("RGBA")
    icon_16 = Image.open(
        io.BytesIO(
            _read_asset(
                harness.asset_store,
                harness.asset_store.stat(saved.visuals.icon_16_asset_id),
            )
        )
    ).convert("RGBA")
    assert icon_source.size == (128, 128)
    assert icon_16.size == (16, 16)
    assert preview.size == (96, 64)
    assert preview.size != original.size


async def test_initial_ask_gus_hit_reuses_canonical_fields_icons_and_current_preview(
    harness: GenerationHarness,
) -> None:
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    second, _, _ = _canonical_dish(uuid4())
    registry = _RecallRegistry(
        canonical,
        source_icon,
        icon_16,
        second=second,
    )
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.97,
    )
    local = _canonical_orchestrator(harness, registry)
    original = put_original_image(harness, color="navy")
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in local.run(initial_command(saved))]

    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["analyze", "match", "compare_icon", "image"]
    assert len(harness.gateway.image_requests) == 1
    comparison_request = harness.gateway.comparison_requests[0]
    original_data = _read_asset(
        harness.asset_store,
        harness.asset_store.stat(saved.source.original_image_asset_id),
    )
    downscaled_original, original_media_type = downscale_for_vision(
        original_data
    )
    assert comparison_request.current_original.data == downscaled_original
    assert comparison_request.current_original.media_type is original_media_type
    assert comparison_request.canonical_icon_source.data != source_icon
    assert comparison_request.canonical_icon_source.media_type is ImageMediaType.JPEG
    preview_request = harness.gateway.image_requests[0]
    assert preview_request.operation is ImageOperation.EDIT
    assert len(preview_request.source_images) == 2

    restored = local.drafts.get(saved.draft_id)
    assert restored.presentation is not None
    assert canonical.presentation is not None
    assert restored.presentation.display_name == canonical.presentation.display_name
    assert restored.presentation.category_label == canonical.presentation.category_label
    assert restored.presentation.description == canonical.presentation.description
    assert restored.presentation.gus_comment == canonical.presentation.gus_comment
    assert restored.presentation.tags == canonical.presentation.tags
    assert restored.presentation.internal_name != canonical.presentation.internal_name
    assert restored.presentation.internal_name.startswith(
        f"{canonical.presentation.internal_name}_"
    )
    assert restored.gameplay == canonical.gameplay
    assert restored.visuals is not None
    assert restored.visuals.visual_brief == canonical.visual_brief
    assert restored.visuals.source_revision == restored.revision
    assert restored.visuals.preview_asset_id is not None
    assert restored.visuals.icon_source_asset_id is not None
    assert restored.visuals.icon_16_asset_id is not None
    source_ref = harness.asset_store.stat(restored.visuals.icon_source_asset_id)
    icon_16_ref = harness.asset_store.stat(restored.visuals.icon_16_asset_id)
    assert source_ref.source_revision == restored.revision
    assert icon_16_ref.source_revision == restored.revision
    assert source_ref.attempt_id == restored.last_attempt_id
    assert icon_16_ref.attempt_id == restored.last_attempt_id
    assert restored.visuals.preview_asset_id != saved.visuals.preview_asset_id
    assert restored.visuals.icon_source_asset_id != saved.visuals.icon_source_asset_id
    assert restored.visuals.icon_16_asset_id != saved.visuals.icon_16_asset_id
    assert _read_asset(
        harness.asset_store,
        source_ref,
    ) == source_icon
    assert _read_asset(
        harness.asset_store,
        icon_16_ref,
    ) == icon_16
    assert preview_request.source_images[1].data == source_icon
    assert preview_request.source_images[0].data != source_icon
    assert restored.provenance.generation_source is GenerationSource.CANONICAL_REUSED
    assert restored.provenance.canonical_dish_id == canonical.canonical_id
    assert restored.provenance.canonical_dish_signature == canonical.dish_signature
    assert restored.provenance.recall_confidence == 0.97
    assert restored.provenance.recall_elapsed_ms is not None
    assert restored.provenance.recall_elapsed_ms >= 0
    for field in (
        "presentation.display_name",
        "presentation.category_label",
        "presentation.description",
        "presentation.gus_comment",
        "presentation.tags",
        "gameplay.ingredients",
        "gameplay.recovery",
        "gameplay.sell_price",
        "gameplay.is_drink",
        "gameplay.buff",
        "gameplay.recipe_unlock",
        "visuals.visual_brief",
        "visuals.icon_source_asset_id",
        "visuals.icon_16_asset_id",
    ):
        assert restored.provenance.authority_by_field[field].value == "CACHE_REUSED"
    assert (
        restored.provenance.authority_by_field["presentation.internal_name"].value
        == "SYSTEM_GENERATED"
    )
    assert (
        restored.provenance.authority_by_field["visuals.preview_asset_id"].value
        == "SYSTEM_GENERATED"
    )


def test_canonical_internal_name_is_stable_and_distinct() -> None:
    from pelican_town_specials.generation.orchestrator import _canonical_internal_name

    canonical_name = "A" * 48
    first = UUID("12345678-1234-4234-8234-123456789abc")
    second = UUID("87654321-1234-4234-8234-123456789abc")
    assert _canonical_internal_name(canonical_name, first) == _canonical_internal_name(
        canonical_name, first
    )
    assert _canonical_internal_name(canonical_name, first) != _canonical_internal_name(
        canonical_name, second
    )
    assert len(_canonical_internal_name(canonical_name, first)) == 48
    assert _canonical_internal_name(canonical_name, first).endswith("_12345678")


async def test_canonical_miss_falls_back_and_clears_hit_provenance(
    harness: GenerationHarness,
) -> None:
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    registry = _RecallRegistry(canonical, source_icon, icon_16)
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=None,
        confidence=0.0,
    )
    local = _canonical_orchestrator(harness, registry)
    original = put_original_image(harness)
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in local.run(initial_command(saved))]

    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["analyze", "match", "design", "image", "image"]
    restored = local.drafts.get(saved.draft_id)
    assert restored.provenance.generation_source is GenerationSource.FRESH_GENERATION
    assert restored.provenance.canonical_dish_id is None
    assert restored.provenance.canonical_dish_signature is None
    assert restored.provenance.recall_confidence is None
    assert restored.provenance.recall_elapsed_ms is None


async def test_canonical_icon_integrity_failure_falls_back_before_hit_promotion(
    harness: GenerationHarness,
) -> None:
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    registry = _RecallRegistry(canonical, source_icon, icon_16)
    registry.source = b"not-a-valid-png"
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.99,
    )
    local = _canonical_orchestrator(harness, registry)
    original = put_original_image(harness)
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in local.run(initial_command(saved))]

    assert events[-1].type == "attempt.succeeded"
    # The corrupted canonical source cannot even be decoded for the visual
    # comparison, so the gate is skipped and a fresh icon is generated; the
    # already matched text is still promoted with the unavailable decision.
    assert harness.gateway.calls == ["analyze", "match", "image", "image"]
    restored = local.drafts.get(saved.draft_id)
    assert restored.provenance.generation_source is GenerationSource.CANONICAL_REUSED
    assert restored.provenance.canonical_dish_id == canonical.canonical_id
    assert (
        restored.provenance.icon_reuse_decision is IconReuseDecision.UNAVAILABLE
    )
    assert restored.provenance.icon_visual_similarity is None


async def test_canonical_icon16_integrity_failure_downgrades_without_vision_call(
    harness: GenerationHarness,
) -> None:
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    registry = _RecallRegistry(canonical, source_icon, icon_16)
    registry.icon_16 = b"damaged-icon16"
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.99,
    )
    local = _canonical_orchestrator(harness, registry)
    original = put_original_image(harness)
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in local.run(initial_command(saved))]

    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["analyze", "match", "image", "image"]
    restored = local.drafts.get(saved.draft_id)
    assert restored.provenance.icon_reuse_decision is IconReuseDecision.UNAVAILABLE
    assert restored.provenance.icon_visual_similarity is None
    assert (
        restored.provenance.authority_by_field["visuals.icon_source_asset_id"].value
        == "SYSTEM_GENERATED"
    )
    assert (
        restored.provenance.authority_by_field["visuals.icon_16_asset_id"].value
        == "SYSTEM_GENERATED"
    )


async def test_full_regenerate_and_blueprint_never_touch_canonical_registry(
    harness: GenerationHarness,
    reviewable_draft,
    blueprint_stale,
) -> None:
    class _ForbiddenRegistry:
        def __getattr__(self, name: str):
            raise AssertionError(f"canonical registry accessed: {name}")

    local = _canonical_orchestrator(harness, _ForbiddenRegistry())
    events = [event async for event in local.run(full_regen_command(reviewable_draft))]
    assert events[-1].type == "attempt.succeeded"

    harness.gateway.calls.clear()
    harness.gateway.image_requests.clear()
    blueprint_events = [
        event async for event in local.run(
            GenerationCommand(
                draftId=blueprint_stale.draft_id,
                kind=GenerationAttemptKind.BLUEPRINT_PREVIEW,
                requestId=uuid4(),
            )
        )
    ]
    assert blueprint_events[-1].type == "attempt.succeeded"


async def test_fresh_icon_stops_without_image_edit_capability(
    harness: GenerationHarness, ready_draft
) -> None:
    harness.gateway.image_edits_supported = False
    events = [
        event
        async for event in harness.orchestrator.run(initial_command(ready_draft))
    ]
    assert events[-1].type == "attempt.failed"
    assert events[-1].error is not None
    assert events[-1].error.code == "PTS_PROVIDER_IMAGE_EDIT_UNSUPPORTED"
    assert harness.gateway.calls == ["analyze", "design"]
    assert harness.gateway.image_requests == []
    restored = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert restored.status is DraftStatus.FAILED
    assert restored.active_attempt_id is None
    assert restored.last_error is not None
    assert restored.last_error.code == "PTS_PROVIDER_IMAGE_EDIT_UNSUPPORTED"
    assert harness.orchestrator._registry.active_count() == 0


def test_preview_prompt_stays_within_provider_limit() -> None:
    """The full-tooltip prompt must fit the frozen provider contract
    (prompt <= 1500 chars) even with maximum-length structured fields and a
    maximum BuffSpec; otherwise the EDIT request cannot be constructed."""
    from uuid import uuid4

    from pelican_town_specials.domain.dish import (
        BuffAttributes,
        BuffSpec,
        GameIngredient,
        GameplaySpec,
        PresentationSpec,
        RecoverySpec,
    )
    from pelican_town_specials.generation.orchestrator import _preview_prompt
    from pelican_town_specials.providers.contracts import (
        ImageGenerationRequest,
        ImageMediaType,
        ImageOperation,
        ProviderImageInput,
    )

    presentation = PresentationSpec(
        displayName="名" * 60,
        internalName="MaxName",
        categoryLabel="类" * 40,
        description="描" * 400,
        tags=[],
    )
    gameplay = GameplaySpec(
        ingredients=[
            GameIngredient(
                itemId="24",
                displayName="材" * 80,
                quantity=99,
                mappingReason="catalog match",
                catalogVersion="stardew-1.6.15-v1",
            )
        ],
        recovery=RecoverySpec(edibility=500),
        sellPrice=50000,
        isDrink=False,
        buff=BuffSpec(
            id="益" * 80,
            durationMinutes=1440,
            attributes=BuffAttributes(
                farmingLevel=99999,
                fishingLevel=99999,
                miningLevel=99999,
                foragingLevel=99999,
                combatLevel=99999,
                luckLevel=99999,
                attack=99999,
                defense=99999,
                immunity=99999,
                magneticRadius=99999,
                maxStamina=99999,
                speed=99999,
            ),
        ),
    )
    prompt = _preview_prompt(presentation, gameplay)
    assert len(prompt) <= 1500
    request = ImageGenerationRequest(
        operation=ImageOperation.EDIT,
        prompt=prompt,
        source_images=[
            ProviderImageInput(data=b"x", media_type=ImageMediaType.JPEG),
            ProviderImageInput(data=b"y", media_type=ImageMediaType.PNG),
        ],
        size="1024x2048",
        request_id=uuid4(),
    )
    assert request.prompt == prompt


def test_prepare_vision_input_rejects_impossible_ratio_controlled() -> None:
    """An input whose aspect ratio cannot meet the provider minimum pixel
    count within the max side fails as a controlled non-retryable error, not
    a raw ValueError surfacing as a 500."""
    from pelican_town_specials.domain.errors import AppError
    from pelican_town_specials.generation.orchestrator import (
        _prepare_vision_input,
    )

    buffer = io.BytesIO()
    Image.new("RGB", (16, 2048), "seagreen").save(buffer, format="PNG")
    with pytest.raises(AppError) as raised:
        _prepare_vision_input(buffer.getvalue())
    error = raised.value
    assert error.code == "PTS_IMAGE_INPUT_UNSUPPORTED"
    assert error.http_status == 422
    assert error.retryable is False


def test_enforce_preview_prompt_budget_rejects_oversized_prompt() -> None:
    """The shared budget gate still rejects an oversized prompt with a
    controlled non-retryable error, keeping the provider contract intact even
    though the current prompt builder stays within it for maximum legal
    fields."""
    from pelican_town_specials.domain.errors import AppError
    from pelican_town_specials.generation.blueprint import (
        enforce_preview_prompt_budget,
    )

    enforce_preview_prompt_budget("词条" * 700)  # within 1500 chars: no-op.
    with pytest.raises(AppError) as raised:
        enforce_preview_prompt_budget("词条" * 800)  # > 1500 chars.
    error = raised.value
    assert error.code == "PTS_PREVIEW_PROMPT_TOO_LONG"
    assert error.http_status == 422
    assert error.retryable is False


async def test_low_confidence_stops_after_dish_analysis(
    harness: GenerationHarness, ready_draft
) -> None:
    harness.gateway.confidence = 0.1
    events = [
        event
        async for event in harness.orchestrator.run(initial_command(ready_draft))
    ]
    assert events[-1].type == "attempt.failed"
    error = events[-1].error
    assert error is not None
    assert error.code == "PTS_GEN_LOW_CONFIDENCE"
    succeeded = [
        event.stage for event in events if event.type == "stage.succeeded"
    ]
    assert succeeded == [GenerationStage.INPUT_VALIDATION]
    # Gameplay and image gateways must not be called after a low-confidence stop.
    assert harness.gateway.calls == ["analyze"]


async def test_initial_generation_rejects_reviewable_draft(
    harness: GenerationHarness, reviewable_draft
) -> None:
    with pytest.raises(AppError) as excinfo:
        async for _ in harness.orchestrator.run(
            initial_command(reviewable_draft)
        ):
            pass
    assert excinfo.value.code == "PTS_STATE_ILLEGAL_TRANSITION"


async def test_en_draft_uses_english_visual_and_icon_prompts(
    harness: GenerationHarness, ready_draft_en
) -> None:
    """An en-US draft threads its language into the icon and preview prompts:
    English tooltip labels, English icon phrasing, and no Chinese field
    labels. Ingredient display names stay mapped to the vanilla English item
    identity; provenance records the language-suffixed prompt versions."""
    events = [
        event
        async for event in harness.orchestrator.run(initial_command(ready_draft_en))
    ]
    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["analyze", "design", "image", "image"]
    icon_request, preview_request = harness.gateway.image_requests

    # Icon prompt is English and carries no Chinese icon phrasing.
    assert "Stardew Valley-style 16×16 game icon" in icon_request.prompt
    assert "星露谷风格的 16×16 游戏图标" not in icon_request.prompt
    assert icon_request.operation is ImageOperation.EDIT
    assert len(icon_request.source_images) == 1
    for required_text in (
        "Use the source photo as the visual reference",
        "recognizable silhouette, main colors, plating, and key ingredient features",
        "Do not make the table or photo background the subject",
        "one Stardew Valley-style pixel item icon",
    ):
        assert required_text in icon_request.prompt

    # Preview tooltip prompt uses English field labels and layout guidance.
    for required_text in (
        "item hover tooltip",
        "not a poster",
        "Title:",
        "Category:",
        "Description:",
        "Energy:",
        "Health:",
        "Price:",
    ):
        assert required_text in preview_request.prompt
    for forbidden in (
        "标题：",
        "类别：",
        "描述：",
        "能量：",
        "生命：",
        "售价：",
        "无 Buff：",
    ):
        assert forbidden not in preview_request.prompt

    saved = harness.orchestrator.drafts.get(ready_draft_en.draft_id)
    assert saved.provenance.prompt_versions["analysis"] == "analysis-v1-en"
    assert saved.provenance.prompt_versions["ask-gus"] == "ask-gus-v3-en"
    assert saved.provenance.prompt_versions["visual"] == "visual-v3-multi-image-edit-en"
    assert saved.visuals is not None
    assert saved.visuals.prompt_version == "visual-v3-multi-image-edit-en"
    # Ingredient display names follow the en-US mapping language while the
    # item_id identity stays authoritative.
    assert saved.gameplay is not None
    for ingredient in saved.gameplay.ingredients:
        assert (
            ingredient.display_name
            == harness.catalog.require(ingredient.item_id).display_name_en
        )


async def test_unmatched_ingredient_uses_catalog_fallback(
    harness: GenerationHarness,
) -> None:
    """A semantic ingredient with no catalog match falls back instead of failing."""

    class BeefGateway(FakeGateway):
        async def design_ask_gus(self, request, *, json_only: bool = False):
            self.calls.append("design")
            core = core_fixture()
            return core.model_copy(
                update={
                    "ingredients": [
                        SemanticRecipeIngredient(
                            name="Parsnip", normalizedName="parsnip"
                        ),
                        SemanticRecipeIngredient(
                            name="Spring Onion", normalizedName="spring onion"
                        ),
                        SemanticRecipeIngredient(
                            name="Beef", normalizedName="beef"
                        ),
                    ]
                }
            )

    local_orchestrator = GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=lambda: BeefGateway(),
        registry=AttemptRegistry(),
        min_confidence=0.5,
    )
    ref = put_original_image(harness)
    draft = make_domain_draft(
        mode=DraftMode.ASK_GUS, status=DraftStatus.READY, revision=1
    )
    source = draft.source.model_copy(
        update={"original_image_asset_id": ref.asset_id}
    )
    draft = draft.model_copy(update={"source": source})
    saved = local_orchestrator.drafts.save(draft, expected_revision=None)

    events = [
        event async for event in local_orchestrator.run(initial_command(saved))
    ]

    assert events[-1].type == "attempt.succeeded"
    reloaded = local_orchestrator.drafts.get(saved.draft_id)
    assert reloaded.status is DraftStatus.REVIEWABLE
    assert reloaded.gameplay is not None
    beef = [
        ingredient
        for ingredient in reloaded.gameplay.ingredients
        if ingredient.item_id == "176"
    ]
    assert beef
    assert "catalog fallback" in beef[0].mapping_reason


async def test_egg_plus_two_unmatched_ingredients_keep_unique_item_ids(
    harness: GenerationHarness,
) -> None:
    """Egg (matched to item 176) plus two unmatched ingredients must not
    collide on the fallback item, so GameplaySpec uniqueness still holds."""

    class MultiUnmatchedGateway(FakeGateway):
        async def design_ask_gus(self, request, *, json_only: bool = False):
            self.calls.append("design")
            core = core_fixture()
            return core.model_copy(
                update={
                    "ingredients": [
                        SemanticRecipeIngredient(
                            name="Egg", normalizedName="egg"
                        ),
                        SemanticRecipeIngredient(
                            name="Beef", normalizedName="beef"
                        ),
                        SemanticRecipeIngredient(
                            name="Lamb", normalizedName="lamb"
                        ),
                    ]
                }
            )

    local_orchestrator = GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=lambda: MultiUnmatchedGateway(),
        registry=AttemptRegistry(),
        min_confidence=0.5,
    )
    ref = put_original_image(harness)
    draft = make_domain_draft(
        mode=DraftMode.ASK_GUS, status=DraftStatus.READY, revision=1
    )
    source = draft.source.model_copy(
        update={"original_image_asset_id": ref.asset_id}
    )
    draft = draft.model_copy(update={"source": source})
    saved = local_orchestrator.drafts.save(draft, expected_revision=None)

    events = [
        event async for event in local_orchestrator.run(initial_command(saved))
    ]

    assert events[-1].type == "attempt.succeeded"
    reloaded = local_orchestrator.drafts.get(saved.draft_id)
    assert reloaded.status is DraftStatus.REVIEWABLE
    assert reloaded.gameplay is not None
    item_ids = [ingredient.item_id for ingredient in reloaded.gameplay.ingredients]
    assert len(item_ids) == len(set(item_ids))
    assert "176" in item_ids
    fallbacks = [
        ingredient
        for ingredient in reloaded.gameplay.ingredients
        if "catalog fallback" in ingredient.mapping_reason
    ]
    assert len(fallbacks) == 2
    assert len({ingredient.item_id for ingredient in fallbacks}) == 2


async def test_failed_draft_retry_reaches_reviewable(
    harness: GenerationHarness, orchestrator: GenerationOrchestrator
) -> None:
    ref = put_original_image(harness)
    failed = make_domain_draft(
        mode=DraftMode.ASK_GUS, status=DraftStatus.FAILED, revision=1
    )
    failed = failed.model_copy(
        update={
            "source": failed.source.model_copy(
                update={"original_image_asset_id": ref.asset_id}
            )
        }
    )
    saved = orchestrator.drafts.save(failed, expected_revision=None)

    events = [
        event async for event in orchestrator.run(initial_command(saved))
    ]

    assert events[-1].type == "attempt.succeeded"
    reloaded = orchestrator.drafts.get(saved.draft_id)
    assert reloaded.status is DraftStatus.REVIEWABLE


async def test_failed_draft_retry_returns_to_failed_on_second_failure(
    harness: GenerationHarness, orchestrator: GenerationOrchestrator
) -> None:
    harness.gateway.fail_stage = GenerationStage.GAMEPLAY_DESIGN
    ref = put_original_image(harness)
    failed = make_domain_draft(
        mode=DraftMode.ASK_GUS, status=DraftStatus.FAILED, revision=1
    )
    failed = failed.model_copy(
        update={
            "source": failed.source.model_copy(
                update={"original_image_asset_id": ref.asset_id}
            )
        }
    )
    saved = orchestrator.drafts.save(failed, expected_revision=None)

    events = [
        event async for event in orchestrator.run(initial_command(saved))
    ]

    assert events[-1].type == "attempt.failed"
    reloaded = orchestrator.drafts.get(saved.draft_id)
    assert reloaded.status is DraftStatus.FAILED


async def test_dish_analysis_receives_downscaled_jpeg(
    harness: GenerationHarness,
) -> None:
    """DISH_ANALYSIS sends a downscaled JPEG to the gateway, not the original."""

    class RecordingGateway(FakeGateway):
        def __init__(self) -> None:
            super().__init__()
            self.analysis_image: tuple[bytes, ImageMediaType] | None = None

        async def analyze_dish(self, request, *, json_only: bool = False):
            self.analysis_image = (request.image.data, request.image.media_type)
            return await super().analyze_dish(request, json_only=json_only)

    recorder = RecordingGateway()
    local_orchestrator = GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=lambda: recorder,
        registry=AttemptRegistry(),
        min_confidence=0.5,
    )
    ref = put_original_image(harness, size=3000)
    stored_before = _read_asset(harness.asset_store, ref)
    draft = make_domain_draft(
        mode=DraftMode.ASK_GUS, status=DraftStatus.READY, revision=1
    )
    source = draft.source.model_copy(
        update={"original_image_asset_id": ref.asset_id}
    )
    draft = draft.model_copy(update={"source": source})
    saved = local_orchestrator.drafts.save(draft, expected_revision=None)

    events = [
        event
        async for event in local_orchestrator.run(initial_command(saved))
    ]

    assert events[-1].type == "attempt.succeeded"
    assert recorder.analysis_image is not None
    data, media = recorder.analysis_image
    assert media is ImageMediaType.JPEG
    with Image.open(io.BytesIO(data)) as image:
        assert max(image.size) <= 2048
    # The stored original image asset is untouched.
    assert _read_asset(harness.asset_store, ref) == stored_before


async def test_client_disconnect_detaches_initial_generation(
    harness: GenerationHarness, ready_draft
) -> None:
    """Task 19.2: a client disconnect (aclose) only detaches the subscriber.
    The server-owned generation keeps running and reaches a terminal state;
    the draft is not rolled back and the slot is released when it finishes."""
    harness.gateway.delay = 0.2
    agen = harness.orchestrator.run(initial_command(ready_draft))
    first = await anext(agen)
    assert first.type == "attempt.started"
    attempt_id = first.attempt_id
    assert attempt_id is not None
    second = await anext(agen)
    assert second.type == "stage.started"

    mid = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert mid.status is DraftStatus.GENERATING
    assert mid.active_attempt_id == attempt_id

    # Detach: the stream stops reading, the generation continues server-side.
    await agen.aclose()

    # Detach is not a cancel: the draft stays GENERATING until it completes.
    still = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert still.status is DraftStatus.GENERATING
    assert still.active_attempt_id == attempt_id

    # Wait for the server-owned task to finish.
    await harness.orchestrator.await_cancelled(attempt_id)

    restored = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert restored.status is DraftStatus.REVIEWABLE
    assert restored.active_attempt_id is None
    attempt = harness.orchestrator.attempts.get(attempt_id)
    assert attempt.status is AttemptStatus.SUCCEEDED
    assert harness.orchestrator._registry.owner() is None


async def test_client_disconnect_detaches_regeneration(
    harness: GenerationHarness, reviewable_draft
) -> None:
    harness.gateway.delay = 0.2
    agen = harness.orchestrator.run(full_regen_command(reviewable_draft))
    first = await anext(agen)
    assert first.type == "attempt.started"
    attempt_id = first.attempt_id
    assert attempt_id is not None
    second = await anext(agen)
    assert second.type == "stage.started"

    mid = harness.orchestrator.drafts.get(reviewable_draft.draft_id)
    assert mid.status is DraftStatus.REGENERATING
    assert mid.active_attempt_id == attempt_id

    await agen.aclose()

    still = harness.orchestrator.drafts.get(reviewable_draft.draft_id)
    assert still.status is DraftStatus.REGENERATING

    await harness.orchestrator.await_cancelled(attempt_id)

    restored = harness.orchestrator.drafts.get(reviewable_draft.draft_id)
    assert restored.status is DraftStatus.REVIEWABLE
    assert restored.active_attempt_id is None
    attempt = harness.orchestrator.attempts.get(attempt_id)
    assert attempt.status is AttemptStatus.SUCCEEDED
    assert harness.orchestrator._registry.owner() is None


async def test_canonical_hit_icon_gate_reuses_at_exactly_0_75(
    harness: GenerationHarness,
) -> None:
    """M13 Task 58: 0.75 passes the visual reuse gate (inclusive boundary)."""
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    registry = _RecallRegistry(canonical, source_icon, icon_16)
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.97,
    )
    harness.gateway.visual_similarity = 0.75
    local = _canonical_orchestrator(harness, registry)
    original = put_original_image(harness)
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in local.run(initial_command(saved))]

    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["analyze", "match", "compare_icon", "image"]
    assert len(harness.gateway.image_requests) == 1  # preview only
    restored = local.drafts.get(saved.draft_id)
    assert (
        restored.provenance.icon_reuse_decision is IconReuseDecision.REUSED
    )
    assert restored.provenance.icon_visual_similarity == 0.75


async def test_canonical_hit_icon_gate_generates_below_0_75_and_keeps_text(
    harness: GenerationHarness,
) -> None:
    """0.749 misses the gate: a new icon is drawn from the current photo while
    every matched text/field value stays canonical and design is not called."""
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    registry = _RecallRegistry(canonical, source_icon, icon_16)
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.97,
    )
    harness.gateway.visual_similarity = 0.749
    local = _canonical_orchestrator(harness, registry)
    original = put_original_image(harness, color="goldenrod")
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in local.run(initial_command(saved))]

    assert events[-1].type == "attempt.succeeded"
    # compare_icon -> fresh icon EDIT -> preview EDIT; no design call.
    assert harness.gateway.calls == [
        "analyze",
        "match",
        "compare_icon",
        "image",
        "image",
    ]
    icon_request = harness.gateway.image_requests[0]
    assert icon_request.operation is ImageOperation.EDIT
    assert len(icon_request.source_images) == 1
    assert icon_request.source_images[0].data != source_icon
    restored = local.drafts.get(saved.draft_id)
    assert (
        restored.provenance.icon_reuse_decision is IconReuseDecision.GENERATED
    )
    assert restored.provenance.icon_visual_similarity == 0.749
    assert restored.provenance.generation_source is GenerationSource.CANONICAL_REUSED
    assert restored.provenance.canonical_dish_id == canonical.canonical_id
    assert restored.presentation == restored.presentation  # text reused via state
    assert restored.presentation.display_name == canonical.presentation.display_name
    assert (
        restored.provenance.authority_by_field[
            "visuals.icon_source_asset_id"
        ].value
        == "SYSTEM_GENERATED"
    )
    assert (
        restored.provenance.authority_by_field["visuals.icon_16_asset_id"].value
        == "SYSTEM_GENERATED"
    )
    # The fresh icon is a different asset than the canonical recorded source.
    assert restored.visuals is not None
    fresh_source = harness.asset_store.stat(restored.visuals.icon_source_asset_id)
    assert harness.asset_store.stat(restored.visuals.icon_source_asset_id) is not None
    assert fresh_source.attempt_id == restored.last_attempt_id


async def test_visual_decision_checkpoint_prevents_repeat_compare_after_icon_failure(
    harness: GenerationHarness,
) -> None:
    """A saved visual decision is enough to resume the next paid icon step."""
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    registry = _RecallRegistry(canonical, source_icon, icon_16)
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.97,
    )
    harness.gateway.visual_similarity = 0.749
    harness.gateway.fail_stage = GenerationStage.ICON_GENERATION_AND_NORMALIZATION
    local = _canonical_orchestrator(harness, registry)
    original = put_original_image(harness)
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    failed = [event async for event in local.run(initial_command(saved))]

    assert failed[-1].type == "attempt.failed"
    assert harness.gateway.calls == ["analyze", "match", "compare_icon", "image"]
    checkpoint = local.attempts.get_checkpoint(failed[-1].attempt_id)
    assert checkpoint is not None
    assert checkpoint.icon_reuse_decision is IconReuseDecision.GENERATED
    assert checkpoint.icon_visual_similarity == 0.749
    assert GenerationStage.ICON_GENERATION_AND_NORMALIZATION not in (
        checkpoint.completed_stages
    )

    harness.gateway.fail_stage = None
    harness.gateway.calls.clear()
    resumed = _canonical_orchestrator(harness, registry)
    events = [
        event
        async for event in resumed.run(
            initial_command(resumed.drafts.get(saved.draft_id))
        )
    ]

    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["image", "image"]


async def test_canonical_icon_gate_failure_keeps_text_hit_checkpoint(
    harness: GenerationHarness,
) -> None:
    """A vision-provider outage at the comparison step fails the attempt with
    a resumable checkpoint: the completed text stages are preserved and the
    resume path does not re-run the matcher."""
    canonical, source_icon, icon_16 = _canonical_dish(uuid4())
    second, _, _ = _canonical_dish(uuid4())
    registry = _RecallRegistry(canonical, source_icon, icon_16, second=second)
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.94,
    )
    harness.gateway.visual_similarity = None  # comparison step raises
    local = _canonical_orchestrator(harness, registry)
    original = put_original_image(harness)
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = local.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in local.run(initial_command(saved))]

    assert events[-1].type == "attempt.failed"
    assert harness.gateway.calls == ["analyze", "match", "compare_icon"]
    assert events[-1].error.code == "PTS_GEN_UNEXPECTED"
    assert events[-1].error.details.get("progressSaved") is True
    checkpoint = local.attempts.get_checkpoint(events[-1].attempt_id)
    assert checkpoint is not None
    assert checkpoint.canonical == canonical
    assert GenerationStage.GAMEPLAY_DESIGN in checkpoint.completed_stages
    assert (
        GenerationStage.ICON_GENERATION_AND_NORMALIZATION
        not in checkpoint.completed_stages
    )

    # Resume after "provider recovery" regenerates a fresh icon and succeeds
    # without calling the matcher again.
    harness.gateway.visual_similarity = 0.9
    resumed = _canonical_orchestrator(harness, registry)
    harness.gateway.calls.clear()
    events = [
        event
        async for event in resumed.run(
            initial_command(resumed.drafts.get(saved.draft_id))
        )
    ]
    assert events[-1].type == "attempt.succeeded"
    assert "match" not in harness.gateway.calls
    assert harness.gateway.calls[0] == "compare_icon"
    restored = resumed.drafts.get(saved.draft_id)
    assert restored.provenance.canonical_dish_id == canonical.canonical_id
    assert (
        restored.provenance.icon_reuse_decision is IconReuseDecision.REUSED
    )
