"""Optional PostHog batch sink with a bounded, fail-open dispatcher."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import Field, field_validator

from pelican_town_specials.application.telemetry import (
    NoopTelemetryRecorder,
    TelemetryRecorder,
)
from pelican_town_specials.domain.common import StrictModel
from pelican_town_specials.domain.telemetry import (
    TELEMETRY_SCHEMA_VERSION,
    TelemetryEvent,
)

POSTHOG_BATCH_PATH = "/batch/"
DEFAULT_QUEUE_SIZE = 100
DEFAULT_BATCH_SIZE = 20
DEFAULT_TIMEOUT_SECONDS = 2.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 1.0
DEFAULT_RETRY_DELAY_SECONDS = 0.05


class PostHogTelemetryConfig(StrictModel):
    """The small Release-only configuration accepted by the sink."""

    schema_version: Literal[1] = Field(
        default=cast(Literal[1], TELEMETRY_SCHEMA_VERSION),
        alias="schemaVersion",
    )
    host: str
    project_token: str = Field(alias="projectToken", min_length=1)
    enabled_for_build: bool = Field(alias="enabledForBuild", strict=True)

    @field_validator("host")
    @classmethod
    def _validate_https_origin(cls, value: str) -> str:
        candidate = value.strip()
        try:
            parsed = urlsplit(candidate)
        except ValueError as exc:
            raise ValueError("telemetry host must be a valid HTTPS origin") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("telemetry host must be an HTTPS origin without a path")
        # Accessing port catches malformed values such as ``:not-a-port``.
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("telemetry host must have a valid port") from exc
        return candidate.rstrip("/")

    @field_validator("project_token")
    @classmethod
    def _validate_project_token(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("telemetry project token must not be empty")
        return token

    @classmethod
    def from_file(cls, path: Path) -> PostHogTelemetryConfig | None:
        return load_posthog_config(path)


class PostHogTelemetryRecorder:
    """Asynchronously sends only validated events to PostHog ``/batch/``."""

    enabled = True

    def __init__(
        self,
        config: PostHogTelemetryConfig,
        *,
        installation_id: UUID,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        batch_size: int = DEFAULT_BATCH_SIZE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> None:
        if queue_size < 1:
            raise ValueError("telemetry queue size must be positive")
        if not 1 <= batch_size <= DEFAULT_BATCH_SIZE:
            raise ValueError("telemetry batch size must be between 1 and 20")
        if not 0 < timeout_seconds <= DEFAULT_TIMEOUT_SECONDS:
            raise ValueError("telemetry timeout must be between 0 and 2 seconds")
        if retry_delay_seconds < 0:
            raise ValueError("telemetry retry delay must not be negative")

        self.config = config
        self.installation_id = installation_id
        if self.installation_id.version != 4:
            raise ValueError("telemetry installation id must be UUID4")
        self.queue_capacity = queue_size
        self.batch_capacity = batch_size
        self.timeout_seconds = timeout_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self._events: deque[TelemetryEvent] = deque()
        self._dropped_count = 0
        self._wake_event: asyncio.Event | None = None
        self._dispatcher_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._closed = False
        self._flush_lock = asyncio.Lock()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.config.host,
            timeout=httpx.Timeout(self.timeout_seconds),
            transport=transport,
        )

    @property
    def queue_size(self) -> int:
        return len(self._events)

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    @property
    def dispatcher_task(self) -> asyncio.Task[None] | None:
        return self._dispatcher_task

    def record(self, event: TelemetryEvent) -> None:
        """Validate the type and enqueue synchronously without I/O."""

        if not isinstance(event, TelemetryEvent):
            raise TypeError("telemetry record expects a TelemetryEvent")
        if self._closed or self._stopping:
            return
        if len(self._events) >= self.queue_capacity:
            self._events.popleft()
            self._dropped_count += 1
        self._events.append(event)
        if self._wake_event is not None:
            self._wake_event.set()

    async def start(self) -> None:
        if self._closed or self._dispatcher_task is not None:
            return
        self._stopping = False
        self._wake_event = asyncio.Event()
        self._dispatcher_task = asyncio.create_task(self._dispatch())
        if self._events:
            self._wake_event.set()

    async def flush(self, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Best-effort drain used by tests and the bounded shutdown path."""

        bounded_timeout = min(max(timeout_seconds, 0.0), DEFAULT_TIMEOUT_SECONDS)
        deadline = asyncio.get_running_loop().time() + bounded_timeout
        async with self._flush_lock:
            while self._events:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return
                batch = self._take_batch()
                try:
                    await asyncio.wait_for(
                        self._send_with_retry(batch),
                        timeout=min(remaining, self.timeout_seconds * 2),
                    )
                except Exception:  # noqa: BLE001, S110 - failed batch is dropped
                    pass

    async def shutdown(
        self,
        *,
        timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
    ) -> None:
        """Stop dispatch and attempt a flush for no more than one second."""

        if self._closed:
            return
        timeout = min(max(timeout_seconds, 0.0), DEFAULT_SHUTDOWN_TIMEOUT_SECONDS)
        started = asyncio.get_running_loop().time()
        self._stopping = True
        if self._wake_event is not None:
            self._wake_event.set()

        task = self._dispatcher_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                task = None
            except Exception:  # noqa: BLE001 - dispatcher is fail-open
                task = None
        self._dispatcher_task = None

        remaining = max(0.0, timeout - (asyncio.get_running_loop().time() - started))
        if remaining > 0 and self._events:
            try:
                await asyncio.wait_for(
                    self.flush(timeout_seconds=remaining),
                    timeout=remaining,
                )
            except Exception:  # noqa: BLE001 - shutdown is best effort
                self._events.clear()

        if self._owns_client:
            remaining = max(
                0.0,
                timeout - (asyncio.get_running_loop().time() - started),
            )
            if remaining > 0:
                try:
                    await asyncio.wait_for(self._client.aclose(), timeout=remaining)
                except Exception:  # noqa: BLE001 - client close is best effort
                    self._closed = True
        self._closed = True

    close = shutdown

    async def _dispatch(self) -> None:
        assert self._wake_event is not None
        while not self._stopping:
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=0.25)
            except TimeoutError:
                continue
            self._wake_event.clear()
            if self._events:
                try:
                    await self.flush(timeout_seconds=self.timeout_seconds * 2)
                except Exception:  # noqa: BLE001 - dispatcher must remain isolated
                    self._events.clear()

    def _take_batch(self) -> list[TelemetryEvent]:
        batch: list[TelemetryEvent] = []
        while self._events and len(batch) < self.batch_capacity:
            batch.append(self._events.popleft())
        return batch

    async def _send_with_retry(self, events: list[TelemetryEvent]) -> None:
        payload = build_batch_payload(self.config, self.installation_id, events)
        for attempt in range(2):
            try:
                response = await self._client.post(POSTHOG_BATCH_PATH, json=payload)
            except Exception:  # noqa: BLE001 - DNS/TLS/timeout are telemetry-only
                if attempt == 0:
                    await _bounded_retry_delay(self.retry_delay_seconds)
                    continue
                return

            if 200 <= response.status_code < 300:
                return
            if response.status_code >= 500 and attempt == 0:
                await _bounded_retry_delay(self.retry_delay_seconds)
                continue
            # Client errors are discarded without exposing response contents.
            return


