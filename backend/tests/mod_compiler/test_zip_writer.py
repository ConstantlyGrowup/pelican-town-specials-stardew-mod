"""Deterministic ZIP writer and reopen verification tests (plan Task 16 Steps 2/5)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from pelican_town_specials.mod_compiler.zip_writer import verify_zip, write_zip

_PACK_ROOT = "[CP] Pelican Town Specials - FamilyMenu"


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (16, 16), "tomato").save(buffer, format="PNG")
    return buffer.getvalue()


def _valid_entries() -> dict[str, bytes]:
    return {
        f"{_PACK_ROOT}/manifest.json": json.dumps(
            {"Name": "Pelican Town Specials - FamilyMenu"}, indent=2
        ).encode("utf-8"),
        f"{_PACK_ROOT}/content.json": b'{"Format": "2.9.0", "Changes": []}',
        f"{_PACK_ROOT}/i18n/default.json": b'{"item.X.name": "X"}',
        f"{_PACK_ROOT}/README.txt": b"install instructions",
        f"{_PACK_ROOT}/assets/objects.png": _png_bytes(),
    }


def test_write_zip_is_byte_identical_for_same_input(tmp_path: Path) -> None:
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    write_zip(first, _valid_entries())
    write_zip(second, _valid_entries())

    assert first.read_bytes() == second.read_bytes()


def test_write_zip_uses_fixed_timestamps_and_sorted_entries(tmp_path: Path) -> None:
    path = tmp_path / "pack.zip"

    write_zip(path, _valid_entries())

    with zipfile.ZipFile(path) as handle:
        names = handle.namelist()
        assert names == sorted(names)
        for info in handle.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_DEFLATED


def test_verify_zip_accepts_single_root_pack(tmp_path: Path) -> None:
    path = tmp_path / "pack.zip"

    write_zip(path, _valid_entries())
    verify_zip(path)


def test_write_zip_rejects_path_traversal(tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"

    with pytest.raises(ValueError):
        write_zip(path, {"../escape.txt": b"oops"})


def test_write_zip_rejects_absolute_entry(tmp_path: Path) -> None:
    path = tmp_path / "abs.zip"

    with pytest.raises(ValueError):
        write_zip(path, {"/etc/passwd": b"oops"})


def test_verify_zip_rejects_traversal_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"
    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr(f"{_PACK_ROOT}/../../escape.txt", b"oops")

    with pytest.raises(ValueError):
        verify_zip(path)


def test_verify_zip_rejects_multiple_root_folders(tmp_path: Path) -> None:
    path = tmp_path / "multi.zip"
    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr("PackOne/manifest.json", b"{}")
        handle.writestr("PackTwo/manifest.json", b"{}")

    with pytest.raises(ValueError):
        verify_zip(path)


def test_verify_zip_rejects_duplicate_entries(tmp_path: Path) -> None:
    path = tmp_path / "dup.zip"
    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr(f"{_PACK_ROOT}/manifest.json", b"{}")
        handle.writestr(f"{_PACK_ROOT}/manifest.json", b"{}")

    with pytest.raises(ValueError):
        verify_zip(path)


def test_verify_zip_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad-json.zip"
    write_zip(path, {f"{_PACK_ROOT}/manifest.json": b"not json"})

    with pytest.raises(ValueError):
        verify_zip(path)


def test_verify_zip_rejects_non_rgba_png(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "tomato").save(buffer, format="PNG")
    path = tmp_path / "rgb.zip"
    write_zip(path, {f"{_PACK_ROOT}/assets/objects.png": buffer.getvalue()})

    with pytest.raises(ValueError):
        verify_zip(path)
