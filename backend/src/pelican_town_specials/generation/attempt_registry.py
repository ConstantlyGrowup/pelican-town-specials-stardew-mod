"""Process-wide generation slot and cancellation registry.

Task 19.1: the slot is attributable — it records which draft and which attempt
holds it, is released only by its owning attempt, and can reconcile against the
persisted attempt so a stale holder never blocks a new generation forever.

Task 27 (M8): the single attributable slot becomes a small set of up to
``MAX_CONCURRENT_GENERATIONS`` slots keyed by attempt id. Owners are isolated
from each other, the same draft still owns at most one active attempt, and
reconciliation sweeps stale owners per owner while running owners are preserved.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import UUID

from pelican_town_specials.domain.draft import AttemptStatus

#: Terminal attempt statuses: the generation that owned the slot is finished,
#: so an otherwise-stale holder can be reclaimed.
_TERMINAL_ATTEMPT_STATUSES = frozenset(
    {
        AttemptStatus.SUCCEEDED,
        AttemptStatus.FAILED,
        AttemptStatus.CANCELLED,
        AttemptStatus.INTERRUPTED,
    }
)

#: Maximum concurrent generations in this process (M8: three-way concurrency).
MAX_CONCURRENT_GENERATIONS = 3


@dataclass(frozen=True)
class SlotOwner:
    """The draft and attempt that currently hold a generation slot."""

    draft_id: UUID
    attempt_id: UUID
    started_at: float


AttemptStatusResolver = Callable[[UUID], AttemptStatus | None]


def _is_stale_owner(
    resolver: AttemptStatusResolver, owner: SlotOwner
) -> bool:
    """A persisted attempt that is terminal, or has no record at all, is stale."""
    status = resolver(owner.attempt_id)
    return status is None or status in _TERMINAL_ATTEMPT_STATUSES


class AttemptRegistry:
    """Up to ``MAX_CONCURRENT_GENERATIONS`` attributable generation slots.

    Each slot is attributable: ``reserve_slot`` records the draft and attempt
    that own it, ``owner()`` answers who holds the first slot (and ``owners()``
    all of them), and ``release_slot`` only frees a slot for the matching
    attempt so a stale release never frees another owner's slot. When an
    ``attempt_status_resolver`` is wired in, a reservation first reconciles
    every occupied slot against the holder's persisted attempt: terminal or
    missing records are reclaimed, running attempts are never swept, and only
    then are same-draft uniqueness and capacity checked.
    """

    def __init__(
        self,
        *,
        attempt_status_resolver: AttemptStatusResolver | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._owners: dict[UUID, SlotOwner] = {}
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)
        self._cancellations: dict[UUID, str] = {}
        self._tasks: dict[UUID, asyncio.Task[Any]] = {}
        self.attempt_status_resolver = attempt_status_resolver

    def _reconcile_stale_owners(self) -> None:
        """Sweep owners whose persisted attempt is terminal or missing.

        Must be called with ``self._lock`` held. Owners still RUNNING (or for
        which the resolver reports no terminal/missing signal) are preserved.
        """
        resolver = self.attempt_status_resolver
        if resolver is None:
            return
        stale = [
            attempt_id
            for attempt_id, owner in self._owners.items()
            if _is_stale_owner(resolver, owner)
        ]
        for attempt_id in stale:
            del self._owners[attempt_id]

    def reserve_slot(self, draft_id: UUID, attempt_id: UUID) -> bool:
        """Try to occupy one of the generation slots for ``draft_id``.

        Returns False when the registry is genuinely busy: the draft already
        owns a slot, or all ``MAX_CONCURRENT_GENERATIONS`` slots are taken.
        When an ``attempt_status_resolver`` is configured, stale owners are
        reconciled first (self-healing): an owner whose persisted attempt is
        terminal or missing is reclaimed and this reservation proceeds.
        """
        with self._lock:
            self._reconcile_stale_owners()
            if any(
                owner.draft_id == draft_id for owner in self._owners.values()
            ):
                return False
            if len(self._owners) >= MAX_CONCURRENT_GENERATIONS:
                return False
            self._owners[attempt_id] = SlotOwner(
                draft_id=draft_id,
                attempt_id=attempt_id,
                started_at=monotonic(),
            )
            return True

    def release_slot(self, attempt_id: UUID) -> bool:
        """Release the slot only if it is still held by ``attempt_id``.

        Returns True when this attempt actually released its slot. A stale
        release (from an attempt that no longer owns a slot) is a no-op so a
        late cleanup can never free a new holder's slot.
        """
        with self._lock:
            if attempt_id in self._owners:
                del self._owners[attempt_id]
                return True
            return False

    def owner(self) -> SlotOwner | None:
        """Return the first slot owner (or None when no slot is held).

        Compatibility entry for the orchestrator's busy-error construction.
        """
        with self._lock:
            if not self._owners:
                return None
            return next(iter(self._owners.values()))

    def owners(self) -> tuple[SlotOwner, ...]:
        """Return a snapshot of all current slot owners."""
        with self._lock:
            return tuple(self._owners.values())

    def active_count(self) -> int:
        with self._lock:
            return len(self._owners)

    def semaphore(self) -> asyncio.Semaphore:
        return self._semaphore

    def register(
        self, attempt_id: UUID, task: asyncio.Task[Any] | None
    ) -> None:
        if task is not None:
            self._tasks[attempt_id] = task

    def unregister(self, attempt_id: UUID) -> None:
        self._tasks.pop(attempt_id, None)
        self._cancellations.pop(attempt_id, None)

    def request_cancel(self, attempt_id: UUID, reason: str) -> bool:
        self._cancellations[attempt_id] = reason
        task = self._tasks.get(attempt_id)
        if task is not None:
            task.cancel()
        return task is not None

    async def await_task(
        self, attempt_id: UUID, timeout: float = 5.0
    ) -> None:
        """Wait for a tracked attempt's task to finish (rollback complete).

        Best-effort: returns without raising when the task is absent or
        already finished, on timeout, or when the waiter itself is cancelled.
        The cancel route uses this so a 202 is only returned after the draft
        rollback and slot release have completed.
        """
        task = self._tasks.get(attempt_id)
        if task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout)
        except (TimeoutError, asyncio.CancelledError):
            pass

    def is_cancelled(self, attempt_id: UUID) -> bool:
        return attempt_id in self._cancellations

    def cancellation_reason(self, attempt_id: UUID) -> str | None:
        return self._cancellations.get(attempt_id)
