"""ZIP slip regression tests for export validation (Task 19 Step 2).

Covers T19-SECURITY-001 against the Task 18 validator: path traversal,
absolute paths, duplicate entries and root orphans are rejected, and
``safe_extract`` refuses any archive that would write outside its target.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

try:
    from scripts.validate_mod_zip import (
        PTS_EXPORT_ZIP_PATH_UNSAFE,
        ModZipValidationResult,
        safe_extract,
        validate_mod_zip,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.validate_mod_zip import (
        PTS_EXPORT_ZIP_PATH_UNSAFE,
        ModZipValidationResult,
        safe_extract,
        validate_mod_zip,
    )

_PACK_ROOT = "[CP] Pelican Town Specials - FamilyMenu"


def build_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for name, data in entries.items():
            handle.writestr(name, data)
    return buffer.getvalue()


def _valid_entries() -> dict[str, bytes]:
    return {
        f"{_PACK_ROOT}/manifest.json": b'{"Name": "x"}',
        f"{_PACK_ROOT}/content.json": b'{"Format": "2.9.0", "Changes": []}',
        f"{_PACK_ROOT}/README.txt": b"install instructions",
    }


def test_zip_rejects_path_traversal() -> None:
    result = validate_mod_zip(build_zip({"../outside.txt": b"bad"}))

    assert isinstance(result, ModZipValidationResult)
    assert result.valid is False
    assert any(issue.code == PTS_EXPORT_ZIP_PATH_UNSAFE for issue in result.issues)


def test_zip_rejects_absolute_paths() -> None:
    for malicious in ("/etc/passwd", "C:/escape.txt", "C:\\escape.txt"):
        result = validate_mod_zip(build_zip({malicious: b"bad"}))
        assert result.valid is False
        assert any(issue.code == PTS_EXPORT_ZIP_PATH_UNSAFE for issue in result.issues)


def test_zip_rejects_backslash_and_colon_paths() -> None:
    result = validate_mod_zip(build_zip({f"{_PACK_ROOT}\\..\\escape.txt": b"bad"}))

    assert result.valid is False
    assert any(issue.code == PTS_EXPORT_ZIP_PATH_UNSAFE for issue in result.issues)


def test_zip_rejects_duplicate_entries() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as handle:
        handle.writestr(f"{_PACK_ROOT}/manifest.json", b"{}")
        handle.writestr(f"{_PACK_ROOT}/manifest.json", b"{}")
    result = validate_mod_zip(buffer.getvalue())

    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_DUPLICATE" for issue in result.issues)


def test_zip_rejects_root_level_orphan() -> None:
    entries = _valid_entries()
    entries["orphan.txt"] = b"stray"
    result = validate_mod_zip(build_zip(entries))

    assert result.valid is False
    assert any(issue.code == "PTS_EXPORT_ZIP_ROOT_FOLDER" for issue in result.issues)


def test_safe_extract_refuses_invalid_zip(tmp_path: Path) -> None:
    malicious = build_zip({"../escape.txt": b"bad"})
    target = tmp_path / "out"

    with pytest.raises(ValueError, match="refusing to extract"):
        safe_extract(malicious, target)

    assert not target.exists()


def test_safe_extract_writes_only_inside_target(tmp_path: Path) -> None:
    target = tmp_path / "out"
    result = safe_extract(build_zip(_valid_entries()), target)

    assert result == target
    assert (target / _PACK_ROOT / "manifest.json").is_file()
    outside = tmp_path / "escape.txt"
    assert not outside.exists()
