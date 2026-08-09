"""Verify public docs use the frozen product names and feature labels.

Single source of truth for the naming gate (Task 20). `tests/repo/test_product_copy.py`
imports `check_product_copy` from here so the pytest gate and the standalone script
cannot drift apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Frozen product identity: README and app copy must use these.
FROZEN_REQUIRED_NAMES = (
    "鹈鹕镇新菜单",
    "Pelican Town Specials",
)

# Frozen tagline used across the product shell.
FROZEN_TAGLINE = "把你做的菜，写进鹈鹕镇的下一张菜单。"

# User-facing guide anchors a complete README must contain (Task 20 README
# ordering). These are not product-identity names; they keep the README from
# regressing to a stub.
FROZEN_REQUIRED_ANCHORS = (
    "开始使用",
    "首次设置",
    "收集品",
    "打包菜单",
    "带进游戏",
    "隐私",
)

# Obsolete names that must never appear in public docs.
FROZEN_FORBIDDEN_NAMES = (
    "StarValley Cook Agent",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def check_product_copy(repo_root: Path | None = None) -> list[str]:
    root = repo_root or _repo_root()
    readme_path = root / "README.md"
    if not readme_path.is_file():
        return [f"missing README.md at {readme_path}"]
    text = readme_path.read_text(encoding="utf-8")

    violations: list[str] = []
    for name in FROZEN_REQUIRED_NAMES:
        if name not in text:
            violations.append(f"README.md must contain frozen product name: {name}")
    if FROZEN_TAGLINE not in text:
        violations.append(f"README.md must contain the product tagline: {FROZEN_TAGLINE}")
    for anchor in FROZEN_REQUIRED_ANCHORS:
        if anchor not in text:
            violations.append(f"README.md must contain user guide anchor: {anchor}")
    for name in FROZEN_FORBIDDEN_NAMES:
        if name in text:
            violations.append(f"README.md must not contain obsolete name: {name}")
    return violations


def main() -> int:
    violations = check_product_copy()
    if violations:
        print("FAIL: product copy check")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("OK: README uses frozen product names and required guide anchors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
