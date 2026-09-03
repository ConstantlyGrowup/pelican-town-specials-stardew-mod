from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import Field

from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.common import (
    DraftMode,
    GenerationStage,
    Language,
    StrictModel,
    utc_now,
)
from pelican_town_specials.domain.dish import FieldAuthority, GenerationSource
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    DraftRecord,
    DraftStatus,
    GenerationAttempt,
    GenerationAttemptKind,
    StageStatus,
)
from pelican_town_specials.domain.export import ExportRecord, ExportStatus
from pelican_town_specials.generation.checkpoints import GenerationCheckpoint

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
    "artifactAssetId",
    "assetId",
    "attemptId",
    "canonicalDishId",
    "canonicalId",
    "dishId",
    "draftId",
    "exportId",
    "generatedArtAssetId",
    "icon16AssetId",
    "iconSourceAssetId",
    "lastAttemptId",
    "originalImageAssetId",
    "previewAssetId",
    "requestId",
    "sourceArchiveId",
    "sourceDraftId",
}
_DATETIME_FIELD_NAMES = {
    "archivedAt",
    "createdAt",
    "finishedAt",
    "lastUsedAt",
    "occurredAt",
    "registeredAt",
    "startedAt",
    "updatedAt",
    "validatedAt",
}
_ENUM_FIELD_PARSERS = {
    "generationSource": GenerationSource,
    "language": Language,
    "mediaType": MediaType,
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

    def delete(self, draft_id: UUID) -> None:
        """Permanently remove a draft record directory and refresh the index."""
        shutil.rmtree(self._workspace.drafts_dir / str(draft_id), ignore_errors=True)
        self._write_index()

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

    def _write_record(self, record: DraftRecord) -> DraftRecord:
        record_dir = self._workspace.drafts_dir / str(record.draft_id)
        record_dir.mkdir(parents=True, exist_ok=True)
        record_path = record_dir / "record.json"
        atomic_write_json(
            record_path, record.model_dump(by_alias=True, mode="json")
        )
        self._write_index()
        return record

    def control_write(
        self,
        record: DraftRecord,
        *,
        expected_revision: int,
        expected_attempt_id: UUID | None,
    ) -> DraftRecord:
        """Persist a generation status change without advancing the revision.

        ``expected_attempt_id=None`` means the caller expects no attempt to be
        active yet (used when starting a fresh attempt); otherwise the persisted
        active attempt must match exactly so stale attempts can never overwrite.
        """
        current = self.get(record.draft_id)
        if expected_revision != current.revision:
            raise RevisionConflictError("expected revision does not match current record")
        active = current.active_attempt_id
        if expected_attempt_id is None:
            if active is not None:
                raise AttemptMismatchError("active attempt does not match expected attempt")
        elif active != expected_attempt_id:
            raise AttemptMismatchError("active attempt does not match expected attempt")
        return self._write_record(record)

    def promote(
        self,
        record: DraftRecord,
        *,
        expected_revision: int,
        expected_attempt_id: UUID,
    ) -> DraftRecord:
        """Atomically promote a fully generated candidate, advancing revision once."""
        current = self.get(record.draft_id)
        if expected_revision != current.revision:
            raise RevisionConflictError("source revision does not match current record")
        if current.active_attempt_id != expected_attempt_id:
            raise AttemptMismatchError("active attempt does not match expected attempt")
        promoted = record.model_copy(
            update={"revision": current.revision + 1}
        )
        return self._write_record(promoted)


class AttemptMismatchError(Exception):
    pass


def _normalize_attempt_payload(payload: object, *, in_stage: bool = False) -> object:
    if isinstance(payload, list):
        return [_normalize_attempt_payload(item) for item in payload]
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
        if key == "kind" and isinstance(value, str):
            normalized[key] = GenerationAttemptKind(value)
            continue
        if key in ("currentStage", "stage") and isinstance(value, str):
            normalized[key] = GenerationStage(value)
            continue
        if key == "status" and isinstance(value, str):
            normalized[key] = StageStatus(value) if in_stage else AttemptStatus(value)
            continue
        if key == "stages" and isinstance(value, list):
            normalized[key] = [
                _normalize_attempt_payload(item, in_stage=True) for item in value
            ]
            continue
        if key == "error" and isinstance(value, dict):
            normalized[key] = _normalize_attempt_payload(value)
            continue
        normalized[key] = _normalize_attempt_payload(value)
    return normalized


def _validate_attempt(payload: object) -> GenerationAttempt:
    return GenerationAttempt.model_validate(_normalize_attempt_payload(payload))


def _normalize_checkpoint_payload(payload: object) -> object:
    """Normalize JSON enum/UUID/datetime values before strict checkpoint parsing."""
    normalized = _normalize_domain_payload(payload)
    if not isinstance(normalized, dict):
        return normalized
    if isinstance(payload, dict):
        kind = payload.get("kind")
        if isinstance(kind, str):
            normalized["kind"] = GenerationAttemptKind(kind)
        completed = payload.get("completedStages")
        if isinstance(completed, list):
            normalized["completedStages"] = [
                GenerationStage(stage) if isinstance(stage, str) else stage
                for stage in completed
            ]
    return normalized


def _validate_checkpoint(payload: object) -> GenerationCheckpoint:
    return GenerationCheckpoint.model_validate(_normalize_checkpoint_payload(payload))


class GenerationAttemptRepository:
    """Atomic attempt and candidate persistence under workspace staging."""

    def __init__(self, workspace: WorkspacePaths) -> None:
        self._staging_root = workspace.staging_dir

    def _attempt_dir(self, attempt_id: UUID) -> Path:
        return self._staging_root / f"attempt-{attempt_id}"

    def _checkpoint_path(self, attempt_id: UUID) -> Path:
        return self._attempt_dir(attempt_id) / "checkpoint.json"

    def save(self, attempt: GenerationAttempt) -> GenerationAttempt:
        attempt_dir = self._attempt_dir(attempt.attempt_id)
        attempt_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            attempt_dir / "attempt.json",
            attempt.model_dump(by_alias=True, mode="json"),
        )
        return attempt

    def get(self, attempt_id: UUID) -> GenerationAttempt:
        return read_json_with_backup(
            self._attempt_dir(attempt_id) / "attempt.json",
            _validate_attempt,
        )

    def save_candidate(
        self,
        attempt_id: UUID,
        candidate: DraftRecord,
    ) -> DraftRecord:
        attempt_dir = self._attempt_dir(attempt_id)
        attempt_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            attempt_dir / "candidate.json",
            candidate.model_dump(by_alias=True, mode="json"),
        )
        return candidate

    def get_candidate(self, attempt_id: UUID) -> DraftRecord | None:
        path = self._attempt_dir(attempt_id) / "candidate.json"
        if not path.exists():
            return None
        return read_json_with_backup(path, _validate_model_payload(DraftRecord))

    def save_checkpoint(self, checkpoint: GenerationCheckpoint) -> GenerationCheckpoint:
        """Atomically persist one typed checkpoint inside its attempt directory."""
        attempt_dir = self._attempt_dir(checkpoint.attempt_id)
        attempt_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self._checkpoint_path(checkpoint.attempt_id),
            checkpoint.model_dump(by_alias=True, mode="json"),
        )
        return checkpoint

    def get_checkpoint(self, attempt_id: UUID) -> GenerationCheckpoint | None:
        """Load a checkpoint only when its JSON and nested domain data validate."""
        path = self._checkpoint_path(attempt_id)
        if not path.exists():
            return None
        try:
            return read_json_with_backup(path, _validate_checkpoint)
        except (OSError, TypeError, ValueError, AttributeError):
            # Corrupt or future-version staging is an ordinary cache miss. It
            # must never block a fresh generation, failure handling, or leak
            # storage details.
            return None

    def delete_checkpoint(self, attempt_id: UUID) -> None:
        """Clear checkpoint metadata while leaving assets for orphan GC."""
        self._checkpoint_path(attempt_id).unlink(missing_ok=True)

    def delete_checkpoints_for_draft(self, draft_id: UUID) -> int:
        """Clear all checkpoint metadata belonging to a draft."""
        deleted = 0
        for attempt_path in self._staging_root.glob("attempt-*/attempt.json"):
            try:
                attempt = read_json_with_backup(attempt_path, _validate_attempt)
            except (OSError, TypeError, ValueError):
                continue
            if attempt.draft_id != draft_id:
                continue
            checkpoint_path = attempt_path.parent / "checkpoint.json"
            if checkpoint_path.exists():
                checkpoint_path.unlink(missing_ok=True)
                deleted += 1
        return deleted

    def list_checkpoint_asset_ids(self, *, excluding: UUID | None = None) -> set[UUID]:
        """Return assets retained by valid checkpoints for shared-asset safety."""
        referenced: set[UUID] = set()
        for checkpoint_path in self._staging_root.glob("attempt-*/checkpoint.json"):
            try:
                checkpoint = read_json_with_backup(
                    checkpoint_path,
                    _validate_checkpoint,
                )
            except (OSError, TypeError, ValueError):
                continue
            if excluding is not None and checkpoint.draft_id == excluding:
                continue
            for asset_id in (
                checkpoint.icon_source_asset_id,
                checkpoint.icon_16_asset_id,
                checkpoint.preview_asset_id,
            ):
                if asset_id is not None:
                    referenced.add(asset_id)
            if checkpoint.candidate.visuals is not None:
                for visuals_asset_id in (
                    checkpoint.candidate.visuals.generated_art_asset_id,
                    checkpoint.candidate.visuals.preview_asset_id,
                    checkpoint.candidate.visuals.icon_source_asset_id,
                    checkpoint.candidate.visuals.icon_16_asset_id,
                ):
                    if visuals_asset_id is not None:
                        referenced.add(visuals_asset_id)
        return referenced

    def list_running(self) -> list[GenerationAttempt]:
        running: list[GenerationAttempt] = []
        for path in self._staging_root.glob("attempt-*/attempt.json"):
            attempt = read_json_with_backup(path, _validate_attempt)
            if attempt.status is AttemptStatus.RUNNING:
                running.append(attempt)
        return running

    def interrupt_running(
        self,
        now: datetime | None = None,
    ) -> list[GenerationAttempt]:
        interrupted: list[GenerationAttempt] = []
        for attempt in self.list_running():
            updated = attempt.model_copy(
                update={
                    "status": AttemptStatus.INTERRUPTED,
                    "finished_at": now or utc_now(),
                }
            )
            self.save(updated)
            interrupted.append(updated)
        return interrupted

    def delete_for_draft(self, draft_id: UUID) -> int:
        """Remove every attempt directory belonging to a draft.

        Returns the number of attempt directories removed. Attempts that
        cannot be read are skipped so a corrupt staging entry never blocks
        the draft deletion.
        """
        deleted = 0
        for attempt_path in self._staging_root.glob("attempt-*/attempt.json"):
            try:
                attempt = read_json_with_backup(attempt_path, _validate_attempt)
            except (OSError, ValueError, TypeError):
                continue
            if attempt.draft_id == draft_id:
                shutil.rmtree(attempt_path.parent, ignore_errors=True)
                deleted += 1
        return deleted


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


