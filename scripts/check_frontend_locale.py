"""Verify the frontend reads all user-visible copy from the typed catalog.

Milestone 7 Task 25 gate. Three rules keep user-visible strings centralized:

  1. The legacy `PRODUCT_COPY` token must not appear outside `i18n/`.
  2. `features/`, `components/`, and `app/` must not import the copy module
     directly — components read copy through `useCopy()` from `i18n/locale`.
     Type-only imports (`import type { Language } from ...i18n/copy`) are
     allowed and are not user-visible copy.
  3. No scattered CJK / fullwidth text may remain in feature/component/app
     source; the only exceptions are `/assets/game/` asset paths, whose
     filenames legitimately contain Chinese characters.

`tests/repo/test_frontend_locale.py` imports `check_frontend_locale` from here so
the pytest gate and the standalone script cannot drift apart.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# CJK symbols/punctuation, extension A, unified ideographs, compatibility
# ideographs, and fullwidth forms.
_CJK_RE = re.compile(
    "[　-〿㐀-䶿一-鿿豈-﫿＀-￯]"
)

# A `from "...i18n/copy"` import (any quote style, any depth of `../`).
_DIRECT_IMPORT_RE = re.compile(r"""from\s+["'][^"']*i18n/copy["']""")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _frontend_src(root: Path) -> Path | None:
    frontend_src = root / "frontend" / "src"
    if frontend_src.is_dir():
        return frontend_src
    return None


def _scanned_dirs(frontend_src: Path) -> list[Path]:
    return [
        frontend_src / "features",
        frontend_src / "components",
        frontend_src / "app",
    ]


def _source_files(directory: Path) -> list[Path]:
    return [
        path
        for path in directory.rglob("*.ts*")
        if ".test." not in path.name
    ]


def _check_product_copy_token(frontend_src: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(frontend_src.rglob("*.ts*")):
        if "i18n" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "PRODUCT_COPY" in text:
            rel = path.relative_to(frontend_src)
            violations.append(f"{rel}: legacy PRODUCT_COPY token is forbidden")
    return violations


def _check_direct_imports(dirs: list[Path]) -> list[str]:
    violations: list[str] = []
    for directory in dirs:
        for path in _source_files(directory):
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if not _DIRECT_IMPORT_RE.search(line):
                    continue
                # Allow `import type { ... } from "...i18n/copy"` and its
                # continuation line (a `from` clause following `import type`).
                previous = lines[index - 1] if index > 0 else ""
                if line.lstrip().startswith("import type") or previous.lstrip().startswith("import type"):
                    continue
                rel = path.relative_to(dirs[0].parent)
                violations.append(
                    f"{rel}:{index + 1}: use useCopy() from i18n/locale instead "
                    "of importing i18n/copy directly"
                )
    return violations


def _check_scattered_cjk(dirs: list[Path]) -> list[str]:
    violations: list[str] = []
    for directory in dirs:
        for path in _source_files(directory):
            rel = path.relative_to(dirs[0].parent)
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                if "/assets/game/" in line:
                    continue
                if _CJK_RE.search(line):
                    violations.append(
                        f"{rel}:{index + 1}: scattered CJK/fullwidth copy; "
                        "move the string into i18n/copy.ts"
                    )
    return violations


def check_frontend_locale(repo_root: Path | None = None) -> list[str]:
    root = repo_root or _repo_root()
    frontend_src = _frontend_src(root)
    if frontend_src is None:
        return [f"missing frontend/src at {root / 'frontend' / 'src'}"]

    violations: list[str] = []
    violations.extend(_check_product_copy_token(frontend_src))
    violations.extend(_check_direct_imports(_scanned_dirs(frontend_src)))
    violations.extend(_check_scattered_cjk(_scanned_dirs(frontend_src)))
    return violations


def main() -> int:
    violations = check_frontend_locale()
    if violations:
        print("FAIL: frontend locale gate")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("OK: frontend copy stays in the typed catalog.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
