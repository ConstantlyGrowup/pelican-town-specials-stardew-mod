"""AttemptRegistry attributable multi-slot registry.

Task 19.1: the process-wide generation slot is attributable — which draft and
attempt holds it — released only by its owning attempt, and able to reconcile
against the persisted attempt so a stale holder never blocks a new generation.

Task 27 (M8): the registry holds up to three generation slots, keyed by attempt
id and isolated per owner. The same draft still owns at most one active attempt
(M8-D04), reconciliation sweeps stale owners per owner, and active_count() never
exceeds the capacity.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from pelican_town_specials.domain.draft import AttemptStatus
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import (
    GenerationOrchestrator,
)

from .conftest import GenerationHarness, initial_command


def _resolver(*statuses: tuple[object, AttemptStatus | None]) -> object:
    mapping = dict(statuses)
    return lambda attempt_id: mapping.get(attempt_id)


def test_max_concurrent_generations_constant_is_three() -> None:
    from pelican_town_specials.generation.attempt_registry import (
        MAX_CONCURRENT_GENERATIONS,
    )

    assert MAX_CONCURRENT_GENERATIONS == 3


def test_reserve_slot_records_owner() -> None:
    registry = AttemptRegistry()
    draft_id = uuid4()
    attempt_id = uuid4()
    assert registry.reserve_slot(draft_id, attempt_id) is True
    owner = registry.owner()
    assert owner is not None
    assert owner.draft_id == draft_id
    assert owner.attempt_id == attempt_id
    assert registry.active_count() == 1
    assert registry.owners() == (owner,)


def test_three_different_drafts_reserve_and_fourth_is_rejected() -> None:
    """T27-001: the first three different drafts each keep their own slot; the
    fourth concurrent generation is rejected and active_count stays at 3."""
    registry = AttemptRegistry()
    held: list[tuple[UUID, UUID]] = []
    for _ in range(3):
        draft_id = uuid4()
        attempt_id = uuid4()
        assert registry.reserve_slot(draft_id, attempt_id) is True
        held.append((draft_id, attempt_id))
    assert registry.active_count() == 3
    assert registry.reserve_slot(uuid4(), uuid4()) is False
    assert registry.active_count() == 3
    assert {owner.draft_id for owner in registry.owners()} == {
        draft_id for draft_id, _ in held
    }


def test_same_draft_second_reservation_is_rejected() -> None:
    """M8-D04: a second attempt for the same draft is busy — the draft already
    has one active attempt and a fresh generation must not stack on top of it."""
    registry = AttemptRegistry()
    draft_id = uuid4()
    assert registry.reserve_slot(draft_id, uuid4()) is True
    assert registry.reserve_slot(draft_id, uuid4()) is False


def test_same_draft_rejected_even_when_resolver_sees_running() -> None:
    """M8-D04 with a resolver: a RUNNING owner is not stale, so the same draft
    cannot use reconciliation to bypass the per-draft uniqueness rule."""
    attempt_a = uuid4()
    registry = AttemptRegistry(
        attempt_status_resolver=_resolver((attempt_a, AttemptStatus.RUNNING))
    )
    draft_id = uuid4()
    assert registry.reserve_slot(draft_id, attempt_a) is True
    assert registry.reserve_slot(draft_id, uuid4()) is False


def test_release_slot_releases_only_matching_attempt() -> None:
    """T27-002/003: release is keyed by attempt id — a stale release does not
    free another owner's slot, and duplicate/late releases are no-ops."""
    registry = AttemptRegistry()
    draft_a = uuid4()
    attempt_a = uuid4()
    draft_b = uuid4()
    attempt_b = uuid4()
    assert registry.reserve_slot(draft_a, attempt_a) is True
    assert registry.reserve_slot(draft_b, attempt_b) is True
    # A stale release (different attempt id) must not free either owner.
    assert registry.release_slot(uuid4()) is False
    assert registry.active_count() == 2
    # The owning attempt's release frees only its own slot.
    assert registry.release_slot(attempt_a) is True
    assert registry.active_count() == 1
    owners = registry.owners()
    assert len(owners) == 1
    assert owners[0].attempt_id == attempt_b
    # Release after release is idempotent.
    assert registry.release_slot(attempt_a) is False


