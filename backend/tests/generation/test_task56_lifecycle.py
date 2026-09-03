"""Independent Task56 lifecycle acceptance probes; all providers are fake."""

import asyncio
from uuid import UUID, uuid4

import pytest

from pelican_town_specials.application.generation import GenerationService
from pelican_town_specials.application.trial import TrialProviderPreference
from pelican_town_specials.domain.common import GenerationStage
from pelican_town_specials.domain.draft import AttemptStatus, DraftRecord
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import GenerationOrchestrator
from pelican_town_specials.persistence.asset_store import FileAssetStore
from pelican_town_specials.persistence.repositories import (
    DraftRepository,
    GenerationAttemptRepository,
)

from .conftest import GenerationHarness, initial_command


def _reopen(harness: GenerationHarness, **kwargs) -> GenerationOrchestrator:
    """Use new repository/store/registry instances over the same disk workspace."""
    return GenerationOrchestrator(
        draft_repository=DraftRepository(harness.workspace),
        attempt_repository=GenerationAttemptRepository(harness.workspace),
        asset_store=FileAssetStore(harness.workspace),
        catalog=harness.catalog,
        gateway_factory=lambda: harness.gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
        **kwargs,
    )


def _preview_outage(harness: GenerationHarness, monkeypatch):
    original = harness.gateway.generate_image

    async def unavailable(request):
        if len(request.source_images) == 2:
            harness.gateway.calls.append("image")
            raise AppError(
                code="PTS_PROVIDER_UNAVAILABLE",
                message="Fake provider offline.",
                http_status=503,
                details={},
                retryable=True,
            )
        return await original(request)

    monkeypatch.setattr(harness.gateway, "generate_image", unavailable)
    return original


@pytest.mark.parametrize(
    ("stop_stage", "remaining_calls"),
    [
        (GenerationStage.ICON_GENERATION_AND_NORMALIZATION, ["image"]),
        (GenerationStage.PREVIEW_ART_GENERATION_AND_COMPOSITION, []),
    ],
)
async def test_startup_sweep_preserves_disk_checkpoint_without_auto_calls(
    harness: GenerationHarness,
    ready_draft: DraftRecord,
    stop_stage: GenerationStage,
    remaining_calls: list[str],
) -> None:
    # Close the internal engine at a committed stage boundary, simulating loss
    # of the process without sending the product's explicit cancel command.
    old_id = uuid4()
    engine = harness.orchestrator._run(initial_command(ready_draft), old_id)
    async for event in engine:
        if event.type == "stage.succeeded" and event.stage is stop_stage:
            break
    await engine.aclose()
    assert harness.attempt_repository.get(old_id).status is AttemptStatus.RUNNING
    harness.gateway.calls.clear()

    reopened = _reopen(harness)
    reopened.attempts.interrupt_running()
    assert reopened.recover_interrupted(ready_draft.draft_id)
    service = GenerationService(orchestrator=reopened, draft_repository=reopened.drafts)
    progress = service.get_progress(ready_draft.draft_id)
    assert progress.attempt is not None
    assert progress.attempt.status is AttemptStatus.INTERRUPTED
    assert progress.attempt.progress_saved is True
    assert harness.gateway.calls == []

    result = [line async for line in service.begin_generation(ready_draft.draft_id)]
    assert '"attempt.succeeded"' in result[-1]
    assert harness.gateway.calls == remaining_calls
    assert (
        reopened.drafts.get(ready_draft.draft_id).revision == ready_draft.revision + 1
    )
    assert reopened.attempts.get_checkpoint(old_id) is None


