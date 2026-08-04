"""Process-wide generation slot and cancellation registry."""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from uuid import UUID


class AttemptRegistry:
    """One generation slot per process, with per-attempt cancellation state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._occupied = False
        self._semaphore = asyncio.Semaphore(1)
        self._cancellations: dict[UUID, str] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    def reserve_slot(self) -> bool:
        with self._lock:
            if self._occupied:
                return False
            self._occupied = True
            return True

    def release_slot(self) -> None:
        with self._lock:
            self._occupied = False

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

    def is_cancelled(self, attempt_id: UUID) -> bool:
        return attempt_id in self._cancellations

    def cancellation_reason(self, attempt_id: UUID) -> str | None:
        return self._cancellations.get(attempt_id)
