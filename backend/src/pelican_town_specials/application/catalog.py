"""Read-only vanilla ingredient catalog search use case."""

from __future__ import annotations

from pydantic import Field

from pelican_town_specials.catalog.models import CatalogItem
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.common import StrictModel
from pelican_town_specials.domain.errors import AppError


class IngredientCatalogItemView(StrictModel):
    item_id: str = Field(alias="itemId", min_length=1, max_length=80)
    display_name_en: str = Field(alias="displayNameEn", min_length=1, max_length=80)
    display_name_zh: str = Field(alias="displayNameZh", min_length=1, max_length=80)

    @classmethod
    def from_catalog_item(cls, item: CatalogItem) -> IngredientCatalogItemView:
        return cls.model_validate(
            {
                "itemId": item.item_id,
                "displayNameEn": item.display_name_en,
                "displayNameZh": item.display_name_zh,
            }
        )


class IngredientCatalogSearchResult(StrictModel):
    catalog_version: str = Field(alias="catalogVersion", min_length=1)
    items: list[IngredientCatalogItemView]
    total: int = Field(ge=0)


class CatalogService:
    def __init__(self, catalog: VanillaCatalog) -> None:
        self._catalog = catalog

    def search_ingredients(
        self,
        query: str,
        limit: int,
        offset: int = 0,
    ) -> IngredientCatalogSearchResult:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 100
        ):
            raise self._limit_invalid_error()
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise self._offset_invalid_error()

        normalized = query.strip()
        if normalized:
            matches = self._catalog.search_ingredients(normalized, limit=100)
            total = len(matches)
            page = list(matches[offset : offset + limit])
        else:
            ingredients = self._catalog.ingredients
            total = len(ingredients)
            page = list(ingredients[offset : offset + limit])

        return IngredientCatalogSearchResult(
            catalogVersion=self._catalog.version,
            items=[IngredientCatalogItemView.from_catalog_item(item) for item in page],
            total=total,
        )

    @staticmethod
    def _limit_invalid_error() -> AppError:
        return AppError(
            code="PTS_INPUT_CATALOG_LIMIT_INVALID",
            message="食材搜索 limit 必须在 1 到 100 之间。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _offset_invalid_error() -> AppError:
        return AppError(
            code="PTS_INPUT_CATALOG_OFFSET_INVALID",
            message="食材浏览 offset 必须是非负整数。",
            http_status=422,
            details={},
            retryable=False,
        )
