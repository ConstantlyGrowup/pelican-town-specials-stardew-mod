"""Blueprint visual update: user-field protection, stage order, failure keep-stale."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from pelican_town_specials.domain.common import GenerationStage
from pelican_town_specials.domain.dish import FieldAuthority
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.generation.blueprint import (
    BLUEPRINT_STAGE_ORDER,
    build_blueprint_visual_brief,
)
from pelican_town_specials.generation.events import GenerationEvent

from .conftest import (
    GenerationHarness,
    blueprint_preview_command,
)

BLUEPRINT_FORBIDDEN_STAGES = (
    GenerationStage.DISH_ANALYSIS,
    GenerationStage.GAMEPLAY_DESIGN,
    GenerationStage.INGREDIENT_MAPPING,
)


async def _collect(
    agen: AsyncIterator[GenerationEvent],
) -> list[GenerationEvent]:
    events: list[GenerationEvent] = []
    async for event in agen:
        events.append(event)
    return events


async def test_blueprint_generation_never_changes_user_fields(
    harness: GenerationHarness, blueprint_stale
) -> None:
    before = blueprint_stale.model_dump(include={"presentation", "gameplay"})
    await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    after = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    assert after.model_dump(include={"presentation", "gameplay"}) == before
    assert after.status is DraftStatus.REVIEWABLE


async def test_blueprint_stage_order_and_image_only_calls(
    harness: GenerationHarness, blueprint_stale
) -> None:
    events = await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    succeeded = [
        event.stage for event in events if event.type == "stage.succeeded"
    ]
    # Exact six-stage blueprint sequence, no Ask Gus analysis stages.
    assert succeeded == list(BLUEPRINT_STAGE_ORDER)
    for forbidden in BLUEPRINT_FORBIDDEN_STAGES:
        assert forbidden not in succeeded
    # The model is only used for the icon; preview composition is local.
    assert harness.gateway.calls == ["image"]
    assert events[-1].type == "attempt.succeeded"

    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    assert restored.revision == blueprint_stale.revision + 1
    assert restored.visuals is not None
    assert restored.visuals.source_revision == restored.revision


async def test_blueprint_visual_brief_is_deterministic_and_model_free(
    harness: GenerationHarness, blueprint_stale
) -> None:
    await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    # No analyze/design calls: VISUAL_BRIEF is a deterministic user-field function.
    assert harness.gateway.calls == ["image"]
    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    assert restored.visuals is not None
    assert restored.visuals.visual_brief == build_blueprint_visual_brief(
        blueprint_stale.presentation, blueprint_stale.gameplay
    )


async def test_blueprint_failure_keeps_stale_preview(
    harness: GenerationHarness, blueprint_stale
) -> None:
    harness.gateway.fail_stage = GenerationStage.ICON_GENERATION_AND_NORMALIZATION
    events = await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    assert events[-1].type == "attempt.failed"
    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    # Stays STALE_PREVIEW; user fields and old visuals are preserved.
    assert restored.status is DraftStatus.STALE_PREVIEW
    assert restored.presentation == blueprint_stale.presentation
    assert restored.gameplay == blueprint_stale.gameplay
    assert restored.visuals == blueprint_stale.visuals
    # Active attempt cleared and failure recorded.
    assert restored.active_attempt_id is None
    assert restored.last_error is not None
    assert restored.last_attempt_id is not None
    # Only the icon image generation was attempted.
    assert harness.gateway.calls == ["image"]


async def test_blueprint_cancel_keeps_stale_preview(
    harness: GenerationHarness, blueprint_stale
) -> None:
    harness.gateway.delay = 0.3
    agen = harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    holder: list[GenerationEvent] = []

    async def consume() -> None:
        async for event in agen:
            holder.append(event)

    task = asyncio.create_task(consume())
    for _ in range(200):
        if holder and holder[0].attempt_id is not None:
            break
        await asyncio.sleep(0.01)
    assert holder, "attempt.started was never emitted"
    attempt_id = holder[0].attempt_id
    assert attempt_id is not None

    await asyncio.sleep(0.05)
    assert harness.orchestrator.cancel(attempt_id) is True
    await task

    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    # Cancelled preview keeps STALE_PREVIEW with user fields and old visuals.
    assert restored.status is DraftStatus.STALE_PREVIEW
    assert restored.active_attempt_id is None
    assert restored.last_error is not None
    assert restored.presentation == blueprint_stale.presentation
    assert restored.gameplay == blueprint_stale.gameplay
    assert restored.visuals == blueprint_stale.visuals
    assert holder[-1].type == "attempt.failed"
    assert holder[-1].error is not None
    assert holder[-1].error.code == "PTS_GEN_CANCELLED"


async def test_blueprint_preserves_provenance_and_cache_eligibility(
    harness: GenerationHarness, blueprint_stale
) -> None:
    before_provenance = blueprint_stale.provenance
    await _collect(
        harness.orchestrator.run(blueprint_preview_command(blueprint_stale))
    )
    restored = harness.orchestrator.drafts.get(blueprint_stale.draft_id)
    # Provenance is preserved verbatim: no AGENT_ASSIGNED, no cache eligibility.
    assert restored.provenance == before_provenance
    assert restored.provenance.cache_eligibility is False
    assert (
        FieldAuthority.AGENT_ASSIGNED
        not in restored.provenance.authority_by_field.values()
    )
