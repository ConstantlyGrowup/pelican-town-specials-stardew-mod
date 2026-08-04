"""Upload normalization boundary tests."""

from __future__ import annotations

import io
import struct
import zlib

import pytest
from PIL import Image

from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.images.input_normalizer import normalize_upload

from .conftest import png_bytes


def test_normalize_png_is_rgba() -> None:
    result = normalize_upload(png_bytes(size=(64, 32)))

    assert result.media_type is MediaType.PNG
    assert result.mode == "RGBA"
    assert (result.width, result.height) == (64, 32)


def test_normalize_jpeg_is_rgb() -> None:
    output = io.BytesIO()
    Image.new("RGB", (32, 16), "blue").save(output, format="JPEG")

    result = normalize_upload(output.getvalue())

    assert result.media_type is MediaType.JPEG
    assert result.mode == "RGB"


def test_normalize_webp_is_stored_as_png() -> None:
    output = io.BytesIO()
    Image.new("RGB", (10, 10), "green").save(output, format="WEBP")

    result = normalize_upload(output.getvalue())

    assert result.media_type is MediaType.PNG
    assert result.mode == "RGBA"


def test_normalize_applies_exif_orientation_and_clears_metadata() -> None:
    output = io.BytesIO()
    image = Image.new("RGB", (32, 64), "red")
    exif = Image.Exif()
    exif[0x0112] = 6
    image.save(output, format="JPEG", exif=exif)

    result = normalize_upload(output.getvalue())

    assert (result.width, result.height) == (64, 32)
    with Image.open(io.BytesIO(result.data)) as reopened:
        assert not reopened.getexif()


def test_normalize_rejects_oversized_file() -> None:
    with pytest.raises(AppError) as excinfo:
        normalize_upload(b"\x00" * (20 * 1024 * 1024 + 1))
    assert excinfo.value.code == "PTS_INPUT_IMAGE_LIMIT_EXCEEDED"


def test_normalize_rejects_decompression_bomb() -> None:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    raw = bytearray(output.getvalue())
    data_start = 16
    chunk_data = bytearray(raw[data_start : data_start + 13])
    chunk_data[0:4] = (40000).to_bytes(4, "big")
    chunk_data[4:8] = (40000).to_bytes(4, "big")
    raw[data_start : data_start + 13] = chunk_data
    crc = zlib.crc32(b"IHDR" + bytes(chunk_data)) & 0xFFFFFFFF
    raw[data_start + 13 : data_start + 17] = struct.pack(">I", crc)

    with pytest.raises(AppError) as excinfo:
        normalize_upload(bytes(raw))
    assert excinfo.value.code == "PTS_INPUT_IMAGE_LIMIT_EXCEEDED"


def test_normalize_rejects_corrupt_content() -> None:
    with pytest.raises(AppError) as excinfo:
        normalize_upload(b"not-an-image")
    assert excinfo.value.code == "PTS_INPUT_IMAGE_INVALID"


def test_normalize_clears_png_text_metadata() -> None:
    from PIL.PngImagePlugin import PngInfo

    output = io.BytesIO()
    image = Image.new("RGBA", (8, 8), "red")
    metadata = PngInfo()
    metadata.add_text("Comment", "secret-text")
    image.save(output, format="PNG", pnginfo=metadata)

    result = normalize_upload(output.getvalue())

    with Image.open(io.BytesIO(result.data)) as reopened:
        assert "Text" not in reopened.info
        assert reopened.info == {}


def test_normalize_clears_jpeg_comment() -> None:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, format="JPEG", comment=b"secret")

    result = normalize_upload(output.getvalue())

    with Image.open(io.BytesIO(result.data)) as reopened:
        assert not reopened.info.get("comment")


def test_normalize_maps_decompression_warning_to_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)

    with pytest.raises(AppError) as excinfo:
        normalize_upload(png_bytes(size=(15, 10)))
    assert excinfo.value.code == "PTS_INPUT_IMAGE_LIMIT_EXCEEDED"
