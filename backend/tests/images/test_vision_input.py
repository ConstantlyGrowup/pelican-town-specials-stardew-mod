"""Vision input downscaling tests."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from pelican_town_specials.images import downscale_for_vision
from pelican_town_specials.images.vision_input import VISION_MAX_SIDE
from pelican_town_specials.providers.contracts import ImageMediaType


def _noise_bytes(*, width: int, height: int, fmt: str) -> bytes:
    """Build a deterministic, high-entropy source image in the given format."""
    noise = Image.effect_noise((width, height), sigma=80).convert("RGB")
    output = io.BytesIO()
    if fmt == "JPEG":
        noise.save(output, format="JPEG", quality=92)
    elif fmt == "WEBP":
        noise.save(output, format="WEBP", quality=90)
    else:
        noise.save(output, format="PNG")
    return output.getvalue()


def _assert_jpeg(data: bytes) -> Image.Image:
    assert data.startswith(b"\xff\xd8\xff")
    image = Image.open(io.BytesIO(data))
    assert image.format == "JPEG"
    assert image.mode == "RGB"
    return image


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_downscales_large_source_to_max_side(fmt: str) -> None:
    source = _noise_bytes(width=4032, height=2689, fmt=fmt)

    downscaled, media = downscale_for_vision(source)

    assert media is ImageMediaType.JPEG
    image = _assert_jpeg(downscaled)
    assert max(image.size) <= VISION_MAX_SIDE
    # Aspect ratio is preserved (4032:2689).
    assert image.size[0] / image.size[1] == pytest.approx(4032 / 2689, rel=0.01)
    # The vision request body is substantially smaller than the original payload.
    assert len(downscaled) * 2 < len(source)


def test_small_image_is_not_upscaled_but_reencoded_jpeg() -> None:
    source = _noise_bytes(width=640, height=480, fmt="PNG")

    downscaled, media = downscale_for_vision(source)

    assert media is ImageMediaType.JPEG
    image = _assert_jpeg(downscaled)
    assert image.size == (640, 480)


def test_custom_max_side_is_honored() -> None:
    source = _noise_bytes(width=3000, height=2000, fmt="PNG")

    downscaled, _ = downscale_for_vision(source, max_side=1024)

    image = _assert_jpeg(downscaled)
    assert max(image.size) <= 1024


def test_does_not_mutate_source_bytes() -> None:
    source = _noise_bytes(width=3000, height=2000, fmt="PNG")
    original = source

    downscaled, media = downscale_for_vision(source)

    assert source == original
    assert media is ImageMediaType.JPEG
    assert downscaled != source


def test_non_image_bytes_raise() -> None:
    with pytest.raises((OSError, ValueError)):
        downscale_for_vision(b"not an image at all")
