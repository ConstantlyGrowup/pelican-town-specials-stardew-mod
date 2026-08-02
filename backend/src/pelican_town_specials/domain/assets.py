import re
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .common import Language, StrictModel, ensure_utc, ensure_uuid4

_RELATIVE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]*$")
_IMAGE_MEDIA_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
}


class AssetKind(str, Enum):
    ORIGINAL_IMAGE = "ORIGINAL_IMAGE"
    GENERATED_ART = "GENERATED_ART"
    PREVIEW = "PREVIEW"
    ICON_SOURCE = "ICON_SOURCE"
    ICON_16 = "ICON_16"
    MOD_SPRITESHEET = "MOD_SPRITESHEET"
    EXPORT_ZIP = "EXPORT_ZIP"


class MediaType(str, Enum):
    PNG = "image/png"
    JPEG = "image/jpeg"
    WEBP = "image/webp"
    ZIP = "application/zip"


class AssetRef(StrictModel):
    asset_id: UUID = Field(alias="assetId")
    kind: AssetKind
    media_type: MediaType = Field(alias="mediaType")
    relative_path: str = Field(alias="relativePath")
    sha256: str
    byte_size: int = Field(alias="byteSize", gt=0)
    created_at: datetime = Field(alias="createdAt")
    width: int | None = Field(default=None, ge=1, le=8192)
    height: int | None = Field(default=None, ge=1, le=8192)
    source_revision: int | None = Field(default=None, alias="sourceRevision", ge=1)
    attempt_id: UUID | None = Field(default=None, alias="attemptId")

    @field_validator("asset_id", mode="before")
    @classmethod
    def _validate_asset_id(cls, value: UUID) -> UUID:
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

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        if value.strip() != value or not value:
            raise ValueError("relative_path must be a safe relative path")
        if value.startswith(("/", "\\")) or ":" in value or "\\" in value:
            raise ValueError("relative_path must be a safe relative path")
        if ".." in value.split("/") or not _RELATIVE_PATH_PATTERN.match(value):
            raise ValueError("relative_path must be a safe relative path")
        return value

    @field_validator("attempt_id", mode="before")
    @classmethod
    def _validate_attempt_id(cls, value: UUID | None) -> UUID | None:
        if value is None:
            return None
        return ensure_uuid4(value)

    @model_validator(mode="after")
    def _validate_dimensions(self) -> "AssetRef":
        is_image = self.media_type.value in _IMAGE_MEDIA_TYPES
        if self.kind is AssetKind.EXPORT_ZIP:
            if self.media_type is not MediaType.ZIP:
                raise ValueError("EXPORT_ZIP assets must use application/zip")
            if self.width is not None or self.height is not None:
                raise ValueError("ZIP assets must not define image dimensions")
            return self
        if self.media_type is MediaType.ZIP:
            raise ValueError("image assets must use an image media type")
        if not is_image:
            raise ValueError("unsupported media type")
        if self.width is None or self.height is None:
            raise ValueError("image assets must define width and height")
        return self


class SourceInput(StrictModel):
    original_image_asset_id: UUID = Field(alias="originalImageAssetId")
    context_text: str | None = Field(default=None, alias="contextText")
    language: Language

    @field_validator("original_image_asset_id", mode="before")
    @classmethod
    def _validate_original_image_asset_id(cls, value: UUID) -> UUID:
        return ensure_uuid4(value)

    @field_validator("context_text", mode="before")
    @classmethod
    def _strip_context_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) > 500:
            raise ValueError("context_text must be 500 characters or fewer")
        return stripped
