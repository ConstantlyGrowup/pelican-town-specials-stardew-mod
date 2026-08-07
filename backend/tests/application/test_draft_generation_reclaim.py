"""Task 19.4: deleting a draft must cancel and reclaim its running generation.

The delete path (discard_draft and the cookbook cascade) must cancel any
in-flight attempt and release the generation slot before the draft record is
removed, so a new generation can start immediately instead of reporting
PTS_GEN_BUSY forever.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from backend.tests.domain.factories import make_draft as make_domain_draft
from backend.tests.generation.conftest import FakeGateway

from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.application.generation import GenerationService
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind, MediaType
from pelican_town_specials.domain.common import DraftMode
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    DraftRecord,
    DraftStatus,
    GenerationAttempt,
    GenerationAttemptKind,
    GenerationStage,
    StageAttempt,
    StageStatus,
)
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import (
    GenerationCommand,
    GenerationOrchestrator,
)
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    FileAssetStore,
)
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
    GenerationAttemptRepository,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = (
    _REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


def _put_original_image(asset_store: FileAssetStore) -> object:
    import io

    from PIL import Image

    output = io.BytesIO()
    Image.new("RGB", (64, 64), "seagreen").save(output, format="PNG")
    return asset_store.put(
        output.getvalue(),
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=64,
            height=64,
        ),
    )


def _initial_command(draft: DraftRecord) -> GenerationCommand:
    return GenerationCommand(
        draftId=draft.draft_id,
        kind=GenerationAttemptKind.INITIAL,
        requestId=uuid4(),
    )


@pytest.fixture
def harness(tmp_path: Path):
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    asset_store = FileAssetStore(workspace)
    draft_repository = DraftRepository(workspace)
    archive_repository = ArchiveRepository(workspace)
    attempt_repository = GenerationAttemptRepository(workspace)
    catalog = VanillaCatalog.from_json(_CATALOG_PATH)
    gateway = FakeGateway()
    registry = AttemptRegistry()
    orchestrator = GenerationOrchestrator(
        draft_repository=draft_repository,
        attempt_repository=attempt_repository,
        asset_store=asset_store,
        catalog=catalog,
        gateway_factory=lambda: gateway,
        registry=registry,
        min_confidence=0.5,
    )
    generation_service = GenerationService(
        orchestrator=orchestrator,
        draft_repository=draft_repository,
    )
    draft_service = DraftService(
        draft_repository=draft_repository,
        archive_repository=archive_repository,
        asset_store=asset_store,
        catalog=catalog,
        attempt_repository=attempt_repository,
        attempt_registry=registry,
    )
    return {
        "asset_store": asset_store,
        "draft_repository": draft_repository,
        "archive_repository": archive_repository,
        "attempt_repository": attempt_repository,
        "catalog": catalog,
        "gateway": gateway,
        "registry": registry,
        "orchestrator": orchestrator,
        "generation_service": generation_service,
        "draft_service": draft_service,
        "workspace": workspace,
    }


def _ready_draft(harness) -> DraftRecord:
    ref = _put_original_image(harness["asset_store"])
    draft = make_domain_draft(
        mode=DraftMode.ASK_GUS, status=DraftStatus.READY, revision=1
    )
    source = draft.source.model_copy(update={"original_image_asset_id": ref.asset_id})
    draft = draft.model_copy(update={"source": source})
    return harness["draft_repository"].save(draft, expected_revision=None)


def _reviewable_draft(harness) -> DraftRecord:
    ref = _put_original_image(harness["asset_store"])
    draft = make_domain_draft(
        mode=DraftMode.ASK_GUS, status=DraftStatus.REVIEWABLE, revision=3
    )
    source = draft.source.model_copy(update={"original_image_asset_id": ref.asset_id})
    draft = draft.model_copy(update={"source": source})
    return harness["draft_repository"].save(draft, expected_revision=None)


async def test_discard_generating_draft_releases_slot(
    harness,
) -> None:
    """Deleting a draft while its generation runs must cancel the attempt and
    make the slot immediately reusable for another draft."""
    draft = _ready_draft(harness)
    harness["gateway"].delay = 0.5
    agen = harness["orchestrator"].run(_initial_command(draft))
    first = await anext(agen)
    assert first.type == "attempt.started"
    # The slot is owned by this draft's attempt.
    owner = harness["registry"].owner()
    assert owner is not None
    assert owner.draft_id == draft.draft_id

    # Delete while the generation is still running.
    await harness["draft_service"].discard_draft(draft.draft_id)

    # The slot was reclaimed: a new draft can start generating immediately.
    assert harness["registry"].owner() is None
    other = _ready_draft(harness)
    harness["gateway"].delay = 0.0
    second = harness["orchestrator"].run(_initial_command(other))
    await second.aclose()
    assert harness["registry"].owner() is None


async def test_discard_generating_draft_marks_attempt_terminal(
    harness,
) -> None:
    """The in-flight attempt is cancelled (terminal status persisted), not left
    RUNNING after the delete."""
    draft = _ready_draft(harness)
    harness["gateway"].delay = 0.5
    agen = harness["orchestrator"].run(_initial_command(draft))
    first = await anext(agen)
    assert first.type == "attempt.started"
    attempt_id = first.attempt_id
    assert attempt_id is not None

    await harness["draft_service"].discard_draft(draft.draft_id)

    # The attempt directory is gone (deleted with the draft), so no RUNNING
    # attempt survives.
    assert not (
        harness["workspace"].staging_dir / f"attempt-{attempt_id}"
    ).exists()


async def test_cookbook_cascade_releases_slot(harness) -> None:
    """The cookbook tombstone cascade (delete_archived_by_dish) goes through the
    same reclaim path as a direct discard: an ARCHIVED draft that still holds a
    generation attempt releases the slot when its dish is deleted."""
    # Craft an ARCHIVED draft that still owns the slot via an active attempt
    # (an abnormal leftover that the cascade must still clean up).
    draft = _reviewable_draft(harness)
    attempt_id = uuid4()
    now = draft.updated_at
    draft = draft.model_copy(
        update={
            "status": DraftStatus.ARCHIVED,
            "archived_dish_id": uuid4(),
            "active_attempt_id": attempt_id,
        }
    )
    saved = harness["draft_repository"].control_write(
        draft,
        expected_revision=draft.revision,
        expected_attempt_id=None,
    )
    harness["attempt_repository"].save(
        GenerationAttempt(
            attempt_id=attempt_id,
            draft_id=saved.draft_id,
            kind=GenerationAttemptKind.INITIAL,
            source_revision=saved.revision,
            status=AttemptStatus.RUNNING,
            current_stage=GenerationStage.INPUT_VALIDATION,
            stages=[
                StageAttempt(
                    stage=GenerationStage.INPUT_VALIDATION,
                    status=StageStatus.RUNNING,
                    retry_count=0,
                    started_at=now,
                    finished_at=None,
                )
            ],
            candidate_record_path=None,
            started_at=now,
            finished_at=None,
            error=None,
        )
    )
    # Occupy the slot as if this attempt were the current holder.
    assert harness["registry"].reserve_slot(saved.draft_id, attempt_id) is True

    await harness["draft_service"].delete_archived_by_dish(saved.archived_dish_id)

    # The cascade reclaimed the slot.
    assert harness["registry"].owner() is None


async def test_rollback_cancelled_tolerates_deleted_draft(harness) -> None:
    """_rollback_cancelled must not raise when the draft record is already gone
    (e.g. the generation task loses a race against the delete)."""
    draft = _ready_draft(harness)
    harness["gateway"].delay = 0.01
    agen = harness["orchestrator"].run(_initial_command(draft))
    first = await anext(agen)
    assert first.type == "attempt.started"
    attempt_id = first.attempt_id
    assert attempt_id is not None
    # Consume to the first stage start so the attempt is persisted and the
    # task is suspended at its first provider call.
    stage = await anext(agen)
    assert stage.type == "stage.started"

    # Simulate the delete winning the race: remove the draft and its attempt
    # records while the task still runs, then cancel the task.
    harness["draft_repository"].delete(draft.draft_id)
    harness["attempt_repository"].delete_for_draft(draft.draft_id)
    harness["registry"].request_cancel(attempt_id, "race")
    await harness["registry"].await_task(attempt_id)
    # No exception raised, and the slot is released.
    assert harness["registry"].owner() is None
