"""Milestone 7 Task 22: Windows app identity and Gus-portrait icon gates.

Single source of truth for the icon contract is ``scripts/generate_app_icon.py``
(regenerate + ``--check``). These tests import it so the repo gate and the
standalone script cannot drift apart — same pattern as
``scripts/check_product_copy.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCRIPT = REPO_ROOT / "scripts" / "generate_app_icon.py"


def _load_generate_icon() -> object:
    spec = importlib.util.spec_from_file_location("generate_app_icon", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_app_icon"] = module
    spec.loader.exec_module(module)
    return module


def test_app_icon_regenerates_deterministically_and_is_complete() -> None:
    gen = _load_generate_icon()
    violations = gen.check_app_icon(REPO_ROOT)
    assert violations == [], f"app icon gate: {violations}"


def test_app_icon_is_not_default_pyinstaller_icon() -> None:
    gen = _load_generate_icon()
    ico_path = REPO_ROOT / "packaging" / "assets" / "pelican-town-specials.ico"
    assert ico_path.is_file(), "missing generated app icon"
    sizes = gen.ico_sizes(ico_path)
    # A bare default PyInstaller icon would not carry this full size ladder.
    assert set(sizes) == set(gen.REQUIRED_SIZES), f"unexpected sizes: {sizes}"


def test_pyinstaller_spec_embeds_app_icon() -> None:
    spec_path = REPO_ROOT / "packaging" / "pyinstaller" / "PelicanTownSpecials.spec"
    text = spec_path.read_text(encoding="utf-8")
    assert "icon=" in text, "PyInstaller spec must embed an icon"
    assert "pelican-town-specials.ico" in text, "spec must point at the app icon"


def test_version_info_identity_is_frozen() -> None:
    vinfo_path = REPO_ROOT / "packaging" / "pyinstaller" / "version_info.txt"
    text = vinfo_path.read_text(encoding="utf-8")
    assert "Pelican Town Specials" in text
    assert "PelicanTownSpecials" in text
    assert "'1.2.0'" in text or "1.2.0" in text
    assert "FileVersion" in text and "ProductVersion" in text


def test_check_exe_icon_script_exists() -> None:
    script = REPO_ROOT / "scripts" / "check_exe_icon.ps1"
    assert script.is_file(), "build-time EXE icon check script must exist"
