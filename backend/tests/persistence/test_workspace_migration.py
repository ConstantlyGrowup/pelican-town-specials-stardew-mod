from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pelican_town_specials.persistence.workspace import (
    WorkspacePaths,
    migrate_workspace,
)


def test_workspace_paths_create_bootstraps_directories_author_name_and_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"

    paths = WorkspacePaths.create(root, today=date(2026, 8, 2))

    assert paths.root == root.resolve()
    assert paths.author_name == "D20260802"
    assert paths.app_state_dir.is_dir()
    assert paths.drafts_dir.is_dir()
    assert paths.cookbook_dir.is_dir()
    assert paths.assets_dir.is_dir()
    assert paths.canonical_dir.is_dir()
    assert paths.canonical_assets_dir.is_dir()
    assert paths.canonical_registry_path == paths.canonical_dir / "registry.sqlite3"
    assert not paths.canonical_registry_path.exists()
    assert paths.exports_dir.is_dir()
    assert paths.staging_dir.is_dir()
    assert paths.trash_dir.is_dir()
    assert paths.workspace_record_path.read_text(encoding="utf-8") == (
        '{\n  "authorName": "D20260802",\n  "schemaVersion": 1\n}\n'
    )
    assert json.loads(paths.bootstrap_path.read_text(encoding="utf-8")) == {
        "schemaVersion": 1,
        "workspacePath": str(root.resolve()),
    }


def test_workspace_paths_create_is_idempotent_and_keeps_original_author_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"

    first = WorkspacePaths.create(root, today=date(2026, 8, 2))
    second = WorkspacePaths.create(root, today=date(2026, 8, 3))

    assert first.author_name == "D20260802"
    assert second.author_name == "D20260802"
    assert second.workspace_record_path.read_text(encoding="utf-8") == (
        '{\n  "authorName": "D20260802",\n  "schemaVersion": 1\n}\n'
    )


def test_migrate_workspace_copies_and_verifies_source_then_keeps_old_workspace(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-workspace"
    source_paths = WorkspacePaths.create(source_root, today=date(2026, 8, 2))
    draft_path = source_paths.drafts_dir / "draft-1" / "record.json"
    draft_path.parent.mkdir(parents=True)
    draft_path.write_text('{\n  "value": "source"\n}\n', encoding="utf-8")
    registry_bytes = b"SQLite format 3\\x00canonical-registry-bytes"
    icon_bytes = b"owned-canonical-icon-bytes"
    source_paths.canonical_registry_path.write_bytes(registry_bytes)
    canonical_icon = source_paths.canonical_assets_dir / "dish-1" / "icon-16.png"
    canonical_icon.parent.mkdir(parents=True)
    canonical_icon.write_bytes(icon_bytes)

    target_root = tmp_path / "target-workspace"

    migrated = migrate_workspace(
        source_root,
        target_root,
        today=date(2026, 8, 3),
    )

    assert migrated.root == target_root.resolve()
    assert migrated.author_name == "D20260802"
    assert (target_root / "drafts" / "draft-1" / "record.json").read_text(
        encoding="utf-8"
    ) == '{\n  "value": "source"\n}\n'
    assert (source_root / "drafts" / "draft-1" / "record.json").read_text(
        encoding="utf-8"
    ) == '{\n  "value": "source"\n}\n'
    assert migrated.canonical_registry_path.read_bytes() == registry_bytes
    assert source_paths.canonical_registry_path.read_bytes() == registry_bytes
    assert (
        migrated.canonical_assets_dir / "dish-1" / "icon-16.png"
    ).read_bytes() == icon_bytes
    assert canonical_icon.read_bytes() == icon_bytes
    assert json.loads(migrated.bootstrap_path.read_text(encoding="utf-8")) == {
        "schemaVersion": 1,
        "workspacePath": str(target_root.resolve()),
    }


def test_migrate_workspace_rejects_hash_mismatch_before_bootstrap_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source-workspace"
    source_paths = WorkspacePaths.create(source_root, today=date(2026, 8, 2))
    asset_path = source_paths.assets_dir / "preview.png"
    asset_path.write_bytes(b"original-image")

    target_root = tmp_path / "target-workspace"

    original_copy2 = __import__("shutil").copy2

    def tampering_copy2(
        src: str | Path, dst: str | Path, *, follow_symlinks: bool = True
    ) -> str | Path:
        copied = original_copy2(src, dst, follow_symlinks=follow_symlinks)
        destination = Path(dst)
        if destination.name == "preview.png":
            destination.write_bytes(b"tampered-image")
        return copied

    monkeypatch.setattr(
        "pelican_town_specials.persistence.workspace.shutil.copy2",
        tampering_copy2,
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        migrate_workspace(source_root, target_root, today=date(2026, 8, 3))

    assert not (target_root / "app-state" / "bootstrap.json").exists()
