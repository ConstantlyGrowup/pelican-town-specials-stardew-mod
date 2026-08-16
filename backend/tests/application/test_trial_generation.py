"""Orchestrator trial-claim integration tests.

Covers T30-TRIAL-002 (limit error before any provider call), T30-TRIAL-003
(personal mode does not consume trial quota), T30-TRIAL-006 (input validation
failure does not claim; a successful attempt claims exactly once).
"""

from __future__ import annotations

from pathlib import Path

from backend.tests.domain.factories import make_draft as make_domain_draft
from backend.tests.generation.conftest import (
    FakeGateway,
    _png_bytes,
    initial_command,
)

from pelican_town_specials.application.trial import TrialSafeGateway
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.common import DraftMode
from pelican_town_specials.domain.dish import DishAnalysis
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import GenerationOrchestrator
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
    def __init__(self, *, active: bool = True, claim_result: bool = True) -> None:
        self.active = active
        self.claim_result = claim_result
        self.is_active_calls = 0
        self.claim_calls = 0

    def is_active(self) -> bool:
        self.is_active_calls += 1
        return self.active

    def claim_attempt(self) -> bool:
        self.claim_calls += 1
        return self.claim_result


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
    trial_access: FakeTrialAccess | None = None,
    trial_gateway: FakeGateway | None = None,
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
    )
    return orchestrator, personal, trial


async def test_trial_generation_claims_once_and_uses_trial_gateway(
    tmp_path: Path,
) -> None:
    trial_access = FakeTrialAccess(active=True, claim_result=True)
    orchestrator, personal, trial = _orchestrator(tmp_path, trial_access=trial_access)
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert trial_access.claim_calls == 1
    assert trial_access.is_active_calls == 1
    assert trial.calls == ["analyze", "design", "image", "image"]
    assert personal.calls == []


async def test_personal_mode_does_not_claim(tmp_path: Path) -> None:
    trial_access = FakeTrialAccess(active=False, claim_result=True)
    orchestrator, personal, trial = _orchestrator(tmp_path, trial_access=trial_access)
    draft = _saved_ready_draft(orchestrator)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.succeeded"
    assert trial_access.claim_calls == 0
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
    trial_access = FakeTrialAccess(active=True, claim_result=False)
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
    trial_access = FakeTrialAccess(active=True, claim_result=True)
    orchestrator, personal, trial = _orchestrator(tmp_path, trial_access=trial_access)
    draft = _saved_ready_draft(orchestrator, missing_source=True)

    events = [event async for event in orchestrator.run(initial_command(draft))]

    assert events[-1].type == "attempt.failed"
    assert trial_access.claim_calls == 0
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
    trial_access = FakeTrialAccess(active=True, claim_result=True)
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
    assert events[-1].error.code == "PTS_PROVIDER_REQUEST_FAILED"
    details = events[-1].error.details
    assert details == {}
    assert "yibuapi" not in str(details)
    assert "gpt-5.6-luna" not in str(details)
    assert "sk-test-trial" not in str(details)
    assert echo.calls == ["analyze"]
    assert personal.calls == []
