"""Task 9 Cookbook public-projection and tombstone delete use-case tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.domain.errors import AppError

from .conftest import AppServices, make_reviewable_draft

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
    return draft_service, CookbookService(services.archive_repository)


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


def test_cookbook_delete_moves_record_to_trash(services: AppServices) -> None:
    draft_service, cookbook = _cookbook(services)
    dish_id = _archived_dish_id(services, draft_service)

    cookbook.delete(dish_id)

    assert cookbook.list().total == 0
    trash_dir = services.workspace.trash_dir / "cookbook" / str(dish_id)
    assert (trash_dir / "record.json").exists()
    assert (trash_dir / "tombstone.json").exists()


def test_cookbook_detail_after_delete_is_not_found(services: AppServices) -> None:
    draft_service, cookbook = _cookbook(services)
    dish_id = _archived_dish_id(services, draft_service)
    cookbook.delete(dish_id)

    with pytest.raises(AppError) as excinfo:
        cookbook.get_detail(dish_id)
    assert excinfo.value.code == "PTS_COOKBOOK_NOT_FOUND"


def test_cookbook_repeat_delete_is_not_found(services: AppServices) -> None:
    draft_service, cookbook = _cookbook(services)
    dish_id = _archived_dish_id(services, draft_service)
    cookbook.delete(dish_id)

    with pytest.raises(AppError) as excinfo:
        cookbook.delete(dish_id)
    assert excinfo.value.code == "PTS_COOKBOOK_NOT_FOUND"


def test_cookbook_unknown_id_is_not_found(services: AppServices) -> None:
    _, cookbook = _cookbook(services)

    with pytest.raises(AppError) as excinfo:
        cookbook.get_detail(uuid4())
    assert excinfo.value.code == "PTS_COOKBOOK_NOT_FOUND"
