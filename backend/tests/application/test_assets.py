"""Task 9 upload-boundary and asset-read use-case tests."""

from __future__ import annotations

import hashlib
import io
import struct
import zlib
from uuid import uuid4

import pytest
from PIL import Image

from pelican_town_specials.application.assets import AssetService
from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.errors import AppError

from .conftest import AppServices


def _service(services: AppServices) -> AssetService:
    return AssetService(services.asset_store)


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (64, 32), "red").save(output, format="PNG")
    return output.getvalue()


def _jpeg_bytes(*, size: tuple[int, int] = (32, 64), orientation: int = 6) -> bytes:
    output = io.BytesIO()
    image = Image.new("RGB", size, "green")
    exif = Image.Exif()
    exif[0x0112] = orientation
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def _oversized_png_bytes() -> bytes:
    """A tiny PNG whose IHDR claims 40000x40000 pixels (a decompression bomb)."""
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
    return bytes(raw)


def test_upload_png_returns_view_without_path(services: AppServices) -> None:
    view = _service(services).upload_image(content_type="image/png", data=_png_bytes())

    assert view.media_type is MediaType.PNG
    assert (view.width, view.height) == (64, 32)
    assert len(view.sha256) == 64
    assert view.byte_size > 0
    assert "relativePath" not in view.model_dump(by_alias=True)


def test_upload_dedups_identical_normalized_content(services: AppServices) -> None:
    service = _service(services)
    data = _png_bytes()

    first = service.upload_image(content_type="image/png", data=data)
    second = service.upload_image(content_type="image/png", data=data)

    assert second.asset_id == first.asset_id
    assert second.sha256 == first.sha256


def test_get_image_round_trips_verified_bytes(services: AppServices) -> None:
    service = _service(services)
    view = service.upload_image(content_type="image/png", data=_png_bytes())

    payload = service.get_image(view.asset_id)
    data = b"".join(payload.iter_bytes())

    assert payload.media_type is MediaType.PNG
    assert hashlib.sha256(data).hexdigest() == view.sha256


def test_get_image_unknown_raises_not_found(services: AppServices) -> None:
    with pytest.raises(AppError) as excinfo:
        _service(services).get_image(uuid4())
    assert excinfo.value.code == "PTS_ASSET_NOT_FOUND"
    assert excinfo.value.http_status == 404


def test_upload_rejects_decompression_bomb(services: AppServices) -> None:
    with pytest.raises(AppError) as excinfo:
        _service(services).upload_image(
            content_type="image/png",
            data=_oversized_png_bytes(),
        )
    assert excinfo.value.code == "PTS_INPUT_IMAGE_LIMIT_EXCEEDED"
    assert excinfo.value.http_status == 422


def test_upload_rejects_oversized_file(services: AppServices) -> None:
    with pytest.raises(AppError) as excinfo:
        _service(services).upload_image(
            content_type="image/png",
            data=b"\x00" * (20 * 1024 * 1024 + 1),
        )
    assert excinfo.value.code == "PTS_INPUT_IMAGE_LIMIT_EXCEEDED"


def test_upload_rejects_unsupported_content_type(services: AppServices) -> None:
    with pytest.raises(AppError) as excinfo:
        _service(services).upload_image(content_type="text/plain", data=b"x")
    assert excinfo.value.code == "PTS_INPUT_IMAGE_INVALID"


def test_upload_rejects_content_type_mismatch(services: AppServices) -> None:
    with pytest.raises(AppError) as excinfo:
        _service(services).upload_image(
            content_type="image/jpeg",
            data=_png_bytes(),
        )
    assert excinfo.value.code == "PTS_INPUT_IMAGE_INVALID"


def test_upload_webp_is_stored_as_png(services: AppServices) -> None:
    output = io.BytesIO()
    Image.new("RGB", (80, 40), "orange").save(output, format="WEBP")

    view = _service(services).upload_image(
        content_type="image/webp",
        data=output.getvalue(),
    )

    assert view.media_type is MediaType.PNG
    assert (view.width, view.height) == (80, 40)


def test_upload_applies_exif_orientation(services: AppServices) -> None:
    view = _service(services).upload_image(
        content_type="image/jpeg",
        data=_jpeg_bytes(size=(32, 64), orientation=6),
    )

    assert view.media_type is MediaType.JPEG
    assert (view.width, view.height) == (64, 32)


def test_upload_clears_exif_and_metadata(services: AppServices) -> None:
    service = _service(services)
    view = service.upload_image(
        content_type="image/jpeg",
        data=_jpeg_bytes(size=(32, 64), orientation=6),
    )
    payload = service.get_image(view.asset_id)
    stored = b"".join(payload.iter_bytes())

    with Image.open(io.BytesIO(stored)) as image:
        assert not image.getexif()
