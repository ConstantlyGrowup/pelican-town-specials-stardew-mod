"""Deterministic preview template resource generator with --check.

Generates resources/templates/preview-v1/{layout.json,frame.png,parchment.png}
and the root resources/provenance.json from fixed parameters. The font is a
registered external asset (Noto Sans SC 2.04), not generated here.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

GENERATOR_VERSION = "preview-resource-generator-v1"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATE_DIR = _REPO_ROOT / "resources" / "templates" / "preview-v1"
_FONT_PATH = _REPO_ROOT / "resources" / "fonts" / "NotoSansSC-VF.ttf"
_PROVENANCE_PATH = _REPO_ROOT / "resources" / "provenance.json"

_FONT_SHA256 = "763146584cf0710223441356b4395e279021b0806c196614377a7a0174ae074a"

_LAYOUT = {
    "schemaVersion": 1,
    "generatorVersion": GENERATOR_VERSION,
    "canvas": {"width": 960, "height": 540},
    "layers": {"frame": "frame.png", "parchment": "parchment.png"},
    "art": {"x": 32, "y": 32, "width": 576, "height": 476},
    "parchment": {"x": 632, "y": 32, "width": 296, "height": 476},
    "frame": {"x": 0, "y": 0, "width": 960, "height": 540},
    "text": {
        "displayName": {
            "x": 660,
            "y": 72,
            "width": 240,
            "height": 132,
            "initialFontSize": 34,
            "minFontSize": 18,
            "maxLines": 5,
        },
        "valueX": 660,
        "valueFontSize": 24,
        "energy": {"y": 250},
        "health": {"y": 296},
        "price": {"y": 386},
    },
}


def _png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _build_frame() -> bytes:
    image = Image.new("RGBA", (960, 540), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 4, 955, 535), outline=(90, 62, 28, 255), width=6)
    draw.rectangle((14, 14, 945, 525), outline=(150, 108, 52, 255), width=2)
    return _png_bytes(image)


def _build_parchment() -> bytes:
    image = Image.new("RGBA", (296, 476), (236, 222, 194, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 295, 475), outline=(150, 120, 70, 255), width=2)
    return _png_bytes(image)


def _build_layout() -> bytes:
    return (json.dumps(_LAYOUT, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _provenance_entries() -> list[dict]:
    assets = [
        ("templates/preview-v1/layout.json", _build_layout()),
        ("templates/preview-v1/frame.png", _build_frame()),
        ("templates/preview-v1/parchment.png", _build_parchment()),
    ]
    entries = []
    for rel_path, data in assets:
        entries.append(
            {
                "path": rel_path,
                "source": "project-original",
                "sourceVersion": GENERATOR_VERSION,
                "sha256": _sha256(data),
                "licenseOrAuthorization": "project-original; no external license required",
                "purpose": "preview-v1 deterministic placeholder resource",
            }
        )
    font_data = _FONT_PATH.read_bytes()
    entries.append(
        {
            "path": "fonts/NotoSansSC-VF.ttf",
            "source": "Google Fonts Noto Sans SC",
            "sourceVersion": "2.04",
            "sha256": _sha256(font_data),
            "licenseOrAuthorization": "SIL Open Font License 1.1",
            "purpose": "Chinese preview text rendering",
        }
    )
    return entries


def _build_provenance() -> bytes:
    document = {
        "schemaVersion": 1,
        "generatorVersion": GENERATOR_VERSION,
        "assets": _provenance_entries(),
    }
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _expected_outputs() -> dict[str, bytes]:
    return {
        str(_TEMPLATE_DIR / "layout.json"): _build_layout(),
        str(_TEMPLATE_DIR / "frame.png"): _build_frame(),
        str(_TEMPLATE_DIR / "parchment.png"): _build_parchment(),
        str(_PROVENANCE_PATH): _build_provenance(),
    }


def build() -> None:
    for path, data in _expected_outputs().items():
        _write(Path(path), data)
    print("Wrote preview resources")


def check() -> int:
    failures = []
    for path, expected in _expected_outputs().items():
        actual = Path(path)
        if not actual.exists():
            failures.append(f"missing: {path}")
            continue
        if actual.read_bytes() != expected:
            failures.append(f"drift: {path}")
    if not _FONT_PATH.exists():
        failures.append(f"missing font: {_FONT_PATH}")
    else:
        actual_font = _sha256(_FONT_PATH.read_bytes())
        if actual_font != _FONT_SHA256:
            failures.append(f"font hash drift: {actual_font}")
    if failures:
        print("\n".join(failures))
        return 1
    print("preview resources OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return check()
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
