from __future__ import annotations

from typing import Any

import pytest

from pelican_town_specials.launcher.runtime import (
    BrowserOpener,
    HealthProbe,
    PortAllocator,
)


class _FakeSocket:
    def __init__(self, *, occupied: bool = False, assigned_port: int = 0) -> None:
        self.occupied = occupied
        self.assigned_port = assigned_port
        self.bound_address: tuple[str, int] | None = None
        self.closed = False

    def bind(self, address: tuple[str, int]) -> None:
        self.bound_address = address
        if self.occupied:
            raise OSError("address already in use")

    def getsockname(self) -> tuple[str, int]:
        assert self.bound_address is not None
        return (self.bound_address[0], self.assigned_port or self.bound_address[1])

    def close(self) -> None:
        self.closed = True


def test_port_allocator_skips_occupied_preferred_port() -> None:
    sockets = iter(
        [
            _FakeSocket(occupied=True),
            _FakeSocket(assigned_port=43128),
        ]
    )
    allocator = PortAllocator(socket_factory=lambda: next(sockets))

    assert allocator.choose([43127, 43128]) == 43128


def test_port_allocator_falls_back_to_os_assigned_port() -> None:
    sockets = iter(
        [
            _FakeSocket(occupied=True),
            _FakeSocket(occupied=True),
            _FakeSocket(assigned_port=51234),
        ]
    )
    allocator = PortAllocator(socket_factory=lambda: next(sockets))

    assert allocator.choose([43127, 43128]) == 51234


def test_browser_opener_delegates_to_injected_callable() -> None:
    opened: list[str] = []
    opener = BrowserOpener(open_url=opened.append)

    opener.open("http://127.0.0.1:43127/#launch=not-persisted")

    assert opened == ["http://127.0.0.1:43127/#launch=not-persisted"]


def test_browser_opener_rejects_port_zero() -> None:
    opened: list[str] = []

    with pytest.raises(ValueError, match="loopback HTTP URL"):
        BrowserOpener(open_url=opened.append).open(
            "http://127.0.0.1:0/#launch=not-persisted",
        )

    assert opened == []


def test_health_probe_retries_injected_request_until_status_is_ok() -> None:
    responses = iter([{"status": "starting"}, {"status": "ok"}])
    requested_urls: list[str] = []
    requested_timeouts: list[float] = []
    sleeps: list[float] = []

    def request_json(url: str, timeout_seconds: float) -> dict[str, Any]:
        requested_urls.append(url)
        requested_timeouts.append(timeout_seconds)
        return next(responses)

    probe = HealthProbe(
        request_json=request_json,
        sleep=sleeps.append,
        monotonic=_IncrementingClock(),
        retry_interval_seconds=0.1,
    )

    probe.wait_until_ready("http://127.0.0.1:43127/", timeout_seconds=1.0)

    assert requested_urls == [
        "http://127.0.0.1:43127/api/v1/health",
        "http://127.0.0.1:43127/api/v1/health",
    ]
    assert all(timeout > 0 for timeout in requested_timeouts)
    assert sleeps == [0.1]


def test_health_probe_rejects_port_zero_before_request() -> None:
    requested_urls: list[str] = []

    def request_json(url: str, _timeout_seconds: float) -> dict[str, Any]:
        requested_urls.append(url)
        return {"status": "ok"}

    with pytest.raises(ValueError, match="loopback HTTP URL"):
        HealthProbe(request_json=request_json).wait_until_ready(
            "http://127.0.0.1:0/",
            timeout_seconds=1.0,
        )

    assert requested_urls == []


def test_health_probe_honors_total_timeout_for_request_and_sleep() -> None:
    clock = _ManualClock()
    requested_timeouts: list[float] = []
    sleeps: list[float] = []

    def request_json(_url: str, timeout_seconds: float) -> dict[str, Any]:
        requested_timeouts.append(timeout_seconds)
        clock.advance(0.09)
        return {"status": "starting"}

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    with pytest.raises(TimeoutError):
        HealthProbe(
            request_json=request_json,
            monotonic=clock,
            sleep=sleep,
            retry_interval_seconds=1.0,
        ).wait_until_ready("http://127.0.0.1:43127/", timeout_seconds=0.1)

    assert requested_timeouts == [pytest.approx(0.1)]
    assert sleeps == [pytest.approx(0.01)]


class _IncrementingClock:
    def __init__(self) -> None:
        self._current = 0.0

    def __call__(self) -> float:
        current = self._current
        self._current += 0.1
        return current


class _ManualClock:
    def __init__(self) -> None:
        self.current = 0.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


def test_port_allocator_reserves_socket_until_caller_closes() -> None:
    candidate = _FakeSocket(assigned_port=43127)
    reservation = PortAllocator(socket_factory=lambda: candidate).reserve([43127])

    assert reservation.port == 43127
    assert candidate.closed is False

    reservation.close()

    assert candidate.closed is True
