from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.security import SecurityConfig, SecurityState
from pelican_town_specials.persistence.secret_store import (
    API_KEY_ENVIRONMENT_VARIABLE,
    WindowsEnvironmentSecretStore,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths


@dataclass
class FakeEnvironmentAdapter:
    process: dict[str, str] = field(default_factory=dict)
    current_user: dict[str, str] = field(default_factory=dict)

    def get_process(self, name: str) -> str | None:
        return self.process.get(name)

    def set_process(self, name: str, value: str) -> None:
        self.process[name] = value

    def delete_process(self, name: str) -> None:
        self.process.pop(name, None)

    def get_current_user(self, name: str) -> str | None:
        return self.current_user.get(name)

    def set_current_user(self, name: str, value: str) -> None:
        self.current_user[name] = value

    def delete_current_user(self, name: str) -> None:
        self.current_user.pop(name, None)


def _valid_settings() -> dict[str, object]:
    return {
        "providerKind": "OPENAI_COMPATIBLE",
        "baseUrl": "https://example.test/v1",
        "visionModel": "vision-model",
        "textModel": "text-model",
        "imageModel": "image-model",
        "chatTimeoutSeconds": 120,
        "imageTimeoutSeconds": 300,
        "maxAutomaticRetries": 2,
    }


def test_create_app_registers_settings_and_preserves_health(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    adapter = FakeEnvironmentAdapter()
    secret_store = WindowsEnvironmentSecretStore(adapter)
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=None,
            allowed_origins=frozenset({"http://testserver"}),
        )
    )
    client = TestClient(
        create_app(
            workspace_paths=workspace,
            secret_store=secret_store,
            security_state=security,
        )
    )
    launch_token = security.issue_launch_token()
    bootstrap_response = client.post(
        "/session/bootstrap",
        json={"launchToken": launch_token},
        headers={"Host": "testserver"},
    )
    csrf_token = bootstrap_response.headers["x-pts-csrf"]
    session_headers = {"Host": "testserver"}
    mutation_headers = {
        **session_headers,
        "Origin": "http://testserver",
        "X-PTS-CSRF": csrf_token,
    }

    assert client.get("/api/v1/health").status_code == 200
    assert bootstrap_response.status_code == 204
    settings_response = client.get(
        "/api/v1/settings/provider",
        headers=session_headers,
    )

    assert settings_response.status_code == 200
    assert settings_response.json()["apiKeyConfigured"] is False

    key = "sk-create-app-wiring-sentinel"
    put_key = client.put(
        "/api/v1/settings/provider/key",
        json={"apiKey": key},
        headers=mutation_headers,
    )
    assert put_key.status_code == 200
    assert key not in put_key.text
    assert adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] == key

    saved = client.put(
        "/api/v1/settings/provider",
        json=_valid_settings(),
        headers=mutation_headers,
    )
    assert saved.status_code == 200
    assert client.get(
        "/api/v1/settings/provider",
        headers=session_headers,
    ).json() == {
        **_valid_settings(),
        "apiKeyConfigured": True,
        "apiKeySource": "ENVIRONMENT",
    }