"""Vision input downscaling: long-side cap and JPEG RGB re-encode.

The stored original image asset is preserved exactly; this helper only shapes
the bytes handed to a vision model, which does not need full-resolution input.
"""

from __future__ import annotations

import io
import warnings

from PIL import Image

from pelican_town_specials.providers.contracts import ImageMediaType

VISION_MAX_SIDE = 2048
VISION_JPEG_QUALITY = 85

_SOURCE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})


def downscale_for_vision(
    data: bytes,
    *,
    max_side: int = VISION_MAX_SIDE,
    quality: int = VISION_JPEG_QUALITY,
) -> tuple[bytes, ImageMediaType]:
    """Return (JPEG bytes, ImageMediaType.JPEG) with the long side <= max_side.

    Opens the source image (JPEG/PNG/WEBP), scales the long side to at most
    ``max_side`` preserving aspect ratio with LANCZOS resampling, converts to
    RGB, and re-encodes as JPEG at ``quality``. The original asset bytes are
    never mutated.
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
                new_width = max(1, round(width * scale))
                new_height = max(1, round(height * scale))
                resized = source.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )
            else:
                resized = source
            rgb = resized.convert("RGB")
    output = io.BytesIO()
    rgb.save(output, format="JPEG", quality=quality, optimize=False)
    return output.getvalue(), ImageMediaType.JPEG
