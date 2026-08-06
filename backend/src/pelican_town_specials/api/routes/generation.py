"""Task 13 Ask Gus generation streaming and cancellation endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from pelican_town_specials.api.dependencies import generation_service
from pelican_town_specials.application.generation import GenerationService

if TYPE_CHECKING:
    from starlette.types import Send

router = APIRouter()


class _ClosingStreamingResponse(StreamingResponse):
    """StreamingResponse that always closes the body iterator.

    Starlette 1.3 (ASGI spec >= 2.4) raises ``ClientDisconnect`` from
    ``stream_response`` without closing the body iterator when the client goes
    away. The generation slot lives in the body iterator's wrapper, so an
    unclosed iterator leaks the slot and every later generation request fails
    with PTS_GEN_BUSY. Closing here makes the disconnect cleanup deterministic
    (rollback + slot release) instead of relying on generator GC.
    """

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            aclose = getattr(self.body_iterator, "aclose", None)
            if aclose is not None:
                await aclose()


@router.post("/drafts/{draft_id}/generate")
def generate_draft(draft_id: UUID, request: Request) -> StreamingResponse:
    """Start Ask Gus generation and stream NDJSON GenerationEvent lines."""
    stream = _service(request).begin_generation(draft_id)
    return _ClosingStreamingResponse(stream, media_type="application/x-ndjson")


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
