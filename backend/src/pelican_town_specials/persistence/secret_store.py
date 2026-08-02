from __future__ import annotations

import os
import sys
from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

from pydantic import SecretStr

from pelican_town_specials.domain.errors import AppError

API_KEY_ENVIRONMENT_VARIABLE = "PTS_OPENAI_API_KEY"


class ApiKeySource(StrEnum):
    ENVIRONMENT = "ENVIRONMENT"
    SESSION = "SESSION"
    NONE = "NONE"


SecretValue = SecretStr
EnvironmentReader = Callable[[str], str | None]


class EnvironmentAdapter(Protocol):
    def get_process(self, name: str) -> str | None: ...

    def set_process(self, name: str, value: str) -> None: ...

    def delete_process(self, name: str) -> None: ...

    def get_current_user(self, name: str) -> str | None: ...

    def set_current_user(self, name: str, value: str) -> None: ...

    def delete_current_user(self, name: str) -> None: ...


class WindowsEnvironmentAdapter:
    """Read and write process and current-user Windows environment values."""

    _user_environment_key = r"Environment"

    def get_process(self, name: str) -> str | None:
        return os.environ.get(name)

    def set_process(self, name: str, value: str) -> None:
        os.environ[name] = value

    def delete_process(self, name: str) -> None:
        os.environ.pop(name, None)

    def get_current_user(self, name: str) -> str | None:
        if sys.platform != "win32":
            return None
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self._user_environment_key,
                0,
                winreg.KEY_READ,
            ) as key:
                value, _value_type = winreg.QueryValueEx(key, name)
                return value if isinstance(value, str) else None
        except FileNotFoundError:
            return None

    def set_current_user(self, name: str, value: str) -> None:
        if sys.platform != "win32":
            raise OSError("current-user environment persistence requires Windows")
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            self._user_environment_key,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        self._broadcast_environment_change()

    def delete_current_user(self, name: str) -> None:
        if sys.platform != "win32":
            raise OSError("current-user environment persistence requires Windows")
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self._user_environment_key,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            self._broadcast_environment_change()
        except FileNotFoundError:
            return

    @staticmethod
    def _broadcast_environment_change() -> None:
        if sys.platform != "win32":
            return
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            1000,
            ctypes.byref(result),
        )


class WindowsEnvironmentSecretStore:
    def __init__(
        self,
        adapter: EnvironmentAdapter | None = None,
        *,
        session_value: SecretValue | None = None,
    ) -> None:
        self._adapter = adapter or WindowsEnvironmentAdapter()
        self._session_value = session_value

    def get_api_key(self) -> SecretValue | None:
        process_value = self._read_value(self._adapter.get_process)
        if process_value is not None:
            return SecretStr(process_value)

        user_value = self._read_value(self._adapter.get_current_user)
        if user_value is not None:
            return SecretStr(user_value)

        return self._session_value

    def set_api_key(self, value: SecretValue) -> None:
        plain_value = self._validated_value(value)
        previous_process = self._read_raw(self._adapter.get_process)
        previous_user = self._read_raw(self._adapter.get_current_user)
        try:
            self._adapter.set_process(API_KEY_ENVIRONMENT_VARIABLE, plain_value)
            self._adapter.set_current_user(API_KEY_ENVIRONMENT_VARIABLE, plain_value)
        except Exception as exc:
            self._restore_process(previous_process)
            self._restore_current_user(previous_user)
            raise self._storage_error("无法保存本机配置，请检查当前用户权限。") from exc

    def delete_api_key(self) -> None:
        previous_process = self._read_raw(self._adapter.get_process)
        previous_user = self._read_raw(self._adapter.get_current_user)
        try:
            self._adapter.delete_process(API_KEY_ENVIRONMENT_VARIABLE)
            self._adapter.delete_current_user(API_KEY_ENVIRONMENT_VARIABLE)
        except Exception as exc:
            self._restore_process(previous_process)
            self._restore_current_user(previous_user)
            raise self._storage_error("无法删除本机配置，请检查当前用户权限。") from exc
        self._session_value = None

    def get_source(self) -> ApiKeySource:
        if self._read_value(self._adapter.get_process) is not None:
            return ApiKeySource.ENVIRONMENT
        if self._read_value(self._adapter.get_current_user) is not None:
            return ApiKeySource.ENVIRONMENT
        if self._session_value is not None:
            return ApiKeySource.SESSION
        return ApiKeySource.NONE

    @staticmethod
    def _validated_value(value: SecretValue) -> str:
        plain_value = value.get_secret_value().strip()
        if not plain_value:
            raise AppError(
                code="PTS_INPUT_API_KEY_INVALID",
                message="API Key 不能为空。",
                http_status=422,
                details={},
                retryable=False,
            )
        return plain_value

    @classmethod
    def _read_raw(cls, reader: EnvironmentReader) -> str | None:
        try:
            value = reader(API_KEY_ENVIRONMENT_VARIABLE)
        except Exception as exc:
            raise cls._storage_error("无法读取本机配置，请检查当前用户权限。") from exc
        return value if isinstance(value, str) else None

    @classmethod
    def _read_value(cls, reader: EnvironmentReader) -> str | None:
        value = cls._read_raw(reader)
        if value is None:
            return None
        stripped_value = value.strip()
        return stripped_value or None

    def _restore_process(self, value: str | None) -> None:
        try:
            if value is None:
                self._adapter.delete_process(API_KEY_ENVIRONMENT_VARIABLE)
            else:
                self._adapter.set_process(API_KEY_ENVIRONMENT_VARIABLE, value)
        except OSError:
            return

    def _restore_current_user(self, value: str | None) -> None:
        try:
            if value is None:
                self._adapter.delete_current_user(API_KEY_ENVIRONMENT_VARIABLE)
            else:
                self._adapter.set_current_user(API_KEY_ENVIRONMENT_VARIABLE, value)
        except OSError:
            return

    @staticmethod
    def _storage_error(message: str) -> AppError:
        return AppError(
            code="PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE",
            message=message,
            http_status=500,
            details={},
            retryable=False,
        )
