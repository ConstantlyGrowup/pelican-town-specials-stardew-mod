from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Self
from urllib.parse import SplitResult, urlsplit

import portalocker
from pydantic import Field, ValidationError, field_validator, model_validator

from pelican_town_specials.domain.common import StrictModel, ensure_utc
from pelican_town_specials.persistence.atomic import atomic_write_json

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


class RuntimeRecord(StrictModel):
    pid: int = Field(gt=0)
    port: int = Field(ge=1, le=65_535)
    url: str = Field(min_length=1)
    started_at: datetime

    @field_validator("started_at", mode="after")
    @classmethod
    def _validate_started_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def _validate_loopback_url(self) -> RuntimeRecord:
        parsed = _parse_loopback_url(self.url, allow_fragment=False)
        if parsed.port != self.port:
            raise ValueError("runtime URL port must match runtime record port")
        if parsed.path not in {"", "/"} or parsed.query:
            raise ValueError("runtime URL must point to the local application root")
        return self


class InstanceLock:
    """A non-blocking process-wide lock that never deletes its lock file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock: portalocker.Lock | None = None

    def acquire(self) -> bool:
        if self._lock is not None:
            return True
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = portalocker.Lock(
            self._path,
            mode="a+",
            timeout=0,
            fail_when_locked=True,
        )
        try:
            lock.acquire()
        except portalocker.exceptions.LockException:
            return False
        self._lock = lock
        return True

    def release(self) -> None:
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def __enter__(self) -> Self:
        if not self.acquire():
            raise RuntimeError("another Pelican Town Specials launcher is active")
        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        self.release()


class RuntimeRecordStore:
    """Stores non-sensitive launcher state using atomic writes and a short lock."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._mutation_lock_path = path.with_suffix(f"{path.suffix}.lock")

    def read(self) -> RuntimeRecord | None:
        try:
            return RuntimeRecord.model_validate_json(
                self._path.read_text(encoding="utf-8"),
            )
        except (OSError, ValidationError, ValueError):
            return None

    def write(self, record: RuntimeRecord) -> None:
        with self._locked():
            atomic_write_json(
                self._path,
                record.model_dump(mode="json", by_alias=True),
            )

    def clear(self) -> None:
        """Remove a stale record after the caller has acquired the app instance lock."""
        with self._locked():
            self._path.unlink(missing_ok=True)

    def clear_if_matches(self, record: RuntimeRecord) -> bool:
        """Remove the record only when it still identifies this launcher instance."""
        with self._locked():
            current = self.read()
            if current != record:
                return False
            self._path.unlink(missing_ok=True)
            return True

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._mutation_lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = portalocker.Lock(
            self._mutation_lock_path,
            mode="a+",
            timeout=5,
        )
        with lock:
            yield


def validate_loopback_url(url: str, *, allow_fragment: bool = False) -> None:
    _parse_loopback_url(url, allow_fragment=allow_fragment)


def _parse_loopback_url(url: str, *, allow_fragment: bool) -> SplitResult:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL must be a valid loopback HTTP URL") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in _LOOPBACK_HOSTS
        or port is None
        or not 1 <= port <= 65_535
        or parsed.username is not None
        or parsed.password is not None
        or (parsed.fragment and not allow_fragment)
    ):
        raise ValueError("URL must be a valid loopback HTTP URL")
    return parsed
