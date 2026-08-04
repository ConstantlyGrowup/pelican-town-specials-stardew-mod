from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from pelican_town_specials.domain.assets import AssetKind, MediaType
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    AssetNotFoundError,
    FileAssetStore,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths


def test_file_asset_store_put_open_and_stat_round_trip_for_images(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    store = FileAssetStore(workspace)
    output = io.BytesIO()
    Image.new("RGB", (64, 32), "red").save(output, format="PNG")
    data = output.getvalue()

    asset_ref = store.put(
        data,
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=64,
            height=32,
            sourceRevision=3,
            attemptId=uuid4(),
        ),
    )

    assert asset_ref.sha256 == hashlib.sha256(data).hexdigest()
    assert asset_ref.byte_size == len(data)
    assert re.fullmatch(r"[a-f0-9]{2}/[0-9a-f]{32}\.png", asset_ref.relative_path)
    assert str(workspace.assets_dir) not in asset_ref.model_dump_json(by_alias=True)
    assert store.stat(asset_ref) == asset_ref
    with store.open(asset_ref) as handle:
        assert handle.read() == data


def test_file_asset_store_reuses_existing_ref_for_duplicate_content(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    store = FileAssetStore(workspace)
    output = io.BytesIO()
    Image.new("RGB", (128, 64), "blue").save(output, format="WEBP")
    data = output.getvalue()
    metadata = AssetMetadata(
        kind=AssetKind.PREVIEW,
        mediaType=MediaType.WEBP,
        fileExtension=".webp",
        width=128,
        height=64,
    )

    first = store.put(data, metadata)
    second = store.put(data, metadata)

    assert second == first


def test_file_asset_store_accepts_zip_assets_without_dimensions(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    store = FileAssetStore(workspace)

    asset_ref = store.put(
        _zip_bytes(),
        AssetMetadata(
            kind=AssetKind.EXPORT_ZIP,
            mediaType=MediaType.ZIP,
            fileExtension=".zip",
        ),
    )

    assert asset_ref.media_type is MediaType.ZIP
    assert asset_ref.width is None
    assert asset_ref.height is None


def test_asset_store_lookup_and_open_by_uuid(tmp_path: Path) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    store = FileAssetStore(workspace)
    output = io.BytesIO()
    Image.new("RGB", (48, 24), "green").save(output, format="PNG")
    data = output.getvalue()

    ref = store.put(
        data,
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=48,
            height=24,
        ),
    )

    assert store.stat(ref.asset_id) == ref
    with store.open(ref.asset_id) as handle:
        assert handle.read() == data

    with pytest.raises(AssetNotFoundError):
        store.stat(uuid4())
    with pytest.raises(AssetNotFoundError):
        store.open(uuid4())


def test_asset_store_uuid_stat_detects_tampering(tmp_path: Path) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    store = FileAssetStore(workspace)
    output = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(output, format="PNG")
    ref = store.put(
        output.getvalue(),
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=1,
            height=1,
        ),
    )
    tampered = bytearray(store._resolve_asset_path(ref.relative_path).read_bytes())
    tampered[-1] ^= 0x01
    store._resolve_asset_path(ref.relative_path).write_bytes(bytes(tampered))

    with pytest.raises(ValueError, match="hash"):
        store.stat(ref.asset_id)
    with pytest.raises(ValueError, match="hash"):
        store.open(ref.asset_id)


def test_asset_metadata_rejects_unsupported_extension_and_missing_dimensions() -> None:
    with pytest.raises(ValueError, match="unsupported file extension"):
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".gif",
            width=64,
            height=32,
        )

    with pytest.raises(ValueError, match="image assets must define width and height"):
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".png",
        )


def test_asset_metadata_rejects_path_traversal_and_absolute_extensions() -> None:
    with pytest.raises(ValueError, match="unsupported file extension"):
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension="../escape.png",
            width=8,
            height=8,
        )

    with pytest.raises(ValueError, match="unsupported file extension"):
        AssetMetadata(
            kind=AssetKind.EXPORT_ZIP,
            mediaType=MediaType.ZIP,
            fileExtension="C:/escape.zip",
        )


def _zip_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", "{}")
    return output.getvalue()


def test_asset_store_rejects_invalid_content_and_stat_detects_tampering(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    store = FileAssetStore(workspace)
    metadata = AssetMetadata(
        kind=AssetKind.PREVIEW,
        mediaType=MediaType.PNG,
        fileExtension=".png",
        width=1,
        height=1,
    )
    with pytest.raises(ValueError, match="valid image"):
        store.put(b"not-png", metadata)
    output = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(output, format="PNG")
    ref = store.put(output.getvalue(), metadata)
    workspace_path = workspace.assets_dir / ref.relative_path
    tampered = bytearray(workspace_path.read_bytes())
    tampered[-1] ^= 0x01
    workspace_path.write_bytes(tampered)
    with pytest.raises(ValueError, match="hash"):
        store.stat(ref)
    with pytest.raises(ValueError, match="hash"):
        store.open(ref)
