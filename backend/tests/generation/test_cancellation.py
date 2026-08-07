"""Generation cancellation and the single-slot semaphore."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from pelican_town_specials.domain.common import GenerationStage, utc_now
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    DraftStatus,
    GenerationAttempt,
    GenerationAttemptKind,
    StageAttempt,
    StageStatus,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.events import GenerationEvent

from .conftest import GenerationHarness, initial_command


async def test_cancel_mid_generation_rolls_back(
    harness: GenerationHarness, ready_draft
) -> None:
    harness.gateway.delay = 0.3
    agen = harness.orchestrator.run(initial_command(ready_draft))
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

    # Let the generator reach a long-running gateway stage, then cancel.
    await asyncio.sleep(0.05)
    assert harness.orchestrator.cancel(attempt_id) is True
    await task

    restored = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert restored.status is DraftStatus.READY
    assert restored.active_attempt_id is None
    attempt = harness.orchestrator.attempts.get(attempt_id)
    assert attempt.status is AttemptStatus.CANCELLED
    assert holder[-1].type == "attempt.failed"
    assert holder[-1].error is not None
    assert holder[-1].error.code == "PTS_GEN_CANCELLED"


async def test_second_concurrent_generation_is_rejected(
    harness: GenerationHarness, ready_draft
) -> None:
    first = harness.orchestrator.run(initial_command(ready_draft))
    try:
        with pytest.raises(AppError) as excinfo:
            harness.orchestrator.run(initial_command(ready_draft))
        assert excinfo.value.code == "PTS_GEN_BUSY"
    finally:
        await first.aclose()

    # Closing the unstarted generator releases the slot for the next attempt.
    second = harness.orchestrator.run(initial_command(ready_draft))
    await second.aclose()


async def test_aclose_detaches_without_rolling_back(
    harness: GenerationHarness, ready_draft
) -> None:
    """Task 19.2: a client disconnect (what the route's ``_ClosingStreamingResponse``
    guarantees via aclose) only detaches the subscriber. The server-owned
    generation keeps running: the draft stays in its generating state, the
    active attempt is not cleared, and the slot stays held until the
    generation itself finishes."""
    harness.gateway.delay = 0.3
    agen = harness.orchestrator.run(initial_command(ready_draft))
    iterator = agen.__aiter__()
    first = await iterator.__anext__()
    assert first.type == "attempt.started"
    attempt_id = first.attempt_id
    assert attempt_id is not None
    stage_event = await iterator.__anext__()
    assert stage_event.type == "stage.started"

    # Deterministic detach (the route always acloses on disconnect).
    await agen.aclose()

    # Detach is not a cancel: the draft is still GENERATING, the active attempt
    # is still set, and the slot is still owned by this attempt.
    restored = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert restored.status is DraftStatus.GENERATING
    assert restored.active_attempt_id == attempt_id
    attempt = harness.orchestrator.attempts.get(attempt_id)
    assert attempt.status is AttemptStatus.RUNNING
    owner = harness.orchestrator._registry.owner()
    assert owner is not None
    assert owner.attempt_id == attempt_id

    # The slot is still held: a new generation stays busy.
    with pytest.raises(AppError) as excinfo:
        harness.orchestrator.run(initial_command(ready_draft))
    assert excinfo.value.code == "PTS_GEN_BUSY"

    # The detached generation continues to a terminal state: the draft reaches
    # REVIEWABLE and the slot is released by the server-owned task.
    await harness.orchestrator.await_cancelled(attempt_id)
    final = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert final.status is DraftStatus.REVIEWABLE
    assert final.active_attempt_id is None
    persisted = harness.orchestrator.attempts.get(attempt_id)
    assert persisted.status is AttemptStatus.SUCCEEDED
    assert harness.orchestrator._registry.owner() is None


async def test_recover_interrupted_rolls_back_generating_draft(
    harness: GenerationHarness, ready_draft
) -> None:
    """Regression: an attempt persisted as GENERATING but with no live in-process
    task (page reload / client disconnect / previous-process crash) must be
    recoverable: recover_interrupted rolls the draft back and marks the attempt
    INTERRUPTED so a fresh generation can start."""
    attempt_id = uuid4()
    staged = ready_draft.model_copy(
        update={
            "status": DraftStatus.GENERATING,
            "active_attempt_id": attempt_id,
            "updated_at": utc_now(),
        }
    )
    harness.orchestrator.drafts.control_write(
        staged,
        expected_revision=ready_draft.revision,
        expected_attempt_id=None,
    )
    now = utc_now()
    harness.orchestrator.attempts.save(
        GenerationAttempt(
            attempt_id=attempt_id,
            draft_id=ready_draft.draft_id,
            kind=GenerationAttemptKind.INITIAL,
            source_revision=ready_draft.revision,
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
    )

    assert harness.orchestrator.recover_interrupted(ready_draft.draft_id) is True

    restored = harness.orchestrator.drafts.get(ready_draft.draft_id)
    assert restored.status is DraftStatus.READY
    assert restored.active_attempt_id is None
    assert restored.last_attempt_id == attempt_id
    assert restored.last_error is not None
    assert restored.last_error.code == "PTS_GEN_INTERRUPTED"

    persisted = harness.orchestrator.attempts.get(attempt_id)
    assert persisted.status is AttemptStatus.INTERRUPTED

    # The slot was never reserved by this orphan; a fresh generation starts.
    second = harness.orchestrator.run(initial_command(ready_draft))
    await second.aclose()
