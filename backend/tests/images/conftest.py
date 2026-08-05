"""Task 12 image test fixtures."""

from __future__ import annotations

import io

from PIL import Image


def png_bytes(*, size: tuple[int, int] = (64, 64), color: str = "red") -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG")
    return output.getvalue()
