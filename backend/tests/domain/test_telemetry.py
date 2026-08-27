from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from pelican_town_specials.domain.telemetry import (
    DishCountBucket,
    ErrorCategory,
    ExportOutcome,
    GenerationKind,
    GenerationOutcome,
    MemoryOutcome,
    RejectionReason,
    TelemetryEvent,
    TelemetryEventName,
    TelemetryMode,
)


def test_event_factories_use_the_frozen_event_names_and_enum_values() -> None:
    events = (
        TelemetryEvent.app_opened(),
        TelemetryEvent.generation_started(
            mode=TelemetryMode.ASK_GUS,
            trial_used=False,
            generation_kind=GenerationKind.INITIAL,
        ),
        TelemetryEvent.generation_finished(
            mode=TelemetryMode.BLUEPRINT,
            outcome=GenerationOutcome.SUCCEEDED,
            duration_ms=1234,
            trial_used=True,
            memory_outcome=MemoryOutcome.NOT_ELIGIBLE,
            error_category=ErrorCategory.NONE,
        ),
        TelemetryEvent.generation_rejected(reason=RejectionReason.BUSY),
        TelemetryEvent.dish_archived(mode=TelemetryMode.ASK_GUS),
        TelemetryEvent.menu_export_finished(
            outcome=ExportOutcome.SUCCEEDED,
            dish_count_bucket=DishCountBucket.TWO_TO_FIVE,
        ),
    )

    assert [event.event for event in events] == [
        TelemetryEventName.APP_OPENED,
        TelemetryEventName.GENERATION_STARTED,
        TelemetryEventName.GENERATION_FINISHED,
        TelemetryEventName.GENERATION_REJECTED,
        TelemetryEventName.DISH_ARCHIVED,
        TelemetryEventName.MENU_EXPORT_FINISHED,
    ]
    assert events[1].model_dump(mode="json") == {
        "event": "generation started",
        "properties": {
            "mode": "ask_gus",
            "trial_used": False,
            "generation_kind": "initial",
        },
    }


def test_event_properties_are_strict_and_do_not_accept_content_or_exception_values() -> None:
    with pytest.raises(ValidationError):
        TelemetryEvent.generation_started(
            mode="a user supplied mode",  # type: ignore[arg-type]
            trial_used=False,
            generation_kind=GenerationKind.INITIAL,
        )

    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(
            {
                "event": "generation finished",
                "properties": {
                    "mode": "ask_gus",
                    "outcome": "failed",
                    "duration_ms": 10,
                    "trial_used": False,
                    "memory_outcome": "unavailable",
                    "error_category": "internal",
                    "prompt": "raw user content",
                },
            }
        )

    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(
            {
                "event": "generation rejected",
                "properties": {
                    "reason": "busy",
                    "exception": RuntimeError("provider details"),
                },
            }
        )

    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(
            {
                "event": "app opened",
                "properties": {"unknown": "value"},
            }
        )


def test_generation_finished_duration_is_a_bounded_strict_integer() -> None:
    with pytest.raises(ValidationError):
        TelemetryEvent.generation_finished(
            mode=TelemetryMode.ASK_GUS,
            outcome=GenerationOutcome.SUCCEEDED,
            duration_ms=-1,
            trial_used=False,
            memory_outcome=MemoryOutcome.MISS,
            error_category=ErrorCategory.NONE,
        )

    with pytest.raises(ValidationError):
        TelemetryEvent.generation_finished(
            mode=TelemetryMode.ASK_GUS,
            outcome=GenerationOutcome.SUCCEEDED,
            duration_ms=86_400_001,
            trial_used=False,
            memory_outcome=MemoryOutcome.MISS,
            error_category=ErrorCategory.NONE,
        )

    with pytest.raises(ValidationError):
        TelemetryEvent.generation_finished(
            mode=TelemetryMode.ASK_GUS,
            outcome=GenerationOutcome.SUCCEEDED,
            duration_ms=True,  # type: ignore[arg-type]
            trial_used=False,
            memory_outcome=MemoryOutcome.MISS,
            error_category=ErrorCategory.NONE,
        )


def test_event_model_does_not_accept_an_arbitrary_event_name_or_installation_id() -> None:
    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(
            {
                "event": "user typed arbitrary event",
                "properties": {},
            }
        )

    # Installation identity is deliberately added by the recorder adapter,
    # not accepted as an arbitrary event property.
    event = TelemetryEvent.app_opened()
    assert "distinct_id" not in event.properties.model_dump()
    assert uuid4()  # keep this test independent of a fixed installation id
