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
from pelican_town_specials.persistence.asset_store import FileAssetStore
from pelican_town_specials.providers.contracts import (
    ImageMediaType,
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
    assert harness.gateway.calls == ["analyze", "design", "image"]
    saved = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert saved.visuals is not None
    assert saved.visuals.generated_art_asset_id is None
    assert saved.visuals.preview_asset_id is not None
    assert saved.visuals.icon_16_asset_id is not None
    original_ref = harness.asset_store.stat(saved.source.original_image_asset_id)
    preview_ref = harness.asset_store.stat(saved.visuals.preview_asset_id)
    original = Image.open(
        io.BytesIO(_read_asset(harness.asset_store, original_ref))
    ).convert("RGBA")
    preview = Image.open(
        io.BytesIO(_read_asset(harness.asset_store, preview_ref))
    ).convert("RGBA")
    assert preview.size == original.size
    assert preview.getpixel((0, 0)) == original.getpixel((0, 0))


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
