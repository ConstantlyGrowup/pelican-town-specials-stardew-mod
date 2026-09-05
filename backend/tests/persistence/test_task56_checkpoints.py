"""Task56 typed staging checkpoint persistence tests."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from backend.tests.domain.factories import ask_gus_reviewable_fixture

from pelican_town_specials.domain.common import (
    GenerationStage,
    Language,
    utc_now,
)
from pelican_town_specials.domain.draft import GenerationAttemptKind
from pelican_town_specials.generation.checkpoints import (
    CHECKPOINT_PROTOCOL_VERSION,
    GenerationCheckpoint,
)
from pelican_town_specials.persistence.repositories import GenerationAttemptRepository
from pelican_town_specials.persistence.workspace import WorkspacePaths


def _checkpoint() -> GenerationCheckpoint:
    draft = ask_gus_reviewable_fixture()
    return GenerationCheckpoint(
        attemptId=uuid4(),
        draftId=draft.draft_id,
        kind=GenerationAttemptKind.INITIAL,
        sourceRevision=draft.revision,
        inputFingerprint="a" * 64,
        language=Language.ZH_CN,
        catalogVersion="stardew-1.6.15-v1",
        protocolVersion=CHECKPOINT_PROTOCOL_VERSION,
        completedStages=[GenerationStage.INPUT_VALIDATION],
        candidate=draft,
        updatedAt=utc_now(),
    )


def test_generation_attempt_repository_round_trips_typed_checkpoint(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    repository = GenerationAttemptRepository(workspace)
    checkpoint = _checkpoint()

    repository.save_checkpoint(checkpoint)

    assert repository.get_checkpoint(checkpoint.attempt_id) == checkpoint
    payload = json.loads(
        (
            workspace.staging_dir
            / f"attempt-{checkpoint.attempt_id}"
            / "checkpoint.json"
        ).read_text(encoding="utf-8")
    )
    assert "apiKey" not in json.dumps(payload)
    assert "baseUrl" not in json.dumps(payload)


def test_generation_attempt_repository_treats_corrupt_checkpoint_as_cache_miss(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    repository = GenerationAttemptRepository(workspace)
    checkpoint = _checkpoint()
    repository.save_checkpoint(checkpoint)
    path = (
        workspace.staging_dir
        / f"attempt-{checkpoint.attempt_id}"
        / "checkpoint.json"
    )
    path.write_text("{not-json", encoding="utf-8")

    assert repository.get_checkpoint(checkpoint.attempt_id) is None
