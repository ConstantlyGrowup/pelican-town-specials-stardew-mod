"""Generate and validate the local M14 PostHog event demonstration.

This module deliberately has no project or third-party imports.  It creates a
deterministic, constructed event list for local dashboard verification.  The
``pts_data_origin`` property is retained in the event payload so downstream
tools can keep this fixture separate from observed production events without
adding a visible dashboard annotation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID


ORIGIN = "m14_seeded_v1"
SCHEMA_VERSION = 1
INSTALLATION_COUNT = 12
START_DATE = date(2026, 9, 17)
END_DATE = date(2026, 9, 22)

# Sydney remains UTC+10 during the selected September window.  A fixed offset
# keeps the output deterministic on machines whose local tzdata is missing or
# differs from the build environment while preserving the intended zone.
SYDNEY_OFFSET = timezone(timedelta(hours=10), name="Australia/Sydney")

EVENT_NAMES = frozenset(
    {
        "app opened",
        "generation started",
        "generation finished",
        "generation rejected",
        "dish archived",
        "menu export finished",
    }
)
TRANSPORT_PROPERTIES = frozenset(
    {
        "schema_version",
        "distinct_id",
        "$process_person_profile",
        "$insert_id",
        "pts_data_origin",
    }
)
EVENT_PROPERTIES: dict[str, frozenset[str]] = {
    "app opened": frozenset(),
    "generation started": frozenset(
        {"mode", "trial_used", "generation_kind"}
    ),
    "generation finished": frozenset(
        {
            "mode",
            "outcome",
            "duration_ms",
            "trial_used",
            "memory_outcome",
            "error_category",
        }
    ),
    "generation rejected": frozenset({"reason"}),
    "dish archived": frozenset({"mode"}),
    "menu export finished": frozenset(
        {"outcome", "dish_count_bucket"}
    ),
}

MODES = frozenset({"ask_gus", "blueprint"})
GENERATION_KINDS = frozenset(
    {"initial", "full_regenerate", "blueprint_preview", "retry_failed_stage"}
)
GENERATION_OUTCOMES = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)
MEMORY_OUTCOMES = frozenset(
    {"hit", "miss", "fallback_error", "not_eligible", "unavailable"}
)
ERROR_CATEGORIES = frozenset(
    {
        "none",
        "validation",
        "settings",
        "busy",
        "trial_limit",
        "provider",
        "timeout",
        "network",
        "cancelled",
        "interrupted",
        "internal",
    }
)
REJECTION_REASONS = frozenset({"busy", "trial_limit", "settings", "validation"})
EXPORT_OUTCOMES = frozenset({"succeeded", "failed"})
DISH_COUNT_BUCKETS = frozenset(
    {"one", "two_to_five", "six_to_ten", "eleven_plus"}
)

_REQUIRED_EVENT_KEYS = frozenset({"event", "properties", "timestamp"})
_MAX_DURATION_MS = 24 * 60 * 60 * 1000


def _installation_id(index: int) -> str:
    """Return a stable RFC-4122 UUIDv4 derived from the fixture seed."""

    digest = hashlib.sha256(f"{ORIGIN}:installation:{index}".encode()).digest()
    return str(UUID(bytes=digest[:16], version=4))


def _timestamp(value: datetime) -> str:
    return value.astimezone(SYDNEY_OFFSET).isoformat(timespec="seconds")


def _insert_id(*, event: str, installation_id: str, at: datetime) -> str:
    """Build a stable PostHog deduplication id for one event."""

    material = f"{ORIGIN}:{installation_id}:{event}:{at.isoformat()}".encode()
    return f"m14_{hashlib.sha256(material).hexdigest()}"


def _event(
    *,
    event: str,
    installation_id: str,
    at: datetime,
    properties: Mapping[str, Any],
) -> dict[str, Any]:
    transport = {
        "schema_version": SCHEMA_VERSION,
        "distinct_id": installation_id,
        "$process_person_profile": False,
        "$insert_id": _insert_id(
            event=event,
            installation_id=installation_id,
            at=at,
        ),
        "pts_data_origin": ORIGIN,
    }
    return {
        "event": event,
        "properties": {**transport, **dict(properties)},
        "timestamp": _timestamp(at),
    }


def generate_events() -> list[dict[str, Any]]:
    """Build the deterministic 12-installation M14 event list.

    Each installation has one app-open event and 2--5 ordered generation
    start/finish pairs.  The first generation for every installation succeeds;
    only four installations are archived so the unique-install archive funnel
    remains visibly below sixty percent.  Events intentionally use only the
    M10 event/property vocabulary.
    """

    events: list[dict[str, Any]] = []
    archive_indices = {1, 7, 9, 10}
    export_indices = {1, 7, 9}

    for index in range(INSTALLATION_COUNT):
        installation_id = _installation_id(index)
        # Spread two installations across each day of the current
        # 2026-09-17..22 dashboard window so ingestion does not depend on
        # historical-event backfill permissions.
        opened_at = datetime(
            2026,
            9,
            17 + (index % 6),
            8 + (index % 8),
            0,
            tzinfo=SYDNEY_OFFSET,
        )
        events.append(
            _event(
                event="app opened",
                installation_id=installation_id,
                at=opened_at,
                properties={},
            )
        )

        attempt_count = 2 + (index % 4)
        first_finished_at: datetime | None = None
        first_mode = "ask_gus"
        previous_outcome: str | None = None
        for attempt in range(attempt_count):
            started_at = opened_at + timedelta(minutes=8 + attempt * 24)
            mode = "blueprint" if (index + attempt) % 3 == 1 else "ask_gus"
            trial_used = attempt < 2

            if attempt == 0:
                outcome = "succeeded"
                error_category = "none"
            elif (index + attempt) % 5 == 0:
                outcome = "cancelled"
                error_category = "cancelled"
            elif (index + attempt) % 4 == 0:
                outcome = "interrupted"
                error_category = "interrupted"
            elif (index + attempt) % 3 == 0:
                outcome = "failed"
                error_category = (
                    "timeout"
                    if index % 3 == 0
                    else "network"
                    if index % 3 == 1
                    else "internal"
                )
            else:
                outcome = "succeeded"
                error_category = "none"

            if attempt == 0:
                generation_kind = "initial"
            elif previous_outcome in {"failed", "interrupted"}:
                generation_kind = "retry_failed_stage"
            elif mode == "blueprint":
                generation_kind = "blueprint_preview"
            else:
                generation_kind = "full_regenerate"

            events.append(
                _event(
                    event="generation started",
                    installation_id=installation_id,
                    at=started_at,
                    properties={
                        "mode": mode,
                        "trial_used": trial_used,
                        "generation_kind": generation_kind,
                    },
                )
            )

            if mode == "blueprint":
                memory_outcome = "not_eligible"
            else:
                memory_outcome = (
                    "hit",
                    "miss",
                    "fallback_error",
                    "unavailable",
                )[(index + attempt) % 4]
            finished_at = started_at + timedelta(
                seconds=18 + index * 3 + attempt * 7
            )
            events.append(
                _event(
                    event="generation finished",
                    installation_id=installation_id,
                    at=finished_at,
                    properties={
                        "mode": mode,
                        "outcome": outcome,
                        "duration_ms": int(
                            (finished_at - started_at).total_seconds() * 1000
                        ),
                        "trial_used": trial_used,
                        "memory_outcome": memory_outcome,
                        "error_category": error_category,
                    },
                )
            )
            if attempt == 0:
                first_finished_at = finished_at
                first_mode = mode
            previous_outcome = outcome

        assert first_finished_at is not None
        if index in archive_indices:
            archive_at = first_finished_at + timedelta(minutes=7)
            events.append(
                _event(
                    event="dish archived",
                    installation_id=installation_id,
                    at=archive_at,
                    properties={"mode": first_mode},
                )
            )
            if index in export_indices:
                events.append(
                    _event(
                        event="menu export finished",
                        installation_id=installation_id,
                        at=archive_at + timedelta(minutes=4),
                        properties={
                            "outcome": "succeeded" if index != 9 else "failed",
                            "dish_count_bucket": (
                                "one" if index == 1 else "two_to_five"
                            ),
                        },
                    )
                )

    return events


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _check_enum(
    errors: list[str],
    properties: Mapping[str, Any],
    key: str,
    allowed: frozenset[str],
    location: str,
) -> None:
    value = properties.get(key)
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{location}.{key} has invalid enum value")


def validate_events(events: object) -> list[str]:
    """Return all contract violations found in a generated event list."""

    errors: list[str] = []
    if not isinstance(events, list):
        return ["event dataset must be a JSON list"]

    by_installation: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    insert_ids: set[str] = set()
    parsed_times: dict[int, datetime] = {}
    for index, item in enumerate(events):
        location = f"events[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location} must be an object")
            continue
        if set(item) != _REQUIRED_EVENT_KEYS:
            errors.append(f"{location} has unexpected top-level keys")
        event_name = item.get("event")
        if not isinstance(event_name, str) or event_name not in EVENT_NAMES:
            errors.append(f"{location}.event is not an M10 event name")
            continue
        timestamp = _parse_timestamp(item.get("timestamp"))
        if timestamp is None:
            errors.append(f"{location}.timestamp must be timezone-aware ISO-8601")
        else:
            parsed_times[index] = timestamp
            if timestamp.utcoffset() != timedelta(hours=10):
                errors.append(f"{location}.timestamp must use Australia/Sydney UTC+10")
            if not START_DATE <= timestamp.date() <= END_DATE:
                errors.append(f"{location}.timestamp is outside the M14 date window")

        properties = item.get("properties")
        if not isinstance(properties, dict):
            errors.append(f"{location}.properties must be an object")
            continue
        expected_keys = TRANSPORT_PROPERTIES | EVENT_PROPERTIES[event_name]
        if set(properties) != expected_keys:
            errors.append(f"{location}.properties has unexpected keys")
        if properties.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{location}.schema_version must be 1")
        if properties.get("$process_person_profile") is not False:
            errors.append(f"{location} must disable person profiling")
        if properties.get("pts_data_origin") != ORIGIN:
            errors.append(f"{location}.pts_data_origin is not the M14 source tag")
        insert_id = properties.get("$insert_id")
        if not isinstance(insert_id, str) or not insert_id.startswith("m14_"):
            errors.append(f"{location}.$insert_id must be a seeded deduplication id")
        elif insert_id in insert_ids:
            errors.append(f"{location}.$insert_id must be unique")
        else:
            insert_ids.add(insert_id)

        installation_id = properties.get("distinct_id")
        if not isinstance(installation_id, str):
            errors.append(f"{location}.distinct_id must be a UUIDv4 string")
        else:
            try:
                parsed_id = UUID(installation_id)
            except ValueError:
                parsed_id = None
            if parsed_id is None or parsed_id.version != 4:
                errors.append(f"{location}.distinct_id must be a UUIDv4 string")
            else:
                by_installation[installation_id].append(item)

        if event_name == "generation started":
            _check_enum(errors, properties, "mode", MODES, location)
            _check_enum(errors, properties, "generation_kind", GENERATION_KINDS, location)
            if not isinstance(properties.get("trial_used"), bool):
                errors.append(f"{location}.trial_used must be boolean")
        elif event_name == "generation finished":
            _check_enum(errors, properties, "mode", MODES, location)
            _check_enum(errors, properties, "outcome", GENERATION_OUTCOMES, location)
            _check_enum(errors, properties, "memory_outcome", MEMORY_OUTCOMES, location)
            _check_enum(errors, properties, "error_category", ERROR_CATEGORIES, location)
            duration = properties.get("duration_ms")
            if (
                not isinstance(duration, int)
                or isinstance(duration, bool)
                or not 0 <= duration <= _MAX_DURATION_MS
            ):
                errors.append(f"{location}.duration_ms is outside the valid range")
            if not isinstance(properties.get("trial_used"), bool):
                errors.append(f"{location}.trial_used must be boolean")
        elif event_name == "generation rejected":
            _check_enum(errors, properties, "reason", REJECTION_REASONS, location)
        elif event_name == "dish archived":
            _check_enum(errors, properties, "mode", MODES, location)
        elif event_name == "menu export finished":
            _check_enum(errors, properties, "outcome", EXPORT_OUTCOMES, location)
            _check_enum(errors, properties, "dish_count_bucket", DISH_COUNT_BUCKETS, location)

    if len(by_installation) != INSTALLATION_COUNT:
        errors.append(
            f"dataset must contain exactly {INSTALLATION_COUNT} UUIDv4 installations"
        )

    successful_installations: set[str] = set()
    archived_installations: set[str] = set()
    for installation_id, installation_events in by_installation.items():
        ordered = sorted(
            (
                (parsed_times.get(index), item)
                for index, item in enumerate(events)
                if item in installation_events and index in parsed_times
            ),
            key=lambda pair: pair[0] or datetime.min.replace(tzinfo=SYDNEY_OFFSET),
        )
        app_opened = [item for _, item in ordered if item.get("event") == "app opened"]
        starts = [
            item for _, item in ordered if item.get("event") == "generation started"
        ]
        finishes = [
            item for _, item in ordered if item.get("event") == "generation finished"
        ]
        archives = [
            item for _, item in ordered if item.get("event") == "dish archived"
        ]
        if len(app_opened) != 1:
            errors.append(f"installation {installation_id} must have one app opened event")
        if not 2 <= len(starts) <= 5:
            errors.append(f"installation {installation_id} must have 2-5 generation starts")
        if len(starts) != len(finishes):
            errors.append(f"installation {installation_id} generation starts/finishes are unpaired")
        trial_starts = sum(
            item.get("properties", {}).get("trial_used") is True for item in starts
        )
        if trial_starts > 5:
            errors.append(f"installation {installation_id} exceeds five trial starts")

        paired_count = min(len(starts), len(finishes))
        starts_with_times = [
            (timestamp, item)
            for timestamp, item in ordered
            if item.get("event") == "generation started"
        ]
        finishes_with_times = [
            (timestamp, item)
            for timestamp, item in ordered
            if item.get("event") == "generation finished"
        ]
        for pair_index in range(paired_count):
            started_at, started = starts_with_times[pair_index]
            finished_at, finished = finishes_with_times[pair_index]
            if started_at is None or finished_at is None or started_at >= finished_at:
                errors.append(f"installation {installation_id} has invalid generation pairing")
            started_properties = started.get("properties", {})
            finished_properties = finished.get("properties", {})
            if started_properties.get("mode") != finished_properties.get("mode"):
                errors.append(f"installation {installation_id} has mismatched generation modes")
            if started_properties.get("trial_used") != finished_properties.get("trial_used"):
                errors.append(f"installation {installation_id} has mismatched trial flags")
            previous_outcome = (
                finishes_with_times[pair_index - 1][1]
                .get("properties", {})
                .get("outcome")
                if pair_index > 0
                else None
            )
            if (
                started_properties.get("generation_kind") == "retry_failed_stage"
                and previous_outcome not in {"failed", "interrupted"}
            ):
                errors.append(
                    f"installation {installation_id} retries only after a failed or interrupted attempt"
                )
            duration = finished_properties.get("duration_ms")
            if (
                isinstance(started_at, datetime)
                and isinstance(finished_at, datetime)
                and isinstance(duration, int)
                and not isinstance(duration, bool)
            ):
                actual_duration_ms = int(
                    (finished_at - started_at).total_seconds() * 1000
                )
                if duration != actual_duration_ms:
                    errors.append(
                        f"installation {installation_id} has a duration_ms/timestamp mismatch"
                    )

        successful_finishes = [
            (timestamp, item)
            for timestamp, item in ordered
            if item.get("event") == "generation finished"
            and item.get("properties", {}).get("outcome") == "succeeded"
        ]
        if successful_finishes:
            successful_installations.add(installation_id)
        else:
            errors.append(f"installation {installation_id} has no successful generation")
        if archives:
            archived_installations.add(installation_id)
            archive_times = [
                archive_timestamp
                for archive_timestamp, archive_event in ordered
                if archive_event.get("event") == "dish archived"
                and archive_timestamp is not None
            ]
            successful_time = successful_finishes[0][0] if successful_finishes else None
            if not successful_finishes or successful_time is None or any(
                archive_timestamp <= successful_time
                for archive_timestamp in archive_times
            ):
                errors.append(f"installation {installation_id} archives before success")

    if not archived_installations:
        errors.append("dataset must include archive events")
    if not any(item.get("event") == "menu export finished" for item in events if isinstance(item, dict)):
        errors.append("dataset must include menu export events")
    if successful_installations:
        archive_ratio = len(archived_installations) / len(successful_installations)
        if archive_ratio >= 0.60:
            errors.append("successful-generation to archive funnel must be below 60%")

    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="path for the generated PostHog JSON event list",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    events = generate_events()
    errors = validate_events(events)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(events)} events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["generate_events", "main", "validate_events"]
