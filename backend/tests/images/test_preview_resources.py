"""Preview template resource registration and integrity tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RESOURCES = _REPO_ROOT / "resources"


def _provenance() -> dict:
    return json.loads((_RESOURCES / "provenance.json").read_text(encoding="utf-8"))


def test_provenance_registers_exactly_the_template_and_font_files() -> None:
    registered = {entry["path"] for entry in _provenance()["assets"]}
    actual = set()
    for directory in ("templates", "fonts"):
        for path in (_RESOURCES / directory).rglob("*"):
            if path.is_file():
                actual.add(str(path.relative_to(_RESOURCES)).replace("\\", "/"))
    assert actual == registered


def test_provenance_entries_have_required_fields_and_matching_hashes() -> None:
    required = {"path", "source", "sourceVersion", "sha256", "licenseOrAuthorization", "purpose"}
    seen: set[str] = set()
    for entry in _provenance()["assets"]:
        assert required.issubset(entry.keys())
        path = entry["path"]
        assert path not in seen
        seen.add(path)
        data = (_RESOURCES / path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_generator_check_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_preview_resources.py", "--check"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
