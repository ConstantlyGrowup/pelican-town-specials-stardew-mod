"""Generation cancellation and the single-slot semaphore."""

from __future__ import annotations

import asyncio

import pytest

from pelican_town_specials.domain.draft import AttemptStatus, DraftStatus
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
