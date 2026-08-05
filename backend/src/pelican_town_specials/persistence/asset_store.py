from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from PIL import Image
from pydantic import Field, field_validator, model_validator

from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.common import (
    StrictModel,
    ensure_uuid4,
    utc_now,
)

from .atomic import atomic_write_bytes, atomic_write_json, read_json_with_backup
from .workspace import WorkspacePaths

_EXTENSIONS_BY_MEDIA_TYPE: dict[MediaType, set[str]] = {
    MediaType.PNG: {".png"},
    MediaType.JPEG: {".jpg", ".jpeg"},
    MediaType.WEBP: {".webp"},
    MediaType.ZIP: {".zip"},
}
_UUID_FIELD_NAMES = {"assetId", "attemptId"}
_DATETIME_FIELD_NAMES = {"createdAt"}
_MAX_ASSET_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_PIXELS = 40_000_000
_ENUM_PARSERS = {
    "kind": AssetKind,
    "mediaType": MediaType,
}


class AssetNotFoundError(Exception):
    """Raised when no registered asset matches an opaque assetId."""


class AssetMetadata(StrictModel):
    kind: AssetKind
    media_type: MediaType = Field(alias="mediaType")
    file_extension: str = Field(alias="fileExtension", min_length=4)
    width: int | None = Field(default=None, ge=1, le=8192)
    height: int | None = Field(default=None, ge=1, le=8192)
    source_revision: int | None = Field(default=None, alias="sourceRevision", ge=1)
    attempt_id: UUID | None = Field(default=None, alias="attemptId")

    @field_validator("file_extension")
    @classmethod
    def _validate_file_extension(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            not normalized.startswith(".")
            or "/" in normalized
            or "\\" in normalized
            or ":" in normalized
            or ".." in normalized
        ):
            raise ValueError("unsupported file extension")
        return normalized

    @field_validator("attempt_id", mode="before")
    @classmethod
    def _validate_attempt_id(cls, value: UUID | None) -> UUID | None:
        if value is None:
            return None
        return ensure_uuid4(value)

    @model_validator(mode="after")
    def _validate_media_constraints(self) -> AssetMetadata:
        allowed_extensions = _EXTENSIONS_BY_MEDIA_TYPE[self.media_type]
        if self.file_extension not in allowed_extensions:
            raise ValueError("unsupported file extension")
        if self.media_type is MediaType.ZIP:
            if self.kind is not AssetKind.EXPORT_ZIP:
                raise ValueError("ZIP assets must use EXPORT_ZIP kind")
            if self.width is not None or self.height is not None:
                raise ValueError("ZIP assets must not define image dimensions")
            return self
        if self.width is None or self.height is None:
            raise ValueError("image assets must define width and height")
        if self.kind is AssetKind.EXPORT_ZIP:
            raise ValueError("image assets must not use EXPORT_ZIP kind")
        return self


def _normalize_asset_payload(payload: object) -> object:
    if isinstance(payload, list):
        return [_normalize_asset_payload(item) for item in payload]
    if not isinstance(payload, dict):
        return payload

    normalized: dict[object, object] = {}
    for key, value in payload.items():
        if key in _UUID_FIELD_NAMES and isinstance(value, str):
            normalized[key] = UUID(value)
            continue
        if key in _DATETIME_FIELD_NAMES and isinstance(value, str):
            normalized[key] = datetime.fromisoformat(value)
            continue
        enum_parser = _ENUM_PARSERS.get(key)
        if enum_parser is not None and isinstance(value, str):
            normalized[key] = enum_parser(value)
            continue
        normalized[key] = _normalize_asset_payload(value)
    return normalized


def _validate_asset_ref(payload: object) -> AssetRef:
    return AssetRef.model_validate(_normalize_asset_payload(payload))


