from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import portalocker

from pelican_town_specials.persistence.telemetry_state import TelemetryStateStore


def test_state_store_creates_and_reuses_a_uuid4_atomically(tmp_path: Path) -> None:
    path = tmp_path / "app-state" / "telemetry-state.json"
    store = TelemetryStateStore(path)

    first = store.ensure_state()
    assert first is not None
    assert first.installation_id.version == 4
    assert first.last_daily_open_date is None
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "installationId": str(first.installation_id),
        "lastDailyOpenDate": None,
        "schemaVersion": 1,
    }

    restarted = TelemetryStateStore(path).ensure_state()
    assert restarted is not None
    assert restarted.installation_id == first.installation_id


def test_state_store_claims_one_open_per_local_day_and_allows_the_next_day(
    tmp_path: Path,
) -> None:
    store = TelemetryStateStore(tmp_path / "telemetry-state.json")
    today = date(2026, 8, 27)

    assert store.claim_daily_open(today) is True
    assert store.claim_daily_open(today) is False
    assert store.claim_daily_open(today + timedelta(days=1)) is True

    state = store.read()
    assert state is not None
    assert state.last_daily_open_date == today + timedelta(days=1)


def test_concurrent_claims_are_serialized_by_the_adjacent_lock_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "app-state" / "telemetry-state.json"
    today = date(2026, 8, 27)

    def claim() -> bool:
        return TelemetryStateStore(path).claim_daily_open(today)

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(lambda _index: claim(), range(12)))

    assert results.count(True) == 1
    assert results.count(False) == 11


def test_lock_contention_fails_open_immediately_without_overwriting_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "telemetry-state.json"
    store = TelemetryStateStore(path)
    state = store.ensure_state()
    assert state is not None
    before = path.read_text(encoding="utf-8")

    acquired = threading.Event()
    release = threading.Event()
    holder_errors: list[Exception] = []

    def hold_sidecar_lock() -> None:
        try:
            with portalocker.Lock(
                store.lock_path,
                mode="a+",
                timeout=0,
                fail_when_locked=True,
            ):
                acquired.set()
                release.wait(timeout=2)
        except (OSError, portalocker.exceptions.LockException) as exc:
            holder_errors.append(exc)

    holder = threading.Thread(target=hold_sidecar_lock)
    holder.start()
    try:
        assert acquired.wait(timeout=2)
        started = time.monotonic()
        assert store.ensure_state() is None
        assert store.claim_daily_open(date(2026, 8, 27)) is False
        assert time.monotonic() - started < 0.5
        assert path.read_text(encoding="utf-8") == before
    finally:
        release.set()
        holder.join(timeout=2)

    assert not holder.is_alive()
    assert holder_errors == []


def test_unknown_schema_and_corrupt_state_fail_open_without_overwriting_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "telemetry-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        '{"schemaVersion": 2, "installationId": "00000000-0000-4000-8000-000000000000"}',
        encoding="utf-8",
    )
    store = TelemetryStateStore(path)
    assert store.ensure_state() is None
    assert store.claim_daily_open(date(2026, 8, 27)) is False
    assert path.read_text(encoding="utf-8").startswith('{"schemaVersion": 2')

    path.write_text("not-json", encoding="utf-8")
    assert store.ensure_state() is None
    assert store.installation_id() is None
    assert store.claim_daily_open(date(2026, 8, 27)) is False
