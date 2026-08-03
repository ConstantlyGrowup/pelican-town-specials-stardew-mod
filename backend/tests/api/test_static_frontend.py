from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from threading import Event
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.routes.app_control import ActivityTracker
from pelican_town_specials.api.security import SecurityConfig, SecurityState
from pelican_town_specials.persistence.workspace import WorkspacePaths


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def static_client(tmp_path: Path) -> Iterator[tuple[TestClient, ActivityTracker, FakeClock]]:
    dist_dir = tmp_path / "dist"
    asset_dir = dist_dir / "assets"
    asset_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<main>Pelican Town Specials</main>")
    (asset_dir / "app.css").write_text("body { color: green; }")

    clock = FakeClock()
    tracker = ActivityTracker(clock=clock)
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=None,
            allowed_origins=frozenset({"http://testserver"}),
        ),
        clock=clock,
    )
    application = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
        static_dir=dist_dir,
        activity_tracker=tracker,
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client, tracker, clock


def _application(client: TestClient) -> FastAPI:
    return cast(FastAPI, client.app)


def _bootstrap(client: TestClient) -> str:
    security = cast(SecurityState, _application(client).state.security)
    response = client.post(
        "/session/bootstrap",
        headers={"Host": "testserver"},
        json={"launchToken": security.issue_launch_token()},
    )
    assert response.status_code == 204
    return response.headers["x-pts-csrf"]


def _mutation_headers(csrf_token: str) -> dict[str, str]:
    return {
        "Host": "testserver",
        "Origin": "http://testserver",
        "X-PTS-CSRF": csrf_token,
    }


def test_static_host_serves_index_assets_and_browser_fallback(
    static_client: tuple[TestClient, ActivityTracker, FakeClock],
) -> None:
    client, _, _ = static_client

    index_response = client.get("/", headers={"Host": "testserver"})
    asset_response = client.get("/assets/app.css", headers={"Host": "testserver"})
    fallback_response = client.get(
        "/cookbook/green-salad",
        headers={"Host": "testserver", "Accept": "text/html"},
    )

    assert index_response.status_code == 200
    assert index_response.text == "<main>Pelican Town Specials</main>"
    assert asset_response.status_code == 200
    assert asset_response.text == "body { color: green; }"
    assert fallback_response.status_code == 200
    assert fallback_response.text == index_response.text


def test_spa_fallback_does_not_swallow_api_or_session_paths(
    static_client: tuple[TestClient, ActivityTracker, FakeClock],
) -> None:
    client, _, _ = static_client

    api_response = client.get("/api/v1/not-a-route", headers={"Host": "testserver"})
    session_response = client.get("/session/not-a-route", headers={"Host": "testserver"})

    assert api_response.status_code == 401
    assert api_response.json()["error"]["code"] == "PTS_AUTH_SESSION_REQUIRED"
    assert session_response.status_code == 404


