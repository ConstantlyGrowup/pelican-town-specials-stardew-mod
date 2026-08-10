"""Milestone 7 Task 25: frontend copy stays in the typed bilingual catalog."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_check_module():
    """Import scripts/check_frontend_locale.py as a plain module (not a package)."""
    script = REPO_ROOT / "scripts" / "check_frontend_locale.py"
    spec = importlib.util.spec_from_file_location("check_frontend_locale", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frontend_locale_gate_reports_no_violations() -> None:
    module = _load_check_module()
    assert module.check_frontend_locale(REPO_ROOT) == []


def test_gate_flags_legacy_product_copy_token() -> None:
    module = _load_check_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "frontend" / "src"
        (src / "features" / "demo").mkdir(parents=True)
        (src / "features" / "demo" / "Page.tsx").write_text(
            "const copy = PRODUCT_COPY.zh;\n", encoding="utf-8"
        )
        violations = module.check_frontend_locale(root)
        assert any("PRODUCT_COPY" in violation for violation in violations)


def test_gate_flags_scattered_cjk_copy() -> None:
    module = _load_check_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "frontend" / "src"
        (src / "features" / "demo").mkdir(parents=True)
        (src / "features" / "demo" / "Page.tsx").write_text(
            "export const label = \"已保存菜品\";\n", encoding="utf-8"
        )
        violations = module.check_frontend_locale(root)
        assert any("scattered CJK" in violation for violation in violations)


def test_gate_allows_asset_path_and_type_import() -> None:
    module = _load_check_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "frontend" / "src"
        (src / "components" / "ui").mkdir(parents=True)
        (src / "components" / "ui" / "Icon.tsx").write_text(
            'edibility: "/assets/game/specific-icons/饱腹度.png",\n'
            'import type { Language } from "../i18n/copy";\n',
            encoding="utf-8",
        )
        assert module.check_frontend_locale(root) == []
