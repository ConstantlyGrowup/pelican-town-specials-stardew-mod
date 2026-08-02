from __future__ import annotations

import pytest
from pydantic import ValidationError

from pelican_town_specials.application.settings import (
    ProviderSettings,
    ProviderSettingsUpdate,
)


def _valid_update(**overrides: object) -> ProviderSettingsUpdate:
    values: dict[str, object] = {
        "baseUrl": "https://example.test/v1",
        "visionModel": "vision-model",
        "textModel": "text-model",
        "imageModel": "image-model",
        "chatTimeoutSeconds": 30,
        "imageTimeoutSeconds": 60,
        "maxAutomaticRetries": 0,
    }
    values.update(overrides)
    return ProviderSettingsUpdate.model_validate(values)


def test_base_url_normalization_does_not_reintroduce_root_trailing_slash() -> None:
    settings = ProviderSettings(baseUrl="https://example.test///")

    assert settings.base_url == "https://example.test"


@pytest.mark.parametrize("field", ["visionModel", "textModel", "imageModel"])
def test_model_identifiers_reject_whitespace_only_values(field: str) -> None:
    with pytest.raises(ValidationError):
        _valid_update(**{field: " \t "})


def test_documented_numeric_lower_bounds_are_accepted() -> None:
    settings = _valid_update(
        chatTimeoutSeconds=30,
        imageTimeoutSeconds=60,
        maxAutomaticRetries=0,
    )

    assert settings.chat_timeout_seconds == 30
    assert settings.image_timeout_seconds == 60
    assert settings.max_automatic_retries == 0
