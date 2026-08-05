"""Integration tests for release ZIP validation and local deploy (Task 18).

Covers the frozen acceptance ledger:

- T18-VALIDATOR-001/002: ``validate_mod_zip`` path-safety rejection, root
  folder uniqueness, duplicate entries, JSON reopen parsing and PNG RGBA.
- T18-DEPLOY-001/002/003: ``deploy_local_mod.ps1`` resolve/containment
  guards, default overwrite refusal, backup-on-replace without recursive
  delete, and WhatIf no-write behavior.
- T18-INTEGRATION-001: this module runs standalone with
  ``python -m pytest tests/integration/test_release_mod.py -q``.

The deploy integration tests invoke the real PowerShell script with
``subprocess`` and always use ``tmp_path`` as the Mods directory; they never
touch a real game directory. They skip when ``pwsh`` is unavailable (R18-3).
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

try:
    from scripts.validate_mod_zip import (
        PTS_EXPORT_ZIP_PATH_UNSAFE,
        ModZipValidationResult,
        root_folder_name,
        validate_mod_zip,
    )
except ImportError:  # R18-2: namespace-package fallback when cwd is not on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.validate_mod_zip import (
        PTS_EXPORT_ZIP_PATH_UNSAFE,
        ModZipValidationResult,
        root_folder_name,
        validate_mod_zip,
    )

_PACK_ROOT = "[CP] Pelican Town Specials - FamilyMenu"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEPLOY_SCRIPT = _REPO_ROOT / "scripts" / "deploy_local_mod.ps1"
_PWSH = shutil.which("pwsh")


def build_zip(entries: dict[str, bytes]) -> bytes:
    """Build an in-memory ZIP archive from entry-name to bytes mappings."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for name, data in entries.items():
            handle.writestr(name, data)
    return buffer.getvalue()


