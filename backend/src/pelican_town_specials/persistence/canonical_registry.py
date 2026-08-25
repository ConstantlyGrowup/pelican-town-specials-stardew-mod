from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import UUID

from PIL import Image

from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.canonical import (
    CANONICAL_CANDIDATE_LIMIT,
    CANONICAL_REGISTRY_SCHEMA_VERSION,
    CanonicalDish,
    CanonicalDishRegistration,
    CanonicalIconInput,
    CanonicalIconKind,
    CanonicalIconMetadata,
    CanonicalRecallCandidate,
    RecallDocument,
)
from pelican_town_specials.domain.common import (
    Language,
    ensure_utc,
    ensure_uuid4,
    utc_now,
)
from pelican_town_specials.domain.dish import GameplaySpec, PresentationSpec

from .atomic import atomic_write_bytes
from .workspace import WorkspacePaths

_MAX_ICON_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_PIXELS = 40_000_000
_MEDIA_FORMATS: dict[MediaType, tuple[str, str]] = {
    MediaType.PNG: ("PNG", "png"),
    MediaType.JPEG: ("JPEG", "jpg"),
    MediaType.WEBP: ("WEBP", "webp"),
}
_EXPECTED_COLUMNS: dict[str, set[str]] = {
    "schema_meta": {"schema_version", "updated_at"},
    "canonical_dishes": {
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
    },
    "canonical_usage_events": {"source_archive_id", "canonical_id", "used_at"},
}


class CanonicalRegistryUnavailableError(RuntimeError):
    """The Registry database cannot be safely opened at the supported schema."""


class CanonicalIconUnavailableError(ValueError):
    """A Registry-owned icon failed its containment or integrity check."""


@dataclass(frozen=True)
class _ValidatedSourceIcon:
    data: bytes
    media_type: MediaType
    width: int
    height: int
    extension: str
    sha256: str


