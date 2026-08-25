from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from pelican_town_specials.domain.common import StrictModel

from .atomic import atomic_write_json, read_json_with_backup


class WorkspaceRecord(StrictModel):
    schema_version: int = Field(default=1)
    author_name: str = Field(min_length=9, max_length=9)


class WorkspaceBootstrap(StrictModel):
    schema_version: int = Field(default=1)
    workspace_path: str = Field(min_length=1)


def _today_author_name(today: date | None) -> str:
    current_date = today or datetime.now().astimezone().date()
    return f"D{current_date.strftime('%Y%m%d')}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_file_manifest(root: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for file_path in root.rglob("*"):
        if file_path.is_file():
            manifest[file_path.relative_to(root).as_posix()] = _file_sha256(file_path)
    return manifest


def _copy_workspace_contents(source_root: Path, destination_root: Path) -> None:
    for source_path in source_root.rglob("*"):
        relative_path = source_path.relative_to(source_root)
        destination_path = destination_root / relative_path
        if source_path.is_dir():
            destination_path.mkdir(parents=True, exist_ok=True)
            continue
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    app_state_dir: Path
    drafts_dir: Path
    cookbook_dir: Path
    assets_dir: Path
    canonical_dir: Path
    canonical_assets_dir: Path
    canonical_registry_path: Path
    exports_dir: Path
    staging_dir: Path
    trash_dir: Path
    workspace_record_path: Path
    bootstrap_path: Path
    author_name: str

    @classmethod
    def create(cls, root: Path, *, today: date | None = None) -> WorkspacePaths:
        resolved_root = root.resolve()
        app_state_dir = resolved_root / "app-state"
        drafts_dir = resolved_root / "drafts"
        cookbook_dir = resolved_root / "cookbook"
        assets_dir = resolved_root / "assets"
        canonical_dir = resolved_root / "canonical"
        canonical_assets_dir = canonical_dir / "assets"
        canonical_registry_path = canonical_dir / "registry.sqlite3"
        exports_dir = resolved_root / "exports"
        staging_dir = resolved_root / "staging"
        trash_dir = resolved_root / "trash"

        for directory in (
            app_state_dir,
            drafts_dir,
            cookbook_dir,
            assets_dir,
            canonical_dir,
            canonical_assets_dir,
            exports_dir,
            staging_dir,
            trash_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        workspace_record_path = app_state_dir / "workspace.json"
        if workspace_record_path.exists():
            workspace_record = read_json_with_backup(
                workspace_record_path,
                WorkspaceRecord.model_validate,
            )
        else:
            workspace_record = WorkspaceRecord(author_name=_today_author_name(today))
            atomic_write_json(
                workspace_record_path,
                workspace_record.model_dump(by_alias=True),
            )

        bootstrap_path = app_state_dir / "bootstrap.json"
        bootstrap = WorkspaceBootstrap(workspace_path=str(resolved_root))
        atomic_write_json(bootstrap_path, bootstrap.model_dump(by_alias=True))

        return cls(
            root=resolved_root,
            app_state_dir=app_state_dir,
            drafts_dir=drafts_dir,
            cookbook_dir=cookbook_dir,
            assets_dir=assets_dir,
            canonical_dir=canonical_dir,
            canonical_assets_dir=canonical_assets_dir,
            canonical_registry_path=canonical_registry_path,
            exports_dir=exports_dir,
            staging_dir=staging_dir,
            trash_dir=trash_dir,
            workspace_record_path=workspace_record_path,
            bootstrap_path=bootstrap_path,
            author_name=workspace_record.author_name,
        )


def migrate_workspace(
    source_root: Path,
    target_root: Path,
    *,
    today: date | None = None,
) -> WorkspacePaths:
    source_paths = WorkspacePaths.create(source_root, today=today)
    resolved_target = target_root.resolve()
    stage_root = resolved_target / "staging" / f"migration-{uuid4().hex}"
    stage_root.mkdir(parents=True, exist_ok=True)

    try:
        _copy_workspace_contents(source_paths.root, stage_root)
        source_manifest = _workspace_file_manifest(source_paths.root)
        staged_manifest = _workspace_file_manifest(stage_root)
        if len(source_manifest) != len(staged_manifest):
            raise ValueError("workspace migration file count mismatch")
        if source_manifest != staged_manifest:
            raise ValueError("workspace migration hash mismatch")

        _copy_workspace_contents(stage_root, resolved_target)
        migrated_paths = WorkspacePaths.create(resolved_target, today=today)
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)

    return migrated_paths