class FileAssetStore:
    def __init__(self, workspace: WorkspacePaths) -> None:
        self._assets_dir = workspace.assets_dir

    def put(self, data: bytes, metadata: AssetMetadata) -> AssetRef:
        if not data or len(data) > _MAX_ASSET_BYTES:
            raise ValueError("asset must be non-empty and at most 20 MiB")
        if metadata.media_type is MediaType.ZIP:
            if not zipfile.is_zipfile(io.BytesIO(data)):
                raise ValueError("asset content is not a valid ZIP")
        else:
            try:
                with Image.open(io.BytesIO(data)) as image:
                    actual_size = image.size
                    image.verify()
            except Exception as exc:
                raise ValueError("asset content is not a valid image") from exc
            if actual_size[0] * actual_size[1] > _MAX_IMAGE_PIXELS:
                raise ValueError("image exceeds 40 megapixels")
            if actual_size != (metadata.width, metadata.height):
                raise ValueError("image dimensions do not match metadata")
        sha256 = hashlib.sha256(data).hexdigest()
        existing = self._find_existing_ref(
            sha256=sha256, metadata=metadata, byte_size=len(data)
        )
        if existing is not None:
            return existing

        relative_path = f"{sha256[:2]}/{uuid4().hex}{metadata.file_extension}"
        asset_ref = AssetRef(
            assetId=uuid4(),
            kind=metadata.kind,
            mediaType=metadata.media_type,
            relativePath=relative_path,
            sha256=sha256,
            byteSize=len(data),
            createdAt=utc_now(),
            width=metadata.width,
            height=metadata.height,
            sourceRevision=metadata.source_revision,
            attemptId=metadata.attempt_id,
        )
        absolute_path = self._resolve_asset_path(asset_ref.relative_path)
        atomic_write_bytes(absolute_path, data)
        atomic_write_json(
            self._sidecar_path(asset_ref.relative_path),
            asset_ref.model_dump(by_alias=True, mode="json"),
        )
        return asset_ref

    def open(self, asset_ref_or_id: AssetRef | UUID) -> BinaryIO:
        validated = self.stat(asset_ref_or_id)
        return self._resolve_asset_path(validated.relative_path).open("rb")

    def stat(self, asset_ref_or_id: AssetRef | UUID) -> AssetRef:
        if isinstance(asset_ref_or_id, UUID):
            asset_ref = self._find_ref_by_asset_id(asset_ref_or_id)
        else:
            asset_ref = asset_ref_or_id
        sidecar_path = self._sidecar_path(asset_ref.relative_path)
        stored = read_json_with_backup(sidecar_path, _validate_asset_ref)
        if stored != asset_ref:
            raise ValueError("asset sidecar does not match asset reference")
        path = self._resolve_asset_path(stored.relative_path)
        try:
            size = path.stat().st_size
        except FileNotFoundError as exc:
            raise ValueError("asset file is missing") from exc
        if size != stored.byte_size:
            raise ValueError("asset byte size does not match sidecar")
        if hashlib.sha256(path.read_bytes()).hexdigest() != stored.sha256:
            raise ValueError("asset hash does not match sidecar")
        return stored

    def delete(self, asset_id: UUID) -> None:
        """Delete the data file and sidecar for a registered asset.

        Raises AssetNotFoundError when no registered asset matches the id.
        """
        asset_ref = self._find_ref_by_asset_id(asset_id)
        self._resolve_asset_path(asset_ref.relative_path).unlink(missing_ok=True)
        self._sidecar_path(asset_ref.relative_path).unlink(missing_ok=True)

    def _find_ref_by_asset_id(self, asset_id: UUID) -> AssetRef:
        for sidecar_path in self._assets_dir.rglob("*.asset.json"):
            candidate = read_json_with_backup(sidecar_path, _validate_asset_ref)
            if candidate.asset_id == asset_id:
                return candidate
        raise AssetNotFoundError(f"asset not found: {asset_id}")

    def _find_existing_ref(
        self,
        *,
        sha256: str,
        metadata: AssetMetadata,
        byte_size: int,
    ) -> AssetRef | None:
        for sidecar_path in self._assets_dir.rglob("*.asset.json"):
            asset_ref = read_json_with_backup(sidecar_path, _validate_asset_ref)
            if (
                asset_ref.sha256 == sha256
                and asset_ref.kind is metadata.kind
                and asset_ref.media_type is metadata.media_type
                and asset_ref.byte_size == byte_size
                and asset_ref.width == metadata.width
                and asset_ref.height == metadata.height
                and asset_ref.source_revision == metadata.source_revision
                and asset_ref.attempt_id == metadata.attempt_id
                and self._resolve_asset_path(asset_ref.relative_path).exists()
            ):
                return asset_ref
        return None

    def _resolve_asset_path(self, relative_path: str) -> Path:
        parts = relative_path.split("/")
        candidate = (self._assets_dir / Path(*parts)).resolve()
        assets_root = self._assets_dir.resolve()
        if candidate != assets_root and assets_root not in candidate.parents:
            raise ValueError("asset path escapes asset store")
        return candidate

    def _sidecar_path(self, relative_path: str) -> Path:
        asset_path = self._resolve_asset_path(relative_path)
        return asset_path.with_name(f"{asset_path.name}.asset.json")
