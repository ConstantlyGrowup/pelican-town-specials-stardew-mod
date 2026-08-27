from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from pelican_town_specials.application.telemetry import NoopTelemetryRecorder
from pelican_town_specials.domain.telemetry import (
    ErrorCategory,
    GenerationOutcome,
    MemoryOutcome,
    TelemetryEvent,
    TelemetryMode,
)
from pelican_town_specials.observability import posthog_telemetry
from pelican_town_specials.observability.posthog_telemetry import (
    PostHogTelemetryConfig,
    PostHogTelemetryRecorder,
    build_telemetry_recorder,
)


def _config() -> PostHogTelemetryConfig:
    return PostHogTelemetryConfig(
        schema_version=1,
        host="https://us.i.posthog.com",
        project_token="phc_test_project_token",
        enabled_for_build=True,
    )


def _finished_event() -> object:
    return TelemetryEvent.generation_finished(
        mode=TelemetryMode.ASK_GUS,
        outcome=GenerationOutcome.SUCCEEDED,
        duration_ms=321,
        trial_used=False,
        memory_outcome=MemoryOutcome.MISS,
        error_category=ErrorCategory.NONE,
    )


@pytest.mark.asyncio
async def test_batch_payload_is_personless_and_contains_only_typed_properties() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    recorder = PostHogTelemetryRecorder(
        _config(),
        installation_id=uuid4(),
        transport=httpx.MockTransport(handler),
    )
    await recorder.start()
    recorder.record(_finished_event())  # type: ignore[arg-type]
    await recorder.flush()
    await recorder.shutdown()

    assert len(requests) == 1
    assert str(requests[0].url) == "https://us.i.posthog.com/batch/"
    payload = json.loads(requests[0].content)
    assert set(payload) == {"api_key", "batch"}
    assert payload["api_key"] == "phc_test_project_token"
    properties = payload["batch"][0]["properties"]
    assert properties["$process_person_profile"] is False
    assert properties["schema_version"] == 1
    assert properties["mode"] == "ask_gus"
    assert properties["duration_ms"] == 321
    serialized = json.dumps(payload)
    for forbidden in (
        "prompt",
        "provider",
        "model",
        "api_key_configured",
        "draft_id",
        "attempt_id",
        "path",
        "ip",
        "geo",
        "app_version",
    ):
        assert forbidden not in serialized.lower()


def test_config_requires_a_complete_https_origin_and_project_token() -> None:
    for host in (
        "http://us.i.posthog.com",
        "https://us.i.posthog.com/path",
        "https://us.i.posthog.com?secret=yes",
        "https://user:password@us.i.posthog.com",
    ):
        with pytest.raises(ValidationError):
            PostHogTelemetryConfig(
                schema_version=1,
                host=host,
                project_token="phc_test_project_token",
                enabled_for_build=True,
            )


def test_missing_invalid_or_disabled_config_builds_a_noop_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert isinstance(build_telemetry_recorder(config_path=tmp_path / "missing.json"), NoopTelemetryRecorder)

    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"schemaVersion": 1, "host": "http://invalid"}', encoding="utf-8")
    assert isinstance(build_telemetry_recorder(config_path=invalid), NoopTelemetryRecorder)

    monkeypatch.setenv("PTS_TELEMETRY_DISABLED", "1")
    assert isinstance(build_telemetry_recorder(config_path=invalid), NoopTelemetryRecorder)


def test_pytest_environment_is_always_noop_even_when_a_release_config_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "telemetry.json"
    config_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "host": "https://us.i.posthog.com",
                "projectToken": "phc_test_project_token",
                "enabledForBuild": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test-pytest-environment")
    assert isinstance(build_telemetry_recorder(config_path=config_path), NoopTelemetryRecorder)


def test_release_config_without_persisted_id_stays_noop_without_constructing_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "telemetry.json"
    config_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "host": "https://us.i.posthog.com",
                "projectToken": "phc_test_project_token",
                "enabledForBuild": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        posthog_telemetry,
        "_telemetry_disabled_by_environment",
        lambda: False,
    )
    constructed: list[bool] = []

    def unexpected_sink(*args: object, **kwargs: object) -> object:
        constructed.append(True)
        raise AssertionError("a missing persisted installation id must not build a sink")

    monkeypatch.setattr(posthog_telemetry, "PostHogTelemetryRecorder", unexpected_sink)

    recorder = build_telemetry_recorder(
        config_path=config_path,
        installation_id=None,
    )

    assert isinstance(recorder, NoopTelemetryRecorder)
    assert constructed == []


@pytest.mark.asyncio
async def test_queue_is_bounded_and_drops_the_oldest_event() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204, request=request)

    recorder = PostHogTelemetryRecorder(
        _config(),
        installation_id=uuid4(),
        queue_size=100,
        transport=httpx.MockTransport(handler),
    )
    for index in range(101):
        recorder.record(
            TelemetryEvent.generation_finished(
                mode=TelemetryMode.ASK_GUS,
                outcome=GenerationOutcome.SUCCEEDED,
                duration_ms=index,
                trial_used=False,
                memory_outcome=MemoryOutcome.MISS,
                error_category=ErrorCategory.NONE,
            )
        )

    assert recorder.queue_size == 100
    assert recorder.dropped_count == 1
    await recorder.shutdown()

    assert len(requests) == 5
    durations = [
        item["properties"]["duration_ms"]
        for request in requests
        for item in json.loads(request.content)["batch"]
    ]
    assert durations == list(range(1, 101))


@pytest.mark.asyncio
async def test_http_failure_is_swallowed_and_retried_at_most_once() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500 if calls == 1 else 204, request=request)

    recorder = PostHogTelemetryRecorder(
        _config(),
        installation_id=uuid4(),
        transport=httpx.MockTransport(handler),
        retry_delay_seconds=0,
    )
    await recorder.start()
    recorder.record(TelemetryEvent.app_opened())
    await recorder.flush()
    await recorder.shutdown()
    assert calls == 2


@pytest.mark.asyncio
async def test_timeout_and_4xx_do_not_propagate_to_the_caller() -> None:
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("collector timeout", request=request)

    recorder = PostHogTelemetryRecorder(
        _config(),
        installation_id=uuid4(),
        transport=httpx.MockTransport(timeout_handler),
        retry_delay_seconds=0,
    )
    await recorder.start()
    recorder.record(TelemetryEvent.app_opened())
    await recorder.flush()
    await recorder.shutdown()

    async def client_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, request=request)

    recorder = PostHogTelemetryRecorder(
        _config(),
        installation_id=uuid4(),
        transport=httpx.MockTransport(client_error_handler),
        retry_delay_seconds=0,
    )
    await recorder.start()
    recorder.record(TelemetryEvent.app_opened())
    await recorder.flush()
    await recorder.shutdown()


@pytest.mark.asyncio
async def test_shutdown_attempts_best_effort_flush_for_at_most_one_second() -> None:
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, request=request)

    recorder = PostHogTelemetryRecorder(
        _config(),
        installation_id=uuid4(),
        transport=httpx.MockTransport(slow_handler),
    )
    await recorder.start()
    recorder.record(TelemetryEvent.app_opened())
    started = time.monotonic()
    await recorder.shutdown(timeout_seconds=1)
    assert time.monotonic() - started < 1.5
