from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import Field

from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.common import (
    DraftMode,
    Language,
    StrictModel,
    utc_now,
)
from pelican_town_specials.domain.dish import FieldAuthority, GenerationSource
from pelican_town_specials.domain.draft import DraftRecord, DraftStatus

from .atomic import atomic_write_json, read_json_with_backup
from .trash import CookbookTombstone, move_directory_to_trash
from .workspace import WorkspacePaths


class RevisionConflictError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class TombstonedDishError(Exception):
    pass


class DraftIndex(StrictModel):
    schema_version: int = Field(default=1)
    draft_ids: list[str] = Field(default_factory=list, alias="draftIds")


class ArchiveIndex(StrictModel):
    schema_version: int = Field(default=1)
    dish_ids: list[str] = Field(default_factory=list, alias="dishIds")


class ArchiveIdempotencyIndex(StrictModel):
    schema_version: int = Field(default=1)
    keys: dict[str, str] = Field(default_factory=dict)


_UUID_FIELD_NAMES = {
    "activeAttemptId",
    "archivedDishId",
    "assetId",
    "attemptId",
    "dishId",
    "draftId",
    "generatedArtAssetId",
    "icon16AssetId",
    "iconSourceAssetId",
    "lastAttemptId",
    "originalImageAssetId",
    "previewAssetId",
    "requestId",
    "sourceDraftId",
}
_DATETIME_FIELD_NAMES = {
    "archivedAt",
    "createdAt",
    "finishedAt",
    "occurredAt",
    "startedAt",
    "updatedAt",
}
_ENUM_FIELD_PARSERS = {
    "generationSource": GenerationSource,
    "language": Language,
    "mode": DraftMode,
    "status": DraftStatus,
}
_RECOVERY_DERIVED_FIELD_NAMES = {
    "calculationVersion",
    "energyRestore",
    "healthRestore",
}


def _normalize_domain_payload(payload: object) -> object:
    if isinstance(payload, list):
        return [_normalize_domain_payload(item) for item in payload]
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
        enum_parser = _ENUM_FIELD_PARSERS.get(key)
        if enum_parser is not None and isinstance(value, str):
            normalized[key] = enum_parser(value)
            continue
        if key == "authorityByField" and isinstance(value, dict):
            normalized[key] = {
                field_name: enum_value
                if isinstance(enum_value, FieldAuthority)
                else FieldAuthority(enum_value)
                for field_name, enum_value in value.items()
            }
            continue
        if key == "recovery" and isinstance(value, dict):
            normalized[key] = _normalize_domain_payload(
                {
                    field_name: field_value
                    for field_name, field_value in value.items()
                    if field_name not in _RECOVERY_DERIVED_FIELD_NAMES
                }
            )
            continue
        normalized[key] = _normalize_domain_payload(value)
    return normalized


def _validate_model_payload[T: StrictModel](
    model_type: type[T],
) -> Callable[[object], T]:
    def _validate(payload: object) -> T:
        return model_type.model_validate(_normalize_domain_payload(payload))

    return _validate


class DraftRepository:
    def __init__(self, workspace: WorkspacePaths) -> None:
        self._workspace = workspace
        self._index_path = workspace.drafts_dir / "index.json"

    def save(
        self,
        record: DraftRecord,
        *,
        expected_revision: int | None,
    ) -> DraftRecord:
        record_dir = self._workspace.drafts_dir / str(record.draft_id)
        record_dir.mkdir(parents=True, exist_ok=True)
        record_path = record_dir / "record.json"

        if record_path.exists():
            current = self.get(record.draft_id)
            if expected_revision != current.revision:
                raise RevisionConflictError(
                    "expected revision does not match current record"
                )
            persisted = record.model_copy(update={"revision": current.revision + 1})
        else:
            if expected_revision is not None:
                raise RevisionConflictError(
                    "expected revision does not match current record"
                )
            persisted = record

        atomic_write_json(record_path, persisted.model_dump(by_alias=True, mode="json"))
        self._write_index()
        return persisted

    def get(self, draft_id: UUID) -> DraftRecord:
        record_path = self._workspace.drafts_dir / str(draft_id) / "record.json"
        return read_json_with_backup(record_path, _validate_model_payload(DraftRecord))

    def list(self) -> list[DraftRecord]:
        index = self._load_or_rebuild_index()
        return [self.get(UUID(draft_id)) for draft_id in index.draft_ids]

    def _load_or_rebuild_index(self) -> DraftIndex:
        try:
            return DraftIndex.model_validate(
                json.loads(self._index_path.read_text(encoding="utf-8"))
            )
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return self._write_index()

    def _write_index(self) -> DraftIndex:
        draft_ids = sorted(
            child.name
            for child in self._workspace.drafts_dir.iterdir()
            if child.is_dir() and (child / "record.json").exists()
        )
        index = DraftIndex(draftIds=draft_ids)
        atomic_write_json(
            self._index_path, index.model_dump(by_alias=True, mode="json")
        )
        return index


