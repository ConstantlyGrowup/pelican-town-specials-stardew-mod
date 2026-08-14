"""M8 Task 28: three-way concurrent generation lifecycle at orchestrator level.

Three fake-provider chains really overlap (a barrier proves all three are
inside the provider at the same time); the fourth request is rejected with a
stable PTS_GEN_BUSY carrying activeCount/maxConcurrent before any attempt
record, draft change, or provider call; completion/failure/cancel release only
their own slot; a client disconnect only detaches its subscriber.
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

import pytest
from backend.tests.domain.factories import make_draft as make_domain_draft

from pelican_town_specials.domain.common import DraftMode
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    DraftRecord,
    DraftStatus,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.events import GenerationEvent

from .conftest import GenerationHarness, initial_command, put_original_image


def _ready_drafts(harness: GenerationHarness, count: int) -> list[DraftRecord]:
    """Create ``count`` distinct READY ASK_GUS drafts with unique context text."""
    drafts: list[DraftRecord] = []
    for index in range(count):
        ref = put_original_image(harness)
        draft = make_domain_draft(
            mode=DraftMode.ASK_GUS, status=DraftStatus.READY, revision=1
        )
        source = draft.source.model_copy(
            update={
                "original_image_asset_id": ref.asset_id,
                "context_text": f"concurrent-draft-{index}",
            }
        )
        draft = draft.model_copy(update={"source": source})
        drafts.append(harness.orchestrator.drafts.save(draft, expected_revision=None))
    return drafts


async def _consume(agen) -> list[GenerationEvent]:
    events: list[GenerationEvent] = []
    async for event in agen:
        events.append(event)
    return events


async def _wait_for(predicate, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition never became true")


def _attempt_ids(holders: list[list[GenerationEvent]]) -> list[UUID | None]:
    return [holder[0].attempt_id for holder in holders]


async def test_three_generations_truly_overlap_at_provider(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T28-001: three fake-provider chains run concurrently — a barrier proves
    all three are inside the provider at the same time — and each draft
    receives its own stages and terminal state (attempts never cross wires)."""
    drafts = _ready_drafts(harness, 3)
    original_analyze = harness.gateway.analyze_dish
    reached = 0
    entered = asyncio.Event()
    released = asyncio.Event()

    async def barrier_analyze(request, *, json_only: bool = False):
        nonlocal reached
        reached += 1
        if reached >= 3:
            entered.set()
        await released.wait()
        return await original_analyze(request, json_only=json_only)

    monkeypatch.setattr(harness.gateway, "analyze_dish", barrier_analyze)

    streams = [harness.orchestrator.run(initial_command(d)) for d in drafts]
    tasks = [asyncio.create_task(_consume(stream)) for stream in streams]
    try:
        # All three must arrive inside the provider before anyone proceeds.
        await asyncio.wait_for(entered.wait(), timeout=5.0)
        assert reached == 3
        assert harness.orchestrator._registry.active_count() == 3
        released.set()
        results = await asyncio.gather(*tasks)

        attempt_ids = [events[0].attempt_id for events in results]
        assert all(attempt_id is not None for attempt_id in attempt_ids)
        assert len(set(attempt_ids)) == 3
        for events, draft in zip(results, drafts):
            assert events[0].type == "attempt.started"
            assert events[-1].type == "attempt.succeeded"
            assert events[-1].attempt_id == events[0].attempt_id
            final = harness.orchestrator.drafts.get(draft.draft_id)
            assert final.status is DraftStatus.REVIEWABLE
            assert final.active_attempt_id is None
            assert final.last_attempt_id == events[0].attempt_id
            persisted = harness.orchestrator.attempts.get(events[0].attempt_id)
            assert persisted.status is AttemptStatus.SUCCEEDED
        # Provider call counts: 3 analyze + 3 design + 6 images.
        assert harness.gateway.calls.count("analyze") == 3
        assert harness.gateway.calls.count("design") == 3
        assert harness.gateway.calls.count("image") == 6
        assert harness.orchestrator._registry.active_count() == 0
    finally:
        released.set()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_fourth_generation_rejected_busy_with_zero_side_effects(
    harness: GenerationHarness,
) -> None:
    """T28-002: with three slots occupied the fourth request is rejected before
    any attempt record, draft change, or provider call; the error details carry
    activeCount, maxConcurrent and the rejected request's draftId."""
    drafts = _ready_drafts(harness, 4)
    harness.gateway.delay = 0.5
    streams = [harness.orchestrator.run(initial_command(d)) for d in drafts[:3]]
    tasks = [asyncio.create_task(_consume(stream)) for stream in streams]
    try:
        await _wait_for(lambda: harness.orchestrator._registry.active_count() == 3)
        # All three are now inside their first provider call (0.5s sleep), so
        # the snapshot below is stable while the fourth request is rejected.
        await _wait_for(lambda: harness.gateway.calls.count("analyze") >= 3)
        analyze_before = harness.gateway.calls.count("analyze")
        calls_before = len(harness.gateway.calls)
        attempt_dirs_before = list(
            harness.workspace.staging_dir.glob("attempt-*")
        )
        draft4 = drafts[3]
        before = harness.orchestrator.drafts.get(draft4.draft_id)
        assert before.status is DraftStatus.READY

        with pytest.raises(AppError) as excinfo:
            harness.orchestrator.run(initial_command(draft4))
        error = excinfo.value
        assert error.code == "PTS_GEN_BUSY"
        assert error.http_status == 409
        assert error.details["activeCount"] == 3
        assert error.details["maxConcurrent"] == 3
        assert error.details["draftId"] == str(draft4.draft_id)

        # No attempt record, no draft change, no provider call.
        assert (
            list(harness.workspace.staging_dir.glob("attempt-*"))
            == attempt_dirs_before
        )
        after = harness.orchestrator.drafts.get(draft4.draft_id)
        assert after.status is DraftStatus.READY
        assert after.active_attempt_id is None
        assert after.revision == before.revision
        assert harness.gateway.calls.count("analyze") == analyze_before
        assert len(harness.gateway.calls) == calls_before
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for stream in streams:
            await stream.aclose()


