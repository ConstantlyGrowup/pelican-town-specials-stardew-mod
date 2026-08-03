from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response

from pelican_town_specials.api.security import (
    Clock,
    SessionCredentials,
    require_mutation_security,
)

router = APIRouter(prefix="/app")

_IDLE_TIMEOUT_SECONDS = 600.0


class ActivityTracker:
    def __init__(
        self,
        *,
        clock: Clock = monotonic,
        shutdown_callback: Callable[[], None] | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._clock = clock
        self._shutdown_callback = shutdown_callback
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._poll_interval_seconds = poll_interval_seconds
        self._lock = Lock()
        self._last_activity_at = clock()
        self._is_busy = False
        self.shutdown_requested = False

    def touch(self, session_id: str, now: float | None = None) -> None:
        del session_id
        with self._lock:
            self._last_activity_at = self._current_time(now)

    def set_busy(self, is_busy: bool) -> None:
        with self._lock:
            self._is_busy = is_busy

    def should_shutdown(self, now: float | None = None) -> bool:
        with self._lock:
            idle_for = self._current_time(now) - self._last_activity_at
            return not self._is_busy and idle_for >= _IDLE_TIMEOUT_SECONDS

    def request_shutdown(self) -> None:
        callback: Callable[[], None] | None
        with self._lock:
            if self.shutdown_requested:
                return
            self.shutdown_requested = True
            callback = self._shutdown_callback
        if callback is not None:
            callback()

    def _current_time(self, now: float | None) -> float:
        return self._clock() if now is None else now
    @property
    def has_shutdown_callback(self) -> bool:
        return self._shutdown_callback is not None

    @property
    def poll_interval_seconds(self) -> float:
        return self._poll_interval_seconds



def _activity_tracker(request: Request) -> ActivityTracker:
    return cast(ActivityTracker, request.app.state.activity_tracker)


@router.post("/heartbeat", status_code=204)
def heartbeat(
    request: Request,
    credentials: Annotated[SessionCredentials, Depends(require_mutation_security)],
) -> Response:
    _activity_tracker(request).touch(credentials.session_id)
    return Response(status_code=204)


@router.post("/shutdown", status_code=202)
def shutdown(
    request: Request,
    _: Annotated[SessionCredentials, Depends(require_mutation_security)],
) -> Response:
    _activity_tracker(request).request_shutdown()
    return Response(status_code=202)
