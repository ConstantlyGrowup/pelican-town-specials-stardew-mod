"""Task56 persisted provider-failure continuation contract tests."""

from __future__ import annotations

from pelican_town_specials.application.generation import GenerationService
from pelican_town_specials.domain.common import GenerationStage
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    GenerationAttemptKind,
    GenerationAttemptPublic,
)
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import (
    GenerationCommand,
    GenerationOrchestrator,
)

from .conftest import GenerationHarness, full_regen_command, initial_command


def _new_orchestrator(harness: GenerationHarness) -> GenerationOrchestrator:
    return GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=lambda: harness.gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
    )


async def test_provider_failure_persists_checkpoint_and_resumes_only_unfinished_stages(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    harness.gateway.fail_stage = GenerationStage.ICON_GENERATION_AND_NORMALIZATION

    events = [
        event async for event in harness.orchestrator.run(initial_command(ready_draft))
    ]
    attempt_id = events[0].attempt_id
    assert attempt_id is not None
    attempt = harness.attempt_repository.get(attempt_id)
    assert attempt.status is AttemptStatus.FAILED

    checkpoint = harness.attempt_repository.get_checkpoint(attempt_id)
    assert checkpoint is not None
    assert checkpoint.draft_id == ready_draft.draft_id
    assert checkpoint.source_revision == ready_draft.revision
    assert checkpoint.completed_stages == [
        GenerationStage.INPUT_VALIDATION,
        GenerationStage.DISH_ANALYSIS,
        GenerationStage.GAMEPLAY_DESIGN,
        GenerationStage.INGREDIENT_MAPPING,
        GenerationStage.VISUAL_BRIEF,
    ]

    progress = GenerationService(
        orchestrator=harness.orchestrator,
        draft_repository=harness.draft_repository,
    ).get_progress(ready_draft.draft_id)
    assert progress.attempt is not None
    assert progress.attempt.progress_saved is True
    assert GenerationAttemptPublic.from_attempt(attempt).progress_saved is False
    assert events[-1].error is not None
    assert events[-1].error.details["progressSaved"] is True

    harness.gateway.fail_stage = None
    harness.gateway.calls.clear()
    restarted = _new_orchestrator(harness)
    restored = restarted.drafts.get(ready_draft.draft_id)
    retry_events = [
        event async for event in restarted.run(initial_command(restored))
    ]

    assert retry_events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["image", "image"]


async def test_explicit_restart_ignores_saved_checkpoint_for_full_regeneration(
    harness: GenerationHarness,
    reviewable_draft,
) -> None:
    harness.gateway.fail_stage = GenerationStage.PREVIEW_ART_GENERATION_AND_COMPOSITION
    failed = [
        event
        async for event in harness.orchestrator.run(
            full_regen_command(reviewable_draft)
        )
    ]
    assert failed[-1].type == "attempt.failed"

    draft = harness.orchestrator.drafts.get(reviewable_draft.draft_id)
    harness.gateway.fail_stage = None
    harness.gateway.calls.clear()
    command = GenerationCommand(
        draftId=draft.draft_id,
        kind=GenerationAttemptKind.FULL_REGENERATE,
        requestId=full_regen_command(draft).request_id,
        restart=True,
    )
    events = [event async for event in harness.orchestrator.run(command)]

    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["analyze", "design", "image", "image"]