def test_missing_static_directory_returns_stable_safe_error(tmp_path: Path) -> None:
    missing_dir = tmp_path / "not-present"
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}), expected_port=None
        )
    )
    application = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
        static_dir=missing_dir,
    )

    response = TestClient(application, raise_server_exceptions=False).get(
        "/", headers={"Host": "testserver"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PTS_SYSTEM_WEB_ASSETS_MISSING"
    assert str(missing_dir) not in response.text


def test_heartbeat_requires_session_and_refreshes_activity(
    static_client: tuple[TestClient, ActivityTracker, FakeClock],
) -> None:
    client, tracker, clock = static_client

    rejected = client.post("/app/heartbeat", headers={"Host": "testserver"})
    csrf_token = _bootstrap(client)
    clock.now += 599
    accepted = client.post("/app/heartbeat", headers=_mutation_headers(csrf_token))
    clock.now += 599

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "PTS_AUTH_ORIGIN_INVALID"
    assert accepted.status_code == 204
    assert tracker.should_shutdown() is False


def test_shutdown_requires_session_and_requests_graceful_exit(
    static_client: tuple[TestClient, ActivityTracker, FakeClock],
) -> None:
    client, tracker, _ = static_client

    rejected = client.post("/app/shutdown", headers={"Host": "testserver"})
    csrf_token = _bootstrap(client)
    accepted = client.post("/app/shutdown", headers=_mutation_headers(csrf_token))

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "PTS_AUTH_ORIGIN_INVALID"
    assert accepted.status_code == 202
    assert tracker.shutdown_requested is True


def test_activity_tracker_exits_only_after_idle_threshold_when_not_busy() -> None:
    clock = FakeClock()
    tracker = ActivityTracker(clock=clock)

    tracker.touch("session-1")
    clock.now += 599
    assert tracker.should_shutdown() is False
    tracker.set_busy(True)
    clock.now += 1
    assert tracker.should_shutdown() is False
    tracker.set_busy(False)
    assert tracker.should_shutdown() is True

def test_idle_monitor_requests_injected_graceful_shutdown_callback(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    shutdown_event = Event()
    tracker = ActivityTracker(
        clock=clock,
        poll_interval_seconds=0.001,
        shutdown_callback=shutdown_event.set,
    )
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}), expected_port=None
        ),
        clock=clock,
    )
    application = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
        activity_tracker=tracker,
    )

    with TestClient(application, raise_server_exceptions=False):
        clock.now += 600
        assert shutdown_event.wait(timeout=1)
    assert tracker.shutdown_requested is True


def test_missing_index_returns_stable_safe_error_for_static_requests(
    tmp_path: Path,
) -> None:
    dist_dir = tmp_path / "dist"
    (dist_dir / "assets").mkdir(parents=True)
    (dist_dir / "assets" / "app.css").write_text("body {}")
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}), expected_port=None
        )
    )
    application = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
        static_dir=dist_dir,
    )

    response = TestClient(application, raise_server_exceptions=False).get(
        "/assets/app.css", headers={"Host": "testserver"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PTS_SYSTEM_WEB_ASSETS_MISSING"
    assert str(dist_dir) not in response.text


def test_outside_root_index_symlink_returns_stable_safe_error(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    outside_index = tmp_path / "outside-index.html"
    outside_index.write_text("outside")
    try:
        (dist_dir / "index.html").symlink_to(outside_index)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}), expected_port=None
        )
    )
    application = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
        static_dir=dist_dir,
    )

    response = TestClient(application, raise_server_exceptions=False).get(
        "/", headers={"Host": "testserver"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PTS_SYSTEM_WEB_ASSETS_MISSING"
    assert "outside" not in response.text


def test_invalid_index_directory_returns_stable_safe_error(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").mkdir()
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}), expected_port=None
        )
    )
    application = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
        static_dir=dist_dir,
    )

    response = TestClient(application, raise_server_exceptions=False).get(
        "/", headers={"Host": "testserver"}
    )

    assert response.status_code == 500


def test_launcher_mode_protects_docs_and_disables_schema_routes(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<main>app</main>")

    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"127.0.0.1"}),
            expected_port=43127,
        )
    )
    application = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
        static_dir=dist_dir,
        enable_docs=False,
        enforce_local_host=True,
    )

    with TestClient(application, raise_server_exceptions=False) as client:
        html_headers = {"Host": "127.0.0.1:43127", "Accept": "text/html"}
        foreign_host = client.get(
            "/docs",
            headers={"Host": "evil.test", "Accept": "text/html"},
        )
        docs = client.get("/docs", headers=html_headers)
        redoc = client.get("/redoc", headers=html_headers)
        schema = client.get("/openapi.json", headers=html_headers)

    assert foreign_host.status_code == 403
    assert foreign_host.json()["error"]["code"] == "PTS_AUTH_HOST_INVALID"
    assert docs.status_code == 404
    assert redoc.status_code == 404
    assert schema.status_code == 404
