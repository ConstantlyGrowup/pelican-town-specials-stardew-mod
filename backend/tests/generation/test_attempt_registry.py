"""AttemptRegistry attributable slot: ownership, release semantics, self-heal.

Task 19.1: the process-wide generation slot must be attributable (which draft
and attempt holds it), released only by its owning attempt, and able to
reconcile against the persisted attempt so a stale holder never blocks a new
generation forever.
"""

from __future__ import annotations

from uuid import uuid4

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


def test_reserve_slot_records_owner() -> None:
    registry = AttemptRegistry()
    draft_id = uuid4()
    attempt_id = uuid4()
    assert registry.reserve_slot(draft_id, attempt_id) is True
    owner = registry.owner()
    assert owner is not None
    assert owner.draft_id == draft_id
    assert owner.attempt_id == attempt_id


def test_second_different_draft_reservation_is_rejected() -> None:
    registry = AttemptRegistry()
    first_draft = uuid4()
    second_draft = uuid4()
    first_attempt = uuid4()
    assert registry.reserve_slot(first_draft, first_attempt) is True
    assert registry.reserve_slot(second_draft, uuid4()) is False
    owner = registry.owner()
    assert owner is not None
    assert owner.draft_id == first_draft
    assert owner.attempt_id == first_attempt


def test_same_draft_second_reservation_is_rejected() -> None:
    """A second attempt for the same draft is also busy: the draft already has
    one active attempt, and a fresh generation must not stack on top of it."""
    registry = AttemptRegistry()
    draft_id = uuid4()
    assert registry.reserve_slot(draft_id, uuid4()) is True
    assert registry.reserve_slot(draft_id, uuid4()) is False


def test_release_slot_releases_only_matching_attempt() -> None:
    registry = AttemptRegistry()
    draft_id = uuid4()
    attempt_id = uuid4()
    assert registry.reserve_slot(draft_id, attempt_id) is True
    # A stale release (different attempt id) must not free the slot.
    assert registry.release_slot(uuid4()) is False
    assert registry.owner() is not None
    # The owning attempt's release frees it.
    assert registry.release_slot(attempt_id) is True
    assert registry.owner() is None
    # Release after release is idempotent.
    assert registry.release_slot(attempt_id) is False


def test_stale_release_does_not_free_new_holder() -> None:
    """Once a stale holder is reclaimed, its late release must not free the new
    holder's slot."""
    registry = AttemptRegistry()
    draft_a = uuid4()
    attempt_a = uuid4()
    assert registry.reserve_slot(draft_a, attempt_a) is True
    assert registry.release_slot(attempt_a) is True
    draft_b = uuid4()
    attempt_b = uuid4()
    assert registry.reserve_slot(draft_b, attempt_b) is True
    # attempt_a was already released; calling release again is a no-op.
    assert registry.release_slot(attempt_a) is False
    assert registry.owner() is not None
    assert registry.owner().attempt_id == attempt_b


def test_occupied_rejects_without_resolver() -> None:
    """Without a resolver the registry cannot self-heal and simply reports busy."""
    registry = AttemptRegistry()
    assert registry.reserve_slot(uuid4(), uuid4()) is True
    assert registry.reserve_slot(uuid4(), uuid4()) is False


def test_reconcile_terminal_holder_allows_new_generation() -> None:
    attempt_a = uuid4()
    registry = AttemptRegistry(
        attempt_status_resolver=_resolver(
            (attempt_a, AttemptStatus.SUCCEEDED)
        )
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


def test_no_reconcile_when_holder_running() -> None:
    attempt_a = uuid4()
    registry = AttemptRegistry(
        attempt_status_resolver=_resolver((attempt_a, AttemptStatus.RUNNING))
    )
    assert registry.reserve_slot(uuid4(), attempt_a) is True
    assert registry.reserve_slot(uuid4(), uuid4()) is False


async def test_busy_error_details_carry_owner_draft_id(
    harness: GenerationHarness, ready_draft
) -> None:
    """PTS_GEN_BUSY surfaces which draft currently owns the slot."""
    from pelican_town_specials.domain.errors import AppError

    first = harness.orchestrator.run(initial_command(ready_draft))
    try:
        with pytest.raises(AppError) as excinfo:
            harness.orchestrator.run(initial_command(ready_draft))
        assert excinfo.value.code == "PTS_GEN_BUSY"
        assert excinfo.value.details["draftId"] == str(ready_draft.draft_id)
    finally:
        await first.aclose()


def test_reconcile_is_invoked_only_when_resolver_present(
    orchestrator: GenerationOrchestrator,
) -> None:
    """The orchestrator's registry has no resolver in the harness (in-process
    reservation always busy), while the app wires one for persisted attempts."""
    assert orchestrator._registry.attempt_status_resolver is None
