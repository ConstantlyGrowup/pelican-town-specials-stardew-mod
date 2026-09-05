"""Task 36 production-boundary verification for Canonical recall."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from backend.tests.domain.factories import make_draft as make_domain_draft
from backend.tests.generation.conftest import (
    FakeGateway,
    initial_command,
    put_original_image,
)

from pelican_town_specials.application.canonical_memory import (
    CanonicalRegistrationService,
)
from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetRef
from pelican_town_specials.domain.canonical import CanonicalIconKind
from pelican_town_specials.domain.common import DraftMode, Language
from pelican_town_specials.domain.dish import GenerationSource
from pelican_town_specials.domain.draft import DraftRecord, DraftStatus
from pelican_town_specials.domain.export import ExportSpec
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import GenerationOrchestrator
from pelican_town_specials.images import downscale_for_vision
from pelican_town_specials.images.vision_input import EDIT_MIN_PIXELS
from pelican_town_specials.mod_compiler.compiler import (
    ContentPatcherCompiler,
)
from pelican_town_specials.mod_compiler.ids import validate_internal_name
from pelican_town_specials.mod_compiler.validator import validate_export
from pelican_town_specials.persistence.asset_store import FileAssetStore
from pelican_town_specials.persistence.canonical_registry import (
    SQLiteCanonicalRegistry,
)
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
    GenerationAttemptRepository,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths
from pelican_town_specials.providers.contracts import (
    CanonicalMatchResponse,
    ImageOperation,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = (
    _REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


@dataclass
class ProductionRuntime:
    """All production owners rebuilt around one persistent workspace."""

    workspace: WorkspacePaths
    catalog: VanillaCatalog
    asset_store: FileAssetStore
    draft_repository: DraftRepository
    archive_repository: ArchiveRepository
    attempt_repository: GenerationAttemptRepository
    canonical_registry: SQLiteCanonicalRegistry
    canonical_registration: CanonicalRegistrationService
    draft_service: DraftService
    cookbook_service: CookbookService
    gateway: FakeGateway
    orchestrator: GenerationOrchestrator


def _runtime(root: Path, gateway: FakeGateway) -> ProductionRuntime:
    """Construct the real persistence/application graph used by the app."""

    workspace = WorkspacePaths.create(root)
    catalog = VanillaCatalog.from_json(_CATALOG_PATH)
    asset_store = FileAssetStore(workspace)
    draft_repository = DraftRepository(workspace)
    archive_repository = ArchiveRepository(workspace)
    attempt_repository = GenerationAttemptRepository(workspace)
    canonical_registry = SQLiteCanonicalRegistry(workspace)
    canonical_registration = CanonicalRegistrationService(
        registry=canonical_registry,
        archive_repository=archive_repository,
        draft_repository=draft_repository,
        asset_store=asset_store,
    )
    draft_service = DraftService(
        draft_repository=draft_repository,
        archive_repository=archive_repository,
        asset_store=asset_store,
        catalog=catalog,
        attempt_repository=attempt_repository,
        canonical_registration_service=canonical_registration,
    )
    cookbook_service = CookbookService(
        archive_repository,
        draft_service=draft_service,
    )
    orchestrator = GenerationOrchestrator(
        draft_repository=draft_repository,
        attempt_repository=attempt_repository,
        asset_store=asset_store,
        catalog=catalog,
        gateway_factory=lambda: gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
        canonical_repository=canonical_registry,
    )
    return ProductionRuntime(
        workspace=workspace,
        catalog=catalog,
        asset_store=asset_store,
        draft_repository=draft_repository,
        archive_repository=archive_repository,
        attempt_repository=attempt_repository,
        canonical_registry=canonical_registry,
        canonical_registration=canonical_registration,
        draft_service=draft_service,
        cookbook_service=cookbook_service,
        gateway=gateway,
        orchestrator=orchestrator,
    )


def _new_ready_draft(runtime: ProductionRuntime, *, color: str) -> DraftRecord:
    original = put_original_image(runtime, size=64, color=color)
    draft = make_domain_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    return runtime.draft_repository.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )


async def _generate_initial(
    runtime: ProductionRuntime, draft: DraftRecord
) -> DraftRecord:
    events = [
        event async for event in runtime.orchestrator.run(initial_command(draft))
    ]
    assert events[-1].type == "attempt.succeeded"
    return runtime.draft_repository.get(draft.draft_id)


def _read_asset(asset_store: FileAssetStore, asset_ref: AssetRef) -> bytes:
    with asset_store.open(asset_ref) as handle:
        return handle.read()


@pytest.mark.asyncio
async def test_production_canonical_memory_survives_restart_and_reuses_current_photo(
    tmp_path: Path,
) -> None:
    """Two formal archives enable a post-restart initial recall without copying photos."""

    root = tmp_path / "production-workspace"
    first = _runtime(root, FakeGateway())

    # The first two formal Ask Gus archives are registered through the same
    # DraftService -> CanonicalRegistrationService boundary as production.
    first_draft = await _generate_initial(
        first, _new_ready_draft(first, color="seagreen")
    )
    first_archive = first.draft_service.archive_draft(
        first_draft.draft_id, "task36-formal-archive-1"
    )
    second_draft = await _generate_initial(
        first, _new_ready_draft(first, color="navy")
    )
    second_archive = first.draft_service.archive_draft(
        second_draft.draft_id, "task36-formal-archive-2"
    )
    assert first.canonical_registry.count_valid() == 2

    first_canonical = first.canonical_registry.get_by_source_archive_id(
        first_archive.dish_id
    )
    second_canonical = first.canonical_registry.get_by_source_archive_id(
        second_archive.dish_id
    )
    assert first_canonical is not None
    assert second_canonical is not None
    assert first_canonical.canonical_id != second_canonical.canonical_id

    source_icon_before_restart = first.canonical_registry.load_owned_icon(
        first_canonical.canonical_id, CanonicalIconKind.SOURCE
    )
    icon_16_before_restart = first.canonical_registry.load_owned_icon(
        first_canonical.canonical_id, CanonicalIconKind.ICON_16
    )

    # Rebuild every owner around the same on-disk WorkspacePaths, then prove
    # that deleting the Cookbook source does not delete Registry-owned icons.
    restarted_gateway = FakeGateway()
    restarted = _runtime(root, restarted_gateway)
    assert restarted.canonical_registry.count_valid() == 2
    assert restarted.canonical_registry.get_valid(first_canonical.canonical_id) is not None
    assert (
        restarted.canonical_registry.load_owned_icon(
            first_canonical.canonical_id, CanonicalIconKind.SOURCE
        )
        == source_icon_before_restart
    )
    assert (
        restarted.canonical_registry.load_owned_icon(
            first_canonical.canonical_id, CanonicalIconKind.ICON_16
        )
        == icon_16_before_restart
    )

    await restarted.cookbook_service.delete(first_archive.dish_id)
    with pytest.raises(FileNotFoundError):
        restarted.archive_repository.get(first_archive.dish_id)
    assert restarted.canonical_registry.get_valid(first_canonical.canonical_id) is not None
    assert (
        restarted.canonical_registry.load_owned_icon(
            first_canonical.canonical_id, CanonicalIconKind.SOURCE
        )
        == source_icon_before_restart
    )

    # The third generation is an INITIAL Ask Gus attempt after restart. The
    # fake gateway supplies only the matcher response; all images still pass
    # through the production asset/orchestrator path. M13 Task 58 adds the
    # dual-image visual reuse gate before the preview edit.
    restarted_gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=first_canonical.canonical_id,
        confidence=0.97,
    )
    third_draft = await _generate_initial(
        restarted, _new_ready_draft(restarted, color="gold")
    )
    assert restarted_gateway.calls == ["analyze", "match", "compare_icon", "image"]
    assert third_draft.provenance.generation_source is GenerationSource.CANONICAL_REUSED
    assert third_draft.provenance.canonical_dish_id == first_canonical.canonical_id
    assert third_draft.provenance.recall_confidence == 0.97
    assert third_draft.presentation is not None
    assert first_canonical.presentation is not None
    assert (
        third_draft.presentation.display_name
        == first_canonical.presentation.display_name
    )
    assert third_draft.presentation.internal_name != first_canonical.presentation.internal_name
    assert third_draft.presentation.internal_name.startswith(
        f"{first_canonical.presentation.internal_name}_"
    )

    assert third_draft.visuals is not None
    assert third_draft.visuals.preview_asset_id is not None
    assert third_draft.visuals.icon_source_asset_id is not None
    assert third_draft.visuals.icon_16_asset_id is not None
    preview_request = restarted_gateway.image_requests[-1]
    assert preview_request.operation is ImageOperation.EDIT
    assert len(preview_request.source_images) == 2
    current_photo = _read_asset(
        restarted.asset_store,
        restarted.asset_store.stat(third_draft.source.original_image_asset_id),
    )
    current_photo_for_edit, _ = downscale_for_vision(
        current_photo,
        min_pixels=EDIT_MIN_PIXELS,
    )
    assert preview_request.source_images[0].data == current_photo_for_edit
    assert _read_asset(
        restarted.asset_store,
        restarted.asset_store.stat(third_draft.visuals.icon_source_asset_id),
    ) == source_icon_before_restart
    assert preview_request.source_images[1].data == source_icon_before_restart
    assert current_photo
    assert _read_asset(
        restarted.asset_store,
        restarted.asset_store.stat(third_draft.visuals.preview_asset_id),
    )

    # Archive the first HIT through the production DraftService boundary. The
    # follow-up registration records usage against the source Canonical row.
    third_archive = restarted.draft_service.archive_draft(
        third_draft.draft_id, "task36-hit-archive-1"
    )
    used_once = restarted.canonical_registry.get_valid(first_canonical.canonical_id)
    assert used_once is not None
    assert used_once.use_count == 1
    assert used_once.last_used_at is not None
    last_used_at_after_first_hit = used_once.last_used_at

    # Reconstruct every Registry/repository/service owner again after a HIT
    # archive. Usage metadata and both Registry-owned icon variants must come
    # from the persisted state, not from the deleted Cookbook/source assets.
    after_hit_gateway = FakeGateway()
    after_hit = _runtime(root, after_hit_gateway)
    persisted_after_restart = after_hit.canonical_registry.get_valid(
        first_canonical.canonical_id
    )
    assert persisted_after_restart is not None
    assert persisted_after_restart.use_count == 1
    assert persisted_after_restart.last_used_at == last_used_at_after_first_hit
    assert (
        after_hit.canonical_registry.load_owned_icon(
            first_canonical.canonical_id, CanonicalIconKind.SOURCE
        )
        == source_icon_before_restart
    )
    assert (
        after_hit.canonical_registry.load_owned_icon(
            first_canonical.canonical_id, CanonicalIconKind.ICON_16
        )
        == icon_16_before_restart
    )

    # A second HIT also goes through DraftService. Its internalName is derived
    # from the new draft id, so both archived export identities remain valid
    # and distinct even though they reuse one Canonical dish.
    after_hit_gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=first_canonical.canonical_id,
        confidence=0.96,
    )
    fourth_draft = await _generate_initial(
        after_hit, _new_ready_draft(after_hit, color="orchid")
    )
    fourth_archive = after_hit.draft_service.archive_draft(
        fourth_draft.draft_id, "task36-hit-archive-2"
    )
    archived_hit_names = {
        third_archive.presentation.internal_name,
        fourth_archive.presentation.internal_name,
    }
    assert len(archived_hit_names) == 2
    assert all(validate_internal_name(name) for name in archived_hit_names)

    # Exercise the existing export validator/compiler uniqueness boundary over
    # the actual immutable HIT archives, including their real icon assets.
    export_spec = ExportSpec(
        dishIds=[third_archive.dish_id, fourth_archive.dish_id],
        packDisplayName="Task 36 Canonical Hits",
        packSlug="Task36CanonicalHits",
        version="1.0.0",
        description="Canonical HIT archive verification pack.",
        language=Language.ZH_CN,
    )
    export_report = validate_export(
        export_spec,
        [third_archive, fourth_archive],
        after_hit.catalog,
    )
    assert export_report.valid is True
    compiler = ContentPatcherCompiler(
        asset_store=after_hit.asset_store,
        author_name=after_hit.workspace.author_name,
    )
    staging = after_hit.workspace.staging_dir / "task36-canonical-export"
    staging.mkdir(parents=True)
    artifact = compiler.compile(
        export_spec,
        [third_archive, fourth_archive],
        staging,
    )
    assert artifact.zip_path.is_file()
    assert artifact.zip_path.stat().st_size > 0
    final_canonical = after_hit.canonical_registry.get_valid(
        first_canonical.canonical_id
    )
    assert final_canonical is not None
    assert final_canonical.use_count == 2
