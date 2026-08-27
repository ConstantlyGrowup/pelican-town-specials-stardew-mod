"""Ask Gus generation application service: NDJSON streaming and cancellation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from pelican_town_specials.domain.common import DraftMode
from pelican_town_specials.domain.draft import (
    DraftRecord,
    DraftStatus,
    GenerationAttemptKind,
    GenerationAttemptPublic,
    GenerationProgressPublic,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.domain.telemetry import RejectionReason, TelemetryEvent
from pelican_town_specials.generation.blueprint import run_blueprint_preview
from pelican_town_specials.generation.events import GenerationEvent
from pelican_town_specials.generation.orchestrator import (
    GenerationCommand,
    GenerationOrchestrator,
)
from pelican_town_specials.persistence.repositories import DraftRepository

from .telemetry import NoopTelemetryRecorder, TelemetryRecorder


class GenerationService:
    def __init__(
        self,
        *,
        orchestrator: GenerationOrchestrator,
        draft_repository: DraftRepository,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._drafts = draft_repository
        self._telemetry = (
            telemetry if telemetry is not None else NoopTelemetryRecorder()
        )

    def begin_generation(self, draft_id: UUID) -> AsyncIterator[str]:
        """Validate the draft and start a generation attempt.

        Returns an iterator over NDJSON lines. AppError (404 draft missing,
        409 illegal state or busy) is raised before the stream begins so the
        route can return a structured HTTP error instead of a broken stream.
        """
        try:
            kind = self._resolve_kind(draft_id)
        except AppError:
            # This boundary runs before an attempt exists.  Keep the public
            # error response unchanged while exposing only the frozen reason.
            self._record_telemetry(
                TelemetryEvent.generation_rejected(
                    reason=RejectionReason.VALIDATION
                )
            )
            raise
        command = GenerationCommand(
            draftId=draft_id, kind=kind, requestId=uuid4()
        )
        if kind is GenerationAttemptKind.BLUEPRINT_PREVIEW:
            events = run_blueprint_preview(self._orchestrator, command)
        else:
            events = self._orchestrator.run(command)
        return _ndjson_lines(events)

    async def cancel(self, draft_id: UUID) -> bool:
        """Request cancellation of the draft's active attempt, if any.

        Awaits the server-side rollback so the caller only proceeds once the
        draft is no longer GENERATING and the generation slot is released. If
        the attempt is persisted but no longer tracked in this process (the
        client disconnected, the stream was dropped, or the server restarted),
        the draft is rolled back directly so /cancel always clears the
        generating state and never leaves the slot busy.
        """
        draft = self._get_draft(draft_id)
        attempt_id = draft.active_attempt_id
        if attempt_id is None:
            return False
        tracked = self._orchestrator.cancel(attempt_id)
        if tracked:
            await self._orchestrator.await_cancelled(attempt_id)
            return True
        return self._orchestrator.recover_interrupted(draft_id)

    def recover_interrupted(self, draft_id: UUID) -> bool:
        """Roll a previously-generating draft back to a recoverable status.

        Used at startup to sweep drafts left in a generating state by a
        previous process crash or hard exit. Never resumes provider calls.
        """
        return self._orchestrator.recover_interrupted(draft_id)

    def get_progress(self, draft_id: UUID) -> GenerationProgressPublic:
        """Return a read-only snapshot of the draft's generation state.

        Pure read: never writes, never starts a provider call. The active
        attempt is returned when one is running; otherwise the most recent
        attempt (terminal state) is surfaced so a reload can rehydrate. A draft
        with no attempt at all reports ``attempt=None``.
        """
        draft = self._get_draft(draft_id)
        attempt_id = draft.active_attempt_id or draft.last_attempt_id
        if attempt_id is None:
            return GenerationProgressPublic(
                draft_id=draft_id, active=False, attempt=None
            )
        attempt = self._orchestrator.attempts.get(attempt_id)
        return GenerationProgressPublic(
            draft_id=draft_id,
            active=draft.active_attempt_id is not None,
            attempt=GenerationAttemptPublic.from_attempt(attempt),
        )

    def _resolve_kind(self, draft_id: UUID) -> GenerationAttemptKind:
        draft = self._get_draft(draft_id)
        if draft.mode is DraftMode.BLUEPRINT:
            if draft.status in (
                DraftStatus.DRAFT,
                DraftStatus.READY,
                DraftStatus.FAILED,
            ):
                return GenerationAttemptKind.INITIAL
            if draft.status is DraftStatus.STALE_PREVIEW:
                return GenerationAttemptKind.BLUEPRINT_PREVIEW
            raise _illegal_state_error(draft)
        if draft.status in (
            DraftStatus.DRAFT,
            DraftStatus.READY,
            DraftStatus.FAILED,
        ):
            return GenerationAttemptKind.INITIAL
        if draft.status is DraftStatus.REVIEWABLE:
            return GenerationAttemptKind.FULL_REGENERATE
        raise _illegal_state_error(draft)

    def _get_draft(self, draft_id: UUID) -> DraftRecord:
        try:
            return self._drafts.get(draft_id)
        except (FileNotFoundError, OSError) as exc:
            raise _draft_not_found_error() from exc

    def _record_telemetry(self, event: TelemetryEvent) -> None:
        try:
            self._telemetry.record(event)
        except Exception:  # noqa: BLE001 - telemetry is explicitly fail-open
            return


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
