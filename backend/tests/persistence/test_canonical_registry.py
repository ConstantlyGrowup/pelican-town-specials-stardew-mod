from __future__ import annotations

import hashlib
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.canonical import (
    CanonicalIconInput,
    CanonicalIconKind,
)
from pelican_town_specials.domain.common import Language
from pelican_town_specials.persistence.canonical_registry import (
    CanonicalIconUnavailableError,
    CanonicalRegistryUnavailableError,
    SQLiteCanonicalRegistry,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths
from tests.domain.factories import canonical_registration_fixture


def _image_bytes(
    *,
    size: tuple[int, int],
    image_format: str = "PNG",
    color: tuple[int, int, int, int] = (40, 120, 80, 255),
) -> bytes:
    image = Image.new("RGBA", size, color)
    if image_format == "JPEG":
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def _icon_input(
    data: bytes,
    *,
    media_type: MediaType,
    width: int,
    height: int,
) -> CanonicalIconInput:
    return CanonicalIconInput(
        data=data,
        mediaType=media_type,
        sha256=hashlib.sha256(data).hexdigest(),
        byteSize=len(data),
        width=width,
        height=height,
    )


def _put_icon_pair(
    *,
    source_format: str = "PNG",
) -> tuple[CanonicalIconInput, CanonicalIconInput, bytes, bytes]:
    source_bytes = _image_bytes(size=(32, 24), image_format=source_format)
    icon_16_bytes = _image_bytes(size=(16, 16))
    source_media = {
        "PNG": MediaType.PNG,
        "JPEG": MediaType.JPEG,
        "WEBP": MediaType.WEBP,
    }[source_format]
    source_input = _icon_input(
        source_bytes,
        media_type=source_media,
        width=32,
        height=24,
    )
    icon_16_input = _icon_input(
        icon_16_bytes,
        media_type=MediaType.PNG,
        width=16,
        height=16,
    )
    return source_input, icon_16_input, source_bytes, icon_16_bytes


def _registry_with_icons(
    tmp_path: Path,
    *,
    source_format: str = "PNG",
) -> tuple[
    WorkspacePaths,
    SQLiteCanonicalRegistry,
    CanonicalIconInput,
    CanonicalIconInput,
    bytes,
    bytes,
]:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    source_ref, icon_16_ref, source_bytes, icon_16_bytes = _put_icon_pair(
        source_format=source_format
    )
    registry = SQLiteCanonicalRegistry(workspace)
    return (
        workspace,
        registry,
        source_ref,
        icon_16_ref,
        source_bytes,
        icon_16_bytes,
    )


def test_first_open_creates_schema_v1_and_reopen_persists_registration(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    assert not workspace.canonical_registry_path.exists()
    source_ref, icon_16_ref, _, _ = _put_icon_pair()

    registry = SQLiteCanonicalRegistry(workspace)
    registration = canonical_registration_fixture()
    stored = registry.register(
        registration,
        icon_source=source_ref,
        icon_16=icon_16_ref,
    )

    assert workspace.canonical_registry_path.is_file()
    with sqlite3.connect(workspace.canonical_registry_path) as connection:
        schema_rows = connection.execute(
            "SELECT schema_version, updated_at FROM schema_meta"
        ).fetchall()
        assert len(schema_rows) == 1
        assert schema_rows[0][0] == 1
        assert datetime.fromisoformat(schema_rows[0][1]).tzinfo is not None
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        } == {"schema_meta", "canonical_dishes", "canonical_usage_events"}
        assert {
            row[1] for row in connection.execute("PRAGMA table_info(schema_meta)")
        } == {"schema_version", "updated_at"}
        assert {
            row[1]
            for row in connection.execute("PRAGMA table_info(canonical_dishes)")
        } == {
            "canonical_id",
            "source_archive_id",
            "signature",
            "language",
            "reuse_contract_version",
            "recognized_dish",
            "normalized_dish_name",
            "summary",
            "cuisine",
            "cooking_methods_json",
            "flavor_profile_json",
            "semantic_ingredients_json",
            "presentation_json",
            "gameplay_json",
            "visual_brief",
            "catalog_version",
            "icon_source_relative_path",
            "icon_source_media_type",
            "icon_source_sha256",
            "icon_source_byte_size",
            "icon_source_width",
            "icon_source_height",
            "icon_16_relative_path",
            "icon_16_media_type",
            "icon_16_sha256",
            "icon_16_byte_size",
            "icon_16_width",
            "icon_16_height",
            "created_at",
            "last_used_at",
            "use_count",
        }

    reopened = SQLiteCanonicalRegistry(workspace)
    assert reopened.get_by_source_archive_id(registration.source_archive_id) == stored
    assert reopened.get_valid(registration.canonical_id) == stored
    assert reopened.count_valid() == 1


@pytest.mark.parametrize("source_format", ["PNG", "JPEG", "WEBP"])
def test_registration_owns_validated_icons_and_survives_source_deletion(
    tmp_path: Path,
    source_format: str,
) -> None:
    (
        workspace,
        registry,
        source_ref,
        icon_16_ref,
        source_bytes,
        icon_16_bytes,
    ) = _registry_with_icons(tmp_path, source_format=source_format)
    registration = canonical_registration_fixture()

    stored = registry.register(
        registration,
        icon_source=source_ref,
        icon_16=icon_16_ref,
    )

    expected_extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[
        source_format
    ]
    assert stored.icon_source.relative_path == (
        f"{registration.canonical_id}/icon-source.{expected_extension}"
    )
    assert stored.icon_16.relative_path == f"{registration.canonical_id}/icon-16.png"
    assert stored.icon_source.sha256 == hashlib.sha256(source_bytes).hexdigest()
    assert stored.icon_16.sha256 == hashlib.sha256(icon_16_bytes).hexdigest()

    original_source = workspace.assets_dir / "original-source"
    original_icon_16 = workspace.assets_dir / "original-icon-16"
    original_source.write_bytes(source_bytes)
    original_icon_16.write_bytes(icon_16_bytes)
    original_source.unlink()
    original_icon_16.unlink()

    assert registry.load_owned_icon(
        registration.canonical_id, CanonicalIconKind.SOURCE
    ) == source_bytes
    assert registry.load_owned_icon(
        registration.canonical_id, CanonicalIconKind.ICON_16
    ) == icon_16_bytes


def test_source_archive_registration_is_immutable_idempotent_and_signature_not_unique(
    tmp_path: Path,
) -> None:
    _, registry, source_ref, icon_16_ref, _, _ = _registry_with_icons(tmp_path)
    first_registration = canonical_registration_fixture(
        dish_signature="b" * 64
    )
    first = registry.register(
        first_registration,
        icon_source=source_ref,
        icon_16=icon_16_ref,
    )

    replay = canonical_registration_fixture(
        source_archive_id=first_registration.source_archive_id,
        dish_signature="c" * 64,
    )
    assert registry.register(
        replay,
        icon_source=source_ref,
        icon_16=icon_16_ref,
    ) == first

    second_registration = canonical_registration_fixture(
        dish_signature="b" * 64
    )
    second = registry.register(
        second_registration,
        icon_source=source_ref,
        icon_16=icon_16_ref,
    )

    assert second.canonical_id != first.canonical_id
    assert second.dish_signature == first.dish_signature
    assert registry.count_valid() == 2


def test_registration_rejects_mismatched_declared_metadata_and_bad_icon16(
    tmp_path: Path,
) -> None:
    workspace, registry, source_ref, icon_16_ref, _, _ = _registry_with_icons(tmp_path)

    wrong_size = CanonicalIconInput(
        data=source_ref.data,
        mediaType=source_ref.media_type,
        sha256=source_ref.sha256,
        byteSize=source_ref.byte_size + 1,
        width=source_ref.width,
        height=source_ref.height,
    )
    with pytest.raises(ValueError, match="byte size"):
        registry.register(
            canonical_registration_fixture(),
            icon_source=wrong_size,
            icon_16=icon_16_ref,
        )

    wrong_hash = CanonicalIconInput(
        data=source_ref.data,
        mediaType=source_ref.media_type,
        sha256="f" * 64,
        byteSize=source_ref.byte_size,
        width=source_ref.width,
        height=source_ref.height,
    )
    with pytest.raises(ValueError, match="hash"):
        registry.register(
            canonical_registration_fixture(),
            icon_source=wrong_hash,
            icon_16=icon_16_ref,
        )

    wrong_icon_bytes = _image_bytes(size=(17, 16))
    wrong_icon_ref = _icon_input(
        wrong_icon_bytes,
        media_type=MediaType.PNG,
        width=17,
        height=16,
    )
    with pytest.raises(ValueError, match="16x16"):
        registry.register(
            canonical_registration_fixture(),
            icon_source=source_ref,
            icon_16=wrong_icon_ref,
        )

    assert not any(workspace.canonical_assets_dir.iterdir())


def test_open_scan_excludes_owned_icon_path_traversal(tmp_path: Path) -> None:
    workspace, registry, source_ref, icon_16_ref, _, _ = _registry_with_icons(tmp_path)
    registration = canonical_registration_fixture()
    registry.register(
        registration,
        icon_source=source_ref,
        icon_16=icon_16_ref,
    )
    with sqlite3.connect(workspace.canonical_registry_path) as connection:
        connection.execute(
            """
            UPDATE canonical_dishes
            SET icon_source_relative_path = '../outside.png'
            WHERE canonical_id = ?
            """,
            (str(registration.canonical_id),),
        )

    reopened = SQLiteCanonicalRegistry(workspace)
    assert reopened.count_valid() == 0


def test_open_scan_and_icon_load_exclude_tampered_owned_assets(tmp_path: Path) -> None:
    workspace, registry, source_ref, icon_16_ref, _, _ = _registry_with_icons(tmp_path)
    registration = canonical_registration_fixture()
    stored = registry.register(
        registration,
        icon_source=source_ref,
        icon_16=icon_16_ref,
    )
    owned_source = workspace.canonical_assets_dir / Path(
        *stored.icon_source.relative_path.split("/")
    )
    owned_source.write_bytes(b"not-an-image")

    with pytest.raises(CanonicalIconUnavailableError):
        registry.load_owned_icon(registration.canonical_id, CanonicalIconKind.SOURCE)
    assert registry.count_valid() == 0

    reopened = SQLiteCanonicalRegistry(workspace)
    assert reopened.count_valid() == 0
    assert reopened.get_valid(registration.canonical_id) is None
    assert reopened.get_by_source_archive_id(registration.source_archive_id) == stored


def test_candidate_queries_are_valid_same_language_catalog_compatible_and_image_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, registry, source_ref, icon_16_ref, _, _ = _registry_with_icons(tmp_path)
    zh_compatible = canonical_registration_fixture(
        language=Language.ZH_CN,
        catalog_version="catalog-v1",
    )
    en_compatible = canonical_registration_fixture(
        language=Language.EN_US,
        catalog_version="catalog-v1",
    )
    zh_incompatible = canonical_registration_fixture(
        language=Language.ZH_CN,
        catalog_version="catalog-v2",
    )
    for registration in (zh_compatible, en_compatible, zh_incompatible):
        registry.register(
            registration,
            icon_source=source_ref,
            icon_16=icon_16_ref,
        )

    def fail_image_read(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("candidate query read image bytes")

    monkeypatch.setattr(registry, "_read_validated_owned_icon", fail_image_read)

    candidates = registry.list_recall_candidates(
        language=Language.ZH_CN,
        catalog_version="catalog-v1",
    )

    assert [candidate.canonical_id for candidate in candidates] == [
        zh_compatible.canonical_id
    ]
    assert candidates[0].recall_document == zh_compatible.recall_document
    assert candidates[0].recall_document.recognized_dish == "Spring Noodles"
    assert candidates[0].recall_document.summary
    assert candidates[0].recall_document.cuisine == "Farmhouse"
    assert candidates[0].recall_document.semantic_ingredients[0].name == "Egg"
    assert registry.count_valid() == 3


def test_usage_event_is_idempotent_by_source_archive_id(tmp_path: Path) -> None:
    _, registry, source_ref, icon_16_ref, _, _ = _registry_with_icons(tmp_path)
    registration = canonical_registration_fixture()
    registry.register(
        registration,
        icon_source=source_ref,
        icon_16=icon_16_ref,
    )
    first_usage_archive = uuid4()
    second_usage_archive = uuid4()
    first_time = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
    second_time = first_time + timedelta(minutes=5)

    first = registry.record_usage(
        registration.canonical_id,
        source_archive_id=first_usage_archive,
        used_at=first_time,
    )
    replay = registry.record_usage(
        registration.canonical_id,
        source_archive_id=first_usage_archive,
        used_at=second_time,
    )
    second = registry.record_usage(
        registration.canonical_id,
        source_archive_id=second_usage_archive,
        used_at=second_time,
    )

    assert first.use_count == 1
    assert first.last_used_at == first_time
    assert replay == first
    assert second.use_count == 2
    assert second.last_used_at == second_time


def test_connections_are_short_configured_and_support_three_concurrent_reads(
    tmp_path: Path,
) -> None:
    _, registry, _, _, _, _ = _registry_with_icons(tmp_path)

    with registry._connect() as first_connection, registry._connect() as second_connection:
        assert first_connection is not second_connection
        assert first_connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert first_connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert first_connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _index: registry.count_valid(), range(3)))
    assert results == [0, 0, 0]


@pytest.mark.parametrize("kind", ["higher", "corrupt", "inconsistent"])
def test_invalid_existing_schema_is_typed_unavailable_without_mutating_database(
    tmp_path: Path,
    kind: str,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    database_path = workspace.canonical_registry_path
    if kind == "corrupt":
        database_path.write_bytes(b"not a sqlite database\x00\x01")
    else:
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TABLE schema_meta (
                    schema_version INTEGER PRIMARY KEY,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO schema_meta(schema_version, updated_at) VALUES (?, ?)",
                (2 if kind == "higher" else 1, "2026-08-25T00:00:00Z"),
            )
    original_bytes = database_path.read_bytes()

    with pytest.raises(CanonicalRegistryUnavailableError):
        SQLiteCanonicalRegistry(workspace)

    assert database_path.read_bytes() == original_bytes
