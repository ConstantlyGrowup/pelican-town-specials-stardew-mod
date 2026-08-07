"""Task 9 Cookbook public-projection and tombstone delete use-case tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from backend.tests.domain.factories import ask_gus_reviewable_fixture

from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.domain.assets import AssetKind
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.asset_store import AssetNotFoundError

from .conftest import AppServices, make_reviewable_draft, put_png

_PRIVATE_FIELDS = {
    "mode",
    "sourceDraftId",
    "gusComment",
    "internalProvenance",
    "visionModel",
    "textModel",
    "imageModel",
    "canonicalDishSignature",
    "promptVersions",
}


def _cookbook(services: AppServices) -> tuple[DraftService, CookbookService]:
    draft_service = DraftService(
        draft_repository=services.draft_repository,
        archive_repository=services.archive_repository,
        asset_store=services.asset_store,
        catalog=services.catalog,
        attempt_repository=services.attempt_repository,
    )
    return draft_service, CookbookService(
        services.archive_repository, draft_service=draft_service
    )


def _archived_dish_id(services: AppServices, draft_service: DraftService) -> object:
    reviewable = make_reviewable_draft(services)
    return draft_service.archive_draft(reviewable.draft_id, "archive-key").dish_id


def test_cookbook_list_returns_public_summaries(services: AppServices) -> None:
    draft_service, cookbook = _cookbook(services)
    _archived_dish_id(services, draft_service)

    page = cookbook.list()

    assert page.total == 1
    summary = page.items[0]
    serialized = summary.model_dump(by_alias=True)
    for private_field in _PRIVATE_FIELDS:
        assert private_field not in serialized
    assert summary.display_name
    assert summary.category_label


def test_cookbook_detail_hides_source_fields(services: AppServices) -> None:
    draft_service, cookbook = _cookbook(services)
    dish_id = _archived_dish_id(services, draft_service)

    detail = cookbook.get_detail(dish_id)

    serialized = detail.model_dump(by_alias=True)
    for private_field in _PRIVATE_FIELDS:
        assert private_field not in serialized
    assert detail.gameplay is not None
    assert detail.visuals is not None


async def test_cookbook_delete_moves_record_to_trash(services: AppServices) -> None:
    draft_service, cookbook = _cookbook(services)
    dish_id = _archived_dish_id(services, draft_service)

    await cookbook.delete(dish_id)

    assert cookbook.list().total == 0
    trash_dir = services.workspace.trash_dir / "cookbook" / str(dish_id)
    assert (trash_dir / "record.json").exists()
    assert (trash_dir / "tombstone.json").exists()


async def test_cookbook_detail_after_delete_is_not_found(
    services: AppServices,
) -> None:
    draft_service, cookbook = _cookbook(services)
    dish_id = _archived_dish_id(services, draft_service)
    await cookbook.delete(dish_id)

    with pytest.raises(AppError) as excinfo:
        cookbook.get_detail(dish_id)
    assert excinfo.value.code == "PTS_COOKBOOK_NOT_FOUND"


async def test_cookbook_repeat_delete_is_not_found(services: AppServices) -> None:
    draft_service, cookbook = _cookbook(services)
    dish_id = _archived_dish_id(services, draft_service)
    await cookbook.delete(dish_id)

    with pytest.raises(AppError) as excinfo:
        await cookbook.delete(dish_id)
    assert excinfo.value.code == "PTS_COOKBOOK_NOT_FOUND"


def test_cookbook_unknown_id_is_not_found(services: AppServices) -> None:
    _, cookbook = _cookbook(services)

    with pytest.raises(AppError) as excinfo:
        cookbook.get_detail(uuid4())
    assert excinfo.value.code == "PTS_COOKBOOK_NOT_FOUND"


async def test_cookbook_delete_cascades_source_draft(
    services: AppServices,
) -> None:
    """Deleting a dish tombstones it and removes its source draft (record,
    attempts, exclusively-owned assets) while preserving shared references."""
    original_ref = put_png(
        services.asset_store, kind=AssetKind.ORIGINAL_IMAGE, color="green"
    )
    preview_ref = put_png(
        services.asset_store, kind=AssetKind.PREVIEW, color="purple"
    )
    icon_ref = put_png(services.asset_store, kind=AssetKind.ICON_16, color="gold")
    draft = ask_gus_reviewable_fixture()
    source = draft.source.model_copy(
        update={"original_image_asset_id": original_ref.asset_id}
    )
    visuals = draft.visuals.model_copy(
        update={
            "preview_asset_id": preview_ref.asset_id,
            "icon_16_asset_id": icon_ref.asset_id,
        }
    )
    draft = draft.model_copy(update={"source": source, "visuals": visuals})
    services.draft_repository.save(draft, expected_revision=None)
    draft_service, cookbook = _cookbook(services)
    # A blueprint created from the source shares the original image; it must
    # survive the cascade while exclusively-owned visual assets are removed.
    blueprint = draft_service.convert_to_blueprint(draft.draft_id)
    assert blueprint.source.original_image_asset_id == original_ref.asset_id
    archive = draft_service.archive_draft(draft.draft_id, "cascade-key")
    dish_id = archive.dish_id

    await cookbook.delete(dish_id)

    with pytest.raises(AppError) as excinfo:
        draft_service.get_draft(draft.draft_id)
    assert excinfo.value.code == "PTS_DRAFT_NOT_FOUND"
    assert [item.draft_id for item in draft_service.list_drafts().items] == [
        blueprint.draft_id
    ]
    assert not (services.workspace.drafts_dir / str(draft.draft_id)).exists()
    assert services.asset_store.stat(original_ref.asset_id) is not None
    with pytest.raises(AssetNotFoundError):
        services.asset_store.stat(preview_ref.asset_id)
    with pytest.raises(AssetNotFoundError):
        services.asset_store.stat(icon_ref.asset_id)
