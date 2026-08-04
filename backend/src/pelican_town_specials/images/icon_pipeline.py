"""Deterministic 16x16 RGBA game icon pipeline."""

from __future__ import annotations

import io

from PIL import Image

from .input_normalizer import normalize_upload
from .preview_compositor import PNGBytes


def build_icon_16(source: bytes) -> PNGBytes:
    """Return a 16x16 RGBA PNG with the subject centered and transparent padding."""
    normalized = normalize_upload(source)
    try:
        with Image.open(io.BytesIO(normalized.data)) as image:
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            bbox = alpha.getbbox()
            if bbox is None:
                raise ValueError("source image is fully transparent")
            subject = rgba.crop(bbox)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("invalid icon source image") from exc

    subject.thumbnail((14, 14), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    offset_x = (16 - subject.width) // 2
    offset_y = (16 - subject.height) // 2
    canvas.paste(subject, (offset_x, offset_y), subject)

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()
