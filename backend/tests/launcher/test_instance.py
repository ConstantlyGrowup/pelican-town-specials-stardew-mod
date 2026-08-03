from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pelican_town_specials.launcher.instance import (
    InstanceLock,
    RuntimeRecord,
    RuntimeRecordStore,
)


def test_instance_lock_reports_contention_without_removing_first_lock(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "runtime" / "application.lock"
    first_lock = InstanceLock(lock_path)
    second_lock = InstanceLock(lock_path)

    assert first_lock.acquire() is True
    assert second_lock.acquire() is False
    assert lock_path.exists()

    first_lock.release()
    assert second_lock.acquire() is True
    second_lock.release()


def test_runtime_record_store_round_trips_atomic_json(tmp_path: Path) -> None:
    store = RuntimeRecordStore(tmp_path / "runtime" / "runtime.json")
    record = RuntimeRecord(
        pid=1234,
        port=43127,
        url="http://127.0.0.1:43127/",
        started_at=datetime(2026, 8, 3, 8, 30, tzinfo=UTC),
    )

    store.write(record)

    assert store.read() == record


def test_runtime_record_store_rejects_malformed_json_safely(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "runtime.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    assert RuntimeRecordStore(path).read() is None


@pytest.mark.parametrize(
    "payload",
    [
        '{"pid": 0, "port": 43127, "url": "http://127.0.0.1:43127/", "startedAt": "2026-08-03T08:30:00Z"}',
        '{"pid": 1234, "port": 0, "url": "http://127.0.0.1:43127/", "startedAt": "2026-08-03T08:30:00Z"}',
        '{"pid": 1234, "port": 43127, "url": "https://example.test/", "startedAt": "2026-08-03T08:30:00Z"}',
        '{"pid": 1234, "port": 43127, "url": "http://127.0.0.1:43127/", "startedAt": "invalid"}',
    ],
)
def test_runtime_record_store_rejects_invalid_runtime_fields_safely(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / "runtime" / "runtime.json"
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")

    assert RuntimeRecordStore(path).read() is None


def test_runtime_record_cleanup_removes_only_owned_record(tmp_path: Path) -> None:
    store = RuntimeRecordStore(tmp_path / "runtime" / "runtime.json")
    ours = RuntimeRecord(
        pid=1234,
        port=43127,
        url="http://localhost:43127/",
        started_at=datetime(2026, 8, 3, 8, 30, tzinfo=UTC),
    )
    another = RuntimeRecord(
        pid=5678,
        port=43128,
        url="http://127.0.0.1:43128/",
        started_at=datetime(2026, 8, 3, 8, 31, tzinfo=UTC),
    )
    store.write(ours)

    assert store.clear_if_matches(another) is False
    assert store.read() == ours
    assert store.clear_if_matches(ours) is True
    assert store.read() is None
