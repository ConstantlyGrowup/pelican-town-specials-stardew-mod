"""Full regeneration atomicity: success replaces all, failure keeps previous."""

from __future__ import annotations

from pelican_town_specials.domain.common import GenerationStage
from pelican_town_specials.domain.draft import DraftStatus
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

    # The attempt is finished; no active attempt remains on the promoted draft.
    assert restored.active_attempt_id is None
    assert restored.last_attempt_id is not None
    assert harness.gateway.calls == ["analyze", "design", "image", "image"]
    assert [request.operation for request in harness.gateway.image_requests] == [
        ImageOperation.GENERATION,
        ImageOperation.EDIT,
    ]