@pytest.mark.parametrize(
    "invalidity", ["input", "missing_icon", "protocol", "kind", "corrupt"]
)
async def test_incompatible_checkpoint_is_not_advertised_or_promoted(
    harness: GenerationHarness,
    ready_draft: DraftRecord,
    monkeypatch,
    invalidity: str,
) -> None:
    original = _preview_outage(harness, monkeypatch)
    events = [
        event async for event in harness.orchestrator.run(initial_command(ready_draft))
    ]
    assert events[-1].type == "attempt.failed"
    failed = harness.draft_repository.get(ready_draft.draft_id)
    checkpoint = harness.attempt_repository.get_checkpoint(failed.last_attempt_id)
    assert checkpoint is not None
    if invalidity == "input":
        failed = harness.draft_repository.control_write(
            failed.model_copy(
                update={
                    "source": failed.source.model_copy(
                        update={"context_text": "different recipe"}
                    ),
                }
            ),
            expected_revision=failed.revision,
            expected_attempt_id=None,
        )
    elif invalidity == "missing_icon":
        assert checkpoint.icon_source_asset_id is not None
        harness.asset_store.delete(checkpoint.icon_source_asset_id)
    elif invalidity == "protocol":
        harness.attempt_repository.save_checkpoint(
            checkpoint.model_copy(update={"protocol_version": "old-protocol"})
        )
    elif invalidity == "corrupt":
        folder = harness.workspace.staging_dir / f"attempt-{failed.last_attempt_id}"
        for filename in ("checkpoint.json", "checkpoint.json.bak"):
            (folder / filename).write_text("{broken", encoding="utf-8")
    else:
        from pelican_town_specials.domain.draft import GenerationAttemptKind

        harness.attempt_repository.save_checkpoint(
            checkpoint.model_copy(
                update={"kind": GenerationAttemptKind.FULL_REGENERATE}
            )
        )
    monkeypatch.setattr(harness.gateway, "generate_image", original)
    harness.gateway.calls.clear()
    reopened = _reopen(harness)
    service = GenerationService(orchestrator=reopened, draft_repository=reopened.drafts)
    progress = service.get_progress(ready_draft.draft_id)
    assert progress.attempt is not None
    assert progress.attempt.progress_saved is False
    result = [event async for event in reopened.run(initial_command(failed))]
    assert result[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["analyze", "design", "image", "image"]


@pytest.mark.parametrize(
    ("stage", "remaining"),
    [
        ("design", ["design", "image", "image"]),
        ("icon", ["image", "image"]),
        ("preview", ["image"]),
    ],
)
async def test_typed_provider_failure_resumes_only_remaining_paid_stages(
    harness: GenerationHarness,
    ready_draft: DraftRecord,
    monkeypatch,
    stage: str,
    remaining: list[str],
) -> None:
    method = "design_ask_gus" if stage == "design" else "generate_image"
    original = getattr(harness.gateway, method)

    async def unavailable(request):
        if stage == "design" or len(request.source_images) == (
            1 if stage == "icon" else 2
        ):
            harness.gateway.calls.append("design" if stage == "design" else "image")
            raise AppError(
                code="PTS_PROVIDER_UNAVAILABLE",
                message="Offline",
                http_status=503,
                details={},
                retryable=True,
            )
        return await original(request)

    monkeypatch.setattr(harness.gateway, method, unavailable)
    failed = [
        event async for event in harness.orchestrator.run(initial_command(ready_draft))
    ]
    assert failed[-1].type == "attempt.failed"
    assert failed[-1].error.details["progressSaved"] is True
    monkeypatch.setattr(harness.gateway, method, original)
    harness.gateway.calls.clear()
    reopened = _reopen(harness)
    events = [
        event
        async for event in reopened.run(
            initial_command(reopened.drafts.get(ready_draft.draft_id))
        )
    ]
    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == remaining


class _Trial:
    def __init__(self) -> None:
        self.reserved: list[UUID] = []
        self.released: list[UUID] = []
        self.committed: list[UUID] = []

    def preference(self):
        return TrialProviderPreference.TRIAL_FIRST

    def is_active(self):
        return True

    def trial_opportunity(self):
        return True

    def reserve_attempt(self, attempt_id):
        self.reserved.append(attempt_id)
        return True

    def release_attempt(self, attempt_id):
        self.released.append(attempt_id)
        return True

    def commit_attempt(self, attempt_id):
        self.committed.append(attempt_id)
        return 4


async def test_repeated_trial_outage_releases_each_attempt_then_consumes_once(
    harness: GenerationHarness,
    ready_draft: DraftRecord,
    monkeypatch,
) -> None:
    original = _preview_outage(harness, monkeypatch)
    trial = _Trial()
    for _ in range(2):
        local = _reopen(
            harness,
            trial_access=trial,
            trial_gateway_factory=lambda: harness.gateway,
        )
        draft = local.drafts.get(ready_draft.draft_id)
        events = [event async for event in local.run(initial_command(draft))]
        assert events[-1].type == "attempt.failed"
        assert events[-1].error.code == "PTS_TRIAL_SERVICE_UNAVAILABLE"
        assert events[-1].error.details["progressSaved"] is True
    assert trial.committed == []
    assert trial.released == trial.reserved
    # Only the failing preview is called again on the second attempt.
    assert harness.gateway.calls == ["analyze", "design", "image", "image", "image"]

    monkeypatch.setattr(harness.gateway, "generate_image", original)
    harness.gateway.calls.clear()
    local = _reopen(
        harness,
        trial_access=trial,
        trial_gateway_factory=lambda: harness.gateway,
    )
    events = [
        event
        async for event in local.run(
            initial_command(local.drafts.get(ready_draft.draft_id))
        )
    ]
    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["image"]
    assert trial.committed == [events[-1].attempt_id]
    attempt = local.attempts.get(events[-1].attempt_id)
    assert attempt.trial_used is True
    assert attempt.trial_remaining == 4


async def test_fully_cached_resume_still_reserves_and_commits_current_trial(
    harness: GenerationHarness,
    ready_draft: DraftRecord,
) -> None:
    engine = harness.orchestrator._run(initial_command(ready_draft), uuid4())
    async for event in engine:
        if (
            event.type == "stage.succeeded"
            and event.stage is GenerationStage.PREVIEW_ART_GENERATION_AND_COMPOSITION
        ):
            break
    await engine.aclose()
    harness.gateway.calls.clear()
    trial = _Trial()
    local = _reopen(
        harness,
        trial_access=trial,
        trial_gateway_factory=lambda: harness.gateway,
    )
    local.attempts.interrupt_running()
    local.recover_interrupted(ready_draft.draft_id)
    events = [
        event
        async for event in local.run(
            initial_command(local.drafts.get(ready_draft.draft_id))
        )
    ]
    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == []
    assert trial.reserved == trial.committed == [events[-1].attempt_id]
    assert trial.released == []


async def test_cancel_resumed_attempt_clears_only_its_checkpoint(
    harness: GenerationHarness,
    ready_draft: DraftRecord,
    monkeypatch,
) -> None:
    original = _preview_outage(harness, monkeypatch)
    other = harness.draft_repository.save(
        ready_draft.model_copy(update={"draft_id": uuid4()}),
        expected_revision=None,
    )
    for draft in (ready_draft, other):
        events = [
            event async for event in harness.orchestrator.run(initial_command(draft))
        ]
        assert events[-1].type == "attempt.failed"
    other = harness.draft_repository.get(other.draft_id)
    other_attempt = harness.attempt_repository.get(other.last_attempt_id)
    other_checkpoint = harness.attempt_repository.get_checkpoint(other.last_attempt_id)
    assert other_checkpoint is not None

    entered = asyncio.Event()
    hold = asyncio.Event()

    async def held_preview(request):
        if len(request.source_images) == 2:
            entered.set()
            await hold.wait()
        return await original(request)

    monkeypatch.setattr(harness.gateway, "generate_image", held_preview)
    service = GenerationService(
        orchestrator=harness.orchestrator,
        draft_repository=harness.draft_repository,
    )

    async def consume():
        return [line async for line in service.begin_generation(ready_draft.draft_id)]

    task = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        current = harness.draft_repository.get(ready_draft.draft_id)
        assert current.active_attempt_id is not None
        assert await service.cancel(ready_draft.draft_id)
        await asyncio.wait_for(task, 5)
        assert (
            harness.attempt_repository.get(current.active_attempt_id).status
            is AttemptStatus.CANCELLED
        )
        assert (
            harness.attempt_repository.get_checkpoint(current.active_attempt_id) is None
        )
        assert (
            harness.orchestrator.compatible_checkpoint(other, other_attempt) is not None
        )
        # The default fake returns identical icon bytes, exercising asset dedup.
        assert other_checkpoint.icon_source_asset_id is not None
        harness.asset_store.stat(other_checkpoint.icon_source_asset_id)
    finally:
        hold.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_canonical_hit_preview_failure_resumes_owned_icon_without_recall(
    harness: GenerationHarness,
    ready_draft: DraftRecord,
    monkeypatch,
) -> None:
    from pelican_town_specials.providers.contracts import CanonicalMatchResponse

    from .test_ask_gus import _canonical_dish, _RecallRegistry

    canonical, source, icon16 = _canonical_dish(uuid4())
    second, _, _ = _canonical_dish(uuid4())
    registry = _RecallRegistry(canonical, source, icon16, second=second)
    harness.gateway.canonical_match_response = CanonicalMatchResponse(
        candidateId=canonical.canonical_id,
        confidence=0.94,
    )
    original = _preview_outage(harness, monkeypatch)
    local = _reopen(harness, canonical_repository=registry)
    failed = [event async for event in local.run(initial_command(ready_draft))]
    assert failed[-1].type == "attempt.failed"
    assert harness.gateway.calls == ["analyze", "match", "image"]
    checkpoint = local.attempts.get_checkpoint(failed[-1].attempt_id)
    assert checkpoint is not None
    assert checkpoint.canonical == canonical
    assert failed[-1].error.details["progressSaved"] is True

    monkeypatch.setattr(harness.gateway, "generate_image", original)
    harness.gateway.calls.clear()
    registry.calls.clear()
    # Already-copied data/icons must not require a fresh Registry lookup.
    reopened = _reopen(harness)
    events = [
        event
        async for event in reopened.run(
            initial_command(reopened.drafts.get(ready_draft.draft_id))
        )
    ]
    assert events[-1].type == "attempt.succeeded"
    assert harness.gateway.calls == ["image"]
    assert registry.calls == []


async def test_trial_semantic_validation_failure_does_not_offer_resume(
    harness: GenerationHarness,
    ready_draft: DraftRecord,
    monkeypatch,
) -> None:
    def reject_candidate(_candidate):
        raise AppError(
            code="PTS_GEN_VALIDATION_FAILED",
            message="Invalid local result",
            http_status=422,
            details={},
            retryable=False,
        )

    monkeypatch.setattr(
        "pelican_town_specials.generation.orchestrator.validate_draft",
        reject_candidate,
    )
    trial = _Trial()
    local = _reopen(
        harness, trial_access=trial, trial_gateway_factory=lambda: harness.gateway
    )
    events = [event async for event in local.run(initial_command(ready_draft))]
    assert events[-1].type == "attempt.failed"
    # Keep M11's public safe trial envelope, but classify resumability using
    # the real pre-redaction local error, not the generic trial wrapper.
    assert events[-1].error.code == "PTS_TRIAL_SERVICE_UNAVAILABLE"
    assert events[-1].error.details.get("progressSaved") is not True
    assert local.attempts.get_checkpoint(events[-1].attempt_id) is None
    assert trial.committed == []
    assert trial.released == trial.reserved