def build_zip_with_duplicates(pairs: list[tuple[str, bytes]]) -> bytes:
    """Build an in-memory ZIP archive that may contain duplicate entry names."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for name, data in pairs:
            handle.writestr(name, data)
    return buffer.getvalue()


def _png_bytes(*, mode: str = "RGBA") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (16, 16), "tomato").save(buffer, format="PNG")
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


def _run_deploy(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    # Windows PowerShell may emit localized (GBK/UTF-8) bytes on stderr; decode
    # with UTF-8 and replacement characters so the test never crashes on the
    # locale encoding (assertions only look at ASCII substrings).
    return subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(_DEPLOY_SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )


# --- T18-VALIDATOR-001 -----------------------------------------------------


def test_release_zip_rejects_path_traversal() -> None:
    malicious = build_zip({"../outside.txt": b"bad"})
    result = validate_mod_zip(malicious)
    assert isinstance(result, ModZipValidationResult)
    assert result.valid is False
    assert result.issues[0].code == PTS_EXPORT_ZIP_PATH_UNSAFE


# --- T18-VALIDATOR-002 -----------------------------------------------------


def test_release_zip_accepts_single_root_pack() -> None:
    result = validate_mod_zip(build_zip(_valid_entries()))
    assert result.valid is True, result.issues
    assert result.issues == []


def test_release_zip_reports_multiple_root_folders() -> None:
    data = build_zip(
        {
            f"{_PACK_ROOT}/manifest.json": b"{}",
            "SecondPack/manifest.json": b"{}",
        }
    )
    result = validate_mod_zip(data)
    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_ROOT_FOLDER" for issue in result.issues)


def test_release_zip_reports_wrong_root_prefix() -> None:
    data = build_zip({"NotOurPrefix/manifest.json": b"{}"})
    result = validate_mod_zip(data)
    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_ROOT_FOLDER" for issue in result.issues)


def test_release_zip_rejects_root_level_orphan_entry() -> None:
    entries = _valid_entries()
    entries["orphan.txt"] = b"stray"
    result = validate_mod_zip(build_zip(entries))
    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_ROOT_FOLDER" for issue in result.issues)


def test_release_zip_rejects_absolute_path() -> None:
    data = build_zip({"C:/escape.txt": b"bad"})
    result = validate_mod_zip(data)
    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_PATH_UNSAFE" for issue in result.issues)


def test_release_zip_rejects_duplicate_entries() -> None:
    data = build_zip_with_duplicates(
        [
            (f"{_PACK_ROOT}/manifest.json", b"{}"),
            (f"{_PACK_ROOT}/manifest.json", b"{}"),
        ]
    )
    result = validate_mod_zip(data)
    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_DUPLICATE" for issue in result.issues)


def test_release_zip_rejects_invalid_json() -> None:
    data = build_zip({f"{_PACK_ROOT}/manifest.json": b"not json"})
    result = validate_mod_zip(data)
    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_JSON_INVALID" for issue in result.issues)


def test_release_zip_rejects_non_rgba_png() -> None:
    entries = {
        name: content
        for name, content in _valid_entries().items()
        if not name.endswith("objects.png")
    }
    entries[f"{_PACK_ROOT}/assets/objects.png"] = _png_bytes(mode="RGB")
    result = validate_mod_zip(build_zip(entries))
    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_PNG_NOT_RGBA" for issue in result.issues)


def test_release_zip_rejects_not_a_zip() -> None:
    result = validate_mod_zip(b"this is definitely not a zip archive")
    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_INVALID" for issue in result.issues)


def test_root_folder_name_returns_unique_root() -> None:
    assert root_folder_name(build_zip(_valid_entries())) == _PACK_ROOT


# --- T18-DEPLOY-001/002/003 (pwsh integration) -----------------------------


@pytest.mark.skipif(_PWSH is None, reason="pwsh is not available")
def test_deploy_whatif_prints_target_without_writing(tmp_path: Path) -> None:
    pack_zip = tmp_path / "pack.zip"
    pack_zip.write_bytes(build_zip(_valid_entries()))
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()

    proc = _run_deploy(
        "-PackZip", str(pack_zip), "-ModsDir", str(mods_dir), "-WhatIf"
    )

    assert proc.returncode == 0, proc.stderr
    assert _PACK_ROOT in proc.stdout
    assert list(mods_dir.iterdir()) == []


@pytest.mark.skipif(_PWSH is None, reason="pwsh is not available")
def test_deploy_stops_when_mods_dir_missing(tmp_path: Path) -> None:
    pack_zip = tmp_path / "pack.zip"
    pack_zip.write_bytes(build_zip(_valid_entries()))
    missing = tmp_path / "does-not-exist"

    proc = _run_deploy(
        "-PackZip", str(pack_zip), "-ModsDir", str(missing), "-WhatIf"
    )

    assert proc.returncode != 0
    assert not missing.exists()


@pytest.mark.skipif(_PWSH is None, reason="pwsh is not available")
def test_deploy_refuses_overwrite_without_replace(tmp_path: Path) -> None:
    pack_zip = tmp_path / "pack.zip"
    pack_zip.write_bytes(build_zip(_valid_entries()))
    mods_dir = tmp_path / "mods"
    target = mods_dir / _PACK_ROOT
    target.mkdir(parents=True)
    (target / "existing.txt").write_text("existing", encoding="utf-8")

    proc = _run_deploy("-PackZip", str(pack_zip), "-ModsDir", str(mods_dir))

    assert proc.returncode != 0
    assert (target / "existing.txt").read_text(encoding="utf-8") == "existing"
    assert not (target / "manifest.json").exists()


@pytest.mark.skipif(_PWSH is None, reason="pwsh is not available")
def test_deploy_replace_moves_old_pack_to_backup(tmp_path: Path) -> None:
    pack_zip = tmp_path / "pack.zip"
    pack_zip.write_bytes(build_zip(_valid_entries()))
    mods_dir = tmp_path / "mods"
    target = mods_dir / _PACK_ROOT
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old", encoding="utf-8")

    proc = _run_deploy(
        "-PackZip", str(pack_zip), "-ModsDir", str(mods_dir), "-Replace"
    )

    assert proc.returncode == 0, proc.stderr
    assert (target / "manifest.json").exists()
    backup_roots = [d for d in (mods_dir / "_pts_backup").iterdir() if d.is_dir()]
    assert len(backup_roots) == 1
    backup_target = backup_roots[0] / _PACK_ROOT
    assert (backup_target / "old.txt").read_text(encoding="utf-8") == "old"


@pytest.mark.skipif(_PWSH is None, reason="pwsh is not available")
def test_deploy_whatif_replace_prints_backup_without_writing(tmp_path: Path) -> None:
    pack_zip = tmp_path / "pack.zip"
    pack_zip.write_bytes(build_zip(_valid_entries()))
    mods_dir = tmp_path / "mods"
    target = mods_dir / _PACK_ROOT
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old", encoding="utf-8")

    proc = _run_deploy(
        "-PackZip",
        str(pack_zip),
        "-ModsDir",
        str(mods_dir),
        "-Replace",
        "-WhatIf",
    )

    assert proc.returncode == 0, proc.stderr
    assert _PACK_ROOT in proc.stdout
    assert "_pts_backup" in proc.stdout
    assert (target / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (mods_dir / "_pts_backup").exists()
