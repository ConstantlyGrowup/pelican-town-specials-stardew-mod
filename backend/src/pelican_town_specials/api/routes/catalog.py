"""Read-only vanilla ingredient catalog search endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from pelican_town_specials.api.dependencies import catalog_service
from pelican_town_specials.application.catalog import IngredientCatalogSearchResult

router = APIRouter()


@router.get(
    "/catalog/ingredients",
    response_model=IngredientCatalogSearchResult,
    response_model_by_alias=True,
)
def search_ingredients(
    request: Request,
    query: Annotated[str, Query(max_length=80)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IngredientCatalogSearchResult:
    return catalog_service(request).search_ingredients(query, limit, offset)
