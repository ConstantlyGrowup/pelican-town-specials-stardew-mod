"""Standalone Content Patcher ZIP validation and safe extraction (Task 18).

This script validates an arbitrary exported content pack ZIP before it is
deployed into a Stardew Valley Mods directory. It is intentionally independent
of the backend compiler (``mod_compiler``) so the deployment toolchain works on
any ZIP produced by any exporter, but it mirrors the Task 16 reopen-verification
semantics (design 14.7 step 9): path traversal / absolute paths / duplicate
entries are rejected, the ZIP must contain exactly one ``[CP] Pelican Town
Specials - <PackSlug>`` root folder, JSON documents must reopen-parse and PNGs
must be RGBA.

CLI::

    python scripts/validate_mod_zip.py --zip <path>                  # report
    python scripts/validate_mod_zip.py --zip <path> --print-root     # root name
    python scripts/validate_mod_zip.py --zip <path> --extract-to <dir>

The validator never writes to a game directory; ``--extract-to`` extracts only
after the whole archive has passed validation.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - RGBA audit is skipped without Pillow
    Image = None  # type: ignore[assignment]

PACK_FOLDER_PREFIX = "[CP] Pelican Town Specials - "

# Stable issue codes surfaced by the validator.
PTS_EXPORT_ZIP_PATH_UNSAFE = "PTS_EXPORT_ZIP_PATH_UNSAFE"
PTS_EXPORT_ZIP_INVALID = "PTS_EXPORT_ZIP_INVALID"
PTS_EXPORT_ZIP_EMPTY = "PTS_EXPORT_ZIP_EMPTY"
PTS_EXPORT_ZIP_DUPLICATE = "PTS_EXPORT_ZIP_DUPLICATE"
PTS_EXPORT_ZIP_ROOT_FOLDER = "PTS_EXPORT_ZIP_ROOT_FOLDER"
PTS_EXPORT_ZIP_JSON_INVALID = "PTS_EXPORT_ZIP_JSON_INVALID"
PTS_EXPORT_ZIP_PNG_INVALID = "PTS_EXPORT_ZIP_PNG_INVALID"
PTS_EXPORT_ZIP_PNG_NOT_RGBA = "PTS_EXPORT_ZIP_PNG_NOT_RGBA"


@dataclass(frozen=True)
class ModZipIssue:
    """One validation finding."""

    code: str
    message: str


@dataclass(frozen=True)
class ModZipValidationResult:
    """Outcome of validating a candidate content pack ZIP."""

    valid: bool
    issues: list[ModZipIssue]


def validate_mod_zip(data: bytes) -> ModZipValidationResult:
    """Reopen and audit a ZIP archive, returning every issue found."""
    issues: list[ModZipIssue] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as handle:
            infos = handle.infolist()
            names = [info.filename for info in infos]
            _audit_entry_names(names, issues)
            for info in infos:
                if info.filename.endswith(".json"):
                    _audit_json(handle.read(info), info.filename, issues)
                elif info.filename.endswith(".png"):
                    _audit_png(handle.read(info), info.filename, issues)
    except zipfile.BadZipFile as exc:
        issues.append(
            ModZipIssue(PTS_EXPORT_ZIP_INVALID, f"ZIP 无法打开: {exc}")
        )
    return ModZipValidationResult(valid=not issues, issues=issues)


def root_folder_name(data: bytes) -> str:
    """Return the single content pack root folder name inside the ZIP.

    Raises ``ValueError`` when the archive has zero or more than one root
    folder. The caller is expected to have validated the archive first.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as handle:
        names = [info.filename for info in handle.infolist()]
    roots = {name.partition("/")[0] for name in names if "/" in name}
    if len(roots) != 1:
        raise ValueError(
            f"expected exactly one root folder, got {len(roots)}: {', '.join(sorted(roots))}"
        )
    return next(iter(roots))


def safe_extract(data: bytes, target: Path) -> Path:
    """Extract a validated ZIP under ``target`` without path escapes.

    Refuses to extract anything when validation fails. Because validation has
    already rejected absolute paths, ``..`` segments and duplicates, extraction
    is additionally guarded by a containment check on every member.
    """
    result = validate_mod_zip(data)
    if not result.valid:
        summary = "; ".join(f"{issue.code}: {issue.message}" for issue in result.issues)
        raise ValueError(f"refusing to extract invalid ZIP: {summary}")
    target.mkdir(parents=True, exist_ok=True)
    target_root = target.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as handle:
        for info in handle.infolist():
            if info.is_dir():
                continue
            member = _safe_member_target(target_root, info.filename)
            member.parent.mkdir(parents=True, exist_ok=True)
            member.write_bytes(handle.read(info))
    return target


