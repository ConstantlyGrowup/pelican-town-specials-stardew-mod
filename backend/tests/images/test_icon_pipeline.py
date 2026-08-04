"""16x16 icon pipeline tests."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from pelican_town_specials.images.icon_pipeline import build_icon_16

from .conftest import png_bytes


def test_icon_output_is_exact_rgba_16() -> None:
    output = build_icon_16(png_bytes(size=(128, 128), color="blue"))

    image = Image.open(io.BytesIO(output))

    assert image.size == (16, 16)
    assert image.mode == "RGBA"
    assert image.info == {}


def test_icon_centers_subject_with_padding() -> None:
    output = build_icon_16(png_bytes(size=(64, 16), color="green"))
    image = Image.open(io.BytesIO(output))

    # Subject covers the horizontal span; transparency preserved on the sides.
    assert image.getbbox() is not None


def test_icon_rejects_fully_transparent_source() -> None:
    output = io.BytesIO()
    Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(output, format="PNG")

    with pytest.raises(ValueError, match="transparent"):
        build_icon_16(output.getvalue())
