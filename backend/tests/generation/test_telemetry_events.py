"""Task 38 generation telemetry: lifecycle, rejection, privacy, and isolation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from pelican_town_specials.domain.canonical import RecallDecision
from pelican_town_specials.domain.common import DraftMode, GenerationStage, utc_now
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    DraftStatus,
    GenerationAttempt,
    GenerationAttemptKind,
    StageAttempt,
    StageStatus,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.domain.telemetry import (
    ErrorCategory,
    GenerationOutcome,
    MemoryOutcome,
    RejectionReason,
    TelemetryEvent,
    TelemetryEventName,
)
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import (
    GenerationCommand,
    GenerationOrchestrator,
    _default_memory_outcome,
    _error_category,
    _memory_outcome_for_recall,
    _rejection_reason,
)

from .conftest import (
    FakeGateway,
    GenerationHarness,
    initial_command,
)


@dataclass
class RecordingTelemetryRecorder:
    enabled: bool = True
    events: list[TelemetryEvent] = field(default_factory=list)

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)

    async def start(self) -> None:
        return None

    async def shutdown(self, *, timeout_seconds: float = 1.0) -> None:
        return None


@dataclass
class FailingTelemetryRecorder:
    enabled: bool = True

    def record(self, _event: TelemetryEvent) -> None:
        raise RuntimeError("collector failure must not affect generation")

    async def start(self) -> None:
        return None

    async def shutdown(self, *, timeout_seconds: float = 1.0) -> None:
        return None


@dataclass
class TrialLimitAccess:
    def is_active(self) -> bool:
        return True

    def trial_opportunity(self) -> bool:
        return True

    def claim_attempt(self) -> bool:
        return False


@dataclass
class TrialSuccessAccess:
    def is_active(self) -> bool:
        return True

    def trial_opportunity(self) -> bool:
        return True

    def claim_attempt(self) -> bool:
        return True


class ValidationGateway(FakeGateway):
    async def design_ask_gus(self, request, *, json_only: bool = False):
        self.calls.append("design")
        raise AppError(
            code="PTS_GEN_VALIDATION_FAILED",
            message="must not be sent to telemetry",
            http_status=502,
            details={"prompt": "must not be sent to telemetry"},
            retryable=False,
        )


class ProviderAuthFailureGateway(FakeGateway):
    async def analyze_dish(self, request, *, json_only: bool = False):
        self.calls.append("analyze")
        raise AppError(
            code="PTS_PROVIDER_AUTH_FAILED",
            message="must not be sent to telemetry",
            http_status=502,
            details={"provider": "must not be sent to telemetry"},
            retryable=False,
        )


class TimelineGateway(FakeGateway):
    def __init__(self, timeline: list[str]) -> None:
        super().__init__()
        self._timeline = timeline

    async def analyze_dish(self, request, *, json_only: bool = False):
        self._timeline.append("provider")
        return await super().analyze_dish(request, json_only=json_only)


def _orchestrator(
    harness: GenerationHarness,
    recorder: object,
    *,
    gateway: FakeGateway | None = None,
    gateway_error: AppError | None = None,
    registry: AttemptRegistry | None = None,
    clock=None,
    trial_access=None,
    on_gateway=None,
) -> GenerationOrchestrator:
    selected_gateway = gateway or harness.gateway

    def gateway_factory() -> FakeGateway:
        if on_gateway is not None:
            on_gateway()
        if gateway_error is not None:
            raise gateway_error
        return selected_gateway

    return GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=gateway_factory,
        registry=registry or AttemptRegistry(),
        min_confidence=0.5,
        clock=clock or (lambda: 10.0),
        trial_access=trial_access,
        trial_gateway_factory=(lambda: selected_gateway) if trial_access else None,
        telemetry=recorder,
    )


async def _consume(orchestrator: GenerationOrchestrator, command: GenerationCommand):
    return [event async for event in orchestrator.run(command)]


def _telemetry_names(recorder: RecordingTelemetryRecorder) -> list[TelemetryEventName]:
    return [event.event for event in recorder.events]


def _event(recorder: RecordingTelemetryRecorder, name: TelemetryEventName) -> TelemetryEvent:
    matches = [event for event in recorder.events if event.event is name]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.asyncio
async def test_persisted_attempt_records_started_before_one_finished_with_total_duration(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    timeline: list[str] = []
    clock_values = iter((10.0, 10.321))

    def clock() -> float:
        timeline.append("clock")
        return next(clock_values)

    orchestrator = _orchestrator(
        harness,
        recorder,
        gateway=TimelineGateway(timeline),
        clock=clock,
        on_gateway=lambda: timeline.append("gateway"),
    )

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.succeeded"
    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    started = _event(recorder, TelemetryEventName.GENERATION_STARTED)
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert started.properties.trial_used is False
    assert started.properties.generation_kind.value == "initial"
    assert finished.properties.outcome is GenerationOutcome.SUCCEEDED
    assert finished.properties.duration_ms == 321
    assert finished.properties.memory_outcome is MemoryOutcome.UNAVAILABLE
    assert finished.properties.error_category is ErrorCategory.NONE

    attempt_id = harness.draft_repository.get(ready_draft.draft_id).last_attempt_id
    assert attempt_id is not None
    assert harness.attempt_repository.get(attempt_id).status is AttemptStatus.SUCCEEDED
    assert timeline == ["clock", "gateway", "provider", "clock"]


@pytest.mark.asyncio
async def test_trial_limit_is_a_stable_rejection_and_terminal_attempt_without_provider_call(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    orchestrator = _orchestrator(
        harness,
        recorder,
        trial_access=TrialLimitAccess(),
    )

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.failed"
    assert harness.gateway.calls == []
    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_REJECTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    started = _event(recorder, TelemetryEventName.GENERATION_STARTED)
    rejected = _event(recorder, TelemetryEventName.GENERATION_REJECTED)
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert started.properties.trial_used is False
    assert rejected.properties.reason is RejectionReason.TRIAL_LIMIT
    assert finished.properties.outcome is GenerationOutcome.FAILED
    assert finished.properties.error_category is ErrorCategory.TRIAL_LIMIT
    assert finished.properties.memory_outcome is MemoryOutcome.UNAVAILABLE


@pytest.mark.asyncio
async def test_successful_trial_marks_started_and_finished_as_trial_used(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    orchestrator = _orchestrator(
        harness,
        recorder,
        trial_access=TrialSuccessAccess(),
    )

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.succeeded"
    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    started = _event(recorder, TelemetryEventName.GENERATION_STARTED)
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert started.properties.trial_used is True
    assert finished.properties.trial_used is True


@pytest.mark.asyncio
async def test_provider_failure_has_started_and_finished_without_rejection(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    gateway = FakeGateway(fail_stage=GenerationStage.DISH_ANALYSIS)
    orchestrator = _orchestrator(harness, recorder, gateway=gateway)

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.failed"
    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert finished.properties.error_category is ErrorCategory.INTERNAL


@pytest.mark.asyncio
async def test_provider_auth_failure_after_provider_activity_has_no_rejection(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    gateway = ProviderAuthFailureGateway()
    orchestrator = _orchestrator(
        harness,
        recorder,
        gateway=gateway,
    )

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.failed"
    assert gateway.calls == ["analyze"]
    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert finished.properties.error_category is ErrorCategory.SETTINGS


@pytest.mark.asyncio
async def test_settings_error_has_stable_rejection_reason(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    orchestrator = _orchestrator(
        harness,
        recorder,
        gateway_error=AppError(
            code="PTS_PROVIDER_NOT_CONFIGURED",
            message="must not be sent to telemetry",
            http_status=422,
            details={"secret": "must not be sent to telemetry"},
            retryable=False,
        ),
    )

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.failed"
    assert harness.gateway.calls == []
    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_REJECTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    rejected = _event(recorder, TelemetryEventName.GENERATION_REJECTED)
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert rejected.properties.reason is RejectionReason.SETTINGS
    assert finished.properties.error_category is ErrorCategory.SETTINGS


@pytest.mark.asyncio
async def test_low_confidence_after_provider_has_no_rejection(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    orchestrator = _orchestrator(
        harness,
        recorder,
        gateway=FakeGateway(confidence=0.1),
    )

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.failed"
    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert finished.properties.error_category is ErrorCategory.VALIDATION


@pytest.mark.asyncio
async def test_result_validation_after_provider_has_no_rejection(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    orchestrator = _orchestrator(
        harness,
        recorder,
        gateway=ValidationGateway(),
    )

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.failed"
    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert finished.properties.error_category is ErrorCategory.VALIDATION


@pytest.mark.asyncio
async def test_cancelled_attempt_has_started_and_finished_without_rejection(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    harness.gateway.delay = 0.3
    orchestrator = _orchestrator(harness, recorder)
    stream = orchestrator.run(initial_command(ready_draft))
    holder = []

    async def consume() -> None:
        async for event in stream:
            holder.append(event)

    task = asyncio.create_task(consume())
    for _ in range(200):
        if holder and holder[0].attempt_id is not None:
            break
        await asyncio.sleep(0.01)
    assert holder
    attempt_id = holder[0].attempt_id
    assert attempt_id is not None
    for _ in range(200):
        if "analyze" in harness.gateway.calls:
            break
        await asyncio.sleep(0.01)
    assert "analyze" in harness.gateway.calls
    assert orchestrator.cancel(attempt_id) is True
    await task

    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]
    finished = _event(recorder, TelemetryEventName.GENERATION_FINISHED)
    assert finished.properties.outcome is GenerationOutcome.CANCELLED
    assert finished.properties.error_category is ErrorCategory.CANCELLED


@pytest.mark.asyncio
async def test_terminal_finished_recording_is_once_guarded(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    orchestrator = _orchestrator(harness, recorder)
    original = orchestrator._record_generation_finished

    def record_twice(state, **kwargs):
        original(state, **kwargs)
        original(state, **kwargs)

    orchestrator._record_generation_finished = record_twice

    await _consume(orchestrator, initial_command(ready_draft))

    assert _telemetry_names(recorder) == [
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
    ]


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (RecallDecision.MATCH_HIT, MemoryOutcome.HIT),
        (RecallDecision.MATCH_MISS, MemoryOutcome.MISS),
        (RecallDecision.NO_CANDIDATES, MemoryOutcome.MISS),
        (RecallDecision.FALLBACK_ERROR, MemoryOutcome.FALLBACK_ERROR),
    ],
)
def test_recall_decisions_map_to_frozen_memory_outcomes(
    decision: RecallDecision,
    expected: MemoryOutcome,
) -> None:
    assert _memory_outcome_for_recall(decision) is expected


def test_memory_outcome_defaults_preserve_ineligible_and_unavailable_paths() -> None:
    assert (
        _default_memory_outcome(DraftMode.ASK_GUS, GenerationAttemptKind.INITIAL)
        is MemoryOutcome.UNAVAILABLE
    )
    assert (
        _default_memory_outcome(DraftMode.BLUEPRINT, GenerationAttemptKind.INITIAL)
        is MemoryOutcome.NOT_ELIGIBLE
    )
    assert (
        _default_memory_outcome(
            DraftMode.ASK_GUS, GenerationAttemptKind.FULL_REGENERATE
        )
        is MemoryOutcome.NOT_ELIGIBLE
    )


def test_error_and_rejection_mapping_never_uses_provider_validation_after_await() -> None:
    error = AppError(
        code="PTS_GEN_VALIDATION_FAILED",
        message="private message",
        http_status=502,
        details={"prompt": "private details"},
        retryable=False,
    )
    assert _error_category(error) is ErrorCategory.VALIDATION
    assert _rejection_reason(error, provider_started=False) is RejectionReason.VALIDATION
    assert _rejection_reason(error, provider_started=True) is None


def test_recover_interrupted_keeps_telemetry_empty(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    attempt_id = uuid4()
    staged = ready_draft.model_copy(
        update={
            "status": DraftStatus.GENERATING,
            "active_attempt_id": attempt_id,
            "updated_at": utc_now(),
        }
    )
    harness.draft_repository.control_write(
        staged,
        expected_revision=ready_draft.revision,
        expected_attempt_id=None,
    )
    now = utc_now()
    harness.attempt_repository.save(
        GenerationAttempt(
            attempt_id=attempt_id,
            draft_id=ready_draft.draft_id,
            kind=GenerationAttemptKind.INITIAL,
            source_revision=ready_draft.revision,
            status=AttemptStatus.RUNNING,
            current_stage=GenerationStage.INPUT_VALIDATION,
            stages=[
                StageAttempt(
                    stage=GenerationStage.INPUT_VALIDATION,
                    status=StageStatus.RUNNING,
                    retry_count=0,
                    started_at=now,
                    finished_at=None,
                )
            ],
            total_stages=len(GenerationStage),
            candidate_record_path=None,
            started_at=now,
            finished_at=None,
            error=None,
        )
    )
    recorder = RecordingTelemetryRecorder()
    orchestrator = _orchestrator(harness, recorder)

    assert orchestrator.recover_interrupted(ready_draft.draft_id) is True
    assert recorder.events == []


def test_busy_rejection_has_only_the_frozen_reason_and_no_persisted_attempt(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    registry = AttemptRegistry()
    owners: list[UUID] = []
    for _ in range(3):
        attempt_id = uuid4()
        owners.append(attempt_id)
        assert registry.reserve_slot(uuid4(), attempt_id)
    orchestrator = _orchestrator(harness, recorder, registry=registry)

    with pytest.raises(AppError) as excinfo:
        orchestrator.run(initial_command(ready_draft))

    assert excinfo.value.code == "PTS_GEN_BUSY"
    assert _telemetry_names(recorder) == [TelemetryEventName.GENERATION_REJECTED]
    rejected = recorder.events[0]
    assert rejected.properties.reason is RejectionReason.BUSY
    assert harness.attempt_repository.list_running() == []
    for attempt_id in owners:
        registry.release_slot(attempt_id)


@pytest.mark.asyncio
async def test_recorder_failure_does_not_change_generation_result_or_slot_cleanup(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    registry = AttemptRegistry()
    orchestrator = _orchestrator(
        harness,
        FailingTelemetryRecorder(),
        registry=registry,
    )

    events = await _consume(orchestrator, initial_command(ready_draft))

    assert events[-1].type == "attempt.succeeded"
    restored = harness.draft_repository.get(ready_draft.draft_id)
    assert restored.status.value == "REVIEWABLE"
    assert restored.active_attempt_id is None
    assert registry.active_count() == 0
    assert restored.last_attempt_id is not None
    assert harness.attempt_repository.get(restored.last_attempt_id).status is AttemptStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_generation_telemetry_contains_no_business_ids_or_content(
    harness: GenerationHarness,
    ready_draft,
) -> None:
    recorder = RecordingTelemetryRecorder()
    orchestrator = _orchestrator(harness, recorder)

    await _consume(orchestrator, initial_command(ready_draft))

    serialized = json.dumps(
        [event.model_dump(mode="json") for event in recorder.events],
        ensure_ascii=False,
    ).lower()
    for forbidden in (
        "draft_id",
        "attempt_id",
        "canonical_id",
        "archive_id",
        "export_id",
        "display_name",
        "ingredient",
        "prompt",
        "provider",
        "model",
        "api_key",
        "exception",
    ):
        assert forbidden not in serialized


def test_generation_service_reports_immediate_validation_rejection_without_attempt(
    harness: GenerationHarness,
) -> None:
    from pelican_town_specials.application.generation import GenerationService

    recorder = RecordingTelemetryRecorder()
    service = GenerationService(
        orchestrator=_orchestrator(harness, recorder),
        draft_repository=harness.draft_repository,
        telemetry=recorder,
    )

    with pytest.raises(AppError) as excinfo:
        service.begin_generation(uuid4())

    assert excinfo.value.code == "PTS_DRAFT_NOT_FOUND"
    assert _telemetry_names(recorder) == [TelemetryEventName.GENERATION_REJECTED]
    assert recorder.events[0].properties.reason is RejectionReason.VALIDATION
    assert harness.attempt_repository.list_running() == []
