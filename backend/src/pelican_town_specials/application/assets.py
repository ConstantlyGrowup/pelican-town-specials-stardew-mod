"""Original-image upload, safe normalization, and registered-asset reads."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import datetime
from typing import BinaryIO
from uuid import UUID

from PIL import Image, ImageOps
from pydantic import Field, field_validator

from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.common import StrictModel, ensure_utc, ensure_uuid4
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    AssetNotFoundError,
    FileAssetStore,
)

MAX_ASSET_BYTES = 20 * 1024 * 1024
MAX_IMAGE_SIDE = 8192
MAX_IMAGE_PIXELS = 40_000_000

_ALLOWED_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/webp"}
)
_FORMAT_BY_CONTENT_TYPE = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/webp": "WEBP",
}
_MEDIA_BY_CONTENT_TYPE = {
    "image/png": MediaType.PNG,
    "image/jpeg": MediaType.JPEG,
    "image/jpg": MediaType.JPEG,
    "image/webp": MediaType.WEBP,
}
_PIL_DECOMPRESSION_ERRORS = (Image.DecompressionBombError, Image.DecompressionBombWarning)


class AssetView(StrictModel):
    asset_id: UUID = Field(alias="assetId")
    kind: AssetKind
    media_type: MediaType = Field(alias="mediaType")
    sha256: str
    byte_size: int = Field(alias="byteSize", gt=0)
    created_at: datetime = Field(alias="createdAt")
    width: int | None = Field(default=None, ge=1, le=8192)
    height: int | None = Field(default=None, ge=1, le=8192)
    source_revision: int | None = Field(default=None, alias="sourceRevision", ge=1)
    attempt_id: UUID | None = Field(default=None, alias="attemptId")

    @field_validator("asset_id", "attempt_id", mode="before")
    @classmethod
    def _validate_optional_uuid4(cls, value: UUID | None) -> UUID | None:
        if value is None:
            return None
        return ensure_uuid4(value)

    @field_validator("created_at", mode="before")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value

    @classmethod
    def from_asset_ref(cls, ref: AssetRef) -> AssetView:
        return cls(
            assetId=ref.asset_id,
            kind=ref.kind,
            mediaType=ref.media_type,
            sha256=ref.sha256,
            byteSize=ref.byte_size,
            createdAt=ref.created_at,
            width=ref.width,
            height=ref.height,
            sourceRevision=ref.source_revision,
            attemptId=ref.attempt_id,
        )


class AssetPayload:
    """A validated registered asset streamed to the API caller without exposing paths."""

    __slots__ = ("asset_id", "media_type", "stream")

    def __init__(
        self,
        *,
        asset_id: UUID,
        media_type: MediaType,
        stream: BinaryIO,
    ) -> None:
        self.asset_id = asset_id
        self.media_type = media_type
        self.stream = stream

    def iter_bytes(self) -> Iterator[bytes]:
        with self.stream:
            yield from iter(lambda: self.stream.read(65536), b"")


class AssetService:
    def __init__(self, store: FileAssetStore) -> None:
        self._store = store

    def upload_image(
        self,
        *,
        content_type: str,
        data: bytes,
    ) -> AssetView:
        declared = self._declared_media_type(content_type)
        normalized_media, normalized_bytes, width, height = self._normalize_upload(
            declared, data
        )
        metadata = AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=normalized_media,
            fileExtension=(
                ".png" if normalized_media is MediaType.PNG else ".jpg"
            ),
            width=width,
            height=height,
        )
        try:
            ref = self._store.put(normalized_bytes, metadata)
        except ValueError as exc:
            raise self._invalid_image_error() from exc
        return AssetView.from_asset_ref(ref)

    def get_image(self, asset_id: UUID) -> AssetPayload:
        try:
            ref = self._store.stat(asset_id)
            stream = self._store.open(ref)
        except AssetNotFoundError as exc:
            raise self._not_found_error() from exc
        except ValueError as exc:
            raise self._unavailable_error() from exc
        return AssetPayload(
            asset_id=ref.asset_id,
            media_type=ref.media_type,
            stream=stream,
        )

    def require_existing(self, asset_id: UUID) -> None:
        try:
            self._store.stat(asset_id)
        except AssetNotFoundError as exc:
            raise self._source_image_missing_error() from exc
        except ValueError as exc:
            raise self._unavailable_error() from exc

    def stat(self, asset_id: UUID) -> AssetRef:
        try:
            return self._store.stat(asset_id)
        except AssetNotFoundError as exc:
            raise self._not_found_error() from exc
        except ValueError as exc:
            raise self._unavailable_error() from exc

    def _declared_media_type(self, content_type: str) -> MediaType:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise self._invalid_image_error()
        return _MEDIA_BY_CONTENT_TYPE[content_type]

    def _normalize_upload(
        self,
        declared: MediaType,
        data: bytes,
    ) -> tuple[MediaType, bytes, int, int]:
        if not data:
            raise self._limit_exceeded_error()
        if len(data) > MAX_ASSET_BYTES:
            raise self._limit_exceeded_error()
        expected_format = _FORMAT_BY_CONTENT_TYPE[declared.value]
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format != expected_format:
                    raise self._invalid_image_error()
                width, height = source.size
                if (
                    width > MAX_IMAGE_SIDE
                    or height > MAX_IMAGE_SIDE
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise self._limit_exceeded_error()
                transposed = ImageOps.exif_transpose(source)
                transposed.load()
            normalized_media, normalized_bytes = self._reencode(declared, transposed)
            return normalized_media, normalized_bytes, transposed.width, transposed.height
        except _PIL_DECOMPRESSION_ERRORS:
            raise self._limit_exceeded_error() from None
        except AppError:
            raise
        except (OSError, ValueError, SyntaxError, TypeError, RuntimeError):
            raise self._invalid_image_error() from None

    def _reencode(
        self,
        declared: MediaType,
        image: Image.Image,
    ) -> tuple[MediaType, bytes]:
        output = io.BytesIO()
        if declared is MediaType.JPEG:
            image.convert("RGB").save(output, format="JPEG", quality=90)
            return MediaType.JPEG, output.getvalue()
        image.convert("RGBA").save(output, format="PNG", compress_level=6)
        return MediaType.PNG, output.getvalue()

    @staticmethod
    def _limit_exceeded_error() -> AppError:
        return AppError(
            code="PTS_INPUT_IMAGE_LIMIT_EXCEEDED",
            message="图片文件超过大小或像素/边长上限。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _invalid_image_error() -> AppError:
        return AppError(
            code="PTS_INPUT_IMAGE_INVALID",
            message="图片格式不受支持或内容损坏。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _source_image_missing_error() -> AppError:
        return AppError(
            code="PTS_INPUT_SOURCE_IMAGE_MISSING",
            message="源图片不存在或已删除。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _not_found_error() -> AppError:
        return AppError(
            code="PTS_ASSET_NOT_FOUND",
            message="图片资源不存在或已删除。",
            http_status=404,
            details={},
            retryable=False,
        )

    @staticmethod
    def _unavailable_error() -> AppError:
        return AppError(
            code="PTS_ASSET_UNAVAILABLE",
            message="图片资源暂时不可用，请稍后重试。",
            http_status=500,
            details={},
            retryable=True,
        )