class ArchiveRepository:
    def __init__(self, workspace: WorkspacePaths) -> None:
        self._workspace = workspace
        self._index_path = workspace.cookbook_dir / "index.json"
        self._idempotency_path = workspace.cookbook_dir / "idempotency.json"

    def add_immutable(
        self,
        record: ArchivedDish,
        *,
        idempotency_key: str,
    ) -> ArchivedDish:
        self._repair_deleted_state()
        idempotency_index = self._load_idempotency_index()
        mapped_dish_id = idempotency_index.keys.get(idempotency_key)
        if mapped_dish_id is not None:
            existing = self.get(UUID(mapped_dish_id))
            if existing.dish_id != record.dish_id:
                raise IdempotencyConflictError(
                    "idempotency key already maps to a different record"
                )
            return existing

        record_path = self._record_path(record.dish_id)
        if self._tombstone_path(record.dish_id).exists():
            raise TombstonedDishError("dish has been deleted and cannot be recreated")
        if record_path.exists():
            raise IdempotencyConflictError(
                "record already exists with a different idempotency key"
            )

        record_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(record_path, record.model_dump(by_alias=True, mode="json"))
        idempotency_index.keys[idempotency_key] = str(record.dish_id)
        atomic_write_json(
            self._idempotency_path,
            idempotency_index.model_dump(by_alias=True, mode="json"),
        )
        self._write_index()
        return record

    def get(self, dish_id: UUID) -> ArchivedDish:
        return read_json_with_backup(
            self._record_path(dish_id), _validate_model_payload(ArchivedDish)
        )

    def get_by_idempotency_key(self, idempotency_key: str) -> ArchivedDish | None:
        idempotency_index = self._load_idempotency_index()
        dish_id = idempotency_index.keys.get(idempotency_key)
        if dish_id is None:
            return None
        return self.get(UUID(dish_id))

    def list_active(self) -> list[ArchivedDish]:
        self._repair_deleted_state()
        index = self._load_or_rebuild_index()
        return [self.get(UUID(dish_id)) for dish_id in index.dish_ids]

    def delete(self, dish_id: UUID) -> CookbookTombstone:
        self._repair_deleted_state()
        archive = self.get(dish_id)
        trash_dir = move_directory_to_trash(
            self._record_path(dish_id).parent,
            self._workspace.trash_dir / "cookbook",
        )
        tombstone = CookbookTombstone(
            dishId=dish_id,
            deletedAt=utc_now(),
            contentHash=archive.content_hash,
        )
        atomic_write_json(
            trash_dir / "tombstone.json",
            tombstone.model_dump(by_alias=True, mode="json"),
        )
        self._write_index(excluded_dish_id=dish_id)
        idempotency_index = self._load_idempotency_index()
        idempotency_index.keys = {
            key: value
            for key, value in idempotency_index.keys.items()
            if value != str(dish_id)
        }
        atomic_write_json(
            self._idempotency_path,
            idempotency_index.model_dump(by_alias=True, mode="json"),
        )
        return tombstone

    def _record_path(self, dish_id: UUID) -> Path:
        return self._workspace.cookbook_dir / str(dish_id) / "record.json"

    def _tombstone_path(self, dish_id: UUID) -> Path:
        return self._workspace.trash_dir / "cookbook" / str(dish_id) / "tombstone.json"

    def _repair_deleted_state(self) -> None:
        trash_root = self._workspace.trash_dir / "cookbook"
        if not trash_root.exists():
            return
        deleted_ids: set[str] = set()
        for directory in trash_root.iterdir():
            record_path = directory / "record.json"
            if not directory.is_dir() or not record_path.exists():
                continue
            try:
                archive = read_json_with_backup(
                    record_path, _validate_model_payload(ArchivedDish)
                )
            except (OSError, ValueError, TypeError):
                continue
            if not (directory / "tombstone.json").exists():
                tombstone = CookbookTombstone(
                    dishId=archive.dish_id,
                    deletedAt=utc_now(),
                    contentHash=archive.content_hash,
                )
                atomic_write_json(
                    directory / "tombstone.json",
                    tombstone.model_dump(by_alias=True, mode="json"),
                )
            deleted_ids.add(str(archive.dish_id))
        if deleted_ids:
            self._write_index()
            index = self._load_idempotency_index()
            index.keys = {
                key: value
                for key, value in index.keys.items()
                if value not in deleted_ids
            }
            atomic_write_json(
                self._idempotency_path, index.model_dump(by_alias=True, mode="json")
            )

    def _load_or_rebuild_index(self) -> ArchiveIndex:
        try:
            return ArchiveIndex.model_validate(
                json.loads(self._index_path.read_text(encoding="utf-8"))
            )
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return self._write_index()

    def _load_idempotency_index(self) -> ArchiveIdempotencyIndex:
        try:
            return read_json_with_backup(
                self._idempotency_path,
                ArchiveIdempotencyIndex.model_validate,
            )
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return ArchiveIdempotencyIndex()

    def _write_index(self, *, excluded_dish_id: UUID | None = None) -> ArchiveIndex:
        dish_ids = sorted(
            child.name
            for child in self._workspace.cookbook_dir.iterdir()
            if child.is_dir()
            and (child / "record.json").exists()
            and child.name != str(excluded_dish_id)
        )
        index = ArchiveIndex(dishIds=dish_ids)
        atomic_write_json(
            self._index_path, index.model_dump(by_alias=True, mode="json")
        )
        return index
