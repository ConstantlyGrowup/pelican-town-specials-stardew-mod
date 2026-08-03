from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ["PTS_WORKSPACE_PATH"] = r"backend\workspace\session-security-module-workspace"

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.security import (
    LaunchTokenStore,
    SecurityConfig,
    SecurityState,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.workspace import WorkspacePaths


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def security_client(tmp_path: Path) -> Iterator[TestClient]:
    clock = FakeClock()
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=None,
            allowed_origins=frozenset({"http://testserver"}),
        ),
        clock=clock,
    )
    test_app = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
    )

    @test_app.put("/api/v1/mutation-check")
    def mutation_check() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(test_app, raise_server_exceptions=False) as client:
        yield client


def _app(client: TestClient) -> FastAPI:
    return cast(FastAPI, client.app)


def _security(client: TestClient) -> SecurityState:
    return cast(SecurityState, _app(client).state.security)


def _bootstrap(client: TestClient) -> str:
    token = _security(client).issue_launch_token()
    response = client.post(
        "/session/bootstrap",
        json={"launchToken": token},
        headers={"Host": "testserver"},
    )
    assert response.status_code == 204
    return response.headers["x-pts-csrf"]




def test_bootstrap_sets_http_only_cookie_and_csrf_header(
    security_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = _security(security_client).issue_launch_token()

    response = security_client.post(
        "/session/bootstrap",
        json={"launchToken": token},
        headers={"Host": "testserver"},
    )

    assert response.status_code == 204
    assert "pts_session=" in response.headers["set-cookie"].lower()
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    csrf_token = response.headers["x-pts-csrf"]
    assert csrf_token
    assert response.text == ""
    assert token not in response.text
    assert csrf_token not in response.text
    assert token not in caplog.text
    assert csrf_token not in caplog.text


def test_bootstrap_rejects_expired_launch_token(security_client: TestClient) -> None:
    token = _security(security_client).issue_launch_token()
    _security(security_client).clock.now += 61

    response = security_client.post(
        "/session/bootstrap",
        json={"launchToken": token},
        headers={"Host": "testserver"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "PTS_AUTH_LAUNCH_INVALID"
    assert token not in response.text


def test_bootstrap_rejects_replayed_launch_token(security_client: TestClient) -> None:
    token = _security(security_client).issue_launch_token()
    first_response = security_client.post(
        "/session/bootstrap",
        json={"launchToken": token},
        headers={"Host": "testserver"},
    )
    second_response = security_client.post(
        "/session/bootstrap",
        json={"launchToken": token},
        headers={"Host": "testserver"},
    )

    assert first_response.status_code == 204
    assert second_response.status_code == 401
    assert second_response.json()["error"]["code"] == "PTS_AUTH_LAUNCH_INVALID"
    assert token not in second_response.text


def test_settings_get_requires_session(security_client: TestClient) -> None:
    response = security_client.get(
        "/api/v1/settings/provider",
        headers={"Host": "testserver"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "PTS_AUTH_SESSION_REQUIRED"


def test_bootstrap_rejects_foreign_host(security_client: TestClient) -> None:
    token = _security(security_client).issue_launch_token()

    response = security_client.post(
        "/session/bootstrap",
        json={"launchToken": token},
        headers={"Host": "attacker.example"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_HOST_INVALID"
    assert token not in response.text


def test_mutation_rejects_foreign_origin(security_client: TestClient) -> None:
    csrf_token = _bootstrap(security_client)

    response = security_client.put(
        "/api/v1/mutation-check",
        headers={
            "Host": "testserver",
            "Origin": "http://attacker.example",
            "X-PTS-CSRF": csrf_token,
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_ORIGIN_INVALID"


def test_mutation_requires_csrf_token(security_client: TestClient) -> None:
    _bootstrap(security_client)

    response = security_client.put(
        "/api/v1/mutation-check",
        headers={"Host": "testserver", "Origin": "http://testserver"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_CSRF_INVALID"


def test_mutation_rejects_incorrect_csrf_token(security_client: TestClient) -> None:
    _bootstrap(security_client)

    response = security_client.put(
        "/api/v1/mutation-check",
        headers={
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": "incorrect-csrf-token",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_CSRF_INVALID"


def test_health_rejects_foreign_host(security_client: TestClient) -> None:
    response = security_client.get(
        "/api/v1/health",
        headers={"Host": "attacker.example"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_HOST_INVALID"


def test_invalid_csrf_does_not_extend_session(security_client: TestClient) -> None:
    _bootstrap(security_client)
    clock = cast(FakeClock, _security(security_client).clock)
    clock.now += 599

    rejected_response = security_client.put(
        "/api/v1/mutation-check",
        headers={
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": "incorrect-csrf-token",
        },
    )
    clock.now += 2
    expired_response = security_client.get(
        "/api/v1/settings/provider",
        headers={"Host": "testserver"},
    )

    assert rejected_response.status_code == 403
    assert rejected_response.json()["error"]["code"] == "PTS_AUTH_CSRF_INVALID"
    assert expired_response.status_code == 401
    assert expired_response.json()["error"]["code"] == "PTS_AUTH_SESSION_REQUIRED"


def test_issuing_token_prunes_expired_unused_tokens() -> None:
    clock = FakeClock()
    store = LaunchTokenStore(clock)
    expired_token = store.issue()
    clock.now += 61
    active_token = store.issue()

    assert expired_token not in store._issued_at
    assert active_token in store._issued_at

def test_expected_port_rejects_missing_or_wrong_host_port_and_origin() -> None:
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=8765,
        )
    )

    with pytest.raises(AppError, match="本地应用地址校验失败") as missing_port:
        security.require_allowed_host("testserver")
    with pytest.raises(AppError, match="本地应用地址校验失败") as wrong_port:
        security.require_allowed_host("testserver:8766")
    with pytest.raises(AppError, match="本地请求来源校验失败") as wrong_origin:
        security.require_allowed_origin("http://testserver", "testserver:8765")

    assert missing_port.value.code == "PTS_AUTH_HOST_INVALID"
    assert wrong_port.value.code == "PTS_AUTH_HOST_INVALID"
    assert wrong_origin.value.code == "PTS_AUTH_ORIGIN_INVALID"
    assert security.require_allowed_host("testserver:8765") == "testserver"
    security.require_allowed_origin("http://testserver:8765", "testserver:8765")

def test_production_default_port_rejects_missing_or_wrong_host_port() -> None:
    security = SecurityState()

    with pytest.raises(AppError, match="本地应用地址校验失败") as missing_port:
        security.require_allowed_host("127.0.0.1")
    with pytest.raises(AppError, match="本地应用地址校验失败") as wrong_port:
        security.require_allowed_host("localhost:8001")
    with pytest.raises(AppError, match="本地请求来源校验失败") as missing_origin_port:
        security.require_allowed_origin("http://localhost", "localhost:8000")

    assert missing_port.value.code == "PTS_AUTH_HOST_INVALID"
    assert wrong_port.value.code == "PTS_AUTH_HOST_INVALID"
    assert missing_origin_port.value.code == "PTS_AUTH_ORIGIN_INVALID"
    assert security.require_allowed_host("127.0.0.1:8000") == "127.0.0.1"
    security.require_allowed_origin(
        "http://localhost:8000",
        "localhost:8000",
    )