"""Read-only Cookbook query and tombstone delete endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response

from pelican_town_specials.api.dependencies import cookbook_service
from pelican_town_specials.application.common import Page
from pelican_town_specials.domain.archive import (
    CookbookDishDetail,
    CookbookDishSummary,
)

router = APIRouter()


@router.get(
    "/cookbook",
    response_model=Page[CookbookDishSummary],
    response_model_by_alias=True,
)
def list_cookbook(request: Request) -> Page[CookbookDishSummary]:
    return cookbook_service(request).list()


@router.get(
    "/cookbook/{dish_id}",
    response_model=CookbookDishDetail,
    response_model_by_alias=True,
)
def get_cookbook_dish(dish_id: UUID, request: Request) -> CookbookDishDetail:
    return cookbook_service(request).get_detail(dish_id)


@router.delete("/cookbook/{dish_id}", status_code=204)
async def delete_cookbook_dish(dish_id: UUID, request: Request) -> Response:
    await cookbook_service(request).delete(dish_id)
    return Response(status_code=204)
