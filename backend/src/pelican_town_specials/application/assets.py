"""Original-image upload, safe normalization, and registered-asset reads."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import BinaryIO
from uuid import UUID

from pydantic import Field, field_validator

from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.common import StrictModel, ensure_utc, ensure_uuid4
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.images.input_normalizer import normalize_upload
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    AssetNotFoundError,
    FileAssetStore,
)

_ALLOWED_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/webp"}
)
_MEDIA_BY_CONTENT_TYPE = {
    "image/png": MediaType.PNG,
    "image/jpeg": MediaType.JPEG,
    "image/jpg": MediaType.JPEG,
    "image/webp": MediaType.WEBP,
}
_MEDIA_BY_SOURCE_FORMAT = {
    "PNG": MediaType.PNG,
    "JPEG": MediaType.JPEG,
    "WEBP": MediaType.WEBP,
}


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
        normalized = normalize_upload(data)
        if declared is not _MEDIA_BY_SOURCE_FORMAT[normalized.source_format]:
            raise self._invalid_image_error()
        metadata = AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=normalized.media_type,
            fileExtension=(
                ".png" if normalized.media_type is MediaType.PNG else ".jpg"
            ),
            width=normalized.width,
            height=normalized.height,
        )
        try:
            ref = self._store.put(normalized.data, metadata)
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
