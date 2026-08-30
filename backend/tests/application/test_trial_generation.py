"""Orchestrator trial-claim integration tests.

Covers T30-TRIAL-002 (limit error before any provider call), T30-TRIAL-003
(personal mode does not consume trial quota), T30-TRIAL-006 (input validation
failure does not claim; a successful attempt claims exactly once).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from backend.tests.domain.factories import make_draft as make_domain_draft
from backend.tests.generation.conftest import (
    FakeGateway,
    _png_bytes,
    initial_command,
)

from pelican_town_specials.application.trial import (
    TrialAccessService,
    TrialSafeGateway,
)
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.common import DraftMode, GenerationStage
from pelican_town_specials.domain.dish import DishAnalysis
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import (
    GenerationOrchestrator,
    TrialAccess,
)
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    FileAssetStore,
)
from pelican_town_specials.persistence.repositories import (
    DraftRepository,
    GenerationAttemptRepository,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = (
    _REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


class FakeTrialAccess:
    def __init__(
        self,
        *,
        active: bool = True,
        reserve_result: bool = True,
        opportunity: bool = True,
        commit_remaining: int | None = 1,
    ) -> None:
        self.active = active
        self.reserve_result = reserve_result
        self.opportunity = opportunity
        self.commit_remaining = commit_remaining
        self.is_active_calls = 0
        self.reserve_calls = 0
        self.commit_calls = 0
        self.release_calls = 0
        self.opportunity_calls = 0
        self.reserved_attempts: set[UUID] = set()

    def is_active(self) -> bool:
        self.is_active_calls += 1
        return self.active

    def reserve_attempt(self, attempt_id: UUID) -> bool:
        self.reserve_calls += 1
        if not self.reserve_result:
            return False
        self.reserved_attempts.add(attempt_id)
        return True

    def commit_attempt(self, attempt_id: UUID) -> int | None:
        self.commit_calls += 1
        self.reserved_attempts.discard(attempt_id)
        return self.commit_remaining

    def release_attempt(self, attempt_id: UUID) -> bool:
        self.release_calls += 1
        if attempt_id in self.reserved_attempts:
            self.reserved_attempts.remove(attempt_id)
            return True
        return False

    def trial_opportunity(self) -> bool:
        self.opportunity_calls += 1
        return self.opportunity


class _QuotaTrialAccess(FakeTrialAccess):
    """Stateful fake whose quota drains across attempts (R-09).

    Mirrors the real service: ``trial_opportunity`` reports whether quota
    remains and ``reserve_attempt`` only succeeds while quota is left.
    """

    def __init__(self, *, quota: int) -> None:
        super().__init__(active=True, reserve_result=True, opportunity=True)
        self._remaining = quota

    def trial_opportunity(self) -> bool:
        self.opportunity_calls += 1
        return self._remaining > 0

    def reserve_attempt(self, attempt_id: UUID) -> bool:
        self.reserve_calls += 1
        if self._remaining <= 0:
            return False
        self.reserved_attempts.add(attempt_id)
        return True

    def commit_attempt(self, attempt_id: UUID) -> int | None:
        self.commit_calls += 1
        if attempt_id not in self.reserved_attempts:
            return self._remaining
        self.reserved_attempts.remove(attempt_id)
        self._remaining -= 1
        return self._remaining


def _put_original_image(asset_store: FileAssetStore) -> AssetRef:
    data = _png_bytes(size=64, color="seagreen")
    return asset_store.put(
        data,
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=64,
            height=64,
        ),
    )


def _saved_ready_draft(
    orchestrator: GenerationOrchestrator, *, missing_source: bool = False
):
    draft = make_domain_draft(
        mode=DraftMode.ASK_GUS,
        status=DraftStatus.READY,
        revision=1,
    )
    if not missing_source:
        ref = _put_original_image(orchestrator.assets)
        draft = draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": ref.asset_id}
                )
            }
        )
    return orchestrator.drafts.save(draft, expected_revision=None)


def _orchestrator(
    tmp_path: Path,
    *,
    trial_access: TrialAccess | None = None,
    trial_gateway: FakeGateway | None = None,
    personal_configured: bool = False,
) -> tuple[GenerationOrchestrator, FakeGateway, FakeGateway]:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    asset_store = FileAssetStore(workspace)
    draft_repository = DraftRepository(workspace)
    attempt_repository = GenerationAttemptRepository(workspace)
    catalog = VanillaCatalog.from_json(_CATALOG_PATH)
    personal = FakeGateway()
    trial = trial_gateway or FakeGateway()
    orchestrator = GenerationOrchestrator(
        draft_repository=draft_repository,
        attempt_repository=attempt_repository,
        asset_store=asset_store,
        catalog=catalog,
        gateway_factory=lambda: personal,
        registry=AttemptRegistry(),
        min_confidence=0.5,
        trial_access=trial_access,
        trial_gateway_factory=(lambda: trial) if trial_access is not None else None,
        personal_configured=lambda: personal_configured,
    )
    return orchestrator, personal, trial


async def test_trial_generation_claims_once_and_uses_trial_gateway(
    tmp_path: Path,
) -> None:
    trial_access = FakeTrialAccess(active=True, reserve_result=True)
    orchestrator, personal, trial = _orchestrator(tmp_path, trial_access=trial_access)
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert trial_access.reserve_calls == 1
    assert trial_access.commit_calls == 1
    assert trial_access.release_calls == 0
    assert trial_access.is_active_calls == 1
    assert trial.calls == ["analyze", "design", "image", "image"]
    assert personal.calls == []


async def test_personal_mode_does_not_claim(tmp_path: Path) -> None:
    trial_access = FakeTrialAccess(active=False, reserve_result=True)
    orchestrator, personal, trial = _orchestrator(tmp_path, trial_access=trial_access)
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert trial_access.reserve_calls == 0
    assert personal.calls == ["analyze", "design", "image", "image"]
    assert trial.calls == []


async def test_no_trial_access_uses_personal_gateway(tmp_path: Path) -> None:
    orchestrator, personal, trial = _orchestrator(tmp_path, trial_access=None)
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert personal.calls == ["analyze", "design", "image", "image"]
    assert trial.calls == []


async def test_exhausted_trial_raises_limit_before_any_provider_call(
    tmp_path: Path,
) -> None:
    trial_access = FakeTrialAccess(active=True, reserve_result=False)
    orchestrator, personal, trial = _orchestrator(tmp_path, trial_access=trial_access)
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.failed"
    assert events[-1].error is not None
    assert events[-1].error.code == "PTS_TRIAL_LIMIT_REACHED"
    assert events[-1].error.retryable is False
    assert events[-1].error.recommended_action == "CHECK_LOCAL_CONFIGURATION"
    assert personal.calls == []
    assert trial.calls == []


async def test_input_validation_failure_does_not_claim(tmp_path: Path) -> None:
    trial_access = FakeTrialAccess(active=True, reserve_result=True)
    orchestrator, personal, trial = _orchestrator(tmp_path, trial_access=trial_access)
    draft = _saved_ready_draft(orchestrator, missing_source=True)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.failed"
    assert trial_access.reserve_calls == 0
    assert personal.calls == []
    assert trial.calls == []


class _EchoProviderErrorGateway(FakeGateway):
    """Trial gateway that fails the first provider call with echoing details."""

    def __init__(self, error: AppError) -> None:
        super().__init__()
        self._error = error

    async def analyze_dish(
        self, request, *, json_only: bool = False
    ) -> DishAnalysis:
        self.calls.append("analyze")
        raise self._error


async def test_trial_provider_error_details_do_not_leak(tmp_path: Path) -> None:
    """T30-TRIAL-001: an echoing provider error on the trial path must not leak
    the trial Base URL / model ID / key into the NDJSON attempt.failed event.

    The trial gateway is wrapped in TrialSafeGateway (mirroring the app.py
    wiring), so the orchestrator's ErrorPayload carries empty details.
    """
    trial_access = FakeTrialAccess(active=True, reserve_result=True)
    echo = _EchoProviderErrorGateway(
        AppError(
            code="PTS_PROVIDER_REQUEST_FAILED",
            message="Provider 返回了无法处理的响应。",
            http_status=502,
            details={
                "providerError": "https://yibuapi.com/v1 gpt-5.6-luna sk-test-trial",
                "providerHttpStatus": 502,
            },
            retryable=True,
        )
    )
    safe_trial_gateway = TrialSafeGateway(echo)
    orchestrator, personal, _trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        trial_gateway=safe_trial_gateway,
    )
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.failed"
    assert events[-1].error is not None
    assert events[-1].error.code == "PTS_TRIAL_SERVICE_UNAVAILABLE"
    assert events[-1].error.retryable is True
    details = events[-1].error.details
    assert details == {}
    assert "yibuapi" not in str(details)
    assert "gpt-5.6-luna" not in str(details)
    assert "sk-test-trial" not in str(details)
    assert events[-1].error.message.find("本次未消耗试用次数") >= 0
    assert echo.calls == ["analyze"]
    assert trial_access.reserve_calls == 1
    assert trial_access.commit_calls == 0
    assert trial_access.release_calls == 1
    assert personal.calls == []


async def test_configured_user_prefers_trial_then_silently_falls_back(
    tmp_path: Path,
) -> None:
    """T30-TRIAL-007: a configured user burns the free trial allowance first,
    then silently falls back to the personal provider once it is exhausted."""
    trial_access = _QuotaTrialAccess(quota=2)
    orchestrator, personal, trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        personal_configured=True,
    )

    first = _saved_ready_draft(orchestrator)
    events = [event async for event in orchestrator.run(initial_command(first))]
    assert events[-1].type == "attempt.succeeded"
    assert trial_access.reserve_calls == 1
    assert trial_access.commit_calls == 1
    assert trial.calls == ["analyze", "design", "image", "image"]
    assert personal.calls == []

    second = _saved_ready_draft(orchestrator)
    events = [event async for event in orchestrator.run(initial_command(second))]
    assert events[-1].type == "attempt.succeeded"
    assert trial_access.reserve_calls == 2
    assert trial_access.commit_calls == 2
    assert trial.calls == ["analyze", "design", "image", "image"] * 2
    assert personal.calls == []

    third = _saved_ready_draft(orchestrator)
    events = [event async for event in orchestrator.run(initial_command(third))]
    assert events[-1].type == "attempt.succeeded"
    # No further claims after exhaustion, and no PTS_TRIAL_LIMIT_REACHED: the
    # configured path falls back silently.
    assert trial_access.reserve_calls == 2
    assert trial.calls == ["analyze", "design", "image", "image"] * 2
    assert personal.calls == ["analyze", "design", "image", "image"]

    # The configured branch never consults the opt-in is_active() flag.
    assert trial_access.is_active_calls == 0


async def test_configured_user_no_trial_opportunity_uses_personal_gateway(
    tmp_path: Path,
) -> None:
    trial_access = FakeTrialAccess(active=False, reserve_result=True, opportunity=False)
    orchestrator, personal, trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        personal_configured=True,
    )
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert personal.calls == ["analyze", "design", "image", "image"]
    assert trial.calls == []
    assert trial_access.reserve_calls == 0
    assert trial_access.is_active_calls == 0


async def test_configured_user_claim_lost_in_race_falls_back_to_personal(
    tmp_path: Path,
) -> None:
    """T30-TRIAL-007: a concurrent claim loss must not surface an error on the
    configured path — it silently falls back to the personal provider."""
    trial_access = FakeTrialAccess(active=True, reserve_result=False, opportunity=True)
    orchestrator, personal, trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        personal_configured=True,
    )
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert personal.calls == ["analyze", "design", "image", "image"]
    assert trial.calls == []
    assert trial_access.reserve_calls == 1
    assert trial_access.is_active_calls == 0


async def test_configured_user_real_trial_service_prefers_then_falls_back(
    tmp_path: Path,
) -> None:
    """T30-TRIAL-007: a REAL TrialAccessService (not opted-in) is drained by the
    configured-user path and persists claims through the real state file."""
    trial_workspace = WorkspacePaths.create(tmp_path / "trial-ws")
    trial_service = TrialAccessService(
        trial_workspace,
        key_provider=lambda: "sk-test-trial",
        limit=2,
    )
    # R-09 needs no opt-in click: the fresh service is not enabled yet.
    assert trial_service.status().enabled is False
    assert trial_service.trial_opportunity() is True

    orchestrator, personal, trial = _orchestrator(
        tmp_path,
        trial_access=trial_service,
        personal_configured=True,
    )

    first = _saved_ready_draft(orchestrator)
    events = [event async for event in orchestrator.run(initial_command(first))]
    assert events[-1].type == "attempt.succeeded"
    assert trial.calls == ["analyze", "design", "image", "image"]
    assert personal.calls == []
    assert trial_service.status().claimed_attempts == 1

    second = _saved_ready_draft(orchestrator)
    events = [event async for event in orchestrator.run(initial_command(second))]
    assert events[-1].type == "attempt.succeeded"
    assert trial_service.status().claimed_attempts == 2
    assert trial_service.status().remaining == 0
    assert personal.calls == []

    third = _saved_ready_draft(orchestrator)
    events = [event async for event in orchestrator.run(initial_command(third))]
    assert events[-1].type == "attempt.succeeded"
    assert trial.calls == ["analyze", "design", "image", "image"] * 2
    assert personal.calls == ["analyze", "design", "image", "image"]
    assert trial_service.status().claimed_attempts == 2


async def test_trial_failure_before_first_success_releases_and_does_not_fallback(
    tmp_path: Path,
) -> None:
    trial_access = FakeTrialAccess(active=True, reserve_result=True)
    echo = _EchoProviderErrorGateway(
        AppError(
            code="PTS_PROVIDER_REQUEST_FAILED",
            message="hidden provider error",
            http_status=502,
            details={"provider": "hidden", "key": "sk-test-trial"},
            retryable=True,
        )
    )
    safe_trial_gateway = TrialSafeGateway(echo)
    orchestrator, personal, _ = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        trial_gateway=safe_trial_gateway,
        personal_configured=True,
    )
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.failed"
    assert events[-1].error is not None
    assert events[-1].error.code == "PTS_TRIAL_SERVICE_UNAVAILABLE"
    assert events[-1].error.details == {}
    assert "hidden" not in events[-1].error.message
    assert trial_access.commit_calls == 0
    assert trial_access.release_calls == 1
    assert personal.calls == []


async def test_trial_success_commits_once_and_persists_fixed_attempt_snapshot(
    tmp_path: Path,
) -> None:
    trial_access = FakeTrialAccess(active=True, reserve_result=True, commit_remaining=1)
    orchestrator, _personal, trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
    )
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert trial.calls == ["analyze", "design", "image", "image"]
    assert trial_access.reserve_calls == 1
    assert trial_access.commit_calls == 1
    assert trial_access.release_calls == 0
    attempt_id = orchestrator.drafts.get(draft.draft_id).last_attempt_id
    assert attempt_id is not None
    attempt = orchestrator.attempts.get(attempt_id)
    assert attempt.trial_used is True
    assert attempt.trial_remaining == 1


async def test_trial_post_success_failure_does_not_release_or_clear_snapshot(
    tmp_path: Path,
) -> None:
    trial_access = FakeTrialAccess(active=True, reserve_result=True, commit_remaining=1)
    failing_trial = FakeGateway(fail_stage=GenerationStage.GAMEPLAY_DESIGN)
    orchestrator, _personal, _trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        trial_gateway=failing_trial,
    )
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.failed"
    assert trial_access.commit_calls == 1
    assert trial_access.release_calls == 0
    attempt_id = orchestrator.drafts.get(draft.draft_id).last_attempt_id
    assert attempt_id is not None
    attempt = orchestrator.attempts.get(attempt_id)
    assert attempt.trial_used is True
    assert attempt.trial_remaining == 1


class _UnexpectedProviderGateway(FakeGateway):
    async def analyze_dish(self, request, *, json_only: bool = False):
        self.calls.append("analyze")
        raise RuntimeError("provider response parser exploded")


async def test_unexpected_trial_failure_before_first_success_is_safe_and_released(
    tmp_path: Path,
) -> None:
    trial_access = FakeTrialAccess(active=True, reserve_result=True)
    orchestrator, personal, _trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        trial_gateway=TrialSafeGateway(_UnexpectedProviderGateway()),
    )
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.failed"
    assert events[-1].error is not None
    assert events[-1].error.code == "PTS_TRIAL_SERVICE_UNAVAILABLE"
    assert events[-1].error.retryable is True
    assert events[-1].error.details == {}
    assert trial_access.commit_calls == 0
    assert trial_access.release_calls == 1
    assert personal.calls == []


class _TimelineTrialAccess(FakeTrialAccess):
    def __init__(self, timeline: list[str]) -> None:
        super().__init__(active=True, reserve_result=True, commit_remaining=1)
        self._timeline = timeline

    def reserve_attempt(self, attempt_id: UUID) -> bool:
        result = super().reserve_attempt(attempt_id)
        self._timeline.append("reserved")
        return result

    def commit_attempt(self, attempt_id: UUID) -> int | None:
        self._timeline.append("commit")
        return super().commit_attempt(attempt_id)


class _TimelineGateway(FakeGateway):
    def __init__(self, timeline: list[str]) -> None:
        super().__init__()
        self._timeline = timeline

    async def analyze_dish(self, request, *, json_only: bool = False):
        self.calls.append("analyze")
        self._timeline.append("provider-start")
        result = await super().analyze_dish(request, json_only=json_only)
        self._timeline.append("provider-response")
        return result


async def test_trial_commit_waits_for_first_provider_response(
    tmp_path: Path,
) -> None:
    timeline: list[str] = []
    trial_access = _TimelineTrialAccess(timeline)
    orchestrator, _personal, _trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        trial_gateway=_TimelineGateway(timeline),
    )
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert timeline.index("reserved") < timeline.index("provider-start")
    assert timeline.index("provider-response") < timeline.index("commit")


async def test_trial_cancellation_before_first_success_releases_reservation(
    tmp_path: Path,
) -> None:
    hold = asyncio.Event()
    trial_access = FakeTrialAccess(active=True, reserve_result=True)
    trial_gateway = FakeGateway(hold=hold)
    orchestrator, personal, _trial = _orchestrator(
        tmp_path,
        trial_access=trial_access,
        trial_gateway=trial_gateway,
    )
    draft = _saved_ready_draft(orchestrator)
    stream = orchestrator.run(initial_command(draft))
    events = []

    async def consume() -> None:
        async for event in stream:
            events.append(event)

    task = asyncio.create_task(consume())
    for _ in range(200):
        if "analyze" in trial_gateway.calls:
            break
        await asyncio.sleep(0.01)
    assert "analyze" in trial_gateway.calls
    attempt_id = events[0].attempt_id
    assert attempt_id is not None

    assert orchestrator.cancel(attempt_id) is True
    await task

    assert events[-1].type == "attempt.failed"
    assert events[-1].error is not None
    assert events[-1].error.code == "PTS_GEN_CANCELLED"
    assert trial_access.commit_calls == 0
    assert trial_access.release_calls == 1
    assert personal.calls == []
    attempt = orchestrator.attempts.get(attempt_id)
    assert attempt.trial_used is False
    assert attempt.trial_remaining is None
