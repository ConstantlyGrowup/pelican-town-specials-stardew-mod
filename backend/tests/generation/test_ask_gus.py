"""Ask Gus initial generation: stage order, low-confidence stop, illegal state."""

from __future__ import annotations

import io

import pytest
from backend.tests.domain.factories import make_draft as make_domain_draft
from PIL import Image

from pelican_town_specials.domain.assets import AssetRef
from pelican_town_specials.domain.common import DraftMode, GenerationStage
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import GenerationOrchestrator
from pelican_town_specials.images import downscale_for_vision
from pelican_town_specials.persistence.asset_store import FileAssetStore
from pelican_town_specials.providers.contracts import (
    ImageMediaType,
    ImageOperation,
    SemanticRecipeIngredient,
)

from .conftest import (
    EXPECTED_ASK_GUS_STAGES,
    FakeGateway,
    GenerationHarness,
    core_fixture,
    initial_command,
    put_original_image,
)


def _read_asset(asset_store: FileAssetStore, ref: AssetRef) -> bytes:
    with asset_store.open(ref) as handle:
        return handle.read()


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
    assert icon_request.operation is ImageOperation.GENERATION
    assert icon_request.source_images == []
    assert preview_request.operation is ImageOperation.EDIT
    assert len(preview_request.source_images) == 2
    for required_text in (
        "春日面碗",
        "主菜",
        "一碗带着春天气息的热汤面。",
        "体力+200",
        "生命+90",
        "售价=220g",
        "饱和暖金橙",
        "多层深棕与橙棕硬边像素框",
        "游戏式分隔线",
        "统一像素符号",
    ):
        assert required_text in preview_request.prompt
    saved = harness.orchestrator.drafts.get(ready_draft.draft_id)
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
    downscaled, media_type = downscale_for_vision(original_data)
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
    assert preview.size == (96, 64)
    assert preview.size != original.size


async def test_preview_stops_without_two_image_edit_capability(
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
    assert harness.gateway.calls == ["analyze", "design", "image"]
    assert len(harness.gateway.image_requests) == 1
    assert harness.gateway.image_requests[0].operation is ImageOperation.GENERATION


def test_preview_prompt_stays_within_provider_limit() -> None:
    """The full-tooltip prompt must fit the frozen provider contract
    (prompt <= 1500 chars) even with maximum-length structured fields and a
    long visual brief; otherwise the EDIT request cannot be constructed."""
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
            id="Speed",
            durationMinutes=10,
            attributes=BuffAttributes(speed=2),
        ),
    )
    prompt = _preview_prompt(presentation, gameplay, "氛" * 1500)
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


async def test_preview_prompt_over_budget_fails_controlled(
    harness: GenerationHarness, ready_draft
) -> None:
    """Maximum legal fields (including a maximum BuffSpec) overflow the
    provider's 1500-char prompt contract even after the non-business brief is
    compressed; the run must fail with a controlled non-retryable error before
    any EDIT provider call, not a ValidationError wrapped as a 500."""

    from pelican_town_specials.domain.dish import (
        BuffAttributes,
        BuffSpec,
        PresentationSpec,
        RecoverySpec,
    )

    class MaxFieldsGateway(FakeGateway):
        async def design_ask_gus(self, request, *, json_only: bool = False):
            self.calls.append("design")
            core = core_fixture()
            return core.model_copy(
                update={
                    "presentation": PresentationSpec(
                        displayName="名" * 60,
                        internalName="MaxName",
                        categoryLabel="类" * 40,
                        description="描" * 400,
                        tags=[],
                    ),
                    "recovery": RecoverySpec(edibility=500),
                    "sell_price": 50000,
                    "buff": BuffSpec(
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
                    "visual_brief": "氛" * 1500,
                }
            )

    gateway = MaxFieldsGateway()
    local_orchestrator = GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=lambda: gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
    )
    events = [
        event
        async for event in local_orchestrator.run(initial_command(ready_draft))
    ]
    assert events[-1].type == "attempt.failed"
    error = events[-1].error
    assert error is not None
    assert error.code == "PTS_PREVIEW_PROMPT_TOO_LONG"
    assert error.retryable is False
    # The icon GENERATION ran; the EDIT request never reached the provider.
    assert gateway.calls == ["analyze", "design", "image"]
    assert len(gateway.image_requests) == 1
    assert gateway.image_requests[0].operation is ImageOperation.GENERATION


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
