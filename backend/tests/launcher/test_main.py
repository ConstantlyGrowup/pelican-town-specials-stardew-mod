from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from pelican_town_specials.launcher.instance import RuntimeRecord
from pelican_town_specials.launcher.main import LauncherDependencies, run_launcher


class FakeLock:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.released = False

    def acquire(self) -> bool:
        return self.acquired

    def release(self) -> None:
        self.released = True


class RaisingAcquireLock(FakeLock):
    def acquire(self) -> bool:
        raise OSError("lock secret")


class FakeRecordStore:
    def __init__(self, record: RuntimeRecord | None = None) -> None:
        self.record = record
        self.writes: list[RuntimeRecord] = []
        self.cleared = False
        self.cleared_matches: list[RuntimeRecord] = []

    def read(self) -> RuntimeRecord | None:
        return self.record

    def write(self, record: RuntimeRecord) -> None:
        self.record = record
        self.writes.append(record)

    def clear(self) -> None:
        self.record = None
        self.cleared = True

    def clear_if_matches(self, record: RuntimeRecord) -> bool:
        self.cleared_matches.append(record)
        if self.record != record:
            return False
        self.record = None
        return True


class FakeHealthProbe:
    def __init__(
        self,
        unhealthy_urls: set[str] | None = None,
        error_message: str = "not ready",
    ) -> None:
        self.unhealthy_urls = unhealthy_urls or set()
        self.error_message = error_message
        self.urls: list[str] = []

    def wait_until_ready(self, url: str, timeout_seconds: float) -> None:
        del timeout_seconds
        self.urls.append(url)
        if url in self.unhealthy_urls:
            raise TimeoutError(self.error_message)


class FakeServer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.waited = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def wait(self) -> None:
        self.waited = True


class FailingWaitServer(FakeServer):
    def wait(self) -> None:
        self.waited = True
        raise RuntimeError("wait failed")


class FailingStopAndWaitServer(FakeServer):
    def stop(self) -> None:
        self.stopped = True
        raise RuntimeError("stop failed")

    def wait(self) -> None:
        self.waited = True
        raise RuntimeError("wait failed")


class FailingStopAndWaitServerRunner:
    def __init__(self) -> None:
        self.server = FailingStopAndWaitServer()

    def __call__(
        self,
        _app: FastAPI,
        _host: str,
        _port: int,
        _reservation: object,
    ) -> FailingStopAndWaitServer:
        return self.server


class FailingServerRunner:
    def __init__(self) -> None:
        self.server = FailingWaitServer()

    def __call__(
        self,
        _app: FastAPI,
        _host: str,
        _port: int,
        _reservation: object,
    ) -> FailingWaitServer:
        return self.server


class FakePortReservation:
    def __init__(self, port: int) -> None:
        self.port = port
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeServerRunner:
    def __init__(self) -> None:
        self.servers: list[FakeServer] = []
        self.apps: list[FastAPI] = []
        self.addresses: list[tuple[str, int]] = []
        self.reservations: list[object] = []

    def __call__(
        self,
        app: FastAPI,
        host: str,
        port: int,
        reservation: object,
    ) -> FakeServer:
        self.apps.append(app)
        self.addresses.append((host, port))
        self.reservations.append(reservation)
        server = FakeServer()
        self.servers.append(server)
        return server


def test_first_instance_starts_health_checks_opens_launch_url_and_cleans_up(
    tmp_path: Path,
) -> None:
    lock = FakeLock(acquired=True)
    records = FakeRecordStore()
    health = FakeHealthProbe()
    server_runner = FakeServerRunner()
    opened_urls: list[str] = []
    dependencies = _dependencies(
        static_dir=_static_dir(tmp_path),
        lock=lock,
        records=records,
        health=health,
        server_runner=server_runner,
        open_browser=opened_urls.append,
    )

    result = run_launcher(
        ["--workspace", str(tmp_path / "workspace"), "--port", "43127"],
        dependencies=dependencies,
    )

    assert result == 0
    assert server_runner.addresses == [("127.0.0.1", 43127)]
    assert len(server_runner.reservations) == 1
    assert server_runner.reservations[0].closed is True
    assert health.urls == ["http://127.0.0.1:43127/"]
    assert len(records.writes) == 1
    assert records.writes[0].url == "http://127.0.0.1:43127/"
    assert opened_urls and opened_urls[0].startswith(
        "http://127.0.0.1:43127/#launch="
    )
    assert records.record is None
    assert lock.released is True
    assert server_runner.servers[0].stopped is True
    assert server_runner.servers[0].waited is True


