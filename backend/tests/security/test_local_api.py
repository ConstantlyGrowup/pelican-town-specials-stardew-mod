"""Security regression tests for the local-only API surface (Task 19 Step 2).

Covers T19-SECURITY-001 against controls implemented in Task 1-7:
loopback-only binding, foreign Host/Origin rejection, CSRF, launch token
replay, asset path traversal, upload filename injection and open-folder
containment. These tests verify existing behavior; they do not add new
security controls.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.security import SecurityConfig, SecurityState
from pelican_town_specials.persistence.workspace import WorkspacePaths


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(output, format="PNG")
    return output.getvalue()


def _bootstrap(client: TestClient, security: SecurityState) -> str:
    token = security.issue_launch_token()
    response = client.post(
        "/session/bootstrap",
        json={"launchToken": token},
        headers={"Host": "testserver"},
    )
    assert response.status_code == 204, response.text
    return response.headers["x-pts-csrf"]


@pytest.fixture
def local_client(tmp_path: Path) -> Iterator[tuple[TestClient, SecurityState]]:
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=None,
            allowed_origins=frozenset({"http://testserver"}),
        )
    )
    app = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, security


def test_health_rejects_foreign_host(local_client: tuple[TestClient, SecurityState]) -> None:
    client, _ = local_client
    response = client.get("/api/v1/health", headers={"Host": "attacker.example"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_HOST_INVALID"


def test_mutation_rejects_foreign_origin(local_client: tuple[TestClient, SecurityState]) -> None:
    client, security = local_client
    csrf = _bootstrap(client, security)

    response = client.put(
        "/api/v1/settings/provider",
        json={
            "providerKind": "OPENAI_COMPATIBLE",
            "baseUrl": "https://example.test/v1",
            "visionModel": "vision-model",
            "textModel": "text-model",
            "imageModel": "image-model",
            "chatTimeoutSeconds": 120,
            "imageTimeoutSeconds": 300,
            "maxAutomaticRetries": 2,
        },
        headers={
            "Host": "testserver",
            "Origin": "http://attacker.example",
            "X-PTS-CSRF": csrf,
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_ORIGIN_INVALID"


def test_mutation_requires_csrf(local_client: tuple[TestClient, SecurityState]) -> None:
    client, security = local_client
    _bootstrap(client, security)

    response = client.put(
        "/api/v1/settings/provider",
        json={
            "providerKind": "OPENAI_COMPATIBLE",
            "baseUrl": "https://example.test/v1",
            "visionModel": "vision-model",
            "textModel": "text-model",
            "imageModel": "image-model",
            "chatTimeoutSeconds": 120,
            "imageTimeoutSeconds": 300,
            "maxAutomaticRetries": 2,
        },
        headers={"Host": "testserver", "Origin": "http://testserver"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_CSRF_INVALID"


def test_launch_token_replay_rejected(local_client: tuple[TestClient, SecurityState]) -> None:
    client, security = local_client
    token = security.issue_launch_token()
    headers = {"Host": "testserver"}

    first = client.post("/session/bootstrap", json={"launchToken": token}, headers=headers)
    second = client.post("/session/bootstrap", json={"launchToken": token}, headers=headers)

    assert first.status_code == 204
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "PTS_AUTH_LAUNCH_INVALID"


def test_asset_path_traversal_rejected(local_client: tuple[TestClient, SecurityState]) -> None:
    client, security = local_client
    _bootstrap(client, security)

    # Asset ids are opaque UUIDs; a traversal-shaped or non-UUID path can never
    # resolve to a file inside the asset store.
    response = client.get(
        "/api/v1/assets/..%2F..%2Fetc%2Fpasswd",
        headers={"Host": "testserver"},
    )
    non_uuid = client.get(
        "/api/v1/assets/not-a-uuid",
        headers={"Host": "testserver"},
    )

    assert response.status_code in (404, 422)
    assert non_uuid.status_code == 422


def test_upload_filename_injection_is_ignored(
    local_client: tuple[TestClient, SecurityState],
) -> None:
    client, security = local_client
    csrf = _bootstrap(client, security)

    response = client.post(
        "/api/v1/assets/images",
        headers={
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": csrf,
        },
        files={"file": ("../../evil/photo.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "../evil" not in response.text
    # The injected filename must never influence the stored path: the response
    # exposes an opaque UUID asset id, not the upload filename.
    parsed = UUID(body["assetId"])
    assert parsed.version == 4


def test_open_folder_unknown_export_returns_404(
    local_client: tuple[TestClient, SecurityState],
) -> None:
    client, security = local_client
    csrf = _bootstrap(client, security)
    missing_export_id = uuid4()

    response = client.post(
        f"/api/v1/exports/{missing_export_id}/open-folder",
        headers={
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": csrf,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PTS_EXPORT_NOT_FOUND"


def test_loopback_only_when_enforced(tmp_path: Path) -> None:
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"127.0.0.1"}),
            expected_port=8000,
        )
    )
    app = create_app(
        workspace_paths=WorkspacePaths.create(tmp_path / "workspace"),
        security_state=security,
        enforce_local_host=True,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        foreign = client.get("/api/v1/health", headers={"Host": "attacker.example"})
        loopback = client.get("/api/v1/health", headers={"Host": "127.0.0.1:8000"})

    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "PTS_AUTH_HOST_INVALID"
    assert loopback.status_code == 200


def test_diagnostics_requires_session(
    local_client: tuple[TestClient, SecurityState],
) -> None:
    client, _ = local_client
    response = client.get("/api/v1/diagnostics", headers={"Host": "testserver"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "PTS_AUTH_SESSION_REQUIRED"
