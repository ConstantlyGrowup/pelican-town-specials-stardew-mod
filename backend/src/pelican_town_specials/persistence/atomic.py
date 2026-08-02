from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

T = TypeVar("T")


def _backup_path(path: Path) -> Path:
    return path.with_suffix(f"{path.suffix}.bak")


def _temp_path(path: Path) -> Path:
    return path.parent / f".{path.name}.{uuid4().hex}.tmp"


def _canonical_json_bytes(payload: object) -> bytes:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return f"{text}\n".encode()


def _load_json[T](path: Path, validator: Callable[[object], T]) -> T:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validator(payload)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temp_path(path)

    try:
        with temp_path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        if path.exists():
            shutil.copyfile(path, _backup_path(path))

        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: object) -> None:
    _atomic_write_bytes(path, _canonical_json_bytes(payload))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    _atomic_write_bytes(path, data)


def read_json_with_backup[T](path: Path, validator: Callable[[object], T]) -> T:
    try:
        return _load_json(path, validator)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
    ):
        backup_path = _backup_path(path)
        if not backup_path.exists():
            raise
        return _load_json(backup_path, validator)
