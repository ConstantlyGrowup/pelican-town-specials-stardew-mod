"""Task 39 local fake-collector end-to-end telemetry coverage."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import date
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pelican_town_specials.application.telemetry import TelemetryService
from pelican_town_specials.domain.telemetry import (
    DishCountBucket,
    ErrorCategory,
    ExportOutcome,
    GenerationKind,
    GenerationOutcome,
    MemoryOutcome,
    RejectionReason,
    TelemetryEvent,
    TelemetryMode,
)
from pelican_town_specials.observability.posthog_telemetry import (
    PostHogTelemetryConfig,
    PostHogTelemetryRecorder,
)
from pelican_town_specials.persistence.telemetry_state import TelemetryStateStore

INSTALLATION_ID = UUID("12345678-1234-4234-8234-123456789abc")


def _config() -> PostHogTelemetryConfig:
    return PostHogTelemetryConfig(
        schema_version=1,
        host="https://fake.local",
        project_token="phc_test_only",
        enabled_for_build=True,
    )


@pytest.mark.asyncio
async def test_fake_collector_covers_daily_open_business_matrix_and_privacy(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    async def collect(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204, request=request)

    recorder = PostHogTelemetryRecorder(
        _config(),
        installation_id=INSTALLATION_ID,
        transport=httpx.MockTransport(collect),
        retry_delay_seconds=0,
    )
    service = TelemetryService(
        recorder,
        TelemetryStateStore(tmp_path / "app-state" / "telemetry-state.json"),
        clock=lambda: date(2026, 8, 27),
    )

    await service.startup()
    assert service.record_daily_open(date(2026, 8, 27)) is False
    service.record(
        TelemetryEvent.generation_started(
            mode=TelemetryMode.ASK_GUS,
            trial_used=True,
            generation_kind=GenerationKind.INITIAL,
        )
    )
    service.record(
        TelemetryEvent.generation_finished(
            mode=TelemetryMode.ASK_GUS,
            outcome=GenerationOutcome.SUCCEEDED,
            duration_ms=321,
            trial_used=True,
            memory_outcome=MemoryOutcome.MISS,
            error_category=ErrorCategory.NONE,
        )
    )
    service.record(
        TelemetryEvent.generation_finished(
            mode=TelemetryMode.BLUEPRINT,
            outcome=GenerationOutcome.FAILED,
            duration_ms=654,
            trial_used=False,
            memory_outcome=MemoryOutcome.NOT_ELIGIBLE,
            error_category=ErrorCategory.PROVIDER,
        )
    )
    service.record(TelemetryEvent.generation_rejected(reason=RejectionReason.BUSY))
    service.record(
        TelemetryEvent.generation_rejected(reason=RejectionReason.TRIAL_LIMIT)
    )
    service.record(TelemetryEvent.dish_archived(mode=TelemetryMode.ASK_GUS))
    service.record(
        TelemetryEvent.menu_export_finished(
            outcome=ExportOutcome.SUCCEEDED,
            dish_count_bucket=DishCountBucket.ONE,
        )
    )
    await recorder.flush()
    await service.shutdown()

    payloads = [json.loads(request.content) for request in requests]
    assert payloads
    assert all(request.url.path == "/batch/" for request in requests)
    assert all(set(payload) == {"api_key", "batch"} for payload in payloads)
    events = [item for payload in payloads for item in payload["batch"]]
    assert [item["event"] for item in events].count("app opened") == 1
    assert {item["event"] for item in events} == {
        "app opened",
        "generation started",
        "generation finished",
        "generation rejected",
        "dish archived",
        "menu export finished",
    }

    allowed_properties = {
        "app opened": {"schema_version", "distinct_id", "$process_person_profile"},
        "generation started": {
            "schema_version",
            "distinct_id",
            "$process_person_profile",
            "mode",
            "trial_used",
            "generation_kind",
        },
        "generation finished": {
            "schema_version",
            "distinct_id",
            "$process_person_profile",
            "mode",
            "outcome",
            "duration_ms",
            "trial_used",
            "memory_outcome",
            "error_category",
        },
        "generation rejected": {
            "schema_version",
            "distinct_id",
            "$process_person_profile",
            "reason",
        },
        "dish archived": {
            "schema_version",
            "distinct_id",
            "$process_person_profile",
            "mode",
        },
        "menu export finished": {
            "schema_version",
            "distinct_id",
            "$process_person_profile",
            "outcome",
            "dish_count_bucket",
        },
    }
    for item in events:
        assert set(item["properties"]) == allowed_properties[item["event"]]
        assert item["properties"]["schema_version"] == 1
        assert item["properties"]["distinct_id"] == str(INSTALLATION_ID)
        assert item["properties"]["$process_person_profile"] is False

    serialized = json.dumps(payloads, ensure_ascii=False).lower()
    for forbidden in (
        "salted soup",
        "gpt-5.6",
        "https://real-provider.invalid",
        "draft_id",
        "attempt_id",
        "canonical_id",
        "prompt",
        "provider_url",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_fake_collector_failure_is_fail_open_and_bounded(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    async def fail(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        await asyncio.sleep(10)
        return httpx.Response(204, request=request)

    recorder = PostHogTelemetryRecorder(
        _config(),
        installation_id=INSTALLATION_ID,
        transport=httpx.MockTransport(fail),
        retry_delay_seconds=0,
    )
    service = TelemetryService(
        recorder,
        TelemetryStateStore(tmp_path / "telemetry-state.json"),
        clock=lambda: date(2026, 8, 27),
    )
    await service.startup()
    business_result = {"status": "succeeded", "value": "unchanged"}
    service.record(TelemetryEvent.app_opened())
    started = time.monotonic()
    await service.shutdown(timeout_seconds=0.1)

    assert requests
    assert time.monotonic() - started < 0.5
    assert business_result == {"status": "succeeded", "value": "unchanged"}
