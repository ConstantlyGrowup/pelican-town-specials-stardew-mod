from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from pelican_town_specials.api.routes.settings import router
from pelican_town_specials.application.settings import (
    ApiKeySource,
    ProviderSettingsUpdate,
    ProviderSettingsView,
)
from pelican_town_specials.application.trial import (
    TRIAL_GENERATION_LIMIT,
    TrialStatus,
)


class FakeTrialService:
    def __init__(self) -> None:
        self.disable_calls = 0
        self.status_value = TrialStatus(
            available=True,
            enabled=False,
            claimed_attempts=0,
            limit=TRIAL_GENERATION_LIMIT,
            remaining=TRIAL_GENERATION_LIMIT,
        )

    def status(self) -> TrialStatus:
        return self.status_value

    def enable(self) -> TrialStatus:
        return self.status_value

    def disable(self) -> TrialStatus:
        self.disable_calls += 1
        return self.status_value


class FakeProviderSettingsService:
    def __init__(self) -> None:
        self.saved_settings: ProviderSettingsUpdate | None = None
        self.view = ProviderSettingsView(
            providerKind="OPENAI_COMPATIBLE",
            baseUrl="https://example.test/v1",
            visionModel="vision-model",
            textModel="text-model",
            imageModel="image-model",
            chatTimeoutSeconds=120,
            imageTimeoutSeconds=300,
            maxAutomaticRetries=2,
            apiKeyConfigured=False,
            apiKeySource=ApiKeySource.NONE,
        )

    def get_provider_settings(self) -> ProviderSettingsView:
        return self.view

    def save_provider_settings(
        self, settings: ProviderSettingsUpdate
    ) -> ProviderSettingsView:
        self.saved_settings = settings
        return self.view


class FakeSecretStore:
    def __init__(self) -> None:
        self.api_key: SecretStr | None = None
        self.source = ApiKeySource.NONE

    def get_api_key(self) -> SecretStr | None:
        return self.api_key

    def get_source(self) -> ApiKeySource:
        return self.source

    def set_api_key(self, value: SecretStr) -> None:
        self.api_key = value
        self.source = ApiKeySource.ENVIRONMENT

    def delete_api_key(self) -> None:
        self.api_key = None
        self.source = ApiKeySource.NONE


def _app(
    service: FakeProviderSettingsService | None = None,
    secret_store: FakeSecretStore | None = None,
) -> tuple[FastAPI, FakeProviderSettingsService, FakeSecretStore]:
    app = FastAPI()
    settings_service = service or FakeProviderSettingsService()
    secrets = secret_store or FakeSecretStore()
    app.state.provider_settings_service = settings_service
    app.state.secret_store = secrets
    app.state.trial_service = FakeTrialService()
    app.include_router(router, prefix="/api/v1")
    return app, settings_service, secrets


def test_get_provider_settings_returns_view_from_app_state() -> None:
    app, _, _ = _app()

    response = TestClient(app).get("/api/v1/settings/provider")

    assert response.status_code == 200
    assert response.json() == {
        "providerKind": "OPENAI_COMPATIBLE",
        "baseUrl": "https://example.test/v1",
        "visionModel": "vision-model",
        "textModel": "text-model",
        "imageModel": "image-model",
        "chatTimeoutSeconds": 120,
        "imageTimeoutSeconds": 300,
        "maxAutomaticRetries": 2,
        "apiKeyConfigured": False,
        "apiKeySource": "NONE",
    }


def test_put_provider_settings_passes_strict_update_to_service() -> None:
    app, service, _ = _app()

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
    assert service.saved_settings.text_model == "text-model"


def test_provider_settings_rejects_extra_fields() -> None:
    app, _, _ = _app()

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
            "unexpectedField": "reject-me",
        },
    )

    assert response.status_code == 422


def test_put_provider_key_uses_secretstr_and_never_returns_key() -> None:
    app, _, secret_store = _app()
    sentinel = "sk-settings-route-sentinel"

    response = TestClient(app).put(
        "/api/v1/settings/provider/key",
        json={"apiKey": sentinel},
    )

    assert response.status_code == 200
    assert secret_store.api_key is not None
    assert secret_store.api_key.get_secret_value() == sentinel
    assert response.json() == {
        "apiKeyConfigured": True,
        "apiKeySource": "ENVIRONMENT",
    }
    assert sentinel not in response.text
    assert all(sentinel not in value for value in response.headers.values())


def test_delete_provider_key_returns_unconfigured_status_without_key() -> None:
    secret_store = FakeSecretStore()
    sentinel = "sk-delete-route-sentinel"
    secret_store.set_api_key(SecretStr(sentinel))
    app, _, _ = _app(secret_store=secret_store)

    response = TestClient(app).delete("/api/v1/settings/provider/key")

    assert response.status_code == 200
    assert response.json() == {
        "apiKeyConfigured": False,
        "apiKeySource": "NONE",
    }
    assert sentinel not in response.text
    assert all(sentinel not in value for value in response.headers.values())
