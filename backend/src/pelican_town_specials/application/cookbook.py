"""Safe Cookbook list, detail, and tombstone delete use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pelican_town_specials.domain.archive import (
    CookbookDishDetail,
    CookbookDishSummary,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.repositories import ArchiveRepository

from .common import Page

if TYPE_CHECKING:
    from pelican_town_specials.application.drafts import DraftService


class CookbookService:
    def __init__(
        self,
        repository: ArchiveRepository,
        *,
        draft_service: DraftService | None = None,
    ) -> None:
        self._repository = repository
        self._drafts = draft_service

    def list(self) -> Page[CookbookDishSummary]:
        archives = self._repository.list_active()
        items = [CookbookDishSummary.from_archived_dish(archive) for archive in archives]
        return Page(items=items, nextCursor=None, total=len(items))

    def get_detail(self, dish_id: UUID) -> CookbookDishDetail:
        try:
            archive = self._repository.get(dish_id)
        except (FileNotFoundError, OSError) as exc:
            raise self._not_found_error() from exc
        return CookbookDishDetail.from_archived_dish(archive)

    def delete(self, dish_id: UUID) -> None:
        try:
            self._repository.delete(dish_id)
        except (FileNotFoundError, OSError) as exc:
            raise self._not_found_error() from exc
        # Cascade: a tombstoned dish must not leave its source drafts lingering
        # on the homepage. Reuses DraftService's shared-asset protection.
        if self._drafts is not None:
            self._drafts.delete_archived_by_dish(dish_id)

    @staticmethod
    def _not_found_error() -> AppError:
        return AppError(
            code="PTS_COOKBOOK_NOT_FOUND",
            message="收集品不存在或已删除。",
            http_status=404,
            details={},
            retryable=False,
        )
