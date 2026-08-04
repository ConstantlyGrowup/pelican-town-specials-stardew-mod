"""Task 13 Ask Gus generation streaming and cancellation endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from pelican_town_specials.api.dependencies import generation_service
from pelican_town_specials.application.generation import GenerationService

router = APIRouter()


@router.post("/drafts/{draft_id}/generate")
def generate_draft(draft_id: UUID, request: Request) -> StreamingResponse:
    """Start Ask Gus generation and stream NDJSON GenerationEvent lines."""
    stream = _service(request).begin_generation(draft_id)
    return StreamingResponse(stream, media_type="application/x-ndjson")


@router.post("/drafts/{draft_id}/cancel", status_code=202)
def cancel_generation(draft_id: UUID, request: Request) -> Response:
    """Cancel the draft's active generation attempt, if any."""
    _service(request).cancel(draft_id)
    return Response(status_code=202)


def _service(request: Request) -> GenerationService:
    return generation_service(request)