class ExportIndex(StrictModel):
    schema_version: int = Field(default=1)
    export_ids: list[str] = Field(default_factory=list, alias="exportIds")


class ExportIdempotencyIndex(StrictModel):
    schema_version: int = Field(default=1)
    keys: dict[str, str] = Field(default_factory=dict)


def _normalize_export_payload(payload: object) -> object:
    """Normalize a persisted ExportRecord document for strict model parsing.

    ExportRecord embeds ExportSpec (dishIds UUIDs, language enum),
    ValidationReport (validatedAt datetime) and ErrorSummary; the shared
    normalizer does not know the export status enum or the spec's dish id
    list, so this export-specific pass handles those extra shapes.
    """
    if isinstance(payload, list):
        return [_normalize_export_payload(item) for item in payload]
    if not isinstance(payload, dict):
        return payload

    normalized: dict[object, object] = {}
    for key, value in payload.items():
        if key == "dishIds" and isinstance(value, list):
            normalized[key] = [UUID(item) for item in value]
            continue
        if key in _UUID_FIELD_NAMES and isinstance(value, str):
            normalized[key] = UUID(value)
            continue
        if key in _DATETIME_FIELD_NAMES and isinstance(value, str):
            normalized[key] = datetime.fromisoformat(value)
            continue
        parser = _ENUM_FIELD_PARSERS.get(key)
        if key == "status" and isinstance(value, str):
            parser = ExportStatus
        if parser is not None and isinstance(value, str):
            normalized[key] = parser(value)
            continue
        normalized[key] = _normalize_export_payload(value)
    return normalized