async def test_completion_releases_only_its_own_slot(
    harness: GenerationHarness,
) -> None:
    """T28-003: when all three generations finish, every slot is released and
    the fourth request starts immediately."""
    drafts = _ready_drafts(harness, 4)
    harness.gateway.delay = 0.3
    streams = [harness.orchestrator.run(initial_command(d)) for d in drafts[:3]]
    tasks = [asyncio.create_task(_consume(stream)) for stream in streams]
    try:
        await _wait_for(lambda: harness.orchestrator._registry.active_count() == 3)
        results = await asyncio.gather(*tasks)
        assert harness.orchestrator._registry.active_count() == 0
        for events, draft in zip(results, drafts):
            assert events[-1].type == "attempt.succeeded"
            final = harness.orchestrator.drafts.get(draft.draft_id)
            assert final.status is DraftStatus.REVIEWABLE
            assert final.active_attempt_id is None

        # The freed slots admit the fourth request immediately.
        harness.gateway.delay = 0.0
        events4 = await _consume(
            harness.orchestrator.run(initial_command(drafts[3]))
        )
        assert events4[-1].type == "attempt.succeeded"
        assert harness.orchestrator._registry.active_count() == 0
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for stream in streams:
            await stream.aclose()


async def test_cancel_releases_only_its_own_slot(
    harness: GenerationHarness,
) -> None:
    """T28-003: cancelling one of three attempts releases only its slot; the
    other two stay RUNNING and a fourth request starts immediately."""
    drafts = _ready_drafts(harness, 4)
    harness.gateway.delay = 0.5
    streams = [harness.orchestrator.run(initial_command(d)) for d in drafts[:3]]
    holders: list[list[GenerationEvent]] = [[], [], []]

    async def consume_into(stream, holder: list[GenerationEvent]) -> None:
        async for event in stream:
            holder.append(event)

    tasks = [
        asyncio.create_task(consume_into(stream, holder))
        for stream, holder in zip(streams, holders)
    ]
    try:
        await _wait_for(
            lambda: all(h and h[0].attempt_id is not None for h in holders)
        )
        attempt_ids = _attempt_ids(holders)
        assert len(set(attempt_ids)) == 3

        # Cancel only the first attempt.
        assert harness.orchestrator.cancel(attempt_ids[0]) is True
        await harness.orchestrator.await_cancelled(attempt_ids[0])
        await tasks[0]

        # Only the cancelled attempt's slot was released.
        assert harness.orchestrator._registry.active_count() == 2
        cancelled_draft = harness.orchestrator.drafts.get(drafts[0].draft_id)
        assert cancelled_draft.status is DraftStatus.READY
        assert cancelled_draft.active_attempt_id is None
        for attempt_id in attempt_ids[1:]:
            persisted = harness.orchestrator.attempts.get(attempt_id)
            assert persisted.status is AttemptStatus.RUNNING
        for draft in drafts[1:3]:
            saved = harness.orchestrator.drafts.get(draft.draft_id)
            assert saved.status is DraftStatus.GENERATING

        # The freed slot admits the fourth request immediately.
        harness.gateway.delay = 0.0
        events4 = await _consume(
            harness.orchestrator.run(initial_command(drafts[3]))
        )
        assert events4[-1].type == "attempt.succeeded"
        assert events4[0].attempt_id not in set(attempt_ids)
        await asyncio.gather(tasks[1], tasks[2])
        assert harness.orchestrator._registry.active_count() == 0
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for stream in streams:
            await stream.aclose()


