"""Application boundary for optional, fail-open telemetry."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from datetime import date, datetime
from typing import Protocol

from pelican_town_specials.domain.telemetry import TelemetryEvent
from pelican_town_specials.persistence.telemetry_state import TelemetryStateStore


class TelemetryRecorder(Protocol):
    """The only interface business code needs for telemetry."""

    @property
    def enabled(self) -> bool: ...

    def record(self, event: TelemetryEvent) -> None: ...

    async def start(self) -> None: ...

    async def shutdown(self, *, timeout_seconds: float = 1.0) -> None: ...


class NoopTelemetryRecorder:
    """A zero-I/O recorder used outside a fully configured Release build."""

    enabled = False

    def record(self, _event: TelemetryEvent) -> None:
        return None

    async def start(self) -> None:
        return None

    async def shutdown(self, *, timeout_seconds: float = 1.0) -> None:
        return None

    # Lifecycle aliases make the adapter convenient to embed in hosts that
    # call these operations by their longer names.
    startup = start
    close = shutdown


class TelemetryService:
    """Coordinates daily-open state and isolates the recorder from the app."""

    def __init__(
        self,
        recorder: TelemetryRecorder,
        state_store: TelemetryStateStore,
        *,
        clock: Callable[[], date | datetime] | None = None,
    ) -> None:
        self._recorder = recorder
        self._state_store = state_store
        self._clock = clock or _local_date
        self._started = False

    @property
    def recorder(self) -> TelemetryRecorder:
        return self._recorder

    @property
    def state_store(self) -> TelemetryStateStore:
        return self._state_store

    @property
    def enabled(self) -> bool:
        return bool(getattr(self._recorder, "enabled", True))

    def record(self, event: TelemetryEvent) -> None:
        """Best-effort handoff; collector defects never reach business code."""

        try:
            self._recorder.record(event)
        except Exception:  # noqa: BLE001 - telemetry is explicitly fail-open
            return

    def record_daily_open(self, today: date | datetime | None = None) -> bool:
        """Claim and enqueue one app-open event for an enabled recorder."""

        if not self.enabled:
            return False
        current_date = _as_date(today if today is not None else self._clock())
        try:
            state = self._state_store.ensure_state()
            if state is None:
                return False
            if not self._state_store.claim_daily_open(current_date):
                return False
            self.record(TelemetryEvent.app_opened())
            return True
        except Exception:  # noqa: BLE001 - state failures are fail-open
            return False

    async def startup(self) -> None:
        """Start the dispatcher and record daily-open without blocking startup."""

        try:
            await _invoke_maybe_async(self._recorder, "start")
        except Exception:  # noqa: BLE001 - telemetry must not block app startup
            return

        # Creating the identity is harmless in no-op mode, while the date
        # claim itself is deliberately gated by ``enabled`` above.
        try:
            self._state_store.ensure_state()
        except Exception:  # noqa: BLE001 - telemetry state is fail-open
            return
        if self.enabled:
            self.record_daily_open()
        self._started = True

    async def shutdown(self, *, timeout_seconds: float = 1.0) -> None:
        """Give the sink at most the frozen one-second best-effort flush."""

        bounded_timeout = min(max(timeout_seconds, 0.0), 1.0)
        try:
            await asyncio.wait_for(
                _invoke_maybe_async(
                    self._recorder,
                    "shutdown",
                    timeout_seconds=bounded_timeout,
                ),
                timeout=bounded_timeout,
            )
        except Exception:  # noqa: BLE001 - shutdown must not affect the host
            return
        finally:
            self._started = False

    close = shutdown


async def _invoke_maybe_async(
    target: object,
    method_name: str,
    **kwargs: object,
) -> None:
    method = getattr(target, method_name, None)
    if method is None:
        return
    try:
        result = method(**kwargs)
    except TypeError:
        # Minimal test doubles commonly expose shutdown() without the optional
        # timeout keyword.  Keep that injection seam without weakening the
        # production recorder's bound.
        if kwargs:
            result = method()
        else:
            raise
    if inspect.isawaitable(result):
        await result


def _local_date() -> date:
    return datetime.now().astimezone().date()


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.astimezone().date() if value.tzinfo else value.date()
    return value


# Friendly vocabulary aliases for host wiring.
TelemetryLifecycle = TelemetryService
TelemetryApplicationService = TelemetryService


__all__ = [
    "NoopTelemetryRecorder",
    "TelemetryApplicationService",
    "TelemetryLifecycle",
    "TelemetryRecorder",
    "TelemetryService",
]
