"""Deterministic preview composition from templates and structured dish fields."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from pelican_town_specials.domain.dish import GameplaySpec, PresentationSpec

PNGBytes = bytes

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TEMPLATE_DIR = _REPO_ROOT / "resources" / "templates" / "preview-v1"
_FONT_PATH = _REPO_ROOT / "resources" / "fonts" / "NotoSansSC-VF.ttf"


class PreviewSnapshot:
    __slots__ = ("gameplay", "generated_art", "presentation")

    def __init__(
        self,
        *,
        generated_art: bytes,
        presentation: PresentationSpec,
        gameplay: GameplaySpec,
    ) -> None:
        self.generated_art = generated_art
        self.presentation = presentation
        self.gameplay = gameplay


def compose_preview(snapshot: PreviewSnapshot) -> PNGBytes:
    layout = json.loads((_TEMPLATE_DIR / "layout.json").read_text(encoding="utf-8"))
    canvas = _canvas(layout)
    _paste_art(canvas, snapshot.generated_art, layout["art"])
    _paste_layer(canvas, layout, "parchment", layout["parchment"])
    _draw_text(canvas, snapshot, layout["text"])
    _paste_layer(canvas, layout, "frame", layout["frame"])

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _canvas(layout: dict[str, Any]) -> Image.Image:
    return Image.new("RGBA", (layout["canvas"]["width"], layout["canvas"]["height"]), (0, 0, 0, 0))


def _paste_art(canvas: Image.Image, art_bytes: bytes, region: dict[str, Any]) -> None:
    with Image.open(io.BytesIO(art_bytes)) as source:
        rgba = source.convert("RGBA")
        cropped = _cover_crop(rgba, region["width"], region["height"]).resize(
            (region["width"], region["height"]), Image.Resampling.LANCZOS
        )
        canvas.paste(cropped, (region["x"], region["y"]))


def _paste_layer(
    canvas: Image.Image,
    layout: dict[str, Any],
    name: str,
    region: dict[str, Any],
) -> None:
    path = _TEMPLATE_DIR / layout["layers"][name]
    with Image.open(path) as layer:
        rgba = layer.convert("RGBA")
        canvas.paste(rgba, (region["x"], region["y"]), rgba)


def _draw_text(
    canvas: Image.Image,
    snapshot: PreviewSnapshot,
    text: dict[str, Any],
) -> None:
    draw = ImageDraw.Draw(canvas)
    display_region = text["displayName"]
    lines, font_size = _wrap_lines(
        snapshot.presentation.display_name,
        display_region["width"],
        display_region["initialFontSize"],
        display_region["minFontSize"],
        display_region["maxLines"],
    )
    font = _load_font(font_size)
    y_cursor = display_region["y"]
    for line in lines:
        draw.text(
            (display_region["x"], y_cursor),
            line,
            font=font,
            fill=(40, 32, 20, 255),
        )
        y_cursor += font.getmetrics()[0] + 4

    value_font = _load_font(text["valueFontSize"])
    recovery = snapshot.gameplay.recovery
    rows = (
        (f"体力 +{recovery.energy_restore}", text["energy"]["y"]),
        (f"生命 +{recovery.health_restore}", text["health"]["y"]),
        (f"售价 {snapshot.gameplay.sell_price}g", text["price"]["y"]),
    )
    for label, y in rows:
        draw.text((text["valueX"], y), label, font=value_font, fill=(40, 32, 20, 255))


def _wrap_lines(
    text: str,
    max_width: int,
    initial_size: int,
    min_size: int,
    max_lines: int,
) -> tuple[list[str], int]:
    for size in range(initial_size, min_size - 1, -2):
        font = _load_font(size)
        lines = _measure_lines(text, font, max_width)
        if len(lines) <= max_lines:
            return lines, size
    return _measure_lines(text, _load_font(min_size), max_width), min_size


def _measure_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if font.getlength(candidate) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(_FONT_PATH), size, layout_engine=ImageFont.Layout.BASIC)
    try:
        font.set_variation_by_axes([400.0])
    except (ValueError, OSError):
        pass
    return font


def _cover_crop(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = image.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        box = (left, 0, left + new_w, src_h)
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        box = (0, top, src_w, top + new_h)
    return image.crop(box)
