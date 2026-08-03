from __future__ import annotations

import argparse
import os
import socket
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread
from typing import Protocol, cast

import uvicorn
from fastapi import FastAPI

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.routes.app_control import ActivityTracker
from pelican_town_specials.api.security import SecurityConfig, SecurityState
from pelican_town_specials.config import AppConfig
from pelican_town_specials.persistence.workspace import WorkspacePaths

from .instance import InstanceLock, RuntimeRecord, RuntimeRecordStore
from .runtime import BrowserOpener, HealthProbe, PortAllocator, PortReservation

_HOST = "127.0.0.1"
_HEALTH_TIMEOUT_SECONDS = 10.0
_PREFERRED_PORTS = (43127, 43128, 43129)
_MISSING_ASSETS_CODE = "PTS_SYSTEM_WEB_ASSETS_MISSING"
_LAUNCHER_START_FAILED_CODE = "PTS_LAUNCHER_START_FAILED"
_LAUNCHER_ERROR_LOG = "launcher-error.log"


class ServerControl(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def wait(self) -> None: ...


ServerRunner = Callable[[FastAPI, str, int, PortReservation], ServerControl]
LockFactory = Callable[[WorkspacePaths], InstanceLock]
RecordStoreFactory = Callable[[WorkspacePaths], RuntimeRecordStore]
ReservePort = Callable[[Sequence[int]], PortReservation]
OpenBrowser = Callable[[str], None]
WaitForHealth = Callable[[str, float], None]


class UvicornServer:
    """Runs Uvicorn in a background thread so launcher orchestration stays testable."""

    def __init__(
        self,
        application: FastAPI,
        host: str,
        port: int,
        reservation: PortReservation,
    ) -> None:
        self._reservation = reservation
        self._server = uvicorn.Server(
            uvicorn.Config(application, host=host, port=port, access_log=False)
        )
        self._thread = Thread(
            target=lambda: self._server.run(
                sockets=[cast(socket.socket, self._reservation.socket)]
            ),
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True

    def wait(self) -> None:
        self._thread.join()


@dataclass(frozen=True, slots=True)
class LauncherDependencies:
    instance_lock_factory: LockFactory = lambda workspace: InstanceLock(
        workspace.app_state_dir / "launcher.lock"
    )
    runtime_record_store_factory: RecordStoreFactory = lambda workspace: RuntimeRecordStore(
        workspace.app_state_dir / "runtime.json"
    )
    reserve_port: ReservePort = field(default_factory=lambda: PortAllocator().reserve)
    open_browser: OpenBrowser = field(default_factory=lambda: BrowserOpener().open)
    wait_for_health: WaitForHealth = field(
        default_factory=lambda: HealthProbe().wait_until_ready
    )
    server_runner: ServerRunner = UvicornServer
    static_dir: Path = field(default_factory=lambda: _default_static_dir())
    process_id: Callable[[], int] = os.getpid
    utcnow: Callable[[], datetime] = lambda: datetime.now(UTC)


def main(argv: Sequence[str] | None = None) -> int:
    return run_launcher(argv, dependencies=LauncherDependencies())


def run_launcher(
    argv: Sequence[str] | None = None,
    *,
    dependencies: LauncherDependencies,
) -> int:
    args = _parse_args(argv)
    workspace_root = args.workspace or AppConfig().workspace_path
    try:
        workspace = WorkspacePaths.create(workspace_root)
    except (OSError, RuntimeError, ValueError):
        _report_launcher_failure(
            None,
            _LAUNCHER_START_FAILED_CODE,
            "无法创建本地工作区。",
        )
        return 1
    instance_lock: InstanceLock | None = None
    try:
        instance_lock = dependencies.instance_lock_factory(workspace)
        record_store = dependencies.runtime_record_store_factory(workspace)
        lock_acquired = instance_lock.acquire()
    except Exception as error:  # noqa: BLE001
        if instance_lock is not None:
            _safe_cleanup(instance_lock.release)
        _report_launcher_failure(
            workspace,
            _LAUNCHER_START_FAILED_CODE,
            _failure_message(error),
        )
        return 1

    if not lock_acquired:
        return _reuse_existing_instance(
            args.no_browser,
            record_store,
            dependencies,
            workspace,
        )

    server: ServerControl | None = None
    reservation: PortReservation | None = None
    owned_record: RuntimeRecord | None = None
    try:
        existing_record = record_store.read()
        if existing_record is not None:
            try:
                dependencies.wait_for_health(
                    existing_record.url,
                    _HEALTH_TIMEOUT_SECONDS,
                )
            except (OSError, TimeoutError, ValueError):
                record_store.clear()
            else:
                if not args.no_browser:
                    dependencies.open_browser(existing_record.url)
                return 0

        _require_static_assets(dependencies.static_dir)
        reservation = dependencies.reserve_port(
            (args.port,) if args.port is not None else _PREFERRED_PORTS
        )
        port = reservation.port
        url = f"http://{_HOST}:{port}/"
        security_state = SecurityState(
            config=SecurityConfig(expected_port=port),
        )
        launch_token = security_state.issue_launch_token()
        server_holder: list[ServerControl | None] = [None]
        activity_tracker = ActivityTracker(
            shutdown_callback=lambda: _stop_server(server_holder[0]),
        )
        application = create_app(
            AppConfig(workspace_path=workspace.root),
            workspace_paths=workspace,
            security_state=security_state,
            static_dir=dependencies.static_dir,
            activity_tracker=activity_tracker,
            enable_docs=False,
            enforce_local_host=True,
        )
        server = dependencies.server_runner(application, _HOST, port, reservation)
        server_holder[0] = server
        server.start()
        dependencies.wait_for_health(url, _HEALTH_TIMEOUT_SECONDS)
        owned_record = RuntimeRecord(
            pid=dependencies.process_id(),
            port=port,
            url=url,
            started_at=dependencies.utcnow(),
        )
        record_store.write(owned_record)

        if args.exit_after_health_check:
            return 0
        if not args.no_browser:
            dependencies.open_browser(f"{url}#launch={launch_token}")
        server.wait()
        return 0
    except _MissingStaticAssets:
        _report_launcher_failure(
            workspace,
            _MISSING_ASSETS_CODE,
            "应用界面资源不可用，请重新安装应用后再试。",
        )
        return 1
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        _report_launcher_failure(
            workspace,
            _LAUNCHER_START_FAILED_CODE,
            _failure_message(error),
        )
        return 1
    finally:
        if owned_record is not None:
            _safe_cleanup(lambda: record_store.clear_if_matches(owned_record))
        if server is not None:
            _safe_cleanup(server.stop)
            _safe_cleanup(server.wait)
        if reservation is not None:
            _safe_cleanup(reservation.close)
        _safe_cleanup(instance_lock.release)


def _safe_cleanup(action: Callable[[], object]) -> None:
    try:
        action()
    except Exception:  # noqa: BLE001
        return


def _failure_message(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "本地服务 health 检查超时。"
    if isinstance(error, OSError):
        return "本地服务或工作区无法访问。"
    if isinstance(error, ValueError):
        return "本地启动配置无效。"
    if isinstance(error, RuntimeError):
        return "本地服务启动失败。"
    return "本地应用启动失败。"


def _report_launcher_failure(
    workspace: WorkspacePaths | None,
    code: str,
    message: str,
) -> None:
    log_path: Path | None = None
    if workspace is not None:
        log_path = workspace.app_state_dir / _LAUNCHER_ERROR_LOG
        try:
            log_path.write_text(f"{code}" + chr(10) + f"{message}" + chr(10), encoding="utf-8")
        except OSError:
            log_path = None
    output = f"{code}: {message}"
    if log_path is not None:
        output += f" 日志：{log_path}"
    print(output, file=sys.stderr)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Pelican Town Specials locally")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--port", type=_valid_port)
    parser.add_argument("--exit-after-health-check", action="store_true")
    return parser.parse_args(argv)


def _valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= port <= 65_535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _reuse_existing_instance(
    no_browser: bool,
    record_store: RuntimeRecordStore,
    dependencies: LauncherDependencies,
    workspace: WorkspacePaths,
) -> int:
    try:
        record = record_store.read()
        if record is None:
            _report_launcher_failure(
                workspace,
                _LAUNCHER_START_FAILED_CODE,
                "已有实例正在启动或运行记录不可用。",
            )
            return 1
        dependencies.wait_for_health(record.url, _HEALTH_TIMEOUT_SECONDS)
        if not no_browser:
            dependencies.open_browser(record.url)
        return 0
    except Exception as error:  # noqa: BLE001
        _report_launcher_failure(
            workspace,
            _LAUNCHER_START_FAILED_CODE,
            _failure_message(error),
        )
        return 1


class _MissingStaticAssets(Exception):
    pass


def _require_static_assets(static_dir: Path) -> None:
    try:
        resolved_root = static_dir.resolve()
        index_file = (resolved_root / "index.html").resolve()
    except (OSError, RuntimeError) as error:
        raise _MissingStaticAssets from error
    if (
        not resolved_root.is_dir()
        or not index_file.is_file()
        or not index_file.is_relative_to(resolved_root)
    ):
        raise _MissingStaticAssets


def _stop_server(server: ServerControl | None) -> None:
    if server is not None:
        server.stop()


def _default_static_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "frontend" / "dist"
    return Path(__file__).resolve().parents[4] / "frontend" / "dist"


if __name__ == "__main__":
    raise SystemExit(main())
