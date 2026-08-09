"""Milestone 6 Task 20: public docs use the frozen product names."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_check_module():
    """Import scripts/check_product_copy.py as a plain module (not a package)."""
    script = REPO_ROOT / "scripts" / "check_product_copy.py"
    spec = importlib.util.spec_from_file_location("check_product_copy", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readme_uses_frozen_product_names() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "鹈鹕镇新菜单" in text
    assert "Pelican Town Specials" in text
    assert "StarValley Cook Agent" not in text


def test_check_product_copy_reports_no_violations() -> None:
    module = _load_check_module()
    assert module.check_product_copy(REPO_ROOT) == []
