"""Export use cases: validate, synchronously compile, download and open folder.

The sync state machine follows design 14.7 / 10.1: VALIDATING -> BUILDING ->
SUCCEEDED, with any failure landing on FAILED (validation report preserved,
artifactAssetId unset). Downloads only read the registered EXPORT_ZIP asset,
so a staging ZIP can never be downloaded.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.assets import AssetKind, MediaType
from pelican_town_specials.domain.common import utc_now
from pelican_town_specials.domain.errors import AppError, ErrorSummary
from pelican_town_specials.domain.export import (
    ExportRecord,
    ExportRecordView,
    ExportSpec,
    ExportStatus,
)
from pelican_town_specials.domain.validation import ValidationReport
from pelican_town_specials.mod_compiler.compiler import (
    ContentPatcherCompiler,
    ModCompileError,
)
from pelican_town_specials.mod_compiler.ids import build_mod_id
from pelican_town_specials.mod_compiler.templates import (
    CONTENT_PATCHER_FORMAT,
    MINIMUM_GAME_VERSION,
)
from pelican_town_specials.mod_compiler.validator import (
    ExportValidationError,
    validate_export,
)
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    AssetNotFoundError,
    FileAssetStore,
)
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    ExportRepository,
    IdempotencyConflictError,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths

EXPORT_COMPILER_VERSION = "task16-export-compiler-v1"
_EXPORT_VALIDATOR_VERSION = "task16-export-validator-v1"


class ExportService:
    def __init__(
        self,
        *,
        export_repository: ExportRepository,
        archive_repository: ArchiveRepository,
        asset_store: FileAssetStore,
        catalog: VanillaCatalog,
        compiler: ContentPatcherCompiler,
        workspace: WorkspacePaths,
        open_folder: Callable[[Path], None] | None = None,
    ) -> None:
        self._exports = export_repository
        self._archives = archive_repository
        self._assets = asset_store
        self._catalog = catalog
        self._compiler = compiler
        self._workspace = workspace
        self._open_folder = open_folder

    def validate(self, spec: ExportSpec) -> ValidationReport:
        dishes = self._resolve_dishes(spec.dish_ids)
        return validate_export(spec, dishes, self._catalog)

    def create_export(
        self,
        spec: ExportSpec,
        *,
        idempotency_key: str,
    ) -> ExportRecord:
        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise self._idempotency_key_required_error()

        now = utc_now()
        export_id = uuid4()
        initial = self._new_record(
            export_id=export_id,
            spec=spec,
            status=ExportStatus.VALIDATING,
            validation=self._empty_report(now),
            dish_content_hashes={},
            now=now,
        )
        try:
            record = self._exports.add_or_get_by_idempotency_key(
                initial, idempotency_key=normalized_key
            )
        except IdempotencyConflictError as exc:
            raise self._idempotency_conflict_error() from exc
        if record.export_id != export_id:
            # Idempotent replay: this key already produced an export.
            return record

        dishes = self._resolve_dishes(spec.dish_ids)
        dish_content_hashes = {
            str(dish.dish_id): dish.content_hash for dish in dishes
        }
        validating = self._exports.save(
            initial.model_copy(update={"dish_content_hashes": dish_content_hashes})
        )

        report = validate_export(spec, dishes, self._catalog)
        if not report.valid:
            return self._fail_record(
                validating,
                report,
                error_code="PTS_EXPORT_VALIDATION_FAILED",
                message="导出未通过校验，请检查问题后重试。",
            )

        building = self._exports.save(
            validating.model_copy(
                update={"status": ExportStatus.BUILDING, "validation": report}
            )
        )
        try:
            zip_bytes = self._compile(spec, dishes, export_id)
        except (ExportValidationError, ModCompileError, ValueError) as exc:
            return self._fail_record(
                building,
                report,
                error_code="PTS_EXPORT_COMPILE_FAILED",
                message=f"内容包编译失败：{exc}",
            )

        asset_ref = self._assets.put(
            zip_bytes,
            AssetMetadata(
                kind=AssetKind.EXPORT_ZIP,
                mediaType=MediaType.ZIP,
                fileExtension=".zip",
            ),
        )
        return self._exports.save(
            building.model_copy(
                update={
                    "status": ExportStatus.SUCCEEDED,
                    "artifact_asset_id": asset_ref.asset_id,
                    "finished_at": utc_now(),
                }
            )
        )

    def get_export(self, export_id: UUID) -> ExportRecordView:
        record = self._get_record(export_id)
        return ExportRecordView.from_record(record)

    def download_export(self, export_id: UUID) -> BinaryIO:
        record = self._get_record(export_id)
        if record.artifact_asset_id is None:
            raise self._export_not_ready_error()
        try:
            return self._assets.open(record.artifact_asset_id)
        except (AssetNotFoundError, ValueError) as exc:
            raise self._export_not_ready_error() from exc

    def open_export_folder(self, export_id: UUID) -> None:
        record = self._get_record(export_id)
        exports_root = self._workspace.exports_dir.resolve()
        target = (exports_root / str(record.export_id)).resolve()
        if not target.is_relative_to(exports_root):
            raise self._open_folder_error()
        if self._open_folder is None:
            raise self._open_folder_error()
        self._open_folder(target)

    def _compile(self, spec: ExportSpec, dishes: list[ArchivedDish], export_id: UUID) -> bytes:
        staging = self._workspace.staging_dir / f"export-{export_id}"
        staging.mkdir(parents=True, exist_ok=True)
        artifact = self._compiler.compile(spec, dishes, staging)
        return artifact.zip_path.read_bytes()

    def _resolve_dishes(self, dish_ids: list[UUID]) -> list[ArchivedDish]:
        by_id = {dish.dish_id: dish for dish in self._archives.list_active()}
        return [by_id[dish_id] for dish_id in dish_ids if dish_id in by_id]

    def _new_record(
        self,
        *,
        export_id: UUID,
        spec: ExportSpec,
        status: ExportStatus,
        validation: ValidationReport,
        dish_content_hashes: dict[str, str],
        now,
    ) -> ExportRecord:
        return ExportRecord(
            schema_version=1,
            exportId=export_id,
            spec=spec,
            author_name=self._workspace.author_name,
            uniqueId=build_mod_id(
                author_name=self._workspace.author_name,
                pack_slug=spec.pack_slug,
            ),
            status=status,
            dishContentHashes=dish_content_hashes,
            compilerVersion=EXPORT_COMPILER_VERSION,
            gameVersion=MINIMUM_GAME_VERSION,
            contentPatcherFormat=CONTENT_PATCHER_FORMAT,
            validation=validation,
            artifactAssetId=None,
            createdAt=now,
            finishedAt=None,
            error=None,
        )

    @staticmethod
    def _empty_report(now) -> ValidationReport:
        return ValidationReport(
            valid=True,
            issues=[],
            validated_at=now,
            validator_version=_EXPORT_VALIDATOR_VERSION,
        )

    def _fail_record(
        self,
        record: ExportRecord,
        report: ValidationReport,
        *,
        error_code: str,
        message: str,
    ) -> ExportRecord:
        return self._exports.save(
            record.model_copy(
                update={
                    "status": ExportStatus.FAILED,
                    "validation": report,
                    "error": ErrorSummary(
                        code=error_code,
                        message=message,
                        retryable=False,
                        request_id=uuid4(),
                        occurred_at=utc_now(),
                        stage=None,
                    ),
                    "finished_at": utc_now(),
                }
            )
        )

    def _get_record(self, export_id: UUID) -> ExportRecord:
        try:
            return self._exports.get(export_id)
        except (FileNotFoundError, OSError) as exc:
            raise self._export_not_found_error() from exc

    @staticmethod
    def _idempotency_key_required_error() -> AppError:
        return AppError(
            code="PTS_INPUT_IDEMPOTENCY_KEY_REQUIRED",
            message="export 操作需要 Idempotency-Key 请求头。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _idempotency_conflict_error() -> AppError:
        return AppError(
            code="PTS_IDEMPOTENCY_CONFLICT",
            message="该 Idempotency-Key 已关联其它导出。",
            http_status=409,
            details={},
            retryable=False,
        )

    @staticmethod
    def _export_not_found_error() -> AppError:
        return AppError(
            code="PTS_EXPORT_NOT_FOUND",
            message="导出记录不存在。",
            http_status=404,
            details={},
            retryable=False,
        )

    @staticmethod
    def _export_not_ready_error() -> AppError:
        return AppError(
            code="PTS_EXPORT_NOT_READY",
            message="导出尚未成功，无法下载。",
            http_status=409,
            details={},
            retryable=False,
        )

    @staticmethod
    def _open_folder_error() -> AppError:
        return AppError(
            code="PTS_EXPORT_OPEN_FOLDER_FAILED",
            message="无法打开导出文件夹。",
            http_status=500,
            details={},
            retryable=True,
        )
