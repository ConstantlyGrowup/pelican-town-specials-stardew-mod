"""Trial API endpoint tests.

Covers T30-TRIAL-001 (trial response exposes only safe status fields), T30-TRIAL-004
(exit hooks: saving provider settings or API key disables trial; deleting the key
does not), T30-TRIAL-005 (missing key => available false, no crash).
"""

from __future__ import annotations

from backend.tests.api.conftest import ApiClient, ApiServices
from backend.tests.api.test_settings import (
    FakeProviderSettingsService,
    FakeSecretStore,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from pelican_town_specials.api.routes.settings import router
from pelican_town_specials.application.trial import (
    TRIAL_GENERATION_LIMIT,
    TrialStatus,
)

_SENTINEL_KEY = "sk-test-trial"


class FakeTrialService:
    def __init__(self, status: TrialStatus | None = None) -> None:
        self.status_value = status or TrialStatus(
            available=True,
            enabled=False,
            claimed_attempts=0,
            limit=TRIAL_GENERATION_LIMIT,
            remaining=TRIAL_GENERATION_LIMIT,
        )
        self.enable_calls = 0
        self.disable_calls = 0

    def status(self) -> TrialStatus:
        return self.status_value

    def enable(self) -> TrialStatus:
        self.enable_calls += 1
        return self.status_value

    def disable(self) -> TrialStatus:
        self.disable_calls += 1
        return self.status_value


def _app(
    service: FakeProviderSettingsService | None = None,
    secret_store: FakeSecretStore | None = None,
    trial_service: FakeTrialService | None = None,
) -> tuple[FastAPI, FakeProviderSettingsService, FakeSecretStore, FakeTrialService]:
    app = FastAPI()
    settings_service = service or FakeProviderSettingsService()
    secrets = secret_store or FakeSecretStore()
    trial = trial_service or FakeTrialService()
    app.state.provider_settings_service = settings_service
    app.state.secret_store = secrets
    app.state.trial_service = trial
    app.include_router(router, prefix="/api/v1")
    return app, settings_service, secrets, trial


def test_get_trial_status_exposes_only_safe_fields() -> None:
    app, _, _, _ = _app()

    response = TestClient(app).get("/api/v1/settings/provider/trial")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "enabled": False,
        "claimedAttempts": 0,
        "limit": TRIAL_GENERATION_LIMIT,
        "remaining": TRIAL_GENERATION_LIMIT,
        "providerPreference": "TRIAL_FIRST",
    }
    # No base URL, model ids, or key may leak through the trial response.
    assert "baseUrl" not in response.text
    assert "visionModel" not in response.text
    assert "textModel" not in response.text
    assert "imageModel" not in response.text
    assert "yibuapi" not in response.text
    assert _SENTINEL_KEY not in response.text


def test_post_trial_calls_enable_and_returns_status() -> None:
    app, _, _, trial = _app()

    response = TestClient(app).post("/api/v1/settings/provider/trial")

    assert response.status_code == 200
    assert trial.enable_calls == 1
    assert response.json()["enabled"] is False  # fake returns its fixed status


def test_delete_trial_calls_disable_and_returns_status() -> None:
    app, _, _, trial = _app()

    response = TestClient(app).delete("/api/v1/settings/provider/trial")

    assert response.status_code == 200
    assert trial.disable_calls == 1
    assert response.json()["enabled"] is False


def test_put_provider_settings_exits_trial() -> None:
    app, service, _, trial = _app(trial_service=FakeTrialService())

    response = TestClient(app).put(
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
    )

    assert response.status_code == 200
    assert service.saved_settings is not None
    assert trial.disable_calls == 1


def test_put_provider_key_exits_trial() -> None:
    app, _, secret_store, trial = _app(trial_service=FakeTrialService())

    response = TestClient(app).put(
        "/api/v1/settings/provider/key",
        json={"apiKey": _SENTINEL_KEY},
    )

    assert response.status_code == 200
    assert secret_store.api_key is not None
    assert trial.disable_calls == 1
    assert _SENTINEL_KEY not in response.text


def test_delete_provider_key_does_not_exit_trial() -> None:
    secret_store = FakeSecretStore()
    secret_store.set_api_key(SecretStr(_SENTINEL_KEY))
    app, _, _, trial = _app(secret_store=secret_store, trial_service=FakeTrialService())

    response = TestClient(app).delete("/api/v1/settings/provider/key")

    assert response.status_code == 200
    assert trial.disable_calls == 0
    assert _SENTINEL_KEY not in response.text


def test_get_trial_status_initial_via_real_app(
    services: ApiServices, auth_client: ApiClient
) -> None:
    client = auth_client.client

    response = client.get(
        "/api/v1/settings/provider/trial",
        headers={"Host": "testserver"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "enabled": False,
        "claimedAttempts": 0,
        "limit": TRIAL_GENERATION_LIMIT,
        "remaining": TRIAL_GENERATION_LIMIT,
        "providerPreference": "TRIAL_FIRST",
    }
    assert _SENTINEL_KEY not in response.text


def test_enable_then_save_personal_settings_exits_and_preserves_claims(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    client = auth_client.client
    mutation = auth_client.mutation_headers

    enabled = client.post(
        "/api/v1/settings/provider/trial", headers=mutation
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    # Simulate a trial generation claiming one attempt directly on the service.
    assert services.trial_service.claim_attempt() is True

    saved = client.put(
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
        headers=mutation,
    )
    assert saved.status_code == 200

    after = client.get(
        "/api/v1/settings/provider/trial",
        headers={"Host": "testserver"},
    )
    assert after.json()["enabled"] is False
    # Re-enabling reuses the same claimedAttempts without resetting.
    re_enabled = client.post(
        "/api/v1/settings/provider/trial", headers=mutation
    )
    assert re_enabled.status_code == 200
    assert re_enabled.json()["claimedAttempts"] == 1
    assert re_enabled.json()["remaining"] == TRIAL_GENERATION_LIMIT - 1


def test_missing_key_marks_trial_unavailable_without_crash(
    services: ApiServices,
    auth_client: ApiClient,
    monkeypatch,
) -> None:
    client = auth_client.client
    mutation = auth_client.mutation_headers
    # Force the injected service's key provider to simulate a missing resource.
    monkeypatch.setattr(services.trial_service, "_key_provider", lambda: None)

    status_response = client.get(
        "/api/v1/settings/provider/trial",
        headers={"Host": "testserver"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["available"] is False
    assert status_response.json()["enabled"] is False

    enable_response = client.post(
        "/api/v1/settings/provider/trial", headers=mutation
    )
    assert enable_response.status_code == 409
    assert enable_response.json()["error"]["code"] == "PTS_TRIAL_UNAVAILABLE"
    assert _SENTINEL_KEY not in enable_response.text
