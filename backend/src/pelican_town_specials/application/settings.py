from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from pelican_town_specials.domain.common import StrictModel
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.atomic import (
    atomic_write_json,
    read_json_with_backup,
)
from pelican_town_specials.persistence.secret_store import (
    ApiKeySource,
    SecretValue,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths

DEFAULT_BASE_URL = "https://yibuapi.com/v1"
_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


class ProviderKind(StrEnum):
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"


class SecretStore(Protocol):
    def get_api_key(self) -> SecretValue | None: ...

    def get_source(self) -> ApiKeySource: ...


def _normalize_base_url(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.rstrip("/")
    try:
        parsed = _HTTP_URL_ADAPTER.validate_python(normalized)
    except ValidationError as exc:
        raise ValueError("baseUrl must be a valid HTTP URL") from exc
    return str(parsed).rstrip("/")


class _ProviderSettingsFields(StrictModel):
    provider_kind: ProviderKind = Field(default=ProviderKind.OPENAI_COMPATIBLE)
    base_url: str = Field(default=DEFAULT_BASE_URL, min_length=1)
    vision_model: str = Field(default="gpt-5.6-luna", max_length=120)
    text_model: str = Field(default="gpt-5.6-luna", max_length=120)
    image_model: str = Field(default="gpt-image-2-max", max_length=120)
    chat_timeout_seconds: int = Field(default=120, ge=30, le=600)
    image_timeout_seconds: int = Field(default=300, ge=60, le=900)
    max_automatic_retries: int = Field(default=2, ge=0, le=3)

    @field_validator("provider_kind", mode="before")
    @classmethod
    def _validate_provider_kind(cls, value: object) -> ProviderKind:
        if value in (ProviderKind.OPENAI_COMPATIBLE, ProviderKind.OPENAI_COMPATIBLE.value):
            return ProviderKind.OPENAI_COMPATIBLE
        raise ValueError("providerKind must be OPENAI_COMPATIBLE")

    @field_validator("vision_model", "text_model", "image_model", mode="before")
    @classmethod
    def _validate_model_identifier(cls, value: object) -> object:
        if value == "":
            return value
        if isinstance(value, str) and not value.strip():
            raise ValueError("model identifier must not be blank")
        return value
    _normalize_url = field_validator("base_url", mode="before")(_normalize_base_url)


class ProviderSettings(_ProviderSettingsFields):
    """Public provider settings with safe defaults when not configured."""


class ProviderSettingsUpdate(_ProviderSettingsFields):
    """Full settings update; all model identifiers must be configured."""

    vision_model: str = Field(min_length=1, max_length=120)
    text_model: str = Field(min_length=1, max_length=120)
    image_model: str = Field(min_length=1, max_length=120)


class _PersistedProviderSettings(_ProviderSettingsFields):
    """On-disk shape; every non-secret field is required once the file exists."""

    provider_kind: ProviderKind = Field(...)
    base_url: str = Field(..., min_length=1)
    vision_model: str = Field(..., max_length=120)
    text_model: str = Field(..., max_length=120)
    image_model: str = Field(..., max_length=120)
    chat_timeout_seconds: int = Field(..., ge=30, le=600)
    image_timeout_seconds: int = Field(..., ge=60, le=900)
    max_automatic_retries: int = Field(..., ge=0, le=3)


class ProviderSettingsView(ProviderSettings):
    api_key_configured: bool
    api_key_source: ApiKeySource


ProviderSettingsResponse = ProviderSettingsView


class ProviderSettingsService:
    def __init__(self, workspace: WorkspacePaths, secret_store: SecretStore) -> None:
        self._workspace = workspace
        self._secret_store = secret_store

    @property
    def settings_path(self) -> Path:
        return self._workspace.app_state_dir / "settings.json"

    def get_provider_settings(self) -> ProviderSettingsView:
        return self._public_view(self._load_settings())

    def save_provider_settings(
        self,
        settings: ProviderSettingsUpdate | Mapping[str, Any],
    ) -> ProviderSettingsView:
        try:
            update = ProviderSettingsUpdate.model_validate(settings)
            persisted = _PersistedProviderSettings.model_validate(update.model_dump())
        except (TypeError, ValueError) as exc:
            raise self._invalid_settings_error() from exc

        try:
            atomic_write_json(
                self.settings_path,
                persisted.model_dump(by_alias=True, mode="json"),
            )
        except Exception as exc:
            raise self._unavailable_error() from exc

        return self._public_view(
            ProviderSettings.model_validate(persisted.model_dump())
        )

    def get(self) -> ProviderSettingsView:
        return self.get_provider_settings()

    def save(
        self,
        settings: ProviderSettingsUpdate | Mapping[str, Any],
    ) -> ProviderSettingsView:
        return self.save_provider_settings(settings)

    def _load_settings(self) -> ProviderSettings:
        settings_path = self.settings_path
        backup_path = settings_path.with_suffix(f"{settings_path.suffix}.bak")
        try:
            if not settings_path.exists() and not backup_path.exists():
                return ProviderSettings()
            persisted = read_json_with_backup(
                settings_path,
                _PersistedProviderSettings.model_validate,
            )
            return ProviderSettings.model_validate(persisted.model_dump())
        except FileNotFoundError:
            return ProviderSettings()
        except (TypeError, ValueError, UnicodeError) as exc:
            raise self._invalid_settings_error() from exc
        except Exception as exc:
            raise self._unavailable_error() from exc

    def _public_view(self, settings: ProviderSettings) -> ProviderSettingsView:
        try:
            api_key = self._secret_store.get_api_key()
            api_key_source = self._secret_store.get_source()
            api_key_configured = self._has_value(api_key)
            return ProviderSettingsView(
                **settings.model_dump(),
                api_key_configured=api_key_configured,
                api_key_source=api_key_source,
            )
        except AppError:
            raise
        except Exception as exc:
            raise self._secret_store_error() from exc

    @staticmethod
    def _has_value(value: SecretStr | None) -> bool:
        if value is None:
            return False
        return bool(value.get_secret_value().strip())

    @staticmethod
    def _invalid_settings_error() -> AppError:
        return AppError(
            code="PTS_WORKSPACE_SETTINGS_INVALID",
            message="工作区设置文件无效，请重新配置 Provider。",
            http_status=500,
            details={},
            retryable=False,
        )

    @staticmethod
    def _unavailable_error() -> AppError:
        return AppError(
            code="PTS_WORKSPACE_SETTINGS_UNAVAILABLE",
            message="无法保存或读取本机设置，请检查工作区权限。",
            http_status=500,
            details={},
            retryable=False,
        )

    @staticmethod
    def _secret_store_error() -> AppError:
        return AppError(
            code="PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE",
            message="无法读取本机配置，请检查当前用户权限。",
            http_status=500,
            details={},
            retryable=False,
        )
