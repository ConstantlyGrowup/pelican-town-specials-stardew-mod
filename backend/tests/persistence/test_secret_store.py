from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from pydantic import SecretStr

from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.secret_store import (
    API_KEY_ENVIRONMENT_VARIABLE,
    ApiKeySource,
    WindowsEnvironmentSecretStore,
)


def _memory_secret() -> str:
    return "memory-only-" + str(uuid4())


@dataclass
class FakeEnvironmentAdapter:
    process: dict[str, str] = field(default_factory=dict)
    current_user: dict[str, str] = field(default_factory=dict)
    fail_on: str | None = None

    def get_process(self, name: str) -> str | None:
        return self.process.get(name)

    def set_process(self, name: str, value: str) -> None:
        self._fail_if_requested("set_process")
        self.process[name] = value

    def delete_process(self, name: str) -> None:
        self._fail_if_requested("delete_process")
        self.process.pop(name, None)

    def get_current_user(self, name: str) -> str | None:
        return self.current_user.get(name)

    def set_current_user(self, name: str, value: str) -> None:
        self._fail_if_requested("set_current_user")
        self.current_user[name] = value

    def delete_current_user(self, name: str) -> None:
        self._fail_if_requested("delete_current_user")
        self.current_user.pop(name, None)

    def _fail_if_requested(self, operation: str) -> None:
        if self.fail_on == operation:
            raise OSError("simulated environment failure")


def test_get_prefers_process_value_over_current_user_value() -> None:
    process_value = _memory_secret()
    user_value = _memory_secret()
    adapter = FakeEnvironmentAdapter(
        process={API_KEY_ENVIRONMENT_VARIABLE: process_value},
        current_user={API_KEY_ENVIRONMENT_VARIABLE: user_value},
    )
    store = WindowsEnvironmentSecretStore(adapter)

    result = store.get_api_key()

    assert result is not None
    assert result.get_secret_value() == process_value
    assert str(result) == "**********"
    assert store.get_source() is ApiKeySource.ENVIRONMENT


def test_get_falls_back_to_current_user_and_ignores_blank_values() -> None:
    user_value = _memory_secret()
    adapter = FakeEnvironmentAdapter(
        process={API_KEY_ENVIRONMENT_VARIABLE: "  \t"},
        current_user={API_KEY_ENVIRONMENT_VARIABLE: user_value},
    )
    store = WindowsEnvironmentSecretStore(adapter)

    result = store.get_api_key()

    assert result is not None
    assert result.get_secret_value() == user_value
    assert store.get_source() is ApiKeySource.ENVIRONMENT

    adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] = "\n"
    assert store.get_api_key() is None
    assert store.get_source() is ApiKeySource.NONE


def test_set_writes_current_user_and_process_for_immediate_reads() -> None:
    value = _memory_secret()
    adapter = FakeEnvironmentAdapter()
    store = WindowsEnvironmentSecretStore(adapter)

    store.set_api_key(SecretStr(value))

    assert adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] == value
    assert adapter.process[API_KEY_ENVIRONMENT_VARIABLE] == value
    assert store.get_api_key() is not None
    assert store.get_api_key().get_secret_value() == value  # type: ignore[union-attr]


def test_set_replaces_existing_values_in_both_stores() -> None:
    old_value = _memory_secret()
    new_value = _memory_secret()
    adapter = FakeEnvironmentAdapter(
        process={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        current_user={API_KEY_ENVIRONMENT_VARIABLE: old_value},
    )
    store = WindowsEnvironmentSecretStore(adapter)

    store.set_api_key(SecretStr(new_value))

    assert adapter.process[API_KEY_ENVIRONMENT_VARIABLE] == new_value
    assert adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] == new_value


def test_delete_clears_current_user_and_process() -> None:
    value = _memory_secret()
    adapter = FakeEnvironmentAdapter(
        process={API_KEY_ENVIRONMENT_VARIABLE: value},
        current_user={API_KEY_ENVIRONMENT_VARIABLE: value},
    )
    store = WindowsEnvironmentSecretStore(adapter)

    store.delete_api_key()

    assert API_KEY_ENVIRONMENT_VARIABLE not in adapter.process
    assert API_KEY_ENVIRONMENT_VARIABLE not in adapter.current_user
    assert store.get_api_key() is None
    assert store.get_source() is ApiKeySource.NONE


def test_environment_failures_become_safe_app_errors() -> None:
    value = _memory_secret()
    adapter = FakeEnvironmentAdapter(fail_on="set_current_user")
    store = WindowsEnvironmentSecretStore(adapter)

    with pytest.raises(AppError) as exc_info:
        store.set_api_key(SecretStr(value))

    error = exc_info.value
    assert error.code == "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE"
    assert error.http_status == 500
    assert error.details == {}
    assert value not in str(error)
    assert value not in repr(error)


def test_fake_adapter_keeps_registry_isolated_on_non_windows() -> None:
    adapter = FakeEnvironmentAdapter()
    store = WindowsEnvironmentSecretStore(adapter)

    store.set_api_key(SecretStr(_memory_secret()))

    assert adapter.current_user
    assert adapter.process