def _validate_export_payload(payload: object) -> ExportRecord:
    return ExportRecord.model_validate(_normalize_export_payload(payload))


class ExportRepository:
    """JSON directory + index persistence for export records.

    Each record lives at ``exports/<exportId>/record.json``; an index.json and
    an idempotency.json map keep the directory listable and replay-safe. The
    same Idempotency-Key always returns the same exportId (ruling R17-2).
    """

    def __init__(self, workspace: WorkspacePaths) -> None:
        self._workspace = workspace
        self._index_path = workspace.exports_dir / "index.json"
        self._idempotency_path = workspace.exports_dir / "idempotency.json"

    def add_or_get_by_idempotency_key(
        self,
        record: ExportRecord,
        *,
        idempotency_key: str,
    ) -> ExportRecord:
        idempotency_index = self._load_idempotency_index()
        mapped_export_id = idempotency_index.keys.get(idempotency_key)
        if mapped_export_id is not None:
            return self.get(UUID(mapped_export_id))

        record_path = self._record_path(record.export_id)
        if record_path.exists():
            raise IdempotencyConflictError(
                "export record already exists with a different idempotency key"
            )
        record_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            record_path, record.model_dump(by_alias=True, mode="json")
        )
        idempotency_index.keys[idempotency_key] = str(record.export_id)
        atomic_write_json(
            self._idempotency_path,
            idempotency_index.model_dump(by_alias=True, mode="json"),
        )
        self._write_index()
        return record

    def get(self, export_id: UUID) -> ExportRecord:
        record_path = self._record_path(export_id)
        if not record_path.exists():
            raise FileNotFoundError(f"export record not found: {export_id}")
        return read_json_with_backup(record_path, _validate_export_payload)

    def save(self, record: ExportRecord) -> ExportRecord:
        record_path = self._record_path(record.export_id)
        record_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            record_path, record.model_dump(by_alias=True, mode="json")
        )
        self._write_index()
        return record

    def list(self) -> list[ExportRecord]:
        index = self._load_or_rebuild_index()
        return [self.get(UUID(export_id)) for export_id in index.export_ids]

    def _record_path(self, export_id: UUID) -> Path:
        return self._workspace.exports_dir / str(export_id) / "record.json"

    def _load_or_rebuild_index(self) -> ExportIndex:
        try:
            return ExportIndex.model_validate(
                json.loads(self._index_path.read_text(encoding="utf-8"))
            )
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return self._write_index()

    def _load_idempotency_index(self) -> ExportIdempotencyIndex:
        try:
            return read_json_with_backup(
                self._idempotency_path,
                ExportIdempotencyIndex.model_validate,
            )
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return ExportIdempotencyIndex()

    def _write_index(self) -> ExportIndex:
        export_ids = sorted(
            child.name
            for child in self._workspace.exports_dir.iterdir()
            if child.is_dir() and (child / "record.json").exists()
        )
        index = ExportIndex(exportIds=export_ids)
        atomic_write_json(
            self._index_path, index.model_dump(by_alias=True, mode="json")
        )
        return index
