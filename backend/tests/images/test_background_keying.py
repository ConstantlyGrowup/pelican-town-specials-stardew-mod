"""R12: deterministic solid-background keying for generated icon art."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from pelican_town_specials.images.background_keying import key_icon_background


def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _keyed_pixels(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGBA").copy()


def test_opaque_black_background_is_removed() -> None:
    image = Image.new("RGB", (64, 64), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, 44, 44), fill=(200, 40, 40))

    result = key_icon_background(_png(image))

    assert result.changed is True
    keyed = _keyed_pixels(result.data)
    assert keyed.getpixel((0, 0))[3] == 0
    assert keyed.getpixel((63, 63))[3] == 0
    assert keyed.getpixel((32, 32))[3] == 255


def test_dark_outline_inside_magenta_background_survives() -> None:
    image = Image.new("RGB", (64, 64), (255, 0, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 47, 47), fill=(10, 10, 10))
    draw.rectangle((20, 20, 43, 43), fill=(40, 180, 60))

    result = key_icon_background(_png(image))

    assert result.changed is True
    keyed = _keyed_pixels(result.data)
    assert keyed.getpixel((0, 0))[3] == 0
    assert keyed.getpixel((16, 16))[3] == 255
    assert keyed.getpixel((32, 32))[3] == 255


def test_uniform_image_is_kept_to_avoid_erasing_subject() -> None:
    image = Image.new("RGB", (64, 64), (255, 99, 71))
    source = _png(image)

    result = key_icon_background(source)

    assert result.changed is False
    assert result.data == source


def test_already_transparent_image_is_kept() -> None:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, 44, 44), fill=(200, 40, 40, 255))
    source = _png(image)

    result = key_icon_background(source)

    assert result.changed is False
    assert result.data == source


def test_non_uniform_border_is_kept() -> None:
    image = Image.new("RGB", (64, 64))
    pixels = image.load()
    for y in range(64):
        for x in range(64):
            pixels[x, y] = ((x * 7 + y * 13) % 256, (x * 3 + y * 5) % 256, (x + y) % 256)

    result = key_icon_background(_png(image))

    assert result.changed is False
