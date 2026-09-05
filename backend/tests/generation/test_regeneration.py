"""Full regeneration atomicity: success replaces all, failure keeps previous."""

from __future__ import annotations

from pelican_town_specials.domain.common import GenerationStage
from pelican_town_specials.domain.dish import GenerationSource
from pelican_town_specials.domain.draft import (
    DraftRecord,
    DraftStatus,
    GenerationAttemptKind,
)
from pelican_town_specials.generation.orchestrator import GenerationCommand
from pelican_town_specials.images import downscale_for_vision
from pelican_town_specials.images.vision_input import EDIT_MIN_PIXELS
from pelican_town_specials.providers.contracts import ImageOperation

from .conftest import (
    GenerationHarness,
    full_regen_command,
    reviewable_draft_result_hash,
)


async def test_failed_full_regeneration_keeps_previous_result(
    harness: GenerationHarness, reviewable_draft
) -> None:
    harness.gateway.fail_stage = GenerationStage.ICON_GENERATION_AND_NORMALIZATION
    old_hash = reviewable_draft_result_hash(reviewable_draft)
    events = [
        event
        async for event in harness.orchestrator.run(
            full_regen_command(reviewable_draft)
        )
    ]
    restored = harness.orchestrator.drafts.get(reviewable_draft.draft_id)
    assert restored.status is DraftStatus.REVIEWABLE
    assert reviewable_draft_result_hash(restored) == old_hash
    assert events[-1].type == "attempt.failed"
    assert harness.gateway.calls == [
        "analyze",
        "design",
        "image",
    ]


async def test_successful_full_regeneration_replaces_all_fields(
    harness: GenerationHarness, reviewable_draft
) -> None:
    old_hash = reviewable_draft_result_hash(reviewable_draft)
    old_visuals = reviewable_draft.visuals
    events = [
        event
        async for event in harness.orchestrator.run(
            full_regen_command(reviewable_draft)
        )
    ]
    restored = harness.orchestrator.drafts.get(reviewable_draft.draft_id)
    assert restored.status is DraftStatus.REVIEWABLE
    assert restored.revision == reviewable_draft.revision + 1
    assert reviewable_draft_result_hash(restored) != old_hash
    assert events[-1].type == "attempt.succeeded"

    # Every core field is replaced by the freshly generated candidate.
    assert restored.analysis is not None
    assert restored.analysis.recognized_dish == "Spring Noodles"
    assert restored.presentation is not None
    assert restored.presentation.display_name == "春日面碗"
    assert restored.gameplay is not None
    assert restored.gameplay.sell_price == 220

    # Both visual assets are regenerated and no old revision lingers.
    assert restored.visuals is not None
    assert restored.visuals.icon_16_asset_id != old_visuals.icon_16_asset_id
    assert restored.visuals.preview_asset_id != old_visuals.preview_asset_id
    assert restored.visuals.generated_art_asset_id is None
    assert restored.visuals.source_revision == restored.revision
    assert restored.provenance.generation_source is GenerationSource.FRESH_GENERATION
    assert restored.provenance.canonical_dish_id is None
    assert restored.provenance.canonical_dish_signature is None
    assert restored.provenance.recall_confidence is None
    assert restored.provenance.recall_elapsed_ms is None

    # The attempt is finished; no active attempt remains on the promoted draft.
    assert restored.active_attempt_id is None
    assert restored.last_attempt_id is not None
    assert harness.gateway.calls == ["analyze", "design", "image", "image"]
    icon_request, preview_request = harness.gateway.image_requests
    assert icon_request.operation is ImageOperation.EDIT
    assert len(icon_request.source_images) == 1
    original_ref = harness.asset_store.stat(
        reviewable_draft.source.original_image_asset_id
    )
    with harness.asset_store.open(original_ref) as handle:
        original_data = handle.read()
    downscaled, media_type = downscale_for_vision(
        original_data, min_pixels=EDIT_MIN_PIXELS
    )
    assert icon_request.source_images[0].data == downscaled
    assert icon_request.source_images[0].media_type is media_type
    assert preview_request.operation is ImageOperation.EDIT
    assert len(preview_request.source_images) == 2


def _regen_with_instructions(
    draft: DraftRecord, instructions: str | None
) -> GenerationCommand:
    from uuid import uuid4

    return GenerationCommand(
        draftId=draft.draft_id,
        kind=GenerationAttemptKind.FULL_REGENERATE,
        requestId=uuid4(),
        regenerationInstructions=instructions,
    )


async def test_regeneration_instruction_round_persists_attempt_and_prompt(
    harness: GenerationHarness,
    reviewable_draft,
) -> None:
    """M13 Task 59: a full-regeneration round with an instruction carries it
    into the persisted attempt and the provider design/analysis requests."""
    instruction = "鱼片切厚一点，摆成扇形。"
    events = [
        event
        async for event in harness.orchestrator.run(
            _regen_with_instructions(reviewable_draft, instruction)
        )
    ]
    assert events[-1].type == "attempt.succeeded"

    assert len(harness.gateway.design_requests) == 1
    assert (
        getattr(harness.gateway.design_requests[0], "regeneration_instructions", None)
        == instruction
    )
    attempt = harness.attempt_repository.get(events[-1].attempt_id)
    assert attempt.regeneration_instructions == instruction


async def test_changed_regeneration_instruction_starts_fresh_round(
    harness: GenerationHarness,
    reviewable_draft,
) -> None:
    """Changing the instruction must never reuse the previous round's saved
    output: the checkpoint fingerprint covers the wording, so a new round is
    a full restart and no provider stage is skipped."""
    harness.gateway.fail_stage = GenerationStage.ICON_GENERATION_AND_NORMALIZATION
    first = [
        event
        async for event in harness.orchestrator.run(
            _regen_with_instructions(reviewable_draft, "鱼片切厚一点")
        )
    ]
    assert first[-1].type == "attempt.failed"
    saved_checkpoint = harness.attempt_repository.get_checkpoint(first[-1].attempt_id)
    assert saved_checkpoint is not None

    # Re-run with different wording: old checkpoint is incompatible (fingerprint
    # mismatch) and the attempt starts over from the analysis stage.
    harness.gateway.fail_stage = None
    second = [
        event
        async for event in harness.orchestrator.run(
            _regen_with_instructions(reviewable_draft, "摆成扇形")
        )
    ]
    assert second[-1].type == "attempt.succeeded"
    stages = [event for event in second if event.type == "stage.succeeded"]
    assert {event.stage for event in stages} >= {
        GenerationStage.DISH_ANALYSIS,
        GenerationStage.GAMEPLAY_DESIGN,
        GenerationStage.ICON_GENERATION_AND_NORMALIZATION,
    }