def build_batch_payload(
    config: PostHogTelemetryConfig,
    installation_id: UUID,
    events: list[TelemetryEvent],
) -> dict[str, Any]:
    """Build a deterministic personless PostHog batch payload."""

    if installation_id.version != 4:
        raise ValueError("telemetry installation id must be UUID4")
    return {
        "api_key": config.project_token,
        "batch": [
            {
                "event": event.event.value,
                "properties": {
                    "schema_version": TELEMETRY_SCHEMA_VERSION,
                    "distinct_id": str(installation_id),
                    "$process_person_profile": False,
                    **event.properties.model_dump(mode="json"),
                },
            }
            for event in events
        ],
    }


def load_posthog_config(path: Path) -> PostHogTelemetryConfig | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            return None
        config = PostHogTelemetryConfig.model_validate(raw)
        return config if config.enabled_for_build else None
    except Exception:  # noqa: BLE001 - config failure means no-op
        return None


def build_telemetry_recorder(
    *,
    config_path: Path | None = None,
    installation_id: UUID | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    client: httpx.AsyncClient | None = None,
) -> TelemetryRecorder:
    """Build the Release sink only when every activation gate is satisfied."""

    if _telemetry_disabled_by_environment():
        return NoopTelemetryRecorder()
    config = load_posthog_config(config_path or _default_config_path())
    if config is None:
        return NoopTelemetryRecorder()
    if installation_id is None:
        return NoopTelemetryRecorder()
    try:
        return PostHogTelemetryRecorder(
            config,
            installation_id=installation_id,
            transport=transport,
            client=client,
        )
    except Exception:  # noqa: BLE001 - invalid runtime setup is fail-open
        return NoopTelemetryRecorder()


def _telemetry_disabled_by_environment() -> bool:
    if os.environ.get("PTS_TELEMETRY_DISABLED", "").strip() == "1":
        return True
    # The pytest marker is intentionally a hard safety gate so normal test
    # collection can never send to a configured production project.
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[4] / "resources" / "telemetry" / "telemetry.json"


async def _bounded_retry_delay(delay_seconds: float) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(min(delay_seconds, 0.25))


# Adapter vocabulary aliases for callers that refer to a sink/dispatcher.
PostHogTelemetrySink = PostHogTelemetryRecorder
TelemetryDispatcher = PostHogTelemetryRecorder
PostHogConfig = PostHogTelemetryConfig
create_telemetry_recorder = build_telemetry_recorder


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_QUEUE_SIZE",
    "DEFAULT_SHUTDOWN_TIMEOUT_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "POSTHOG_BATCH_PATH",
    "PostHogConfig",
    "PostHogTelemetryConfig",
    "PostHogTelemetryRecorder",
    "PostHogTelemetrySink",
    "TelemetryDispatcher",
    "build_batch_payload",
    "build_telemetry_recorder",
    "create_telemetry_recorder",
    "load_posthog_config",
]
