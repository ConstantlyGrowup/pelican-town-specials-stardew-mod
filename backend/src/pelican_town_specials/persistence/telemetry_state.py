"""Fail-open persistence for the anonymous telemetry installation identity."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import portalocker
from pydantic import Field, field_validator

from pelican_town_specials.domain.common import StrictModel, ensure_uuid4
from pelican_town_specials.persistence.atomic import atomic_write_json

TELEMETRY_STATE_SCHEMA_VERSION = 1


class TelemetryState(StrictModel):
    """The only state persisted by Task 37.

    The string validators are intentionally limited to the JSON boundary: a
    state file naturally stores UUIDs and dates as strings, while in-process
    callers still receive typed values.
    """

    schema_version: Literal[1] = Field(
        default=cast(Literal[1], TELEMETRY_STATE_SCHEMA_VERSION),
        alias="schemaVersion",
    )
    installation_id: UUID = Field(alias="installationId")
    last_daily_open_date: date | None = Field(
        default=None,
        alias="lastDailyOpenDate",
    )

    @field_validator("installation_id", mode="before")
    @classmethod
    def _parse_installation_id(cls, value: Any) -> UUID:
        if isinstance(value, str):
            value = UUID(value)
        if not isinstance(value, UUID):
            raise TypeError("installationId must be a UUID")
        return ensure_uuid4(value)

    @field_validator("last_daily_open_date", mode="before")
    @classmethod
    def _parse_date(cls, value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise TypeError("lastDailyOpenDate must be an ISO date")


class TelemetryStateStore:
    """Atomically create and update telemetry state under a sidecar lock.

    The lock file contains no event data and is never removed.  Any malformed
    state, unsupported schema, lock failure, or filesystem failure returns the
    safe disabled result rather than affecting application startup.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(f"{path.suffix}.lock")

    def read(self) -> TelemetryState | None:
        try:
            with self._locked():
                return self._read_unlocked()
        except (OSError, portalocker.exceptions.LockException, ValueError, TypeError):
            return None

    def ensure_state(self) -> TelemetryState | None:
        """Return existing state or create one when no file exists.

        Existing corruption is not replaced.  This makes a damaged or newer
        state file a safe no-op and avoids silently discarding data that a
        future version may own.
        """

        try:
            with self._locked():
                if self.path.exists():
                    return self._read_unlocked()
                state = TelemetryState(installationId=uuid4())
                self._write_unlocked(state)
                return state
        except (OSError, portalocker.exceptions.LockException, ValueError, TypeError):
            return None

    def installation_id(self) -> UUID | None:
        state = self.ensure_state()
        return state.installation_id if state is not None else None

    def claim_daily_open(self, today: date | datetime | None = None) -> bool:
        """Atomically claim the supplied local calendar day at most once."""

        current_date = _local_date(today)
        try:
            with self._locked():
                if self.path.exists():
                    state = self._read_unlocked()
                    if state is None:
                        return False
                else:
                    state = TelemetryState(installationId=uuid4())

                if state.last_daily_open_date == current_date:
                    return False

                updated = state.model_copy(
                    update={"last_daily_open_date": current_date}
                )
                self._write_unlocked(updated)
                return True
        except (OSError, portalocker.exceptions.LockException, ValueError, TypeError):
            return False

    # Descriptive aliases for application code and test doubles.
    get_or_create = ensure_state
    claim_daily_open_date = claim_daily_open

    def _read_unlocked(self) -> TelemetryState | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            return TelemetryState.model_validate(raw)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            return None

    def _write_unlocked(self, state: TelemetryState) -> None:
        atomic_write_json(
            self.path,
            state.model_dump(mode="json", by_alias=True),
        )

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = portalocker.Lock(
            self.lock_path,
            mode="a+",
            timeout=0,
            fail_when_locked=True,
        )
        with lock:
            yield


def _local_date(value: date | datetime | None) -> date:
    if value is None:
        return datetime.now().astimezone().date()
    if isinstance(value, datetime):
        return value.astimezone().date() if value.tzinfo else value.date()
    return value


# A name that reads naturally at call sites while preserving the file-store
# implementation as the canonical class.
FileTelemetryStateStore = TelemetryStateStore
TelemetryStateRepository = TelemetryStateStore


__all__ = [
    "TELEMETRY_STATE_SCHEMA_VERSION",
    "FileTelemetryStateStore",
    "TelemetryState",
    "TelemetryStateRepository",
    "TelemetryStateStore",
]
