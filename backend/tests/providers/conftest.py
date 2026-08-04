"""Provider test fixtures: fake secret store, injectable sleep, respx."""

from __future__ import annotations

import pytest

from pelican_town_specials.application.settings import ProviderSettings
from pelican_town_specials.persistence.secret_store import ApiKeySource, SecretValue
from pelican_town_specials.providers import OpenAICompatibleGateway


class FakeSecretStore:
    def __init__(self, key: str = "sk-test-key") -> None:
        self._key = key

    def get_api_key(self) -> SecretValue | None:
        return SecretValue(self._key)

    def get_source(self) -> ApiKeySource:
        return ApiKeySource.NONE


async def _noop_sleep(delay: float) -> None:
    del delay


@pytest.fixture
def settings() -> ProviderSettings:
    return ProviderSettings(
        baseUrl="https://yibuapi.com/v1",
        visionModel="vision-model",
        textModel="text-model",
        imageModel="image-model",
        chatTimeoutSeconds=60,
        imageTimeoutSeconds=90,
        maxAutomaticRetries=2,
    )


@pytest.fixture
def gateway(settings: ProviderSettings) -> OpenAICompatibleGateway:
    return OpenAICompatibleGateway(
        settings=settings,
        secret_store=FakeSecretStore(),
        sleep=_noop_sleep,
    )
