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


def test_small_image_is_upscaled_to_min_pixels() -> None:
    # 640x480 (307,200 px) is below the provider floor of 655,360 px and is
    # upscaled to the smallest aligned size that meets it.
    source = _noise_bytes(width=640, height=480, fmt="PNG")

    downscaled, media = downscale_for_vision(source)

    assert media is ImageMediaType.JPEG
    image = _assert_jpeg(downscaled)
    width, height = image.size
    assert width * height >= 655_360
    assert width % 16 == 0
    assert height % 16 == 0
    assert max(image.size) <= VISION_MAX_SIDE
    assert width / height == pytest.approx(640 / 480, rel=0.01)


def test_small_edit_input_upscaled_to_min_pixels() -> None:
    # The observed real-world failure: 752x672 (505,344 px) below the floor.
    source = _noise_bytes(width=752, height=672, fmt="PNG")

    downscaled, _ = downscale_for_vision(source)

    image = _assert_jpeg(downscaled)
    width, height = image.size
    assert width * height >= 655_360
    assert width % 16 == 0
    assert height % 16 == 0
    assert max(image.size) <= VISION_MAX_SIDE


def test_extreme_ratio_cannot_meet_min_pixels_raises() -> None:
    # 16x2048 (32,768 px): any upscale that reaches the floor exceeds the
    # max side, so the input is rejected instead of producing an invalid edit.
    source = _noise_bytes(width=16, height=2048, fmt="PNG")

    with pytest.raises(ValueError):
        downscale_for_vision(source)


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


def test_scaled_edges_are_multiples_of_sixteen() -> None:
    # 4032x2689 scales to 2048x1366 without alignment; both edges must be
    # multiples of 16 for the image-edits provider contract.
    source = _noise_bytes(width=4032, height=2689, fmt="PNG")

    downscaled, _ = downscale_for_vision(source)

    image = _assert_jpeg(downscaled)
    width, height = image.size
    assert width % 16 == 0
    assert height % 16 == 0
    assert max(image.size) <= VISION_MAX_SIDE


def test_unscaled_edges_are_aligned_to_sixteen() -> None:
    # 990x1051 is already within the max side but both edges fail the
    # multiples-of-16 provider requirement; alignment must still apply.
    source = _noise_bytes(width=990, height=1051, fmt="PNG")

    downscaled, _ = downscale_for_vision(source)

    image = _assert_jpeg(downscaled)
    assert image.size == (976, 1040)
    assert image.size[0] % 16 == 0
    assert image.size[1] % 16 == 0
