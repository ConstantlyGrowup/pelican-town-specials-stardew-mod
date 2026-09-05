"""Draft lifecycle endpoints; generate/cancel streaming lives in generation.py."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response

from pelican_town_specials.api.dependencies import draft_service
from pelican_town_specials.application.drafts import (
    DraftCreateRequest,
    DraftPage,
    DraftPatchRequest,
    DraftService,
    DraftSortBy,
    DraftSortOrder,
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
    response_model=DraftPage,
    response_model_by_alias=True,
)
def list_drafts(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10,
    sort_by: Annotated[DraftSortBy, Query(alias="sortBy")] = DraftSortBy.UPDATED_AT,
    sort_order: Annotated[DraftSortOrder, Query(alias="sortOrder")] = (
        DraftSortOrder.DESC
    ),
) -> DraftPage:
    """List the visible drafts, one page at a time.

    Page metadata lets the homepage keep the full visible set consistent while
    the generation flag covers drafts on every page.
    """
    return _service(request).list_drafts(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


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
async def discard_draft(draft_id: UUID, request: Request) -> Response:
    """Permanently delete a draft.

    Removes the draft record directory, its generation attempts, and asset
    files exclusively owned by the draft. Assets shared with other drafts or
    archived dishes are preserved. ARCHIVED drafts are rejected. A running
    generation is cancelled and its slot reclaimed before deletion (Task 19.4).
    The request and response contract is unchanged.
    """
    await _service(request).discard_draft(draft_id)
    return Response(status_code=204)


def _service(request: Request) -> DraftService:
    return draft_service(request)
