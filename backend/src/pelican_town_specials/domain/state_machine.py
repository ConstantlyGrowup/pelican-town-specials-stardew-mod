from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Final

from .common import DraftMode, ensure_utc, utc_now
from .draft import DraftRecord, DraftStatus
from .errors import AppError


class DraftAction(str, Enum):
    FIELDS_READY = "FIELDS_READY"
    START_INITIAL_GENERATION = "START_INITIAL_GENERATION"
    GENERATION_SUCCEEDED = "GENERATION_SUCCEEDED"
    GENERATION_FAILED = "GENERATION_FAILED"
    RETRY_FAILED_GENERATION = "RETRY_FAILED_GENERATION"
    START_FULL_REGENERATION = "START_FULL_REGENERATION"
    REGENERATION_SUCCEEDED = "REGENERATION_SUCCEEDED"
    REGENERATION_FAILED = "REGENERATION_FAILED"
    REGENERATION_CANCELLED = "REGENERATION_CANCELLED"
    MODIFY_FIELDS = "MODIFY_FIELDS"
    PREVIEW_UPDATED = "PREVIEW_UPDATED"
    ACCEPT = "ACCEPT"
    DISCARD = "DISCARD"


ALLOWED_TRANSITIONS: Final[dict[tuple[DraftStatus, DraftAction], DraftStatus]] = {
    (DraftStatus.DRAFT, DraftAction.FIELDS_READY): DraftStatus.READY,
    (DraftStatus.READY, DraftAction.START_INITIAL_GENERATION): DraftStatus.GENERATING,
    (DraftStatus.GENERATING, DraftAction.GENERATION_SUCCEEDED): DraftStatus.REVIEWABLE,
    (DraftStatus.GENERATING, DraftAction.GENERATION_FAILED): DraftStatus.FAILED,
    (DraftStatus.FAILED, DraftAction.RETRY_FAILED_GENERATION): DraftStatus.GENERATING,
    (DraftStatus.REVIEWABLE, DraftAction.START_FULL_REGENERATION): DraftStatus.REGENERATING,
    (DraftStatus.REGENERATING, DraftAction.REGENERATION_SUCCEEDED): DraftStatus.REVIEWABLE,
    (DraftStatus.REGENERATING, DraftAction.REGENERATION_FAILED): DraftStatus.REVIEWABLE,
    (DraftStatus.REGENERATING, DraftAction.REGENERATION_CANCELLED): DraftStatus.REVIEWABLE,
    (DraftStatus.REVIEWABLE, DraftAction.MODIFY_FIELDS): DraftStatus.STALE_PREVIEW,
    (DraftStatus.STALE_PREVIEW, DraftAction.PREVIEW_UPDATED): DraftStatus.REVIEWABLE,
    (DraftStatus.REVIEWABLE, DraftAction.ACCEPT): DraftStatus.ARCHIVED,
    (DraftStatus.DRAFT, DraftAction.DISCARD): DraftStatus.DISCARDED,
    (DraftStatus.READY, DraftAction.DISCARD): DraftStatus.DISCARDED,
    (DraftStatus.GENERATING, DraftAction.DISCARD): DraftStatus.DISCARDED,
    (DraftStatus.REGENERATING, DraftAction.DISCARD): DraftStatus.DISCARDED,
    (DraftStatus.FAILED, DraftAction.DISCARD): DraftStatus.DISCARDED,
    (DraftStatus.REVIEWABLE, DraftAction.DISCARD): DraftStatus.DISCARDED,
    (DraftStatus.STALE_PREVIEW, DraftAction.DISCARD): DraftStatus.DISCARDED,
}


_MODE_RESTRICTED_ACTIONS: Final[dict[DraftMode, DraftAction]] = {
    DraftMode.ASK_GUS: DraftAction.MODIFY_FIELDS,
    DraftMode.BLUEPRINT: DraftAction.START_FULL_REGENERATION,
}


def _allowed_actions(draft: DraftRecord) -> list[str]:
    actions = [
        action.value
        for (status, action), _target in ALLOWED_TRANSITIONS.items()
        if status is draft.status
        and not (
            action is _MODE_RESTRICTED_ACTIONS[draft.mode]
        )
    ]
    return actions


def _illegal_transition(draft: DraftRecord, action: DraftAction) -> AppError:
    allowed = _allowed_actions(draft)
    return AppError(
        code="PTS_STATE_ILLEGAL_TRANSITION",
        message=f"Action {action.value} is not legal from {draft.status.value}",
        http_status=409,
        details={
            "currentState": draft.status.value,
            "allowedActions": allowed,
        },
        retryable=False,
    )


def transition(
    draft: DraftRecord,
    action: DraftAction,
    now: datetime | None = None,
) -> DraftRecord:
    target = ALLOWED_TRANSITIONS.get((draft.status, action))
    if target is None:
        raise _illegal_transition(draft, action)

    if action is _MODE_RESTRICTED_ACTIONS[draft.mode]:
        raise _illegal_transition(draft, action)

    updated_at = ensure_utc(now if now is not None else utc_now())
    revision = draft.revision + 1 if action is DraftAction.REGENERATION_SUCCEEDED else draft.revision
    return draft.model_copy(
        update={
            "status": target,
            "revision": revision,
            "updated_at": updated_at,
        }
    )