class SQLiteCanonicalRegistry:
    """SQLite schema-v1 Canonical Registry with private, integrity-checked icons."""

    def __init__(
        self,
        workspace: WorkspacePaths,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._workspace = workspace
        self._database_path = workspace.canonical_registry_path
        self._canonical_assets_dir = workspace.canonical_assets_dir
        self._clock = clock
        self._validity_lock = RLock()
        self._valid_canonical_ids: set[UUID] = set()

        if self._database_path.exists():
            self._preflight_existing_database()
        else:
            self._create_schema_v1()
        self._valid_canonical_ids = self._scan_valid_canonical_ids()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=5.0,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            if journal_mode is None or str(journal_mode[0]).lower() != "wal":
                raise CanonicalRegistryUnavailableError(
                    "canonical Registry could not enable WAL mode"
                )
            yield connection
        except CanonicalRegistryUnavailableError:
            raise
        except sqlite3.Error as exc:
            raise CanonicalRegistryUnavailableError(
                "canonical Registry database operation failed"
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    def _preflight_existing_database(self) -> None:
        try:
            database_uri = f"{self._database_path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(database_uri, uri=True, timeout=5.0) as connection:
                connection.execute("PRAGMA query_only = ON")
                integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
                if integrity_rows != [("ok",)]:
                    raise ValueError("canonical Registry integrity check failed")

                versions = connection.execute(
                    "SELECT schema_version, updated_at FROM schema_meta"
                ).fetchall()
                if (
                    len(versions) != 1
                    or int(versions[0][0]) != CANONICAL_REGISTRY_SCHEMA_VERSION
                    or self._parse_timestamp(versions[0][1]) is None
                ):
                    raise ValueError("unsupported canonical Registry schema version")

                primary_keys: dict[str, list[str]] = {}
                for table_name, expected_columns in _EXPECTED_COLUMNS.items():
                    table_info = connection.execute(
                        f'PRAGMA table_info("{table_name}")'
                    ).fetchall()
                    actual_columns = {str(row[1]) for row in table_info}
                    if actual_columns != expected_columns:
                        raise ValueError(
                            f"canonical Registry table is inconsistent: {table_name}"
                        )
                    primary_keys[table_name] = [
                        str(row[1])
                        for row in sorted(table_info, key=lambda value: int(value[5]))
                        if int(row[5]) > 0
                    ]
                if primary_keys != {
                    "schema_meta": ["schema_version"],
                    "canonical_dishes": ["canonical_id"],
                    "canonical_usage_events": ["source_archive_id"],
                }:
                    raise ValueError("canonical Registry primary keys are inconsistent")

                unique_column_sets: set[tuple[str, ...]] = set()
                for index_row in connection.execute(
                    'PRAGMA index_list("canonical_dishes")'
                ).fetchall():
                    if int(index_row[2]) != 1:
                        continue
                    index_name = str(index_row[1]).replace('"', '""')
                    unique_column_sets.add(
                        tuple(
                            str(column_row[2])
                            for column_row in connection.execute(
                                f'PRAGMA index_info("{index_name}")'
                            ).fetchall()
                        )
                    )
                if not {
                    ("canonical_id",),
                    ("source_archive_id",),
                }.issubset(unique_column_sets) or ("signature",) in unique_column_sets:
                    raise ValueError("canonical Registry uniqueness is inconsistent")

                foreign_keys = connection.execute(
                    'PRAGMA foreign_key_list("canonical_usage_events")'
                ).fetchall()
                if not any(
                    row[2] == "canonical_dishes"
                    and row[3] == "canonical_id"
                    and row[4] == "canonical_id"
                    for row in foreign_keys
                ):
                    raise ValueError("canonical Registry foreign key is inconsistent")
        except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
            raise CanonicalRegistryUnavailableError(
                "canonical Registry database is unavailable"
            ) from exc

    def _create_schema_v1(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=5.0,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            if journal_mode is None or str(journal_mode[0]).lower() != "wal":
                raise sqlite3.OperationalError("WAL mode unavailable")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE schema_meta (
                    schema_version INTEGER PRIMARY KEY CHECK (schema_version = 1),
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE canonical_dishes (
                    canonical_id TEXT PRIMARY KEY,
                    source_archive_id TEXT NOT NULL UNIQUE,
                    signature TEXT NOT NULL CHECK (
                        length(signature) = 64
                        AND signature NOT GLOB '*[^0-9a-f]*'
                    ),
                    language TEXT NOT NULL CHECK (language IN ('zh-CN', 'en-US')),
                    reuse_contract_version TEXT NOT NULL,
                    recognized_dish TEXT NOT NULL,
                    normalized_dish_name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    cuisine TEXT,
                    cooking_methods_json TEXT NOT NULL,
                    flavor_profile_json TEXT NOT NULL,
                    semantic_ingredients_json TEXT NOT NULL,
                    presentation_json TEXT NOT NULL,
                    gameplay_json TEXT NOT NULL,
                    visual_brief TEXT NOT NULL,
                    catalog_version TEXT NOT NULL,
                    icon_source_relative_path TEXT NOT NULL,
                    icon_source_media_type TEXT NOT NULL,
                    icon_source_sha256 TEXT NOT NULL,
                    icon_source_byte_size INTEGER NOT NULL CHECK (icon_source_byte_size > 0),
                    icon_source_width INTEGER NOT NULL CHECK (icon_source_width > 0),
                    icon_source_height INTEGER NOT NULL CHECK (icon_source_height > 0),
                    icon_16_relative_path TEXT NOT NULL,
                    icon_16_media_type TEXT NOT NULL CHECK (icon_16_media_type = 'image/png'),
                    icon_16_sha256 TEXT NOT NULL,
                    icon_16_byte_size INTEGER NOT NULL CHECK (icon_16_byte_size > 0),
                    icon_16_width INTEGER NOT NULL CHECK (icon_16_width = 16),
                    icon_16_height INTEGER NOT NULL CHECK (icon_16_height = 16),
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    use_count INTEGER NOT NULL DEFAULT 0 CHECK (use_count >= 0)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE canonical_usage_events (
                    source_archive_id TEXT PRIMARY KEY,
                    canonical_id TEXT NOT NULL,
                    used_at TEXT NOT NULL,
                    FOREIGN KEY (canonical_id)
                        REFERENCES canonical_dishes(canonical_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX canonical_dishes_recall_lookup
                ON canonical_dishes(language, catalog_version, created_at)
                """
            )
            connection.execute(
                "INSERT INTO schema_meta(schema_version, updated_at) VALUES (?, ?)",
                (
                    CANONICAL_REGISTRY_SCHEMA_VERSION,
                    self._serialize_timestamp(ensure_utc(self._clock())),
                ),
            )
            connection.execute("COMMIT")
        except (sqlite3.Error, OSError) as exc:
            if connection is not None and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise CanonicalRegistryUnavailableError(
                "canonical Registry schema could not be created"
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    def register(
        self,
        registration: CanonicalDishRegistration,
        *,
        icon_source: CanonicalIconInput,
        icon_16: CanonicalIconInput,
    ) -> CanonicalDish:
        existing = self.get_by_source_archive_id(registration.source_archive_id)
        if existing is not None:
            return existing

        validated_source = self._validate_icon_input(icon_source)
        validated_icon_16 = self._validate_icon_input(icon_16)
        if validated_icon_16.media_type is not MediaType.PNG:
            raise ValueError("icon16 must be PNG")
        if (validated_icon_16.width, validated_icon_16.height) != (16, 16):
            raise ValueError("icon16 must be exactly 16x16 pixels")

        canonical_directory = self._canonical_assets_dir / str(
            registration.canonical_id
        )
        source_relative_path = (
            f"{registration.canonical_id}/"
            f"icon-source.{validated_source.extension}"
        )
        icon_16_relative_path = f"{registration.canonical_id}/icon-16.png"
        source_destination = canonical_directory / Path(source_relative_path).name
        icon_16_destination = canonical_directory / "icon-16.png"
        created_paths: list[Path] = []
        canonical_directory_was_created = False

        try:
            if self._canonical_assets_dir.is_symlink():
                raise ValueError("canonical assets root must not be a symlink")
            resolved_assets_dir = self._canonical_assets_dir.resolve(strict=True)
            if canonical_directory.exists():
                if canonical_directory.is_symlink() or not canonical_directory.is_dir():
                    raise ValueError("canonical icon directory is unsafe")
            else:
                canonical_directory.mkdir()
                canonical_directory_was_created = True
            resolved_canonical_directory = canonical_directory.resolve(strict=True)
            if resolved_assets_dir not in resolved_canonical_directory.parents:
                raise ValueError("canonical icon directory escapes its root")
            for destination, validated in (
                (source_destination, validated_source),
                (icon_16_destination, validated_icon_16),
            ):
                if destination.exists() or destination.is_symlink():
                    raise ValueError("canonical icon destination already exists")
                atomic_write_bytes(destination, validated.data)
                created_paths.append(destination)

            registered_at = ensure_utc(self._clock())
            dish = CanonicalDish(
                canonicalId=registration.canonical_id,
                sourceArchiveId=registration.source_archive_id,
                dishSignature=registration.dish_signature,
                language=registration.language,
                reuseContractVersion=registration.reuse_contract_version,
                recallDocument=registration.recall_document,
                presentation=registration.presentation,
                gameplay=registration.gameplay,
                visualBrief=registration.visual_brief,
                catalogVersion=registration.catalog_version,
                iconSource=CanonicalIconMetadata(
                    relativePath=source_relative_path,
                    mediaType=validated_source.media_type,
                    sha256=validated_source.sha256,
                    byteSize=len(validated_source.data),
                    width=validated_source.width,
                    height=validated_source.height,
                ),
                icon16=CanonicalIconMetadata(
                    relativePath=icon_16_relative_path,
                    mediaType=validated_icon_16.media_type,
                    sha256=validated_icon_16.sha256,
                    byteSize=len(validated_icon_16.data),
                    width=validated_icon_16.width,
                    height=validated_icon_16.height,
                ),
                registeredAt=registered_at,
                lastUsedAt=None,
                useCount=0,
            )
            self._read_validated_owned_icon(dish, CanonicalIconKind.SOURCE)
            self._read_validated_owned_icon(dish, CanonicalIconKind.ICON_16)
            persisted = self._insert_dish(dish)
            if persisted.canonical_id != dish.canonical_id:
                for created_path in reversed(created_paths):
                    created_path.unlink(missing_ok=True)
                if canonical_directory_was_created:
                    canonical_directory.rmdir()
                return persisted
        except Exception:
            for created_path in reversed(created_paths):
                created_path.unlink(missing_ok=True)
            if canonical_directory_was_created:
                try:
                    canonical_directory.rmdir()
                except OSError:
                    pass
            raise

        with self._validity_lock:
            self._valid_canonical_ids.add(persisted.canonical_id)
        return persisted

    def get_by_source_archive_id(
        self,
        source_archive_id: UUID,
    ) -> CanonicalDish | None:
        ensure_uuid4(source_archive_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM canonical_dishes WHERE source_archive_id = ?",
                (str(source_archive_id),),
            ).fetchone()
        return None if row is None else self._row_to_dish(row)

    def get_valid(self, canonical_id: UUID) -> CanonicalDish | None:
        ensure_uuid4(canonical_id)
        with self._validity_lock:
            if canonical_id not in self._valid_canonical_ids:
                return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM canonical_dishes WHERE canonical_id = ?",
                (str(canonical_id),),
            ).fetchone()
        return None if row is None else self._row_to_dish(row)

    def count_valid(self) -> int:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT canonical_id FROM canonical_dishes"
            ).fetchall()
        persisted_ids = {str(row[0]) for row in rows}
        with self._validity_lock:
            valid_ids = {str(value) for value in self._valid_canonical_ids}
        return len(persisted_ids.intersection(valid_ids))

    def list_recall_candidates(
        self,
        *,
        language: Language,
        catalog_version: str,
        limit: int = CANONICAL_CANDIDATE_LIMIT,
    ) -> list[CanonicalRecallCandidate]:
        if not 1 <= limit <= CANONICAL_CANDIDATE_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {CANONICAL_CANDIDATE_LIMIT}"
            )
        with self._validity_lock:
            valid_ids = {str(value) for value in self._valid_canonical_ids}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT canonical_id, signature, language, catalog_version,
                       recognized_dish, normalized_dish_name, summary, cuisine,
                       cooking_methods_json, flavor_profile_json,
                       semantic_ingredients_json, use_count, last_used_at
                FROM canonical_dishes
                WHERE language = ? AND catalog_version = ?
                ORDER BY created_at ASC, canonical_id ASC
                """,
                (language.value, catalog_version),
            ).fetchall()
        candidates: list[CanonicalRecallCandidate] = []
        for row in rows:
            if str(row["canonical_id"]) not in valid_ids:
                continue
            candidates.append(
                CanonicalRecallCandidate(
                    canonicalId=UUID(str(row["canonical_id"])),
                    dishSignature=str(row["signature"]),
                    language=Language(str(row["language"])),
                    catalogVersion=str(row["catalog_version"]),
                    recallDocument=self._row_to_recall_document(row),
                    useCount=int(row["use_count"]),
                    lastUsedAt=self._parse_timestamp(row["last_used_at"]),
                )
            )
            if len(candidates) == limit:
                break
        return candidates

    def record_usage(
        self,
        canonical_id: UUID,
        *,
        source_archive_id: UUID,
        used_at: datetime | None = None,
    ) -> CanonicalDish:
        ensure_uuid4(canonical_id)
        ensure_uuid4(source_archive_id)
        current_time = ensure_utc(used_at or self._clock())
        timestamp = self._serialize_timestamp(current_time)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO canonical_usage_events(
                        source_archive_id, canonical_id, used_at
                    ) VALUES (?, ?, ?)
                    """,
                    (str(source_archive_id), str(canonical_id), timestamp),
                )
                if cursor.rowcount == 1:
                    connection.execute(
                        """
                        UPDATE canonical_dishes
                        SET use_count = use_count + 1, last_used_at = ?
                        WHERE canonical_id = ?
                        """,
                        (timestamp, str(canonical_id)),
                    )
                row = connection.execute(
                    "SELECT * FROM canonical_dishes WHERE canonical_id = ?",
                    (str(canonical_id),),
                ).fetchone()
                if row is None:
                    raise FileNotFoundError(
                        f"canonical dish not found: {canonical_id}"
                    )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return self._row_to_dish(row)

    def load_owned_icon(
        self,
        canonical_id: UUID,
        kind: CanonicalIconKind,
    ) -> bytes:
        ensure_uuid4(canonical_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM canonical_dishes WHERE canonical_id = ?",
                (str(canonical_id),),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"canonical dish not found: {canonical_id}")
        try:
            dish = self._row_to_dish(row)
            source_bytes = self._read_validated_owned_icon(
                dish,
                CanonicalIconKind.SOURCE,
            )
            icon_16_bytes = self._read_validated_owned_icon(
                dish,
                CanonicalIconKind.ICON_16,
            )
        except (OSError, ValueError) as exc:
            with self._validity_lock:
                self._valid_canonical_ids.discard(canonical_id)
            raise CanonicalIconUnavailableError(
                "canonical owned icon is unavailable"
            ) from exc
        with self._validity_lock:
            self._valid_canonical_ids.add(canonical_id)
        return source_bytes if kind is CanonicalIconKind.SOURCE else icon_16_bytes

    def _insert_dish(self, dish: CanonicalDish) -> CanonicalDish:
        gameplay_payload = dish.gameplay.model_dump(by_alias=True, mode="json")
        recovery = gameplay_payload.get("recovery")
        if isinstance(recovery, dict):
            for derived_field in (
                "calculationVersion",
                "energyRestore",
                "healthRestore",
            ):
                recovery.pop(derived_field, None)
        recall_document = dish.recall_document
        values: dict[str, str | int | None] = {
            "canonical_id": str(dish.canonical_id),
            "source_archive_id": str(dish.source_archive_id),
            "signature": dish.dish_signature,
            "language": dish.language.value,
            "reuse_contract_version": dish.reuse_contract_version,
            "recognized_dish": recall_document.recognized_dish,
            "normalized_dish_name": recall_document.normalized_name,
            "summary": recall_document.summary,
            "cuisine": recall_document.cuisine,
            "cooking_methods_json": self._dump_json(
                list(recall_document.cooking_methods)
            ),
            "flavor_profile_json": self._dump_json(
                list(recall_document.flavor_profile)
            ),
            "semantic_ingredients_json": self._dump_json(
                [
                    ingredient.model_dump(by_alias=True, mode="json")
                    for ingredient in recall_document.semantic_ingredients
                ]
            ),
            "presentation_json": self._dump_json(
                dish.presentation.model_dump(by_alias=True, mode="json")
            ),
            "gameplay_json": self._dump_json(gameplay_payload),
            "visual_brief": dish.visual_brief,
            "catalog_version": dish.catalog_version,
            "icon_source_relative_path": dish.icon_source.relative_path,
            "icon_source_media_type": dish.icon_source.media_type.value,
            "icon_source_sha256": dish.icon_source.sha256,
            "icon_source_byte_size": dish.icon_source.byte_size,
            "icon_source_width": dish.icon_source.width,
            "icon_source_height": dish.icon_source.height,
            "icon_16_relative_path": dish.icon_16.relative_path,
            "icon_16_media_type": dish.icon_16.media_type.value,
            "icon_16_sha256": dish.icon_16.sha256,
            "icon_16_byte_size": dish.icon_16.byte_size,
            "icon_16_width": dish.icon_16.width,
            "icon_16_height": dish.icon_16.height,
            "created_at": self._serialize_timestamp(dish.registered_at),
            "last_used_at": None,
            "use_count": 0,
        }
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO canonical_dishes(
                        canonical_id, source_archive_id, signature, language,
                        reuse_contract_version, recognized_dish,
                        normalized_dish_name, summary, cuisine,
                        cooking_methods_json, flavor_profile_json,
                        semantic_ingredients_json,
                        presentation_json, gameplay_json, visual_brief,
                        catalog_version, icon_source_relative_path,
                        icon_source_media_type, icon_source_sha256,
                        icon_source_byte_size, icon_source_width,
                        icon_source_height, icon_16_relative_path,
                        icon_16_media_type, icon_16_sha256, icon_16_byte_size,
                        icon_16_width, icon_16_height, created_at,
                        last_used_at, use_count
                    ) VALUES (
                        :canonical_id, :source_archive_id, :signature, :language,
                        :reuse_contract_version, :recognized_dish,
                        :normalized_dish_name, :summary, :cuisine,
                        :cooking_methods_json, :flavor_profile_json,
                        :semantic_ingredients_json, :presentation_json,
                        :gameplay_json, :visual_brief, :catalog_version,
                        :icon_source_relative_path, :icon_source_media_type,
                        :icon_source_sha256, :icon_source_byte_size,
                        :icon_source_width, :icon_source_height,
                        :icon_16_relative_path, :icon_16_media_type,
                        :icon_16_sha256, :icon_16_byte_size, :icon_16_width,
                        :icon_16_height, :created_at, :last_used_at, :use_count
                    )
                    """,
                    values,
                )
                connection.execute("COMMIT")
            return dish
        except CanonicalRegistryUnavailableError:
            existing = self.get_by_source_archive_id(dish.source_archive_id)
            if existing is not None:
                return existing
            raise

    def _validate_icon_input(
        self,
        icon_input: CanonicalIconInput,
    ) -> _ValidatedSourceIcon:
        if icon_input.media_type not in _MEDIA_FORMATS:
            raise ValueError("canonical icon media type is unsupported")
        size = len(icon_input.data)
        if size != icon_input.byte_size:
            raise ValueError("source icon byte size does not match metadata")
        if not 0 < size <= _MAX_ICON_BYTES:
            raise ValueError("source icon size is outside the supported range")
        data = icon_input.data
        sha256 = hashlib.sha256(data).hexdigest()
        if sha256 != icon_input.sha256:
            raise ValueError("source icon hash does not match metadata")
        width, height, extension = self._validate_image_bytes(
            data,
            icon_input.media_type,
        )
        if (width, height) != (icon_input.width, icon_input.height):
            raise ValueError("source icon dimensions do not match metadata")
        return _ValidatedSourceIcon(
            data=data,
            media_type=icon_input.media_type,
            width=width,
            height=height,
            extension=extension,
            sha256=sha256,
        )

    def _read_validated_owned_icon(
        self,
        dish: CanonicalDish,
        kind: CanonicalIconKind,
    ) -> bytes:
        metadata = (
            dish.icon_source
            if kind is CanonicalIconKind.SOURCE
            else dish.icon_16
        )
        expected_name = (
            f"icon-source.{_MEDIA_FORMATS[metadata.media_type][1]}"
            if kind is CanonicalIconKind.SOURCE
            else "icon-16.png"
        )
        expected_relative_path = f"{dish.canonical_id}/{expected_name}"
        if metadata.relative_path != expected_relative_path:
            raise ValueError("canonical owned icon path is inconsistent")
        owned_path = self._resolve_contained_regular_file(
            self._canonical_assets_dir,
            metadata.relative_path,
            label="canonical owned icon",
        )
        size = owned_path.stat().st_size
        if size != metadata.byte_size or not 0 < size <= _MAX_ICON_BYTES:
            raise ValueError("canonical owned icon byte size does not match metadata")
        data = owned_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != metadata.sha256:
            raise ValueError("canonical owned icon hash does not match metadata")
        width, height, _extension = self._validate_image_bytes(
            data,
            metadata.media_type,
        )
        if (width, height) != (metadata.width, metadata.height):
            raise ValueError("canonical owned icon dimensions do not match metadata")
        if kind is CanonicalIconKind.ICON_16 and (
            metadata.media_type is not MediaType.PNG or (width, height) != (16, 16)
        ):
            raise ValueError("canonical icon16 must be PNG and exactly 16x16")
        return data

    def _resolve_contained_regular_file(
        self,
        root: Path,
        relative_path: str,
        *,
        label: str,
    ) -> Path:
        parts = relative_path.split("/")
        if (
            not relative_path
            or relative_path.startswith(("/", "\\"))
            or "\\" in relative_path
            or ":" in relative_path
            or ".." in parts
            or any(not part for part in parts)
        ):
            raise ValueError(f"{label} relative path escapes its root")
        if root.is_symlink():
            raise ValueError(f"{label} root must not be a symlink")
        resolved_root = root.resolve()
        candidate = root.joinpath(*parts)
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"{label} must not use a symlink")
        try:
            resolved_candidate = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(f"{label} is missing") from exc
        if (
            resolved_candidate == resolved_root
            or resolved_root not in resolved_candidate.parents
        ):
            raise ValueError(f"{label} path escapes its root")
        if not resolved_candidate.is_file():
            raise ValueError(f"{label} is not a regular file")
        return resolved_candidate

    @staticmethod
    def _validate_image_bytes(
        data: bytes,
        media_type: MediaType,
    ) -> tuple[int, int, str]:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image_format = image.format
                width, height = image.size
                image.verify()
        except Exception as exc:
            raise ValueError("canonical icon bytes are not a valid image") from exc
        expected_format, extension = _MEDIA_FORMATS[media_type]
        if image_format != expected_format:
            raise ValueError("canonical icon media type does not match its bytes")
        if width * height > _MAX_IMAGE_PIXELS:
            raise ValueError("canonical icon exceeds 40 megapixels")
        return width, height, extension

    def _scan_valid_canonical_ids(self) -> set[UUID]:
        valid_ids: set[UUID] = set()
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM canonical_dishes").fetchall()
        for row in rows:
            try:
                dish = self._row_to_dish(row)
                self._read_validated_owned_icon(dish, CanonicalIconKind.SOURCE)
                self._read_validated_owned_icon(dish, CanonicalIconKind.ICON_16)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            valid_ids.add(dish.canonical_id)
        return valid_ids

    @staticmethod
    def _dump_json(payload: object) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _serialize_timestamp(value: datetime) -> str:
        return ensure_utc(value).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(datetime.fromisoformat(str(value)))

    def _row_to_dish(self, row: sqlite3.Row) -> CanonicalDish:
        registered_at = self._parse_timestamp(row["created_at"])
        if registered_at is None:
            raise ValueError("canonical registered_at must not be null")
        return CanonicalDish(
            canonicalId=UUID(str(row["canonical_id"])),
            sourceArchiveId=UUID(str(row["source_archive_id"])),
            dishSignature=str(row["signature"]),
            language=Language(str(row["language"])),
            reuseContractVersion=str(row["reuse_contract_version"]),
            recallDocument=self._row_to_recall_document(row),
            presentation=PresentationSpec.model_validate(
                json.loads(str(row["presentation_json"]))
            ),
            gameplay=GameplaySpec.model_validate(
                json.loads(str(row["gameplay_json"]))
            ),
            visualBrief=str(row["visual_brief"]),
            catalogVersion=str(row["catalog_version"]),
            iconSource=CanonicalIconMetadata(
                relativePath=str(row["icon_source_relative_path"]),
                mediaType=MediaType(str(row["icon_source_media_type"])),
                sha256=str(row["icon_source_sha256"]),
                byteSize=int(row["icon_source_byte_size"]),
                width=int(row["icon_source_width"]),
                height=int(row["icon_source_height"]),
            ),
            icon16=CanonicalIconMetadata(
                relativePath=str(row["icon_16_relative_path"]),
                mediaType=MediaType(str(row["icon_16_media_type"])),
                sha256=str(row["icon_16_sha256"]),
                byteSize=int(row["icon_16_byte_size"]),
                width=int(row["icon_16_width"]),
                height=int(row["icon_16_height"]),
            ),
            registeredAt=registered_at,
            lastUsedAt=self._parse_timestamp(row["last_used_at"]),
            useCount=int(row["use_count"]),
        )

    @staticmethod
    def _row_to_recall_document(row: sqlite3.Row) -> RecallDocument:
        return RecallDocument(
            recognizedDish=str(row["recognized_dish"]),
            normalizedName=str(row["normalized_dish_name"]),
            summary=str(row["summary"]),
            cuisine=None if row["cuisine"] is None else str(row["cuisine"]),
            cookingMethods=json.loads(str(row["cooking_methods_json"])),
            flavorProfile=json.loads(str(row["flavor_profile_json"])),
            semanticIngredients=json.loads(
                str(row["semantic_ingredients_json"])
            ),
        )
