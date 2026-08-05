"""Vision input shaping: long-side cap, min-pixel floor, JPEG RGB re-encode.

The stored original image asset is preserved exactly; this helper only shapes
the bytes handed to a vision or image-edit provider, which does not need
full-resolution input.
"""

from __future__ import annotations

import io
import math
import warnings

from PIL import Image

from pelican_town_specials.providers.contracts import ImageMediaType

VISION_MAX_SIDE = 2048
VISION_JPEG_QUALITY = 85
# Image-edits providers require every edge to be a multiple of this value.
VISION_EDGE_MULTIPLE = 16
# Image providers reject inputs whose total pixels fall below this floor
# (observed: "total pixels must not be less than 655360").
VISION_MIN_PIXELS = 655_360

_SOURCE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})


def _align_edge(px: int) -> int:
    """Round an edge length down to the provider-required multiple (min 16)."""
    aligned = (px // VISION_EDGE_MULTIPLE) * VISION_EDGE_MULTIPLE
    return max(VISION_EDGE_MULTIPLE, aligned)


def _ceil_align_edge(px: float) -> int:
    """Round an edge length up to the provider-required multiple (min 16)."""
    aligned = (math.ceil(px) + VISION_EDGE_MULTIPLE - 1) // VISION_EDGE_MULTIPLE
    return max(VISION_EDGE_MULTIPLE, aligned * VISION_EDGE_MULTIPLE)


def downscale_for_vision(
    data: bytes,
    *,
    max_side: int = VISION_MAX_SIDE,
    quality: int = VISION_JPEG_QUALITY,
    min_pixels: int = VISION_MIN_PIXELS,
) -> tuple[bytes, ImageMediaType]:
    """Return (JPEG bytes, ImageMediaType.JPEG) shaped for vision providers.

    Opens the source image (JPEG/PNG/WEBP), scales the long side to at most
    ``max_side`` preserving aspect ratio with LANCZOS resampling, rounds both
    edges to the provider-required multiple of 16, and — when the resulting
    pixel count is below ``min_pixels`` — upscales (LANCZOS) to the smallest
    aligned size that meets the floor. Raises ``ValueError`` when no aligned
    size can satisfy both the floor and ``max_side`` (extreme aspect ratios).
    Converts to RGB and re-encodes as JPEG at ``quality``. The original asset
    bytes are never mutated.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in _SOURCE_FORMATS:
                raise ValueError(f"unsupported vision source format: {source.format}")
            source.load()
            width, height = source.size
            longest = max(width, height)
            if longest > max_side:
                scale = max_side / longest
                target = (
                    _align_edge(round(width * scale)),
                    _align_edge(round(height * scale)),
                )
            else:
                target = (_align_edge(width), _align_edge(height))
            if target[0] * target[1] < min_pixels:
                upscale = math.sqrt(min_pixels / (target[0] * target[1]))
                target = (
                    _ceil_align_edge(target[0] * upscale),
                    _ceil_align_edge(target[1] * upscale),
                )
                if max(target) > max_side:
                    raise ValueError(
                        "image cannot meet the provider minimum pixel count "
                        "without exceeding the max side"
                    )
            if target != (width, height):
                resized = source.resize(target, Image.Resampling.LANCZOS)
            else:
                resized = source
            rgb = resized.convert("RGB")
    output = io.BytesIO()
    rgb.save(output, format="JPEG", quality=quality, optimize=False)
    return output.getvalue(), ImageMediaType.JPEG