def test_stale_release_does_not_free_new_holder() -> None:
    """Once an owner is released, its late release must not free a new holder."""
    registry = AttemptRegistry()
    draft_a = uuid4()
    attempt_a = uuid4()
    assert registry.reserve_slot(draft_a, attempt_a) is True
    assert registry.release_slot(attempt_a) is True
    draft_b = uuid4()
    attempt_b = uuid4()
    assert registry.reserve_slot(draft_b, attempt_b) is True
    assert registry.release_slot(attempt_a) is False
    assert registry.owner() is not None
    assert registry.owner().attempt_id == attempt_b


def test_freeing_one_slot_allows_new_draft_immediately() -> None:
    """T27-001: after three slots are full, releasing one lets a fresh draft
    reserve right away."""
    registry = AttemptRegistry()
    attempts = [uuid4() for _ in range(3)]
    for draft_id, attempt_id in zip((uuid4() for _ in range(3)), attempts):
        assert registry.reserve_slot(draft_id, attempt_id) is True
    assert registry.reserve_slot(uuid4(), uuid4()) is False
    assert registry.release_slot(attempts[0]) is True
    assert registry.active_count() == 2
    assert registry.reserve_slot(uuid4(), uuid4()) is True
    assert registry.active_count() == 3


def test_occupied_without_resolver_caps_at_three() -> None:
    """Without a resolver the registry cannot self-heal and simply reports busy
    once all three slots are taken."""
    registry = AttemptRegistry()
    for _ in range(3):
        assert registry.reserve_slot(uuid4(), uuid4()) is True
    assert registry.reserve_slot(uuid4(), uuid4()) is False


def test_reconcile_terminal_holder_allows_new_generation() -> None:
    attempt_a = uuid4()
    registry = AttemptRegistry(
        attempt_status_resolver=_resolver((attempt_a, AttemptStatus.SUCCEEDED))
    )
    assert registry.reserve_slot(uuid4(), attempt_a) is True
    # The holder's persisted attempt is terminal: the slot is reclaimed.
    draft_b = uuid4()
    attempt_b = uuid4()
    assert registry.reserve_slot(draft_b, attempt_b) is True
    assert registry.owner() is not None
    assert registry.owner().draft_id == draft_b
    assert registry.owner().attempt_id == attempt_b


def test_reconcile_cancelled_holder_allows_new_generation() -> None:
    attempt_a = uuid4()
    registry = AttemptRegistry(
        attempt_status_resolver=_resolver((attempt_a, AttemptStatus.CANCELLED))
    )
    assert registry.reserve_slot(uuid4(), attempt_a) is True
    assert registry.reserve_slot(uuid4(), uuid4()) is True


def test_reconcile_missing_holder_record_allows_new_generation() -> None:
    attempt_a = uuid4()
    registry = AttemptRegistry(
        attempt_status_resolver=_resolver((attempt_a, None))
    )
    assert registry.reserve_slot(uuid4(), attempt_a) is True
    assert registry.reserve_slot(uuid4(), uuid4()) is True


def test_same_draft_terminal_can_be_retried() -> None:
    """M8-D04 nuance: when the same draft's previous owner is terminal, the
    uniqueness conflict is gone — reconciliation reclaims it and the draft can
    go again."""
    attempt_a = uuid4()
    registry = AttemptRegistry(
        attempt_status_resolver=_resolver((attempt_a, AttemptStatus.SUCCEEDED))
    )
    draft_id = uuid4()
    assert registry.reserve_slot(draft_id, attempt_a) is True
    assert registry.reserve_slot(draft_id, uuid4()) is True


def test_running_owners_are_never_swept() -> None:
    """T27-004: with all three slots owned by RUNNING attempts, a fourth request
    is rejected and the owners are untouched."""
    attempts = [uuid4() for _ in range(3)]
    registry = AttemptRegistry(
        attempt_status_resolver=_resolver(
            (attempts[0], AttemptStatus.RUNNING),
            (attempts[1], AttemptStatus.RUNNING),
            (attempts[2], AttemptStatus.RUNNING),
        )
    )
    for draft_id, attempt_id in zip((uuid4() for _ in range(3)), attempts):
        assert registry.reserve_slot(draft_id, attempt_id) is True
    assert registry.reserve_slot(uuid4(), uuid4()) is False
    assert registry.active_count() == 3
    assert {owner.attempt_id for owner in registry.owners()} == set(attempts)


