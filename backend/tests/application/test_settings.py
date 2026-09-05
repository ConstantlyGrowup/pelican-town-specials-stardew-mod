from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from pelican_town_specials.application import settings as settings_module
from pelican_town_specials.application.settings import (
    ApiKeySource,
    ProviderKind,
    ProviderSettings,
    ProviderSettingsService,
    ProviderSettingsUpdate,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.workspace import WorkspacePaths


@dataclass
class FakeSecretStore:
    configured: bool = False
    source: ApiKeySource = ApiKeySource.NONE

    def get_api_key(self) -> SecretStr | None:
        return SecretStr("memory-only-test-key") if self.configured else None

    def get_source(self) -> ApiKeySource:
        return self.source


def _workspace(tmp_path: Path) -> WorkspacePaths:
    return WorkspacePaths.create(tmp_path / "workspace")


def _update(**overrides: object) -> ProviderSettingsUpdate:
    values: dict[str, object] = {
        "baseUrl": "https://example.test/v1///",
        "visionModel": "vision-model",
        "textModel": "text-model",
        "imageModel": "image-model",
        "chatTimeoutSeconds": 120,
        "imageTimeoutSeconds": 300,
        "maxAutomaticRetries": 2,
    }
    values.update(overrides)
    return ProviderSettingsUpdate.model_validate(values)


def test_new_workspace_returns_safe_defaults_and_dynamic_key_state(
    tmp_path: Path,
) -> None:
    secrets = FakeSecretStore(configured=True, source=ApiKeySource.ENVIRONMENT)
    service = ProviderSettingsService(_workspace(tmp_path), secrets)

    result = service.get_provider_settings()

    assert result.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert result.base_url == "https://totokens.cc/v1"
    assert result.vision_model == "gpt-5.6-terra"
    assert result.text_model == "gpt-5.6-terra"
    assert result.image_model == "gpt-image-2-max"
    assert result.chat_timeout_seconds == 120
    assert result.image_timeout_seconds == 300
    assert result.max_automatic_retries == 2
    assert result.api_key_configured is True
    assert result.api_key_source is ApiKeySource.ENVIRONMENT
    result_payload = json.dumps(
        result.model_dump(by_alias=True, mode="json"),
        ensure_ascii=False,
    )
    assert "memory-only-test-key" not in result_payload


def test_provider_settings_default_to_sample_model_configuration() -> None:
    defaults = ProviderSettings()

    assert defaults.base_url == "https://totokens.cc/v1"
    assert defaults.vision_model == "gpt-5.6-terra"
    assert defaults.text_model == "gpt-5.6-terra"
    assert defaults.image_model == "gpt-image-2-max"


def test_update_requires_non_empty_model_ids_and_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _update(visionModel="")
    with pytest.raises(ValidationError):
        _update(textModel="x" * 121)
    with pytest.raises(ValidationError):
        _update(unknownField="not-allowed")


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("chatTimeoutSeconds", 29),
        ("chatTimeoutSeconds", 601),
        ("imageTimeoutSeconds", 59),
        ("imageTimeoutSeconds", 901),
        ("maxAutomaticRetries", -1),
        ("maxAutomaticRetries", 4),
    ],
)
def test_update_rejects_values_outside_documented_ranges(
    field: str,
    invalid_value: int,
) -> None:
    with pytest.raises(ValidationError):
        _update(**{field: invalid_value})


def test_provider_kind_is_fixed_and_base_url_only_removes_trailing_slashes() -> None:
    settings = ProviderSettings(baseUrl="https://example.test/v1///")

    assert settings.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert settings.base_url == "https://example.test/v1"
    with pytest.raises(ValidationError):
        ProviderSettings(providerKind="OTHER")


def test_save_is_reloadable_and_persists_only_non_secret_fields(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    secrets = FakeSecretStore(configured=True, source=ApiKeySource.SESSION)
    service = ProviderSettingsService(workspace, secrets)

    saved = service.save_provider_settings(_update())
    reloaded = ProviderSettingsService(workspace, secrets).get_provider_settings()
    payload = json.loads((workspace.app_state_dir / "settings.json").read_text())

    assert saved.base_url == "https://example.test/v1"
    assert reloaded.model_dump(by_alias=True) == saved.model_dump(by_alias=True)
    assert payload["providerKind"] == "OPENAI_COMPATIBLE"
    assert "apiKeyConfigured" not in payload
    assert "apiKeySource" not in payload
    assert "apiKey" not in json.dumps(payload, ensure_ascii=False)
    assert "memory-only-test-key" not in json.dumps(payload, ensure_ascii=False)


def test_invalid_primary_settings_are_recovered_from_atomic_backup(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    secrets = FakeSecretStore()
    service = ProviderSettingsService(workspace, secrets)
    service.save_provider_settings(_update(textModel="first"))
    service.save_provider_settings(_update(textModel="second"))
    settings_path = workspace.app_state_dir / "settings.json"
    settings_path.write_text("{not valid json", encoding="utf-8")

    recovered = service.get_provider_settings()

    assert recovered.text_model == "first"


def test_corrupt_settings_are_mapped_to_safe_app_error(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    settings_path = workspace.app_state_dir / "settings.json"
    settings_path.write_text('{"textModel": "missing required shape"}', encoding="utf-8")
    service = ProviderSettingsService(workspace, FakeSecretStore())

    with pytest.raises(AppError) as exc_info:
        service.get_provider_settings()

    error = exc_info.value
    assert error.code == "PTS_WORKSPACE_SETTINGS_INVALID"
    assert error.details == {}
    assert "missing required shape" not in str(error)


def test_write_failure_is_mapped_to_safe_app_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    service = ProviderSettingsService(workspace, FakeSecretStore())

    def fail_write(_path: Path, _payload: object) -> None:
        raise OSError("settings path contains a secret-looking value")

    monkeypatch.setattr(settings_module, "atomic_write_json", fail_write)

    with pytest.raises(AppError) as exc_info:
        service.save_provider_settings(_update())

    error = exc_info.value
    assert error.code == "PTS_WORKSPACE_SETTINGS_UNAVAILABLE"
    assert error.details == {}
    assert "secret-looking value" not in str(error)
