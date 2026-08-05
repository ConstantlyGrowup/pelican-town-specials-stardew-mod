"""Deterministic ZIP writer and reopen verification for compiled packs.

The writer fixes everything that could make two compilations differ:
sorted entry names, a fixed ``date_time``, fixed compression parameters and
no ZIP64 extensions for the small pack payloads. ``verify_zip`` reopens the
artifact and re-audits path safety, duplicate entries, JSON and PNG content
(design 14.7 step 9).
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from pathlib import Path

from PIL import Image

_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_FIXED_COMPRESS_LEVEL = 9
_FIXED_EXTERNAL_ATTR = 0o600 << 16


def write_zip(zip_path: Path, entries: Mapping[str, bytes]) -> None:
    """Write a deterministic ZIP archive from entry name to bytes mappings."""
    _validate_entry_names(list(entries))
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=_FIXED_COMPRESS_LEVEL,
    ) as handle:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = _FIXED_EXTERNAL_ATTR
            handle.writestr(info, entries[name])


def verify_zip(zip_path: Path) -> None:
    """Reopen the ZIP and verify path safety, JSON and PNG contents."""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("artifact is not a valid ZIP")
    with zipfile.ZipFile(zip_path) as handle:
        infos = handle.infolist()
        _validate_entry_names([info.filename for info in infos])
        for info in infos:
            data = handle.read(info)
            if info.filename.endswith(".json"):
                _verify_json(data)
            elif info.filename.endswith(".png"):
                _verify_png(data)


def _validate_entry_names(names: list[str]) -> None:
    if not names:
        raise ValueError("ZIP must contain at least one entry")
    if len(set(names)) != len(names):
        raise ValueError("ZIP contains duplicate entries")
    for name in names:
        if not name:
            raise ValueError("ZIP contains an empty entry name")
        if name.startswith("/") or "\\" in name or ":" in name:
            raise ValueError("ZIP contains an unsafe entry path")
        if ".." in name.split("/"):
            raise ValueError("ZIP contains a path traversal entry")
    roots = {name.partition("/")[0] for name in names if "/" in name}
    if any("/" not in name for name in names) or len(roots) != 1:
        raise ValueError("ZIP must contain exactly one root folder")


def _verify_json(data: bytes) -> None:
    try:
        json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ZIP contains invalid JSON") from exc


def _verify_png(data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            mode = image.mode
    except Exception as exc:
        raise ValueError("ZIP contains an invalid PNG") from exc
    if mode != "RGBA":
        raise ValueError("ZIP PNG must be RGBA")
