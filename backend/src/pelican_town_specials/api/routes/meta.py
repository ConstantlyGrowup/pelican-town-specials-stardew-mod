"""Curated dish category and tag option endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from pelican_town_specials.api.dependencies import meta_service
from pelican_town_specials.application.common import Page
from pelican_town_specials.application.meta import MetaOption

router = APIRouter()


@router.get(
    "/meta/categories",
    response_model=Page[MetaOption],
    response_model_by_alias=True,
)
def list_categories(
    request: Request,
    query: Annotated[str, Query(max_length=40)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[MetaOption]:
    return meta_service(request).list_categories(
        query=query,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/meta/tags",
    response_model=Page[MetaOption],
    response_model_by_alias=True,
)
def list_tags(
    request: Request,
    query: Annotated[str, Query(max_length=40)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[MetaOption]:
    return meta_service(request).list_tags(
        query=query,
        limit=limit,
        offset=offset,
    )
