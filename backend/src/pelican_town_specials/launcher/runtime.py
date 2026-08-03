from __future__ import annotations

import socket
import time
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from .instance import validate_loopback_url


class SocketLike(Protocol):
    def bind(self, address: tuple[str, int]) -> None: ...

    def getsockname(self) -> tuple[str, int]: ...

    def close(self) -> None: ...


SocketFactory = Callable[[], SocketLike]
OpenUrl = Callable[[str], object]
RequestJson = Callable[[str, float], Mapping[str, Any]]
Clock = Callable[[], float]
Sleep = Callable[[float], None]


@dataclass(slots=True)
class PortReservation:
    port: int
    socket: SocketLike
    _closed: bool = False

    def close(self) -> None:
        if not self._closed:
            self.socket.close()
            self._closed = True


class PortAllocator:
    def __init__(self, socket_factory: SocketFactory | None = None) -> None:
        self._socket_factory = socket_factory or _create_loopback_socket

    def choose(self, preferred: Sequence[int]) -> int:
        reservation = self.reserve(preferred)
        try:
            return reservation.port
        finally:
            reservation.close()

    def reserve(self, preferred: Sequence[int]) -> PortReservation:
        for port in preferred:
            if not 1 <= port <= 65_535:
                raise ValueError("preferred ports must be between 1 and 65535")
            candidate = self._socket_factory()
            try:
                candidate.bind(("127.0.0.1", port))
            except OSError:
                candidate.close()
                continue
            return PortReservation(port=port, socket=candidate)
        return self._reserve_ephemeral()

    def _reserve_ephemeral(self) -> PortReservation:
        candidate = self._socket_factory()
        try:
            candidate.bind(("127.0.0.1", 0))
            _host, port = candidate.getsockname()
            if not 1 <= port <= 65_535:
                raise RuntimeError("operating system returned an invalid local port")
            return PortReservation(port=port, socket=candidate)
        except BaseException:
            candidate.close()
            raise


class BrowserOpener:
    def __init__(self, open_url: OpenUrl | None = None) -> None:
        self._open_url = open_url or webbrowser.open

    def open(self, url: str) -> None:
        validate_loopback_url(url, allow_fragment=True)
        self._open_url(url)


class HealthProbe:
    def __init__(
        self,
        *,
        request_json: RequestJson | None = None,
        monotonic: Clock = time.monotonic,
        sleep: Sleep = time.sleep,
        retry_interval_seconds: float = 0.1,
    ) -> None:
        if retry_interval_seconds <= 0:
            raise ValueError("retry_interval_seconds must be positive")
        self._request_json = request_json or _request_health_json
        self._monotonic = monotonic
        self._sleep = sleep
        self._retry_interval_seconds = retry_interval_seconds

    def wait_until_ready(self, url: str, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        validate_loopback_url(url)
        health_url = _health_url(url)
        deadline = self._monotonic() + timeout_seconds
        while True:
            remaining_seconds = deadline - self._monotonic()
            if remaining_seconds <= 0:
                raise TimeoutError(
                    "local application health check did not become ready",
                )
            try:
                response = self._request_json(health_url, remaining_seconds)
                if response.get("status") == "ok":
                    return
            except (httpx.HTTPError, OSError, TypeError, ValueError):
                pass
            remaining_seconds = deadline - self._monotonic()
            if remaining_seconds <= 0:
                raise TimeoutError("local application health check did not become ready")
            self._sleep(min(self._retry_interval_seconds, remaining_seconds))


def _create_loopback_socket() -> SocketLike:
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def _request_health_json(url: str, timeout_seconds: float) -> Mapping[str, Any]:
    response = httpx.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise TypeError("health response must be a JSON object")
    return payload


def _health_url(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}/api/v1/health"
