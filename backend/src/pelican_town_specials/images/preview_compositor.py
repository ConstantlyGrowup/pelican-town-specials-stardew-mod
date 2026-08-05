"""Deterministic local preview composition over the original dish photograph."""

from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pelican_town_specials.domain.dish import GameplaySpec, PresentationSpec

PNGBytes = bytes

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TEMPLATE_DIR = _REPO_ROOT / "resources" / "templates" / "preview-v1"
_FONT_PATH = _REPO_ROOT / "resources" / "fonts" / "NotoSansSC-VF.ttf"


class PreviewSnapshot:
    """The immutable visual inputs consumed by the local compositor.

    ``original_image`` is the only photo canvas. ``icon_16`` is the normalized
    model-produced icon; no generated full-size art is accepted here.
    """

    __slots__ = ("gameplay", "icon_16", "original_image", "presentation")

    def __init__(
        self,
        *,
        original_image: bytes,
        icon_16: bytes,
        presentation: PresentationSpec,
        gameplay: GameplaySpec,
    ) -> None:
        self.original_image = original_image
        self.icon_16 = icon_16
        self.presentation = presentation
        self.gameplay = gameplay


def compose_preview(snapshot: PreviewSnapshot) -> PNGBytes:
    """Add a compact game card to a copy of the original image.

    The source image is opened at its native size and copied directly to the
    output canvas. Only the card rectangle is changed; there is no crop,
    generated-art layer, global recolour, or full-canvas frame.
    """
    layout = json.loads((_TEMPLATE_DIR / "layout.json").read_text(encoding="utf-8"))
    with Image.open(io.BytesIO(snapshot.original_image)) as source:
        canvas = source.convert("RGBA")

    card_x, card_y, card_width, card_height = _card_geometry(canvas.size)
    card = _load_layer(
        layout["layers"]["parchment"], (card_width, card_height)
    )
    canvas.paste(card, (card_x, card_y), card)
    _paste_icon(canvas, snapshot.icon_16, card_x, card_y, card_width, card_height)
    _draw_text(
        canvas,
        snapshot,
        x=card_x,
        y=card_y,
        width=card_width,
        height=card_height,
    )

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _card_geometry(size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    margin = max(4, round(min(width, height) * 0.03))
    card_width = max(32, round(width * 0.30))
    card_width = min(card_width, max(1, width - (margin * 2)))
    # Keep the card compact in landscape photos while retaining the tall
    # parchment proportions for portrait photos.
    card_height = min(round(height * 0.50), card_width)
    card_height = max(32, min(card_height, max(1, height - margin)))
    card_x = max(0, width - card_width - margin)
    card_y = margin
    return card_x, card_y, card_width, card_height


def _load_layer(name: str, size: tuple[int, int]) -> Image.Image:
    path = _TEMPLATE_DIR / name
    with Image.open(path) as layer:
        return layer.convert("RGBA").resize(size, Image.Resampling.NEAREST)


def _paste_icon(
    canvas: Image.Image,
    icon_bytes: bytes,
    card_x: int,
    card_y: int,
    card_width: int,
    card_height: int,
) -> None:
    icon_size = max(16, round(card_width * 0.18))
    with Image.open(io.BytesIO(icon_bytes)) as source:
        if source.size != (16, 16):
            raise ValueError("icon_16 must be exactly 16x16 pixels")
        icon = source.convert("RGBA").resize(
            (icon_size, icon_size), Image.Resampling.NEAREST
        )
    icon_x = card_x + (card_width - icon_size) // 2
    icon_y = card_y + max(4, round(card_height * 0.04))
    canvas.paste(icon, (icon_x, icon_y), icon)


def _draw_text(
    canvas: Image.Image,
    snapshot: PreviewSnapshot,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    del height  # The card geometry is fixed before text is drawn.
    draw = ImageDraw.Draw(canvas)
    padding = max(4, round(width * 0.08))
    content_x = x + padding
    content_width = max(1, width - (padding * 2))
    icon_size = max(16, round(width * 0.18))
    cursor = y + max(4, round(width * 0.04)) + icon_size + max(2, round(width * 0.02))

    title_lines, title_size = _wrap_lines(
        snapshot.presentation.display_name,
        content_width,
        max(10, round(width * 0.11)),
        max(8, round(width * 0.06)),
        5,
    )
    title_font = _load_font(title_size)
    cursor = _draw_lines(draw, title_lines, title_font, content_x, cursor, (40, 32, 20, 255))

    category_font = _load_font(max(8, round(width * 0.065)))
    cursor = _draw_lines(
        draw,
        [snapshot.presentation.category_label],
        category_font,
        content_x,
        cursor + max(1, round(width * 0.01)),
        (128, 44, 30, 255),
    )
    cursor += max(2, round(width * 0.02))
    _draw_divider(draw, content_x, cursor, content_width)
    cursor += max(4, round(width * 0.04))

    description_lines, description_size = _wrap_lines(
        snapshot.presentation.description,
        content_width,
        max(8, round(width * 0.055)),
        max(7, round(width * 0.04)),
        2,
    )
    description_font = _load_font(description_size)
    cursor = _draw_lines(
        draw,
        description_lines,
        description_font,
        content_x,
        cursor,
        (40, 32, 20, 255),
    )
    cursor += max(2, round(width * 0.02))
    _draw_divider(draw, content_x, cursor, content_width)
    cursor += max(4, round(width * 0.04))

    value_font = _load_font(max(9, round(width * 0.068)))
    recovery = snapshot.gameplay.recovery
    rows = [
        f"体力 +{recovery.energy_restore}",
        f"生命 +{recovery.health_restore}",
        f"售价 {snapshot.gameplay.sell_price}g",
    ]
    _draw_lines(draw, rows, value_font, content_x, cursor, (40, 32, 20, 255))


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    fill: tuple[int, int, int, int],
) -> int:
    line_height = font.getmetrics()[0] + font.getmetrics()[1] + max(1, round(font.size * 0.08))
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _draw_divider(draw: ImageDraw.ImageDraw, x: int, y: int, width: int) -> None:
    draw.line((x, y, x + width, y), fill=(150, 90, 40, 220), width=max(1, round(width * 0.008)))


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
