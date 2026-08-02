from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic import SecretStr

from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.secret_store import (
    API_KEY_ENVIRONMENT_VARIABLE,
    WindowsEnvironmentSecretStore,
)


@dataclass
class FailingEnvironmentAdapter:
    process: dict[str, str] = field(default_factory=dict)
    current_user: dict[str, str] = field(default_factory=dict)
    fail_on: str | None = None

    def get_process(self, name: str) -> str | None:
        if self.fail_on == "get_process":
            raise PermissionError("process access denied")
        return self.process.get(name)

    def set_process(self, name: str, value: str) -> None:
        if self.fail_on == "set_process":
            raise PermissionError("process access denied")
        self.process[name] = value

    def delete_process(self, name: str) -> None:
        if self.fail_on == "delete_process":
            raise PermissionError("process access denied")
        self.process.pop(name, None)

    def get_current_user(self, name: str) -> str | None:
        if self.fail_on == "get_current_user":
            raise PermissionError("user environment access denied")
        return self.current_user.get(name)

    def set_current_user(self, name: str, value: str) -> None:
        if self.fail_on == "set_current_user":
            raise PermissionError("user environment access denied")
        self.current_user[name] = value

    def delete_current_user(self, name: str) -> None:
        if self.fail_on == "delete_current_user":
            raise PermissionError("user environment access denied")
        self.current_user.pop(name, None)


def _error_code(callable_object: object, *args: object) -> str:
    with pytest.raises(AppError) as exc_info:
        callable_object(*args)  # type: ignore[operator]
    return exc_info.value.code


def test_set_rolls_back_user_value_when_process_write_fails() -> None:
    old_value = "old-process-value"
    new_value = "new-process-value"
    adapter = FailingEnvironmentAdapter(
        process={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        current_user={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        fail_on="set_process",
    )
    store = WindowsEnvironmentSecretStore(adapter)

    assert _error_code(store.set_api_key, SecretStr(new_value)) == (
        "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE"
    )
    assert adapter.process[API_KEY_ENVIRONMENT_VARIABLE] == old_value
    assert adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] == old_value


def test_set_rolls_back_process_value_when_user_write_fails() -> None:
    old_value = "old-user-value"
    new_value = "new-user-value"
    adapter = FailingEnvironmentAdapter(
        process={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        current_user={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        fail_on="set_current_user",
    )
    store = WindowsEnvironmentSecretStore(adapter)

    assert _error_code(store.set_api_key, SecretStr(new_value)) == (
        "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE"
    )
    assert adapter.process[API_KEY_ENVIRONMENT_VARIABLE] == old_value
    assert adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] == old_value


def test_delete_rolls_back_process_value_when_user_delete_fails() -> None:
    old_value = "value-before-delete"
    adapter = FailingEnvironmentAdapter(
        process={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        current_user={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        fail_on="delete_current_user",
    )
    store = WindowsEnvironmentSecretStore(adapter)

    assert _error_code(store.delete_api_key) == (
        "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE"
    )
    assert adapter.process[API_KEY_ENVIRONMENT_VARIABLE] == old_value
    assert adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] == old_value


def test_delete_rolls_back_user_value_when_process_delete_fails() -> None:
    old_value = "value-before-delete"
    adapter = FailingEnvironmentAdapter(
        process={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        current_user={API_KEY_ENVIRONMENT_VARIABLE: old_value},
        fail_on="delete_process",
    )
    store = WindowsEnvironmentSecretStore(adapter)

    assert _error_code(store.delete_api_key) == (
        "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE"
    )
    assert adapter.process[API_KEY_ENVIRONMENT_VARIABLE] == old_value
    assert adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] == old_value


def test_environment_read_failures_use_safe_app_error() -> None:
    value = "never-return-this-value"
    adapter = FailingEnvironmentAdapter(
        current_user={API_KEY_ENVIRONMENT_VARIABLE: value},
        fail_on="get_process",
    )
    store = WindowsEnvironmentSecretStore(adapter)

    with pytest.raises(AppError) as exc_info:
        store.get_api_key()

    error = exc_info.value
    assert error.code == "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE"
    assert value not in str(error)
    assert value not in repr(error)
