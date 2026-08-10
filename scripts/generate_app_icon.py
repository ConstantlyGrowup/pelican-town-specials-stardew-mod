"""Generate (or verify) the deterministic multi-size Windows app icon.

Task 22 single source of truth for the app icon contract. ``tests/repo`` imports
this module so the pytest gate and the standalone CLI cannot drift apart.

Source of truth: the approved Gus portrait in ``frontend/public/assets/ui``
(stable asset identity; provenance recorded in ``frontend/public/assets/ui/
provenance.json``). The generator resizes it to every size Windows uses for the
EXE, Explorer and shortcuts and writes ``packaging/assets/
pelican-town-specials.ico``. Generation is byte-deterministic: given the same
source PNG, Pillow produces the identical ICO bytes, so the committed artifact
can be audited by re-running the generator.

Usage:
    python scripts/generate_app_icon.py            # (re)generate the .ico
    python scripts/generate_app_icon.py --check    # verify the committed .ico
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_REL = "frontend/public/assets/ui/gus-portrait-1.png"
OUTPUT_REL = "packaging/assets/pelican-town-specials.ico"
PROVENANCE_REL = "packaging/assets/provenance.json"

# Sizes Windows reads from an EXE/ICO resource. Source is square (1254x1254),
# every target is square, so there is no aspect-ratio distortion.
REQUIRED_SIZES = (16, 24, 32, 48, 64, 128, 256)

GENERATOR = "scripts/generate_app_icon.py"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def build_ico_bytes(source: Path) -> bytes:
    """Resize the portrait to every required size and pack into one ICO.

    Deterministic for a fixed source file: same Pillow version + same input
    produce identical bytes (verified by the repo gate re-running this on the
    committed artifact).
    """
    with Image.open(source) as img:
        rgba = img.convert("RGBA")
        buf = io.BytesIO()
        rgba.save(
            buf,
            format="ICO",
            sizes=[(size, size) for size in REQUIRED_SIZES],
            resample=Image.Resampling.LANCZOS,
        )
        return buf.getvalue()


def ico_sizes(ico_path: Path) -> list[int]:
    """Return the stored frame sizes (ICO header, 1 byte width/height per frame)."""
    data = ico_path.read_bytes()
    if len(data) < 6:
        raise ValueError(f"not an ICO: {ico_path}")
    count = int.from_bytes(data[4:6], "little")
    sizes: list[int] = []
    for index in range(count):
        offset = 6 + 16 * index
        if offset + 2 > len(data):
            raise ValueError(f"truncated ICO directory: {ico_path}")
        width = data[offset]
        # ICO stores 256 as 0.
        sizes.append(width if width else 256)
    return sizes


def check_app_icon(repo_root: Path | None = None) -> list[str]:
    """Verify the committed icon; returns a list of violations (empty == OK)."""
    root = repo_root or REPO_ROOT
    source = root / SOURCE_REL
    output = root / OUTPUT_REL
    provenance = root / PROVENANCE_REL

    violations: list[str] = []
    if not source.is_file():
        return [f"missing icon source: {source}"]
    if not output.is_file():
        return [f"missing generated icon: {output}"]

    expected = build_ico_bytes(source)
    actual = output.read_bytes()
    if actual != expected:
        violations.append(
            f"icon is stale: regenerate with `python {GENERATOR}` "
            f"(sha256 got {_sha256_bytes(actual)} expected {_sha256_bytes(expected)})"
        )

    try:
        sizes = sorted(ico_sizes(output))
    except ValueError as exc:
        violations.append(str(exc))
        sizes = []
    if list(REQUIRED_SIZES) != sizes:
        violations.append(f"icon sizes mismatch: expected {list(REQUIRED_SIZES)} got {sizes}")

    if not provenance.is_file():
        violations.append(f"missing icon provenance: {provenance}")
    else:
        try:
            prov = json.loads(provenance.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            violations.append(f"icon provenance is not valid JSON: {provenance} ({exc})")
            prov = {}
        if prov.get("source") != SOURCE_REL:
            violations.append(f"icon provenance source mismatch: {prov.get('source')!r}")
        if prov.get("source_sha256") != _sha256_bytes(source.read_bytes()):
            violations.append(f"icon provenance source_sha256 mismatch: {prov.get('source_sha256')!r}")
        if prov.get("sizes") != list(REQUIRED_SIZES):
            violations.append(f"icon provenance sizes mismatch: {prov.get('sizes')!r}")
        if prov.get("sha256") != _sha256_bytes(actual):
            violations.append(f"icon provenance sha256 mismatch: {prov.get('sha256')!r}")

    return violations


def _write_artifacts(root: Path) -> None:
    source = root / SOURCE_REL
    output = root / OUTPUT_REL
    provenance = root / PROVENANCE_REL

    if not source.is_file():
        raise SystemExit(f"ERROR: missing icon source: {source}")

    data = build_ico_bytes(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)

    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(
        json.dumps(
            {
                "source": SOURCE_REL,
                "source_sha256": _sha256_bytes(source.read_bytes()),
                "sizes": list(REQUIRED_SIZES),
                "sha256": _sha256_bytes(data),
                "generator": GENERATOR,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output} ({len(data)} bytes)")
    print(f"Wrote {provenance}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed icon without writing anything",
    )
    args = parser.parse_args()

    if args.check:
        violations = check_app_icon()
        if violations:
            print("FAIL: app icon check")
            for violation in violations:
                print(f"  - {violation}")
            return 1
        print("OK: app icon is deterministic, complete and provenance is consistent.")
        return 0

    _write_artifacts(REPO_ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