def test_reconcile_sweeps_only_stale_owners() -> None:
    """T27-004: reconciliation is per owner — a terminal A is reclaimed while
    RUNNING B and C survive, and a fourth slot becomes available."""
    attempt_a = uuid4()
    attempt_b = uuid4()
    attempt_c = uuid4()
    statuses: dict[object, AttemptStatus | None] = {
        attempt_a: AttemptStatus.RUNNING,
        attempt_b: AttemptStatus.RUNNING,
        attempt_c: AttemptStatus.RUNNING,
    }
    registry = AttemptRegistry(
        attempt_status_resolver=lambda attempt_id: statuses.get(attempt_id)
    )
    for draft_id, attempt_id in zip(
        (uuid4() for _ in range(3)),
        (attempt_a, attempt_b, attempt_c),
    ):
        assert registry.reserve_slot(draft_id, attempt_id) is True
    assert registry.active_count() == 3
    # A finishes while B and C are still running.
    statuses[attempt_a] = AttemptStatus.SUCCEEDED
    assert registry.reserve_slot(uuid4(), uuid4()) is True
    remaining = {owner.attempt_id for owner in registry.owners()}
    # A was reclaimed; B and C (RUNNING) survive; the fourth holds the freed slot.
    assert attempt_a not in remaining
    assert attempt_b in remaining
    assert attempt_c in remaining
    assert registry.active_count() == 3


async def test_busy_error_details_carry_owner_draft_id(
    harness: GenerationHarness, ready_draft
) -> None:
    """PTS_GEN_BUSY surfaces which draft currently owns a slot."""
    from pelican_town_specials.domain.errors import AppError

    first = harness.orchestrator.run(initial_command(ready_draft))
    try:
        with pytest.raises(AppError) as excinfo:
            harness.orchestrator.run(initial_command(ready_draft))
        assert excinfo.value.code == "PTS_GEN_BUSY"
        assert excinfo.value.details["draftId"] == str(ready_draft.draft_id)
    finally:
        await first.aclose()


async def test_semaphore_capacity_is_three() -> None:
    """T27-006: the process-level semaphore grants three permits; a fourth
    acquire times out while all three are held."""
    registry = AttemptRegistry()
    semaphore = registry.semaphore()
    acquired = 0
    try:
        # Three permits can be held simultaneously.
        for _ in range(3):
            await asyncio.wait_for(semaphore.acquire(), timeout=0.2)
            acquired += 1
        # A fourth acquire must time out while all three are held.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
    finally:
        for _ in range(acquired):
            semaphore.release()


def test_active_count_never_exceeds_three() -> None:
    """T27-001 invariant: reserve/release a dozen different drafts and assert
    active_count() <= 3 throughout."""
    registry = AttemptRegistry()
    held: list[UUID] = []
    for _ in range(12):
        draft_id = uuid4()
        attempt_id = uuid4()
        if registry.reserve_slot(draft_id, attempt_id):
            held.append(attempt_id)
        else:
            # All three slots are full; free the earliest one to continue.
            assert registry.release_slot(held.pop(0)) is True
        assert registry.active_count() <= 3
    assert registry.active_count() <= 3


async def test_register_and_cancel_are_isolated_by_attempt_id() -> None:
    """register/request_cancel are keyed by attempt id: cancelling one attempt
    leaves the other's task and cancellation state untouched."""
    registry = AttemptRegistry()
    attempt_a = uuid4()
    attempt_b = uuid4()

    async def wait_forever() -> None:
        await asyncio.sleep(30)

    task_a = asyncio.create_task(wait_forever())
    task_b = asyncio.create_task(wait_forever())
    registry.register(attempt_a, task_a)
    registry.register(attempt_b, task_b)
    try:
        assert not registry.is_cancelled(attempt_a)
        assert registry.request_cancel(attempt_a, "first") is True
        assert registry.is_cancelled(attempt_a)
        assert registry.cancellation_reason(attempt_a) == "first"
        # attempt_b is untouched by attempt_a's cancellation.
        assert not registry.is_cancelled(attempt_b)
        assert registry.cancellation_reason(attempt_b) is None
        with pytest.raises(asyncio.CancelledError):
            await task_a
        assert task_a.cancelled()
        assert not task_b.cancelled()
        # An untracked attempt is not fireable (though its reason is recorded).
        assert registry.request_cancel(uuid4(), "ghost") is False
    finally:
        registry.unregister(attempt_a)
        registry.unregister(attempt_b)
        task_a.cancel()
        task_b.cancel()
        await asyncio.gather(task_a, task_b, return_exceptions=True)


def test_reconcile_is_invoked_only_when_resolver_present(
    orchestrator: GenerationOrchestrator,
) -> None:
    """The orchestrator's registry has no resolver in the harness (in-process
    reservation always busy), while the app wires one for persisted attempts."""
    assert orchestrator._registry.attempt_status_resolver is None
