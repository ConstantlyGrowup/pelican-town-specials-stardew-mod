"""Task 13 Ask Gus generation streaming and cancellation endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import Field, field_validator

from pelican_town_specials.api.dependencies import generation_service
from pelican_town_specials.application.generation import GenerationService
from pelican_town_specials.domain.common import StrictModel
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


class RegenerationInstructionsRequest(StrictModel):
    """Optional body of the full-regeneration request (M13 Task 59).

    ``regenerationInstructions`` is the user's free-text requirement for the
    next complete regeneration round. It is capped at 500 characters after
    trimming and never replaces the draft's original ``contextText``; an
    empty body (or one with only whitespace) means "no instruction", keeping
    historical clients' restart behavior unchanged.
    """

    regeneration_instructions: str | None = Field(
        default=None,
        alias="regenerationInstructions",
        max_length=500,
    )

    @field_validator("regeneration_instructions", mode="before")
    @classmethod
    def _coerce_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            # pydantic converts ValueError raised in validators into a request
            # ValidationError (422); a bare TypeError would escape as a 500.
            raise ValueError(  # noqa: TRY004 - pydantic contract requires ValueError
                "regenerationInstructions must be a string"
            )
        # Trim first, then enforce the 500-character budget on the trimmed
        # value; whitespace-only input counts as "no instruction".
        stripped = value.strip()
        return stripped or None

    @classmethod
    def instructions_of(
        cls,
        body: RegenerationInstructionsRequest | None,
    ) -> str | None:
        if body is None or body.regeneration_instructions is None:
            return None
        stripped = body.regeneration_instructions.strip()
        return stripped or None


@router.post("/drafts/{draft_id}/generate")
def generate_draft(
    draft_id: UUID,
    request: Request,
    restart: bool = Query(default=False),
    body: RegenerationInstructionsRequest | None = None,
) -> StreamingResponse:
    """Start Ask Gus generation and stream NDJSON GenerationEvent lines.

    The optional JSON body carries the user's regeneration instruction for an
    explicit full regeneration (M13 Task 59); an absent or empty body keeps
    the historical behavior. The instruction is trimmed, capped at 500
    characters, and never written into the draft's original contextText.
    """
    stream = _service(request).begin_generation(
        draft_id,
        restart=restart,
        regeneration_instructions=RegenerationInstructionsRequest.instructions_of(
            body
        ),
    )
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