def test_second_instance_reuses_healthy_runtime_without_starting_another_server(
    tmp_path: Path,
) -> None:
    existing = _runtime_record(port=43128)
    lock = FakeLock(acquired=False)
    records = FakeRecordStore(existing)
    health = FakeHealthProbe()
    server_runner = FakeServerRunner()
    opened_urls: list[str] = []

    result = run_launcher(
        ["--workspace", str(tmp_path / "workspace")],
        dependencies=_dependencies(
            static_dir=_static_dir(tmp_path),
            lock=lock,
            records=records,
            health=health,
            server_runner=server_runner,
            open_browser=opened_urls.append,
        ),
    )

    assert result == 0
    assert health.urls == [existing.url]
    assert opened_urls == [existing.url]
    assert server_runner.servers == []
    assert records.record == existing
    assert lock.released is False


def test_owner_clears_unhealthy_stale_record_before_starting_new_server(
    tmp_path: Path,
) -> None:
    stale = _runtime_record(port=43128)
    records = FakeRecordStore(stale)
    health = FakeHealthProbe(unhealthy_urls={stale.url})
    server_runner = FakeServerRunner()

    result = run_launcher(
        ["--workspace", str(tmp_path / "workspace"), "--port", "43127"],
        dependencies=_dependencies(
            static_dir=_static_dir(tmp_path),
            lock=FakeLock(acquired=True),
            records=records,
            health=health,
            server_runner=server_runner,
        ),
    )

    assert result == 0
    assert records.cleared is True
    assert health.urls == [stale.url, "http://127.0.0.1:43127/"]
    assert server_runner.addresses == [("127.0.0.1", 43127)]
    assert len(server_runner.reservations) == 1
    assert server_runner.reservations[0].closed is True


def test_no_browser_and_exit_after_health_check_stop_server_and_cleanup(
    tmp_path: Path,
) -> None:
    lock = FakeLock(acquired=True)
    records = FakeRecordStore()
    server_runner = FakeServerRunner()
    opened_urls: list[str] = []

    result = run_launcher(
        [
            "--workspace",
            str(tmp_path / "workspace"),
            "--port",
            "43127",
            "--no-browser",
            "--exit-after-health-check",
        ],
        dependencies=_dependencies(
            static_dir=_static_dir(tmp_path),
            lock=lock,
            records=records,
            health=FakeHealthProbe(),
            server_runner=server_runner,
            open_browser=opened_urls.append,
        ),
    )

    assert result == 0
    assert opened_urls == []
    assert server_runner.servers[0].stopped is True
    assert server_runner.servers[0].waited is True
    assert records.record is None
    assert lock.released is True


def test_missing_static_assets_returns_nonzero_without_starting_server(
    tmp_path: Path,
) -> None:
    server_runner = FakeServerRunner()

    result = run_launcher(
        ["--workspace", str(tmp_path / "workspace"), "--port", "43127"],
        dependencies=_dependencies(
            static_dir=tmp_path / "missing-dist",
            lock=FakeLock(acquired=True),
            records=FakeRecordStore(),
            health=FakeHealthProbe(),
            server_runner=server_runner,
        ),
    )

    assert result == 1
    assert server_runner.servers == []


def test_health_failure_writes_sanitized_launcher_error(
    tmp_path: Path,
    capsys: object,
) -> None:
    workspace = tmp_path / "workspace"
    secret_text = "secret-launch-token"
    result = run_launcher(
        ["--workspace", str(workspace), "--port", "43127"],
        dependencies=_dependencies(
            static_dir=_static_dir(tmp_path),
            lock=FakeLock(acquired=True),
            records=FakeRecordStore(),
            health=FakeHealthProbe(
                unhealthy_urls={"http://127.0.0.1:43127/"},
                error_message=secret_text,
            ),
            server_runner=FakeServerRunner(),
        ),
    )

    assert result == 1
    error_log = workspace / "app-state" / "launcher-error.log"
    assert error_log.is_file()
    log_text = error_log.read_text(encoding="utf-8")
    assert "PTS_LAUNCHER_START_FAILED" in log_text
    assert secret_text not in log_text
    captured = capsys.readouterr()
    assert "launcher-error.log" in captured.err
    assert secret_text not in captured.err