async def test_failure_releases_only_its_own_slot(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T28-003: a failing attempt (PTS_GEN_UNEXPECTED) releases only its slot;
    the other two generations are unaffected and a fourth request starts."""
    drafts = _ready_drafts(harness, 4)
    harness.gateway.delay = 0.3
    original_analyze = harness.gateway.analyze_dish

    async def failing_analyze(request, *, json_only: bool = False):
        if request.context_text == "concurrent-draft-0":
            raise RuntimeError("fake provider failure")
        return await original_analyze(request, json_only=json_only)

    monkeypatch.setattr(harness.gateway, "analyze_dish", failing_analyze)

    streams = [harness.orchestrator.run(initial_command(d)) for d in drafts[:3]]
    holders: list[list[GenerationEvent]] = [[], [], []]

    async def consume_into(stream, holder: list[GenerationEvent]) -> None:
        async for event in stream:
            holder.append(event)

    tasks = [
        asyncio.create_task(consume_into(stream, holder))
        for stream, holder in zip(streams, holders)
    ]
    try:
        # The failing draft fails fast (before logging an analyze call); the
        # other two are inside their first provider call (0.3s sleep).
        await tasks[0]
        await _wait_for(lambda: harness.gateway.calls.count("analyze") >= 2)

        failed_events = holders[0]
        assert failed_events[-1].type == "attempt.failed"
        assert failed_events[-1].error is not None
        assert failed_events[-1].error.code == "PTS_GEN_UNEXPECTED"
        failed_attempt_id = failed_events[0].attempt_id
        assert failed_attempt_id is not None
        persisted = harness.orchestrator.attempts.get(failed_attempt_id)
        assert persisted.status is AttemptStatus.FAILED
        failed_draft = harness.orchestrator.drafts.get(drafts[0].draft_id)
        assert failed_draft.status is DraftStatus.FAILED
        assert failed_draft.active_attempt_id is None

        # Only the failing attempt's slot was released.
        assert harness.orchestrator._registry.active_count() == 2
        for attempt_id in _attempt_ids(holders)[1:]:
            persisted = harness.orchestrator.attempts.get(attempt_id)
            assert persisted.status is AttemptStatus.RUNNING
        for draft in drafts[1:3]:
            saved = harness.orchestrator.drafts.get(draft.draft_id)
            assert saved.status is DraftStatus.GENERATING

        # The freed slot admits the fourth request immediately.
        harness.gateway.delay = 0.0
        events4 = await _consume(
            harness.orchestrator.run(initial_command(drafts[3]))
        )
        assert events4[-1].type == "attempt.succeeded"
        await asyncio.gather(tasks[1], tasks[2])
        assert harness.orchestrator._registry.active_count() == 0
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for stream in streams:
            await stream.aclose()


async def test_client_disconnect_only_detaches_one_of_three(
    harness: GenerationHarness,
) -> None:
    """T28-004: with three generations running, a client disconnect on one
    stream only detaches that subscriber — the slot stays occupied, the other
    two are unaffected, and the detached generation continues to its terminal
    state."""
    drafts = _ready_drafts(harness, 3)
    harness.gateway.delay = 0.4
    streams = [harness.orchestrator.run(initial_command(d)) for d in drafts]
    holders: list[list[GenerationEvent]] = [[], []]

    async def consume_into(stream, holder: list[GenerationEvent]) -> None:
        async for event in stream:
            holder.append(event)

    tasks = [
        asyncio.create_task(consume_into(stream, holder))
        for stream, holder in zip(streams[1:], holders)
    ]
    try:
        # Start the first stream (the server-owned task begins) so all three
        # are running...
        iterator = streams[0].__aiter__()
        first = await iterator.__anext__()
        assert first.type == "attempt.started"
        attempt0 = first.attempt_id
        assert attempt0 is not None

        # ...then wait until all three are inside the provider.
        await _wait_for(lambda: harness.gateway.calls.count("analyze") >= 3)

        # Detach only the first subscriber (stream already started; the
        # server-owned task is registered and inside the provider).
        await streams[0].aclose()

        # Detach is not a cancel: all three slots stay occupied, the detached
        # draft stays GENERATING and its attempt still owns the slot.
        assert harness.orchestrator._registry.active_count() == 3
        assert attempt0 in {
            owner.attempt_id
            for owner in harness.orchestrator._registry.owners()
        }
        detached = harness.orchestrator.drafts.get(drafts[0].draft_id)
        assert detached.status is DraftStatus.GENERATING
        assert detached.active_attempt_id == attempt0
        persisted0 = harness.orchestrator.attempts.get(attempt0)
        assert persisted0.status is AttemptStatus.RUNNING

        # The detached generation still runs to its terminal state.
        await _wait_for(
            lambda: harness.orchestrator.drafts.get(drafts[0].draft_id).status
            is DraftStatus.REVIEWABLE,
            timeout=15.0,
        )
        final0 = harness.orchestrator.drafts.get(drafts[0].draft_id)
        assert final0.active_attempt_id is None
        assert final0.last_attempt_id == attempt0
        persisted0 = harness.orchestrator.attempts.get(attempt0)
        assert persisted0.status is AttemptStatus.SUCCEEDED

        # The other two finish unaffected with their own distinct attempts.
        await asyncio.gather(*tasks)
        for draft, holder in zip(drafts[1:], holders):
            assert holder[-1].type == "attempt.succeeded"
            assert holder[0].attempt_id != attempt0
            final = harness.orchestrator.drafts.get(draft.draft_id)
            assert final.status is DraftStatus.REVIEWABLE
            assert final.last_attempt_id == holder[0].attempt_id
        assert harness.orchestrator._registry.active_count() == 0
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for stream in streams:
            await stream.aclose()
