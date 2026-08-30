from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from backend.tests.domain.factories import (
    archived_dish_fixture,
    ask_gus_reviewable_fixture,
    initial_attempt_fixture,
)

from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
    GenerationAttemptRepository,
    IdempotencyConflictError,
    RevisionConflictError,
    TombstonedDishError,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths


def test_draft_repository_save_get_and_list_round_trip(tmp_path: Path) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = DraftRepository(workspace)
    draft = ask_gus_reviewable_fixture()

    saved = repository.save(draft, expected_revision=None)

    assert saved.revision == 1
    assert repository.get(saved.draft_id) == saved
    assert [item.draft_id for item in repository.list()] == [saved.draft_id]


def test_generation_attempt_repository_round_trips_trial_snapshot(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = GenerationAttemptRepository(workspace)
    attempt = initial_attempt_fixture().model_copy(
        update={"trial_used": True, "trial_remaining": 1}
    )

    repository.save(attempt)

    loaded = repository.get(attempt.attempt_id)
    assert loaded.trial_used is True
    assert loaded.trial_remaining == 1


def test_generation_attempt_repository_fills_trial_defaults_for_old_json(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = GenerationAttemptRepository(workspace)
    attempt = initial_attempt_fixture()
    repository.save(attempt)
    path = (
        workspace.staging_dir
        / f"attempt-{attempt.attempt_id}"
        / "attempt.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("trialUsed")
    payload.pop("trialRemaining")
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = repository.get(attempt.attempt_id)

    assert loaded.trial_used is False
    assert loaded.trial_remaining is None


def test_draft_repository_raises_on_expected_revision_conflict(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = DraftRepository(workspace)
    saved = repository.save(ask_gus_reviewable_fixture(), expected_revision=None)

    with pytest.raises(RevisionConflictError, match="expected revision"):
        repository.save(
            saved.model_copy(update={"updatedAt": saved.updated_at}),
            expected_revision=99,
        )

    assert repository.get(saved.draft_id).revision == 1


def test_draft_repository_recovers_from_valid_record_backup(tmp_path: Path) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = DraftRepository(workspace)
    draft = repository.save(ask_gus_reviewable_fixture(), expected_revision=None)
    updated = repository.save(
        draft.model_copy(update={"updatedAt": draft.updated_at}),
        expected_revision=1,
    )

    record_path = workspace.drafts_dir / str(updated.draft_id) / "record.json"
    record_path.write_text("{not-json", encoding="utf-8", newline="\n")

    recovered = repository.get(updated.draft_id)

    assert recovered.revision == 1


def test_draft_repository_rebuilds_missing_index_from_entities(tmp_path: Path) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = DraftRepository(workspace)
    first = repository.save(ask_gus_reviewable_fixture(), expected_revision=None)
    second = repository.save(ask_gus_reviewable_fixture(), expected_revision=None)

    (workspace.drafts_dir / "index.json").unlink()

    assert {item.draft_id for item in repository.list()} == {
        first.draft_id,
        second.draft_id,
    }
    assert (workspace.drafts_dir / "index.json").exists()


def test_archive_repository_add_is_immutable_and_idempotent_per_key(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = ArchiveRepository(workspace)
    archive = archived_dish_fixture()

    saved = repository.add_immutable(archive, idempotency_key="same-key")
    repeated = repository.add_immutable(archive, idempotency_key="same-key")

    assert saved == archive
    assert repeated == archive

    with pytest.raises(IdempotencyConflictError, match="different idempotency key"):
        repository.add_immutable(archive, idempotency_key="different-key")


def test_archive_repository_lookup_by_idempotency_key(tmp_path: Path) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = ArchiveRepository(workspace)
    archive = archived_dish_fixture()

    assert repository.get_by_idempotency_key("missing-key") is None

    repository.add_immutable(archive, idempotency_key="same-key")

    assert repository.get_by_idempotency_key("same-key") == archive


def test_archive_repository_delete_moves_record_to_trash_and_writes_tombstone(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = ArchiveRepository(workspace)
    archive = archived_dish_fixture()
    repository.add_immutable(archive, idempotency_key="archive-key")

    tombstone = repository.delete(archive.dish_id)

    assert tombstone.dish_id == archive.dish_id
    assert [item.dish_id for item in repository.list_active()] == []
    trash_dir = workspace.trash_dir / "cookbook" / str(archive.dish_id)
    assert (trash_dir / "record.json").exists()
    assert json.loads((trash_dir / "tombstone.json").read_text(encoding="utf-8")) == {
        "contentHash": archive.content_hash,
        "deletedAt": tombstone.deleted_at.isoformat().replace("+00:00", "Z"),
        "dishId": str(archive.dish_id),
    }


def test_archive_delete_tombstone_blocks_readd_and_repairs_failed_tombstone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace", today=date(2026, 8, 2))
    repository = ArchiveRepository(workspace)
    archive = archived_dish_fixture()
    repository.add_immutable(archive, idempotency_key="archive-key")
    import pelican_town_specials.persistence.repositories as module

    original = module.atomic_write_json

    def fail_tombstone(path: Path, payload: object) -> None:
        if path.name == "tombstone.json":
            raise OSError("injected tombstone failure")
        original(path, payload)

    monkeypatch.setattr(module, "atomic_write_json", fail_tombstone)
    with pytest.raises(OSError):
        repository.delete(archive.dish_id)
    monkeypatch.setattr(module, "atomic_write_json", original)
    with pytest.raises(TombstonedDishError):
        repository.add_immutable(archive, idempotency_key="new-key")
    assert not repository.list_active()
    assert (
        workspace.trash_dir / "cookbook" / str(archive.dish_id) / "tombstone.json"
    ).exists()
