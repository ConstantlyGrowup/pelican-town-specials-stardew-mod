from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import Request

from pelican_town_specials.domain.errors import AppError

Clock = Callable[[], float]

_LAUNCH_TOKEN_TTL_SECONDS = 60.0
_SESSION_TTL_SECONDS = 600.0
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    allowed_hosts: frozenset[str] = frozenset({"127.0.0.1", "localhost"})
    expected_port: int | None = 8000
    allowed_origins: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class SessionCredentials:
    session_id: str
    csrf_token: str


@dataclass(slots=True)
class _SessionRecord:
    credentials: SessionCredentials
    last_touched_at: float


class LaunchTokenStore:
    def __init__(self, clock: Clock = monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._issued_at: dict[str, float] = {}

    def issue(self, now: float | None = None) -> str:
        token = secrets.token_urlsafe(32)
        issued_at = self._current_time(now)
        with self._lock:
            self._prune_expired_locked(issued_at)
            self._issued_at[token] = issued_at
        return token

    def consume(self, token: str, now: float | None = None) -> bool:
        current_time = self._current_time(now)
        with self._lock:
            self._prune_expired_locked(current_time)
            issued_at = self._issued_at.pop(token, None)
        return issued_at is not None

    def _prune_expired_locked(self, current_time: float) -> None:
        expired_tokens = [
            token
            for token, issued_at in self._issued_at.items()
            if current_time - issued_at > _LAUNCH_TOKEN_TTL_SECONDS
        ]
        for token in expired_tokens:
            self._issued_at.pop(token, None)

    def _current_time(self, now: float | None) -> float:
        return self._clock() if now is None else now


class SessionStore:
    def __init__(self, clock: Clock = monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._records: dict[str, _SessionRecord] = {}

    def create(self, now: float | None = None) -> SessionCredentials:
        credentials = SessionCredentials(
            session_id=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
        )
        with self._lock:
            self._records[credentials.session_id] = _SessionRecord(
                credentials=credentials,
                last_touched_at=self._current_time(now),
            )
        return credentials

    def validate(
        self,
        session_id: str,
        now: float | None = None,
    ) -> SessionCredentials | None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            if self._current_time(now) - record.last_touched_at > _SESSION_TTL_SECONDS:
                self._records.pop(session_id, None)
                return None
            return record.credentials

    def touch(self, session_id: str, now: float | None = None) -> None:
        with self._lock:
            record = self._records.get(session_id)
            if record is not None:
                record.last_touched_at = self._current_time(now)

    def _current_time(self, now: float | None) -> float:
        return self._clock() if now is None else now


class SecurityState:
    def __init__(
        self,
        *,
        config: SecurityConfig | None = None,
        clock: Clock = monotonic,
    ) -> None:
        self.config = config or SecurityConfig()
        self.clock = clock
        self.launch_tokens = LaunchTokenStore(clock)
        self.sessions = SessionStore(clock)

    def issue_launch_token(self) -> str:
        return self.launch_tokens.issue()

    def bootstrap(self, launch_token: str) -> SessionCredentials:
        if not self.launch_tokens.consume(launch_token):
            raise _auth_error("PTS_AUTH_LAUNCH_INVALID", 401)
        return self.sessions.create()

    def require_allowed_host(self, host_header: str | None) -> str:
        host, _ = self._validated_host(host_header)
        return host

    def require_allowed_origin(self, origin: str | None, host_header: str | None) -> None:
        if origin is None:
            raise _auth_error("PTS_AUTH_ORIGIN_INVALID", 403)
        host, host_port = self._validated_host(host_header)
        origin_port = self.config.expected_port or host_port
        expected_origin = f"http://{host}"
        if origin_port is not None:
            expected_origin = f"{expected_origin}:{origin_port}"
        if origin != expected_origin:
            raise _auth_error("PTS_AUTH_ORIGIN_INVALID", 403)
        if (
            self.config.allowed_origins is not None
            and origin not in self.config.allowed_origins
        ):
            raise _auth_error("PTS_AUTH_ORIGIN_INVALID", 403)

    def _validated_host(self, host_header: str | None) -> tuple[str, int | None]:
        host, port = _parse_host_header(host_header)
        if host not in self.config.allowed_hosts:
            raise _auth_error("PTS_AUTH_HOST_INVALID", 403)
        if self.config.expected_port is not None and port != self.config.expected_port:
            raise _auth_error("PTS_AUTH_HOST_INVALID", 403)
        return host, port

    def require_session(self, session_id: str | None) -> SessionCredentials:
        if session_id is None:
            raise _auth_error("PTS_AUTH_SESSION_REQUIRED", 401)
        credentials = self.sessions.validate(session_id)
        if credentials is None:
            raise _auth_error("PTS_AUTH_SESSION_REQUIRED", 401)
        return credentials

    def touch_session(self, session_id: str) -> None:
        self.sessions.touch(session_id)


def require_session(request: Request) -> SessionCredentials:
    security = _security_state(request)
    security.require_allowed_host(request.headers.get("host"))
    credentials = security.require_session(request.cookies.get("PTS_SESSION"))
    security.touch_session(credentials.session_id)
    request.state.session_credentials = credentials
    return credentials


def require_mutation_security(request: Request) -> SessionCredentials:
    security = _security_state(request)
    host_header = request.headers.get("host")
    security.require_allowed_host(host_header)
    security.require_allowed_origin(request.headers.get("origin"), host_header)
    credentials = security.require_session(request.cookies.get("PTS_SESSION"))
    csrf_token = request.headers.get("X-PTS-CSRF")
    if csrf_token is None or not secrets.compare_digest(
        csrf_token,
        credentials.csrf_token,
    ):
        raise _auth_error("PTS_AUTH_CSRF_INVALID", 403)
    security.touch_session(credentials.session_id)
    request.state.session_credentials = credentials
    return credentials


def is_safe_method(method: str) -> bool:
    return method.upper() in _SAFE_METHODS


def _security_state(request: Request) -> SecurityState:
    return request.app.state.security  # type: ignore[no-any-return]


def _parse_host_header(host_header: str | None) -> tuple[str | None, int | None]:
    if host_header is None:
        return None, None
    host, separator, port_text = host_header.lower().partition(":")
    if not host:
        return None, None
    if not separator:
        return host, None
    if not port_text.isdecimal():
        return None, None
    port = int(port_text)
    if not 1 <= port <= 65_535:
        return None, None
    return host, port


def _auth_error(code: str, http_status: int) -> AppError:
    messages = {
        "PTS_AUTH_CSRF_INVALID": "本地会话校验失败，请重新打开应用。",
        "PTS_AUTH_HOST_INVALID": "本地应用地址校验失败，请重新打开应用。",
        "PTS_AUTH_LAUNCH_INVALID": "启动链接已失效，请重新打开应用。",
        "PTS_AUTH_ORIGIN_INVALID": "本地请求来源校验失败，请重新打开应用。",
        "PTS_AUTH_SESSION_REQUIRED": "需要有效的本地应用会话，请重新打开应用。",
    }
    return AppError(
        code=code,
        message=messages[code],
        http_status=http_status,
        details={},
        retryable=False,
    )
