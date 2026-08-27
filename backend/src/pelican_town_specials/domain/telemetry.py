"""Strict, content-free telemetry domain values.

The telemetry boundary intentionally has no ``dict[str, object]`` escape
hatch.  Each event is represented by a small Pydantic model whose fields and
enum values are frozen here; the PostHog adapter is responsible for adding
the installation identity and transport-only properties.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any, ClassVar

from pydantic import Field, model_validator

from .common import StrictModel

TELEMETRY_SCHEMA_VERSION = 1
MAX_DURATION_MS = 24 * 60 * 60 * 1000


class TelemetryMode(str, Enum):
    ASK_GUS = "ask_gus"
    BLUEPRINT = "blueprint"


class GenerationKind(str, Enum):
    INITIAL = "initial"
    FULL_REGENERATE = "full_regenerate"
    BLUEPRINT_PREVIEW = "blueprint_preview"
    RETRY_FAILED_STAGE = "retry_failed_stage"


class GenerationOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class MemoryOutcome(str, Enum):
    HIT = "hit"
    MISS = "miss"
    FALLBACK_ERROR = "fallback_error"
    NOT_ELIGIBLE = "not_eligible"
    UNAVAILABLE = "unavailable"


class ErrorCategory(str, Enum):
    NONE = "none"
    VALIDATION = "validation"
    SETTINGS = "settings"
    BUSY = "busy"
    TRIAL_LIMIT = "trial_limit"
    PROVIDER = "provider"
    TIMEOUT = "timeout"
    NETWORK = "network"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    INTERNAL = "internal"


class RejectionReason(str, Enum):
    BUSY = "busy"
    TRIAL_LIMIT = "trial_limit"
    SETTINGS = "settings"
    VALIDATION = "validation"


class ExportOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DishCountBucket(str, Enum):
    ONE = "one"
    TWO_TO_FIVE = "two_to_five"
    SIX_TO_TEN = "six_to_ten"
    ELEVEN_PLUS = "eleven_plus"


class TelemetryEventName(str, Enum):
    APP_OPENED = "app opened"
    GENERATION_STARTED = "generation started"
    GENERATION_FINISHED = "generation finished"
    GENERATION_REJECTED = "generation rejected"
    DISH_ARCHIVED = "dish archived"
    MENU_EXPORT_FINISHED = "menu export finished"


class AppOpenedProperties(StrictModel):
    """The daily-open event intentionally has no event-specific fields."""


class GenerationStartedProperties(StrictModel):
    mode: TelemetryMode
    trial_used: bool = Field(strict=True)
    generation_kind: GenerationKind


class GenerationFinishedProperties(StrictModel):
    mode: TelemetryMode
    outcome: GenerationOutcome
    duration_ms: int = Field(ge=0, le=MAX_DURATION_MS, strict=True)
    trial_used: bool = Field(strict=True)
    memory_outcome: MemoryOutcome
    error_category: ErrorCategory


class GenerationRejectedProperties(StrictModel):
    reason: RejectionReason


class DishArchivedProperties(StrictModel):
    mode: TelemetryMode


class MenuExportFinishedProperties(StrictModel):
    outcome: ExportOutcome
    dish_count_bucket: DishCountBucket


type TelemetryProperties = (
    AppOpenedProperties
    | GenerationStartedProperties
    | GenerationFinishedProperties
    | GenerationRejectedProperties
    | DishArchivedProperties
    | MenuExportFinishedProperties
)


class TelemetryEvent(StrictModel):
    """A fixed-name event with the matching strict property model."""

    event: TelemetryEventName
    properties: TelemetryProperties

    _PROPERTY_TYPES: ClassVar[dict[TelemetryEventName, type[StrictModel]]] = {
        TelemetryEventName.APP_OPENED: AppOpenedProperties,
        TelemetryEventName.GENERATION_STARTED: GenerationStartedProperties,
        TelemetryEventName.GENERATION_FINISHED: GenerationFinishedProperties,
        TelemetryEventName.GENERATION_REJECTED: GenerationRejectedProperties,
        TelemetryEventName.DISH_ARCHIVED: DishArchivedProperties,
        TelemetryEventName.MENU_EXPORT_FINISHED: MenuExportFinishedProperties,
    }

    @model_validator(mode="before")
    @classmethod
    def _validate_matching_properties(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        event_value = value.get("event")
        try:
            event = (
                event_value
                if isinstance(event_value, TelemetryEventName)
                else TelemetryEventName(event_value)
            )
        except (TypeError, ValueError):
            return value

        property_type = cls._PROPERTY_TYPES[event]
        properties = value.get("properties")
        if isinstance(properties, property_type):
            return value

        # Parse the mapping with the exact event-specific model before Pydantic
        # considers the union.  This prevents a permissive union member from
        # accepting a property set belonging to another event.
        candidate = dict(value)
        candidate["properties"] = property_type.model_validate(properties)
        return candidate

    @model_validator(mode="after")
    def _validate_property_type(self) -> TelemetryEvent:
        property_type = self._PROPERTY_TYPES[self.event]
        if not isinstance(self.properties, property_type):
            raise TypeError(
                f"properties do not match telemetry event {self.event.value}"
            )
        return self

    @property
    def event_name(self) -> TelemetryEventName:
        return self.event

    @classmethod
    def app_opened(cls) -> TelemetryEvent:
        return cls(
            event=TelemetryEventName.APP_OPENED,
            properties=AppOpenedProperties(),
        )

    @classmethod
    def generation_started(
        cls,
        *,
        mode: TelemetryMode,
        trial_used: bool,
        generation_kind: GenerationKind,
    ) -> TelemetryEvent:
        return cls(
            event=TelemetryEventName.GENERATION_STARTED,
            properties=GenerationStartedProperties(
                mode=mode,
                trial_used=trial_used,
                generation_kind=generation_kind,
            ),
        )

    @classmethod
    def generation_finished(
        cls,
        *,
        mode: TelemetryMode,
        outcome: GenerationOutcome,
        duration_ms: int,
        trial_used: bool,
        memory_outcome: MemoryOutcome,
        error_category: ErrorCategory,
    ) -> TelemetryEvent:
        return cls(
            event=TelemetryEventName.GENERATION_FINISHED,
            properties=GenerationFinishedProperties(
                mode=mode,
                outcome=outcome,
                duration_ms=duration_ms,
                trial_used=trial_used,
                memory_outcome=memory_outcome,
                error_category=error_category,
            ),
        )

    @classmethod
    def generation_rejected(cls, *, reason: RejectionReason) -> TelemetryEvent:
        return cls(
            event=TelemetryEventName.GENERATION_REJECTED,
            properties=GenerationRejectedProperties(reason=reason),
        )

    @classmethod
    def dish_archived(cls, *, mode: TelemetryMode) -> TelemetryEvent:
        return cls(
            event=TelemetryEventName.DISH_ARCHIVED,
            properties=DishArchivedProperties(mode=mode),
        )

    @classmethod
    def menu_export_finished(
        cls,
        *,
        outcome: ExportOutcome,
        dish_count_bucket: DishCountBucket,
    ) -> TelemetryEvent:
        return cls(
            event=TelemetryEventName.MENU_EXPORT_FINISHED,
            properties=MenuExportFinishedProperties(
                outcome=outcome,
                dish_count_bucket=dish_count_bucket,
            ),
        )


# Aliases keep the public domain vocabulary discoverable for callers that use
# the event-suffixed enum names while retaining one canonical implementation.
TelemetryEventType = TelemetryEventName
TelemetryEventProperties = TelemetryProperties


def property_model(event: TelemetryEventName) -> type[StrictModel]:
    """Return the exact property model for adapter-side serialization."""

    return TelemetryEvent._PROPERTY_TYPES[event]


__all__ = [
    "MAX_DURATION_MS",
    "TELEMETRY_SCHEMA_VERSION",
    "AppOpenedProperties",
    "DishArchivedProperties",
    "DishCountBucket",
    "ErrorCategory",
    "ExportOutcome",
    "GenerationFinishedProperties",
    "GenerationKind",
    "GenerationOutcome",
    "GenerationRejectedProperties",
    "GenerationStartedProperties",
    "MemoryOutcome",
    "MenuExportFinishedProperties",
    "RejectionReason",
    "TelemetryEvent",
    "TelemetryEventName",
    "TelemetryEventProperties",
    "TelemetryEventType",
    "TelemetryMode",
    "TelemetryProperties",
    "property_model",
]