def test_cleanup_continues_when_server_wait_fails(tmp_path: Path) -> None:
    lock = FakeLock(acquired=True)
    server_runner = FailingServerRunner()
    reservation = FakePortReservation(43127)
    workspace = tmp_path / "workspace"
    dependencies = LauncherDependencies(
        instance_lock_factory=lambda _workspace: lock,
        runtime_record_store_factory=lambda _workspace: FakeRecordStore(),
        reserve_port=lambda _preferred: reservation,
        open_browser=lambda _url: None,
        wait_for_health=FakeHealthProbe().wait_until_ready,
        server_runner=server_runner,  # type: ignore[arg-type]
        static_dir=_static_dir(tmp_path),
        process_id=lambda: 1234,
        utcnow=lambda: datetime(2026, 8, 3, 12, tzinfo=UTC),
    )

    result = run_launcher(
        [
            "--workspace",
            str(workspace),
            "--port",
            "43127",
            "--no-browser",
            "--exit-after-health-check",
        ],
        dependencies=dependencies,
    )

    assert result == 0
    assert server_runner.server.waited is True
    assert reservation.closed is True
    assert lock.released is True


def test_lock_acquisition_failure_writes_launcher_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    result = run_launcher(
        ["--workspace", str(workspace), "--port", "43127"],
        dependencies=_dependencies(
            static_dir=_static_dir(tmp_path),
            lock=RaisingAcquireLock(acquired=True),
            records=FakeRecordStore(),
            health=FakeHealthProbe(),
            server_runner=FakeServerRunner(),
        ),
    )

    assert result == 1
    error_log = workspace / "app-state" / "launcher-error.log"
    assert error_log.is_file()
    assert "PTS_LAUNCHER_START_FAILED" in error_log.read_text(encoding="utf-8")


def test_contended_instance_without_runtime_record_writes_launcher_error(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    result = run_launcher(
        ["--workspace", str(workspace)],
        dependencies=_dependencies(
            static_dir=_static_dir(tmp_path),
            lock=FakeLock(acquired=False),
            records=FakeRecordStore(),
            health=FakeHealthProbe(),
            server_runner=FakeServerRunner(),
        ),
    )

    assert result == 1
    error_log = workspace / "app-state" / "launcher-error.log"
    assert error_log.is_file()
    assert "PTS_LAUNCHER_START_FAILED" in error_log.read_text(encoding="utf-8")


def test_cleanup_continues_when_server_stop_and_wait_fail(tmp_path: Path) -> None:
    lock = FakeLock(acquired=True)
    server_runner = FailingStopAndWaitServerRunner()
    reservation = FakePortReservation(43127)
    workspace = tmp_path / "workspace"
    dependencies = LauncherDependencies(
        instance_lock_factory=lambda _workspace: lock,
        runtime_record_store_factory=lambda _workspace: FakeRecordStore(),
        reserve_port=lambda _preferred: reservation,
        open_browser=lambda _url: None,
        wait_for_health=FakeHealthProbe().wait_until_ready,
        server_runner=server_runner,  # type: ignore[arg-type]
        static_dir=_static_dir(tmp_path),
        process_id=lambda: 1234,
        utcnow=lambda: datetime(2026, 8, 3, 12, tzinfo=UTC),
    )

    result = run_launcher(
        [
            "--workspace",
            str(workspace),
            "--port",
            "43127",
            "--no-browser",
            "--exit-after-health-check",
        ],
        dependencies=dependencies,
    )

    assert result == 0
    assert server_runner.server.stopped is True
    assert server_runner.server.waited is True
    assert reservation.closed is True
    assert lock.released is True


def _dependencies(
    *,
    static_dir: Path,
    lock: FakeLock,
    records: FakeRecordStore,
    health: FakeHealthProbe,
    server_runner: FakeServerRunner,
    open_browser: Callable[[str], None] | None = None,
) -> LauncherDependencies:
    return LauncherDependencies(
        instance_lock_factory=lambda _workspace: lock,
        runtime_record_store_factory=lambda _workspace: records,
        reserve_port=lambda preferred: FakePortReservation(preferred[0]),
        open_browser=open_browser or (lambda _url: None),
        wait_for_health=health.wait_until_ready,
        server_runner=server_runner,
        static_dir=static_dir,
        process_id=lambda: 1234,
        utcnow=lambda: datetime(2026, 8, 3, 12, tzinfo=UTC),
    )


def _static_dir(tmp_path: Path) -> Path:
    static_dir = tmp_path / "dist"
    static_dir.mkdir(exist_ok=True)
    (static_dir / "index.html").write_text("<main>Test app</main>", encoding="utf-8")
    return static_dir


def _runtime_record(port: int) -> RuntimeRecord:
    return RuntimeRecord(
        pid=4321,
        port=port,
        url=f"http://127.0.0.1:{port}/",
        started_at=datetime(2026, 8, 3, 11, tzinfo=UTC),
    )
