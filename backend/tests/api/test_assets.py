"""Task 9 asset upload and read API contract tests."""

from __future__ import annotations

import io
import struct
import zlib
from uuid import uuid4

from PIL import Image

from .conftest import ApiClient, ApiServices


def _png_bytes(*, size: int = 8) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (size, size), "red").save(output, format="PNG")
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


def _upload(auth_client: ApiClient) -> dict[str, object]:
    response = auth_client.client.post(
        "/api/v1/assets/images",
        headers=auth_client.mutation_headers,
        files={"file": ("photo.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_image_returns_asset_view_without_path(auth_client: ApiClient) -> None:
    body = _upload(auth_client)

    assert body["assetId"]
    assert body["mediaType"] == "image/png"
    assert body["sha256"]
    assert body["byteSize"] > 0
    assert body["width"] == 8
    assert body["height"] == 8
    assert "relativePath" not in body


def test_get_image_streams_registered_asset(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)

    response = auth_client.client.get(
        f"/api/v1/assets/{uploaded['assetId']}",
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content


def test_get_unknown_asset_returns_404(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        f"/api/v1/assets/{uuid4()}",
        headers=auth_client.session_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PTS_ASSET_NOT_FOUND"


def test_upload_rejects_decompression_bomb(auth_client: ApiClient) -> None:
    response = auth_client.client.post(
        "/api/v1/assets/images",
        headers=auth_client.mutation_headers,
        files={"file": ("huge.png", _oversized_png_bytes(), "image/png")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PTS_INPUT_IMAGE_LIMIT_EXCEEDED"


def test_upload_rejects_unsupported_content_type(auth_client: ApiClient) -> None:
    response = auth_client.client.post(
        "/api/v1/assets/images",
        headers=auth_client.mutation_headers,
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PTS_INPUT_IMAGE_INVALID"


def test_get_drafts_requires_session(services: ApiServices) -> None:
    response = services.client.get(
        "/api/v1/drafts",
        headers={"Host": "testserver"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "PTS_AUTH_SESSION_REQUIRED"


def test_upload_requires_origin(services: ApiServices) -> None:
    response = services.client.post(
        "/api/v1/assets/images",
        headers={"Host": "testserver"},
        files={"file": ("photo.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PTS_AUTH_ORIGIN_INVALID"
