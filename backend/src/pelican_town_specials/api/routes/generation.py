"""Task 13 Ask Gus generation streaming and cancellation endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from pelican_town_specials.api.dependencies import generation_service
from pelican_town_specials.application.generation import GenerationService
from pelican_town_specials.domain.draft import GenerationProgressPublic

if TYPE_CHECKING:
    from starlette.types import Send

router = APIRouter()


class _ClosingStreamingResponse(StreamingResponse):
    """StreamingResponse that always closes the body iterator.

    Starlette 1.3 (ASGI spec >= 2.4) raises ``ClientDisconnect`` from
    ``stream_response`` without closing the body iterator when the client goes
    away. Task 19.2: the generation runs in a server-owned background task, so
    closing the body iterator on disconnect only detaches this subscriber — it
    never cancels the generation. Closing here makes the response teardown
    deterministic instead of relying on generator GC.
    """

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            aclose = getattr(self.body_iterator, "aclose", None)
            if aclose is not None:
                await aclose()


@router.post("/drafts/{draft_id}/generate")
def generate_draft(
    draft_id: UUID,
    request: Request,
    restart: bool = Query(default=False),
) -> StreamingResponse:
    """Start Ask Gus generation and stream NDJSON GenerationEvent lines."""
    stream = _service(request).begin_generation(draft_id, restart=restart)
    return _ClosingStreamingResponse(stream, media_type="application/x-ndjson")


@router.get(
    "/drafts/{draft_id}/generation", response_model=GenerationProgressPublic
)
def generation_progress(
    draft_id: UUID, request: Request
) -> GenerationProgressPublic:
    """Read-only snapshot of the draft's current or last generation attempt.

    Lets the frontend rehydrate the generation state after a refresh, a page
    nav, or a closed-and-reopened tab without restarting the generation. Pure
    read: never writes state and never starts a provider call.
    """
    return _service(request).get_progress(draft_id)


@router.post("/drafts/{draft_id}/cancel", status_code=202)
async def cancel_generation(draft_id: UUID, request: Request) -> Response:
    """Cancel the draft's active generation attempt, if any.

    Awaits the server-side rollback so a 202 response guarantees the draft is
    no longer GENERATING and the generation slot is free for an immediate
    retry.
    """
    await _service(request).cancel(draft_id)
    return Response(status_code=202)


def _service(request: Request) -> GenerationService:
    return generation_service(request)
