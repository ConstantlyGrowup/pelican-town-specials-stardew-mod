"""Deterministic solid-background removal for model-generated icon art.

Image models asked for a "transparent background" frequently return an
opaque solid backdrop (often black) instead, which renders as an ugly dark
square in the game UI (R12). This module keys out such backgrounds without
any new dependency: when the border of the image is near-uniform, the border
color is treated as the backdrop and every border-connected pixel within a
small per-channel tolerance is made transparent via a flood fill.

Safety rails keep the transform conservative and deterministic:

- images that already carry real transparency are returned untouched;
- a non-uniform (photo-like) border aborts keying;
- if keying would erase almost the whole image, the original is kept.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from statistics import median
from typing import Any, cast

from PIL import Image, ImageChops

from .icon_pipeline import PNGBytes
from .input_normalizer import normalize_upload

# Per-channel absolute distance a pixel may have from the sampled backdrop
# color and still count as background.
_BORDER_TOLERANCE = 40
# Minimum share of border pixels that must match the backdrop color before
# keying is attempted at all.
_BORDER_UNIFORMITY = 0.90
# If the flood fill would remove more than this share of all pixels the
# "background" is almost certainly the subject itself; keep the original.
_MAX_REMOVED_RATIO = 0.98
# Alpha below this means the image already has real transparency.
_OPAQUE_ALPHA = 250


@dataclass(frozen=True, slots=True)
class KeyedIcon:
    data: PNGBytes
    changed: bool


def key_icon_background(source: bytes) -> KeyedIcon:
    """Remove a uniform opaque backdrop from a generated icon.

    Returns the original bytes (``changed=False``) when no keying is needed
    or safe; otherwise returns a re-encoded RGBA PNG with the backdrop made
    transparent (``changed=True``).
    """
    normalized = normalize_upload(source)
    with Image.open(io.BytesIO(normalized.data)) as image:
        rgba = image.convert("RGBA")

    alpha = rgba.getchannel("A")
    lowest_alpha = int(cast(Any, alpha.getextrema())[0])
    if lowest_alpha < _OPAQUE_ALPHA:
        return KeyedIcon(data=source, changed=False)

    background = _sample_border_background(rgba)
    if background is None:
        return KeyedIcon(data=source, changed=False)

    removed = _flood_fill_background(rgba, background)
    total = rgba.width * rgba.height
    removed_count = sum(removed)
    if removed_count == 0 or removed_count > int(total * _MAX_REMOVED_RATIO):
        return KeyedIcon(data=source, changed=False)

    mask = Image.frombytes(
        "L", (rgba.width, rgba.height), bytes(value * 255 for value in removed)
    )
    keyed = rgba.copy()
    keyed.putalpha(ImageChops.subtract(alpha, mask))

    output = io.BytesIO()
    keyed.save(output, format="PNG", optimize=False, compress_level=6)
    return KeyedIcon(data=output.getvalue(), changed=True)


def _as_rgb(value: Any) -> tuple[int, int, int]:
    return (int(value[0]), int(value[1]), int(value[2]))


def _border_pixels(image: Image.Image) -> list[tuple[int, int, int]]:
    pixels = cast(Any, image.load())
    width, height = image.size
    samples: list[tuple[int, int, int]] = []
    for x in range(width):
        samples.append(_as_rgb(pixels[x, 0]))
        samples.append(_as_rgb(pixels[x, height - 1]))
    for y in range(1, height - 1):
        samples.append(_as_rgb(pixels[0, y]))
        samples.append(_as_rgb(pixels[width - 1, y]))
    return samples


def _within_tolerance(
    pixel: tuple[int, int, int], background: tuple[int, int, int]
) -> bool:
    return (
        abs(pixel[0] - background[0]) <= _BORDER_TOLERANCE
        and abs(pixel[1] - background[1]) <= _BORDER_TOLERANCE
        and abs(pixel[2] - background[2]) <= _BORDER_TOLERANCE
    )


def _sample_border_background(image: Image.Image) -> tuple[int, int, int] | None:
    """Return the median border color when the border is near-uniform."""
    samples = _border_pixels(image)
    if not samples:
        return None
    background = (
        int(median(channel[0] for channel in samples)),
        int(median(channel[1] for channel in samples)),
        int(median(channel[2] for channel in samples)),
    )
    inliers = sum(1 for sample in samples if _within_tolerance(sample, background))
    if inliers < len(samples) * _BORDER_UNIFORMITY:
        return None
    return background


def _flood_fill_background(
    image: Image.Image, background: tuple[int, int, int]
) -> bytearray:
    """Mark border-connected background pixels (4-connectivity)."""
    width, height = image.size
    pixels = cast(Any, image.load())
    removed = bytearray(width * height)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        stack.append((x, 0))
        stack.append((x, height - 1))
    for y in range(1, height - 1):
        stack.append((0, y))
        stack.append((width - 1, y))

    while stack:
        x, y = stack.pop()
        if not (0 <= x < width and 0 <= y < height):
            continue
        index = y * width + x
        if removed[index]:
            continue
        if not _within_tolerance(_as_rgb(pixels[x, y]), background):
            continue
        removed[index] = 1
        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))
    return removed
