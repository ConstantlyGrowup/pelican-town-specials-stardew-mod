from __future__ import annotations

from typing import Protocol, cast

from fastapi import APIRouter, Request
from pydantic import SecretStr

from pelican_town_specials.application.settings import (
    ProviderSettingsService,
    ProviderSettingsUpdate,
    ProviderSettingsView,
)
from pelican_town_specials.application.trial import TrialAccessService, TrialStatus
from pelican_town_specials.domain.common import StrictModel
from pelican_town_specials.persistence.secret_store import (
    ApiKeySource,
    SecretValue,
)

router = APIRouter()


class ProviderKeyStore(Protocol):
    def get_api_key(self) -> SecretValue | None: ...

    def get_source(self) -> ApiKeySource: ...

    def set_api_key(self, value: SecretValue) -> None: ...

    def delete_api_key(self) -> None: ...


class ProviderKeyUpdate(StrictModel):
    api_key: SecretStr


class ProviderKeyStatus(StrictModel):
    api_key_configured: bool
    api_key_source: ApiKeySource


def _settings_service(request: Request) -> ProviderSettingsService:
    return cast(ProviderSettingsService, request.app.state.provider_settings_service)


def _secret_store(request: Request) -> ProviderKeyStore:
    return cast(ProviderKeyStore, request.app.state.secret_store)


def _trial_service(request: Request) -> TrialAccessService:
    return cast(TrialAccessService, request.app.state.trial_service)


def _key_status(secret_store: ProviderKeyStore) -> ProviderKeyStatus:
    api_key = secret_store.get_api_key()
    return ProviderKeyStatus(
        api_key_configured=(
            api_key is not None and bool(api_key.get_secret_value().strip())
        ),
        api_key_source=secret_store.get_source(),
    )


@router.get(
    "/settings/provider",
    response_model=ProviderSettingsView,
    response_model_by_alias=True,
)
def get_provider_settings(request: Request) -> ProviderSettingsView:
    return _settings_service(request).get_provider_settings()


@router.put(
    "/settings/provider",
    response_model=ProviderSettingsView,
    response_model_by_alias=True,
)
def put_provider_settings(
    settings: ProviderSettingsUpdate,
    request: Request,
) -> ProviderSettingsView:
    saved = _settings_service(request).save_provider_settings(settings)
    # R-05: saving personal provider settings auto-exits trial mode.
    _trial_service(request).disable()
    return saved


@router.put(
    "/settings/provider/key",
    response_model=ProviderKeyStatus,
    response_model_by_alias=True,
)
def put_provider_key(
    update: ProviderKeyUpdate,
    request: Request,
) -> ProviderKeyStatus:
    secret_store = _secret_store(request)
    secret_store.set_api_key(update.api_key)
    # R-05: saving an API key auto-exits trial mode.
    _trial_service(request).disable()
    return _key_status(secret_store)


@router.delete(
    "/settings/provider/key",
    response_model=ProviderKeyStatus,
    response_model_by_alias=True,
)
def delete_provider_key(request: Request) -> ProviderKeyStatus:
    secret_store = _secret_store(request)
    secret_store.delete_api_key()
    return _key_status(secret_store)


@router.get(
    "/settings/provider/trial",
    response_model=TrialStatus,
    response_model_by_alias=True,
)
def get_trial_status(request: Request) -> TrialStatus:
    return _trial_service(request).status()


@router.post(
    "/settings/provider/trial",
    response_model=TrialStatus,
    response_model_by_alias=True,
)
def enable_trial(request: Request) -> TrialStatus:
    return _trial_service(request).enable()


@router.delete(
    "/settings/provider/trial",
    response_model=TrialStatus,
    response_model_by_alias=True,
)
def disable_trial(request: Request) -> TrialStatus:
    return _trial_service(request).disable()
