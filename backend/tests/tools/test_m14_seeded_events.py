"""Focused contract tests for the local M14 PostHog fixture."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.telemetry.m14_seeded_events import (  # noqa: E402
    END_DATE,
    ORIGIN,
    START_DATE,
    generate_events,
    main,
    validate_events,
)


def _by_installation(events: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for event in events:
        properties = event["properties"]
        assert isinstance(properties, dict)
        installation_id = properties["distinct_id"]
        assert isinstance(installation_id, str)
        grouped.setdefault(installation_id, []).append(event)
    return grouped


def test_fixture_is_deterministic_and_validates() -> None:
    first = generate_events()
    second = generate_events()

    assert first == second
    assert validate_events(first) == []
    assert len(_by_installation(first)) == 12
    assert all(UUID(value).version == 4 for value in _by_installation(first))
    insert_ids = {
        event["properties"]["$insert_id"]  # type: ignore[index]
        for event in first
    }
    assert len(insert_ids) == len(first)


def test_installations_have_paired_attempts_trial_limits_and_dashboard_coverage() -> None:
    events = generate_events()
    grouped = _by_installation(events)
    event_dates = [datetime.fromisoformat(item["timestamp"]).date() for item in events]  # type: ignore[arg-type]

    assert min(event_dates) >= START_DATE
    assert max(event_dates) <= END_DATE
    assert any(day >= datetime(2026, 9, 17).date() for day in event_dates)
    assert any(
        item["event"] == "generation started"
        and datetime.fromisoformat(item["timestamp"]).date()
        >= datetime(2026, 9, 17).date()
        for item in events
    )

    outcomes: set[str] = set()
    memories: set[str] = set()
    archived_ids: set[str] = set()
    successful_ids: set[str] = set()
    for installation_id, installation_events in grouped.items():
        names = [item["event"] for item in installation_events]
        assert names.count("app opened") == 1
        assert 2 <= names.count("generation started") <= 5
        assert names.count("generation started") == names.count("generation finished")
        starts = [item for item in installation_events if item["event"] == "generation started"]
        finishes = [item for item in installation_events if item["event"] == "generation finished"]
        assert sum(item["properties"]["trial_used"] is True for item in starts) <= 5  # type: ignore[index]
        assert all(
            start["properties"]["trial_used"] == finish["properties"]["trial_used"]  # type: ignore[index]
            for start, finish in zip(starts, finishes, strict=True)
        )
        previous_outcome: str | None = None
        for start, finish in zip(starts, finishes, strict=True):
            if start["properties"]["generation_kind"] == "retry_failed_stage":  # type: ignore[index]
                assert previous_outcome in {"failed", "interrupted"}
            start_at = datetime.fromisoformat(start["timestamp"])  # type: ignore[arg-type]
            finish_at = datetime.fromisoformat(finish["timestamp"])  # type: ignore[arg-type]
            assert finish["properties"]["duration_ms"] == int(  # type: ignore[index]
                (finish_at - start_at).total_seconds() * 1000
            )
            previous_outcome = finish["properties"]["outcome"]  # type: ignore[index]
        for finish in finishes:
            properties = finish["properties"]
            outcomes.add(properties["outcome"])  # type: ignore[index]
            memories.add(properties["memory_outcome"])  # type: ignore[index]
            if properties["outcome"] == "succeeded":  # type: ignore[index]
                successful_ids.add(installation_id)
        if "dish archived" in names:
            archived_ids.add(installation_id)

    assert {"succeeded", "failed", "cancelled", "interrupted"} <= outcomes
    assert {"hit", "miss", "fallback_error", "not_eligible", "unavailable"} <= memories
    assert archived_ids
    assert len(archived_ids) / len(successful_ids) < 0.60
    assert any(item["event"] == "menu export finished" for item in events)


def test_every_event_has_exact_transport_source_and_no_private_fields() -> None:
    events = generate_events()
    serialized = json.dumps(events, ensure_ascii=False).lower()
    forbidden = (
        "prompt",
        "provider",
        "model",
        "path",
        "ip",
        "geo",
        "email",
        "username",
        "draft_id",
        "attempt_id",
        "canonical_id",
        "ingredient",
    )
    assert not any(term in serialized for term in forbidden)

    for event in events:
        properties = event["properties"]
        assert properties["schema_version"] == 1  # type: ignore[index]
        assert properties["$process_person_profile"] is False  # type: ignore[index]
        assert properties["pts_data_origin"] == ORIGIN  # type: ignore[index]
        assert UUID(properties["distinct_id"]).version == 4  # type: ignore[index]
        assert str(properties["$insert_id"]).startswith("m14_")  # type: ignore[index]


def _mutate_retry_transition(events: list[dict[str, object]]) -> None:
    starts = [event for event in events if event["event"] == "generation started"]
    starts[1]["properties"]["generation_kind"] = "retry_failed_stage"  # type: ignore[index]


def _mutate_duration(events: list[dict[str, object]]) -> None:
    finish = next(event for event in events if event["event"] == "generation finished")
    finish["properties"]["duration_ms"] = 1  # type: ignore[index]


@pytest.mark.parametrize(
    "mutate",
    (
        lambda events: events[0]["properties"].update(pts_data_origin="wrong"),
        lambda events: events[0]["properties"].update(prompt="raw content"),
        lambda events: events[0].update(timestamp="2026-08-31T23:59:00+10:00"),
        lambda events: events[0]["properties"].update(schema_version=2),
        _mutate_retry_transition,
        _mutate_duration,
    ),
)
def test_validator_rejects_wrong_dataset(mutate: object) -> None:
    events = copy.deepcopy(generate_events())
    assert callable(mutate)
    mutate(events)  # type: ignore[operator]
    assert validate_events(events)


def test_cli_writes_the_valid_json_list(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "m14-events.json"
    assert main(["--output", str(output)]) == 0
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded == generate_events()
