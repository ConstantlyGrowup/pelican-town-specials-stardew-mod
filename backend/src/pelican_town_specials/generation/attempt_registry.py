"""Process-wide generation slot and cancellation registry.

Task 19.1: the slot is attributable — it records which draft and which attempt
holds it, is released only by its owning attempt, and can reconcile against the
persisted attempt so a stale holder never blocks a new generation forever.
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


@dataclass(frozen=True)
class SlotOwner:
    """The draft and attempt that currently hold the generation slot."""

    draft_id: UUID
    attempt_id: UUID
    started_at: float


AttemptStatusResolver = Callable[[UUID], AttemptStatus | None]


class AttemptRegistry:
    """One generation slot per process, with per-attempt cancellation state.

    The slot is attributable: ``reserve_slot`` records the draft and attempt
    that own it, ``owner()`` answers who holds it, and ``release_slot`` only
    frees it for the matching attempt so a stale release never frees a new
    holder's slot. When an ``attempt_status_resolver`` is wired in, an occupied
    reservation first reconciles against the holder's persisted attempt: if it
    is terminal or its record is missing, the stale holder is reclaimed and the
    new generation proceeds.
    """

    def __init__(
        self,
        *,
        attempt_status_resolver: AttemptStatusResolver | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._holder: SlotOwner | None = None
        self._semaphore = asyncio.Semaphore(1)
        self._cancellations: dict[UUID, str] = {}
        self._tasks: dict[UUID, asyncio.Task[Any]] = {}
        self.attempt_status_resolver = attempt_status_resolver

    def reserve_slot(self, draft_id: UUID, attempt_id: UUID) -> bool:
        """Try to occupy the single generation slot for ``draft_id``.

        Returns False when the slot is genuinely busy. When an
        ``attempt_status_resolver`` is configured, the holder's persisted
        attempt is reconciled first: if it is terminal or missing, the stale
        holder is reclaimed and this reservation succeeds (self-healing).
        """
        with self._lock:
            if self._holder is None:
                self._holder = SlotOwner(
                    draft_id=draft_id,
                    attempt_id=attempt_id,
                    started_at=monotonic(),
                )
                return True
            if self.attempt_status_resolver is not None:
                status = self.attempt_status_resolver(self._holder.attempt_id)
                if status is None or status in _TERMINAL_ATTEMPT_STATUSES:
                    self._holder = SlotOwner(
                        draft_id=draft_id,
                        attempt_id=attempt_id,
                        started_at=monotonic(),
                    )
                    return True
            return False

    def release_slot(self, attempt_id: UUID) -> bool:
        """Release the slot only if it is still held by ``attempt_id``.

        Returns True when this attempt actually released the slot. A stale
        release (from an attempt that no longer owns the slot) is a no-op so a
        late cleanup can never free a new holder's slot.
        """
        with self._lock:
            if self._holder is not None and self._holder.attempt_id == attempt_id:
                self._holder = None
                return True
            return False

    def owner(self) -> SlotOwner | None:
        with self._lock:
            return self._holder

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
