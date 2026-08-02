from __future__ import annotations

import pytest

from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.secret_store import (
    API_KEY_ENVIRONMENT_VARIABLE,
    WindowsEnvironmentSecretStore,
)


class SourceReadFailureAdapter:
    def get_process(self, name: str) -> str | None:
        assert name == API_KEY_ENVIRONMENT_VARIABLE
        raise PermissionError("process environment unavailable")

    def set_process(self, name: str, value: str) -> None:
        raise AssertionError("not used")

    def delete_process(self, name: str) -> None:
        raise AssertionError("not used")

    def get_current_user(self, name: str) -> str | None:
        raise AssertionError("process read should fail first")

    def set_current_user(self, name: str, value: str) -> None:
        raise AssertionError("not used")

    def delete_current_user(self, name: str) -> None:
        raise AssertionError("not used")


def test_get_source_maps_environment_read_failure() -> None:
    store = WindowsEnvironmentSecretStore(SourceReadFailureAdapter())

    with pytest.raises(AppError) as exc_info:
        store.get_source()

    assert exc_info.value.code == "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE"
    assert "process environment unavailable" not in str(exc_info.value)
