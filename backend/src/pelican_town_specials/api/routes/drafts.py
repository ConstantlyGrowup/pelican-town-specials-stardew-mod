"""Draft lifecycle endpoints; generate/cancel streaming lives in generation.py."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response

from pelican_town_specials.api.dependencies import draft_service
from pelican_town_specials.application.common import Page
from pelican_town_specials.application.drafts import (
    DraftCreateRequest,
    DraftPatchRequest,
    DraftService,
    DraftSummary,
    DraftView,
)
from pelican_town_specials.domain.archive import CookbookDishDetail

router = APIRouter()


@router.post(
    "/drafts",
    status_code=201,
    response_model=DraftView,
    response_model_by_alias=True,
)
def create_draft(request: Request, body: DraftCreateRequest) -> DraftView:
    return DraftView.from_draft(_service(request).create_draft(body))


@router.get(
    "/drafts",
    response_model=Page[DraftSummary],
    response_model_by_alias=True,
)
def list_drafts(request: Request) -> Page[DraftSummary]:
    return _service(request).list_drafts()


@router.get(
    "/drafts/{draft_id}",
    response_model=DraftView,
    response_model_by_alias=True,
)
def get_draft(draft_id: UUID, request: Request) -> DraftView:
    return DraftView.from_draft(_service(request).get_draft(draft_id))


@router.patch(
    "/drafts/{draft_id}",
    response_model=DraftView,
    response_model_by_alias=True,
)
def patch_draft(
    draft_id: UUID,
    body: DraftPatchRequest,
    request: Request,
) -> DraftView:
    return DraftView.from_draft(_service(request).patch_draft(draft_id, body))


@router.post(
    "/drafts/{draft_id}/convert-to-blueprint",
    status_code=201,
    response_model=DraftView,
    response_model_by_alias=True,
)
def convert_to_blueprint(draft_id: UUID, request: Request) -> DraftView:
    return DraftView.from_draft(_service(request).convert_to_blueprint(draft_id))


@router.post(
    "/drafts/{draft_id}/archive",
    status_code=201,
    response_model=CookbookDishDetail,
    response_model_by_alias=True,
)
def archive_draft(
    draft_id: UUID,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CookbookDishDetail:
    archive = _service(request).archive_draft(draft_id, idempotency_key)
    return CookbookDishDetail.from_archived_dish(archive)


@router.post("/drafts/{draft_id}/discard", status_code=204)
def discard_draft(draft_id: UUID, request: Request) -> Response:
    _service(request).discard_draft(draft_id)
    return Response(status_code=204)


def _service(request: Request) -> DraftService:
    return draft_service(request)
