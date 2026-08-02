from datetime import UTC, datetime, timedelta, timezone

import pytest

from pelican_town_specials.domain.common import DraftMode
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.domain.state_machine import (
    ALLOWED_TRANSITIONS,
    DraftAction,
    transition,
)
from tests.domain.factories import make_draft

UTC_NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


def test_draft_action_has_exact_public_actions() -> None:
    assert [action.name for action in DraftAction] == [
        "FIELDS_READY",
        "START_INITIAL_GENERATION",
        "GENERATION_SUCCEEDED",
        "GENERATION_FAILED",
        "RETRY_FAILED_GENERATION",
        "START_FULL_REGENERATION",
        "REGENERATION_SUCCEEDED",
        "REGENERATION_FAILED",
        "REGENERATION_CANCELLED",
        "MODIFY_FIELDS",
        "PREVIEW_UPDATED",
        "ACCEPT",
        "DISCARD",
    ]


@pytest.mark.parametrize(
    ("status", "action", "target"),
    [
        (DraftStatus.DRAFT, DraftAction.FIELDS_READY, DraftStatus.READY),
        (DraftStatus.READY, DraftAction.START_INITIAL_GENERATION, DraftStatus.GENERATING),
        (DraftStatus.GENERATING, DraftAction.GENERATION_SUCCEEDED, DraftStatus.REVIEWABLE),
        (DraftStatus.GENERATING, DraftAction.GENERATION_FAILED, DraftStatus.FAILED),
        (DraftStatus.FAILED, DraftAction.RETRY_FAILED_GENERATION, DraftStatus.GENERATING),
        (DraftStatus.REVIEWABLE, DraftAction.START_FULL_REGENERATION, DraftStatus.REGENERATING),
        (DraftStatus.REGENERATING, DraftAction.REGENERATION_SUCCEEDED, DraftStatus.REVIEWABLE),
        (DraftStatus.REGENERATING, DraftAction.REGENERATION_FAILED, DraftStatus.REVIEWABLE),
        (DraftStatus.REGENERATING, DraftAction.REGENERATION_CANCELLED, DraftStatus.REVIEWABLE),
        (DraftStatus.REVIEWABLE, DraftAction.MODIFY_FIELDS, DraftStatus.STALE_PREVIEW),
        (DraftStatus.STALE_PREVIEW, DraftAction.PREVIEW_UPDATED, DraftStatus.REVIEWABLE),
        (DraftStatus.REVIEWABLE, DraftAction.ACCEPT, DraftStatus.ARCHIVED),
    ],
)
def test_allowed_transitions_is_the_explicit_status_action_table(
    status: DraftStatus, action: DraftAction, target: DraftStatus
) -> None:
    assert ALLOWED_TRANSITIONS[(status, action)] is target


def test_ask_gus_lifecycle_and_failed_regeneration_preserves_revision() -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.DRAFT, revision=3)
    ready = transition(draft, DraftAction.FIELDS_READY)
    generating = transition(ready, DraftAction.START_INITIAL_GENERATION)
    reviewable = transition(generating, DraftAction.GENERATION_SUCCEEDED)
    regenerating = transition(reviewable, DraftAction.START_FULL_REGENERATION)
    restored = transition(regenerating, DraftAction.REGENERATION_FAILED)

    assert restored.status is DraftStatus.REVIEWABLE
    assert restored.revision == 3


def test_failed_initial_generation_can_be_retried() -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.GENERATING)
    failed = transition(draft, DraftAction.GENERATION_FAILED)
    retrying = transition(failed, DraftAction.RETRY_FAILED_GENERATION)

    assert failed.status is DraftStatus.FAILED
    assert retrying.status is DraftStatus.GENERATING


def test_cancelled_full_regeneration_returns_to_reviewable_without_revision_change() -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.REVIEWABLE, revision=3)
    regenerating = transition(draft, DraftAction.START_FULL_REGENERATION)
    restored = transition(regenerating, DraftAction.REGENERATION_CANCELLED)

    assert restored.status is DraftStatus.REVIEWABLE
    assert restored.revision == 3


def test_successful_full_regeneration_increments_revision_once() -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.REVIEWABLE, revision=3)
    regenerating = transition(draft, DraftAction.START_FULL_REGENERATION)
    result = transition(regenerating, DraftAction.REGENERATION_SUCCEEDED, now=UTC_NOW)

    assert result.status is DraftStatus.REVIEWABLE
    assert result.revision == 4
    assert result.updated_at == UTC_NOW


