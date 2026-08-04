"""Ask Gus generation application service: NDJSON streaming and cancellation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from pelican_town_specials.domain.common import DraftMode
from pelican_town_specials.domain.draft import (
    DraftRecord,
    DraftStatus,
    GenerationAttemptKind,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.blueprint import run_blueprint_preview
from pelican_town_specials.generation.events import GenerationEvent
from pelican_town_specials.generation.orchestrator import (
    GenerationCommand,
    GenerationOrchestrator,
)
from pelican_town_specials.persistence.repositories import DraftRepository


class GenerationService:
    def __init__(
        self,
        *,
        orchestrator: GenerationOrchestrator,
        draft_repository: DraftRepository,
    ) -> None:
        self._orchestrator = orchestrator
        self._drafts = draft_repository

    def begin_generation(self, draft_id: UUID) -> AsyncIterator[str]:
        """Validate the draft and start a generation attempt.

        Returns an iterator over NDJSON lines. AppError (404 draft missing,
        409 illegal state or busy) is raised before the stream begins so the
        route can return a structured HTTP error instead of a broken stream.
        """
        kind = self._resolve_kind(draft_id)
        command = GenerationCommand(
            draftId=draft_id, kind=kind, requestId=uuid4()
        )
        if kind is GenerationAttemptKind.BLUEPRINT_PREVIEW:
            events = run_blueprint_preview(self._orchestrator, command)
        else:
            events = self._orchestrator.run(command)
        return _ndjson_lines(events)

    def cancel(self, draft_id: UUID) -> bool:
        """Request cancellation of the draft's active attempt, if any."""
        draft = self._get_draft(draft_id)
        attempt_id = draft.active_attempt_id
        if attempt_id is None:
            return False
        return self._orchestrator.cancel(attempt_id)

    def _resolve_kind(self, draft_id: UUID) -> GenerationAttemptKind:
        draft = self._get_draft(draft_id)
        if draft.mode is DraftMode.BLUEPRINT:
            if draft.status in (DraftStatus.DRAFT, DraftStatus.READY):
                return GenerationAttemptKind.INITIAL
            if draft.status is DraftStatus.STALE_PREVIEW:
                return GenerationAttemptKind.BLUEPRINT_PREVIEW
            raise _illegal_state_error(draft)
        if draft.status in (DraftStatus.DRAFT, DraftStatus.READY):
            return GenerationAttemptKind.INITIAL
        if draft.status is DraftStatus.REVIEWABLE:
            return GenerationAttemptKind.FULL_REGENERATE
        raise _illegal_state_error(draft)

    def _get_draft(self, draft_id: UUID) -> DraftRecord:
        try:
            return self._drafts.get(draft_id)
        except (FileNotFoundError, OSError) as exc:
            raise _draft_not_found_error() from exc


async def _ndjson_lines(
    events: AsyncIterator[GenerationEvent],
) -> AsyncIterator[str]:
    async for event in events:
        yield event.to_ndjson()


def _draft_not_found_error() -> AppError:
    return AppError(
        code="PTS_DRAFT_NOT_FOUND",
        message="草稿不存在或已删除。",
        http_status=404,
        details={},
        retryable=False,
    )


def _illegal_state_error(draft: DraftRecord) -> AppError:
    return AppError(
        code="PTS_STATE_ILLEGAL_TRANSITION",
        message="草稿当前状态不允许生成。",
        http_status=409,
        details={"currentState": draft.status.value},
        retryable=False,
    )