def _audit_entry_names(names: list[str], issues: list[ModZipIssue]) -> None:
    if not names:
        issues.append(ModZipIssue(PTS_EXPORT_ZIP_EMPTY, "ZIP 不包含任何条目"))
        return

    seen: set[str] = set()
    for name in names:
        if name in seen:
            issues.append(
                ModZipIssue(PTS_EXPORT_ZIP_DUPLICATE, f"重复文件: {name}")
            )
        seen.add(name)

    for name in names:
        if _is_unsafe_path(name):
            issues.append(
                ModZipIssue(PTS_EXPORT_ZIP_PATH_UNSAFE, f"不安全的 ZIP 路径: {name}")
            )

    # Reject root-level orphan members (entries not inside the content pack
    # folder). Design 14.2 requires the ZIP root to contain only the content
    # pack folder; the Task 16 zip_writer enforces the same single-root rule.
    for name in names:
        if "/" not in name:
            issues.append(
                ModZipIssue(
                    PTS_EXPORT_ZIP_ROOT_FOLDER,
                    f"ZIP 根目录下的孤立条目必须位于内容包根文件夹内: {name}",
                )
            )

    roots = {name.partition("/")[0] for name in names if "/" in name}
    if not roots:
        issues.append(
            ModZipIssue(PTS_EXPORT_ZIP_ROOT_FOLDER, "ZIP 没有位于根文件夹内的条目")
        )
    elif len(roots) > 1:
        issues.append(
            ModZipIssue(
                PTS_EXPORT_ZIP_ROOT_FOLDER,
                f"ZIP 必须只包含一个内容包根文件夹, 得到 {len(roots)} 个: "
                f"{', '.join(sorted(roots))}",
            )
        )
    else:
        root = next(iter(roots))
        if not root.startswith(PACK_FOLDER_PREFIX):
            issues.append(
                ModZipIssue(
                    PTS_EXPORT_ZIP_ROOT_FOLDER,
                    f"根文件夹必须以 '{PACK_FOLDER_PREFIX}' 开头, 实际: {root}",
                )
            )


def _is_unsafe_path(name: str) -> bool:
    if not name:
        return True
    if name.startswith("/") or name.startswith("\\"):
        return True
    if "\\" in name or ":" in name:
        return True
    return any(part == ".." for part in name.split("/"))


def _audit_json(data: bytes, name: str, issues: list[ModZipIssue]) -> None:
    try:
        json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        issues.append(
            ModZipIssue(PTS_EXPORT_ZIP_JSON_INVALID, f"JSON 无法解析: {name} ({exc})")
        )


def _audit_png(data: bytes, name: str, issues: list[ModZipIssue]) -> None:
    if Image is None:
        return
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            mode = image.mode
    except Exception as exc:
        issues.append(
            ModZipIssue(PTS_EXPORT_ZIP_PNG_INVALID, f"PNG 无法打开: {name} ({exc})")
        )
        return
    if mode != "RGBA":
        issues.append(
            ModZipIssue(PTS_EXPORT_ZIP_PNG_NOT_RGBA, f"PNG 必须为 RGBA: {name}")
        )


def _safe_member_target(target_root: Path, name: str) -> Path:
    resolved = (target_root / name).resolve()
    if not resolved.is_relative_to(target_root):
        raise ValueError(f"entry escapes extraction root: {name}")
    return resolved


def _print_report(result: ModZipValidationResult, *, stream=sys.stdout) -> None:
    if result.valid:
        print("OK: ZIP is valid")
        return
    print(f"INVALID: {len(result.issues)} issue(s) found", file=stream)
    for issue in result.issues:
        print(f"  - {issue.code}: {issue.message}", file=stream)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True, help="Path to the export ZIP.")
    parser.add_argument(
        "--extract-to",
        type=Path,
        default=None,
        help="Safely extract a validated ZIP into this directory.",
    )
    parser.add_argument(
        "--print-root",
        action="store_true",
        help="Print the unique content pack root folder name after validating.",
    )
    args = parser.parse_args()

    try:
        data = args.zip.read_bytes()
    except OSError as exc:
        print(f"validate_mod_zip: cannot read ZIP {args.zip}: {exc}", file=sys.stderr)
        return 2

    result = validate_mod_zip(data)

    if args.print_root:
        if not result.valid:
            _print_report(result, stream=sys.stderr)
            return 1
        try:
            print(root_folder_name(data))
        except ValueError as exc:
            print(f"validate_mod_zip: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.extract_to is not None:
        if not result.valid:
            _print_report(result, stream=sys.stderr)
            return 1
        try:
            safe_extract(data, args.extract_to)
        except (OSError, ValueError) as exc:
            print(f"validate_mod_zip: extraction failed: {exc}", file=sys.stderr)
            return 1
        print(f"validate_mod_zip: extracted to {args.extract_to}")
        return 0

    _print_report(result)
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