def test_blueprint_lifecycle_allows_modify_and_preview_update() -> None:
    draft = make_draft(mode=DraftMode.BLUEPRINT, status=DraftStatus.REVIEWABLE)
    stale = transition(draft, DraftAction.MODIFY_FIELDS)
    updated = transition(stale, DraftAction.PREVIEW_UPDATED)

    assert stale.status is DraftStatus.STALE_PREVIEW
    assert updated.status is DraftStatus.REVIEWABLE


@pytest.mark.parametrize("status", list(DraftStatus)[:7])
def test_discard_is_allowed_from_every_non_terminal_status(status: DraftStatus) -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=status)
    assert transition(draft, DraftAction.DISCARD).status is DraftStatus.DISCARDED


@pytest.mark.parametrize("status", [DraftStatus.ARCHIVED, DraftStatus.DISCARDED])
@pytest.mark.parametrize("action", list(DraftAction))
def test_terminal_statuses_reject_every_action(
    status: DraftStatus, action: DraftAction
) -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=status)
    with pytest.raises(AppError) as exc_info:
        transition(draft, action)

    assert exc_info.value.code == "PTS_STATE_ILLEGAL_TRANSITION"
    assert exc_info.value.details == {
        "currentState": status.value,
        "allowedActions": [],
    }


@pytest.mark.parametrize(
    ("mode", "action"),
    [
        (DraftMode.BLUEPRINT, DraftAction.START_FULL_REGENERATION),
        (DraftMode.ASK_GUS, DraftAction.MODIFY_FIELDS),
    ],
)
def test_mode_mismatch_has_the_standard_illegal_transition_error(
    mode: DraftMode, action: DraftAction
) -> None:
    draft = make_draft(mode=mode, status=DraftStatus.REVIEWABLE)
    with pytest.raises(AppError) as exc_info:
        transition(draft, action)

    error = exc_info.value
    assert error.code == "PTS_STATE_ILLEGAL_TRANSITION"
    assert error.http_status == 409
    assert error.details["currentState"] == "REVIEWABLE"
    allowed_actions = error.details["allowedActions"]
    assert isinstance(allowed_actions, list)
    assert "DISCARD" in allowed_actions
    assert action.value not in allowed_actions


def test_missing_table_entry_uses_same_error_and_mode_filtered_actions() -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.REVIEWABLE)
    with pytest.raises(AppError) as exc_info:
        transition(draft, DraftAction.PREVIEW_UPDATED)

    details = exc_info.value.details
    assert exc_info.value.code == "PTS_STATE_ILLEGAL_TRANSITION"
    assert details["currentState"] == "REVIEWABLE"
    assert details["allowedActions"] == [
        "START_FULL_REGENERATION",
        "ACCEPT",
        "DISCARD",
    ]


def test_app_error_copies_safe_action_name_lists_and_rejects_unsafe_lists() -> None:
    allowed_actions = ["ACCEPT", "DISCARD"]
    error = AppError(
        code="PTS_STATE_ILLEGAL_TRANSITION",
        message="not allowed",
        http_status=409,
        details={"allowedActions": allowed_actions},
        retryable=False,
    )

    allowed_actions.append("MUTATED")
    assert error.details["allowedActions"] == ["ACCEPT", "DISCARD"]

    with pytest.raises(TypeError):
        AppError(
            code="PTS_STATE_ILLEGAL_TRANSITION",
            message="not allowed",
            http_status=409,
            details={"allowedActions": ["ACCEPT", {"unsafe": True}]},
            retryable=False,
        )


def test_transition_normalizes_non_utc_offset_and_does_not_mutate_input() -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.DRAFT)
    before = draft.model_dump()
    offset_now = datetime(
        2026, 8, 2, 22, 0, tzinfo=timezone(timedelta(hours=10))
    )
    result = transition(draft, DraftAction.FIELDS_READY, now=offset_now)

    assert result.updated_at == UTC_NOW
    assert result is not draft
    assert draft.status is DraftStatus.DRAFT
    assert draft.model_dump() == before


def test_transition_rejects_naive_now() -> None:
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.DRAFT)
    with pytest.raises(ValueError, match="timezone-aware"):
        transition(draft, DraftAction.FIELDS_READY, now=datetime(2026, 8, 2, 7, 0))  # noqa: DTZ001
