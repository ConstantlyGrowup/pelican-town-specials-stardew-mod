"""TrialAccessService unit tests: enable/disable/status/reserve/limit/unavailable.

Covers T30-TRIAL-001 (trial status exposure), T30-TRIAL-002 (claim limit),
T30-TRIAL-003 (atomic concurrency), T30-TRIAL-004 (disable preserves claims),
T30-TRIAL-005 (missing key => unavailable).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from backend.tests.generation.conftest import (
    _png_bytes,
    analysis_fixture,
    core_fixture,
)

from pelican_town_specials.application.trial import (
    TRIAL_BASE_URL,
    TRIAL_CHAT_TIMEOUT_SECONDS,
    TRIAL_GENERATION_LIMIT,
    TRIAL_IMAGE_MODEL,
    TRIAL_IMAGE_TIMEOUT_SECONDS,
    TRIAL_MAX_AUTOMATIC_RETRIES,
    TRIAL_TEXT_MODEL,
    TRIAL_VISION_MODEL,
    FileTrialKeyProvider,
    StaticSecretStore,
    TrialAccessService,
    TrialProviderPreference,
    TrialSafeGateway,
    TrialState,
)
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.dish import DishAnalysis
from pelican_town_specials.domain.errors import AppError, recommended_action
from pelican_town_specials.persistence.secret_store import ApiKeySource
from pelican_town_specials.persistence.workspace import WorkspacePaths
from pelican_town_specials.providers.contracts import (
    AskGusDesignRequest,
    DishAnalysisRequest,
    GeneratedDishCore,
    GeneratedImage,
    ImageGenerationRequest,
    ImageMediaType,
    ImageOperation,
    ProviderImageInput,
)


def _service(
    tmp_path: Path, *, key: str | None = "sk-test-trial"
) -> tuple[TrialAccessService, WorkspacePaths]:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    service = TrialAccessService(workspace, key_provider=lambda: key)
    return service, workspace


def test_initial_status_is_available_disabled_with_full_quota(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    status = service.status()

    assert status.available is True
    assert status.enabled is False
    assert status.claimed_attempts == 0
    assert status.limit == TRIAL_GENERATION_LIMIT
    assert status.remaining == TRIAL_GENERATION_LIMIT


def test_status_surfaces_camel_case_fields(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    attempt_id = uuid4()
    service.enable()
    assert service.reserve_attempt(attempt_id) is True
    assert service.commit_attempt(attempt_id) == TRIAL_GENERATION_LIMIT - 1

    payload = service.status().model_dump(by_alias=True, mode="json")

    assert payload == {
        "available": True,
        "enabled": True,
        "claimedAttempts": 1,
        "limit": TRIAL_GENERATION_LIMIT,
        "remaining": TRIAL_GENERATION_LIMIT - 1,
    }


def test_enable_returns_enabled_status_and_persists(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    status = service.enable()

    assert status.enabled is True
    assert status.available is True

    reloaded = TrialAccessService(workspace, key_provider=lambda: "sk-test-trial")
    assert reloaded.status().enabled is True


def test_state_persists_claimed_attempts_across_instances(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    attempt_id = uuid4()
    service.enable()
    assert service.reserve_attempt(attempt_id) is True
    assert service.commit_attempt(attempt_id) == TRIAL_GENERATION_LIMIT - 1

    reloaded = TrialAccessService(workspace, key_provider=lambda: "sk-test-trial")

    status = reloaded.status()
    assert status.enabled is True
    assert status.claimed_attempts == 1
    assert status.remaining == TRIAL_GENERATION_LIMIT - 1


def test_claim_attempt_increments_until_limit_then_false(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.enable()

    assert service.claim_attempt() is True
    assert service.claim_attempt() is True
    assert service.claim_attempt() is False

    status = service.status()
    assert status.claimed_attempts == TRIAL_GENERATION_LIMIT
    assert status.remaining == 0
    # R-07: enabled stays true after exhaustion; the precise limit error is
    # raised by the orchestrator before any provider call.
    assert status.enabled is True
    assert service.is_active() is True


def test_reserve_commit_release_are_idempotent_and_commit_is_a_fixed_snapshot(
    tmp_path: Path,
) -> None:
    service, _ = _service(tmp_path)
    service.enable()
    attempt_id = uuid4()

    assert service.reserve_attempt(attempt_id) is True
    assert service.reserve_attempt(attempt_id) is True
    assert service.status().claimed_attempts == 0
    assert service.status().remaining == TRIAL_GENERATION_LIMIT

    assert service.commit_attempt(attempt_id) == TRIAL_GENERATION_LIMIT - 1
    assert service.commit_attempt(attempt_id) == TRIAL_GENERATION_LIMIT - 1
    assert service.status().claimed_attempts == 1
    assert service.status().remaining == TRIAL_GENERATION_LIMIT - 1

    # A committed attempt cannot be refunded, even when release is retried.
    assert service.release_attempt(attempt_id) is False
    assert service.release_attempt(attempt_id) is False
    assert service.status().claimed_attempts == 1
    assert service.status().remaining == TRIAL_GENERATION_LIMIT - 1


def test_release_returns_quota_without_affecting_other_attempts(
    tmp_path: Path,
) -> None:
    service, _ = _service(tmp_path)
    first = uuid4()
    second = uuid4()

    assert service.reserve_attempt(first) is True
    assert service.reserve_attempt(second) is True
    assert service.status().claimed_attempts == 0
    assert service.status().remaining == TRIAL_GENERATION_LIMIT

    assert service.commit_attempt(second) == TRIAL_GENERATION_LIMIT - 1
    assert service.status().claimed_attempts == 1
    assert service.release_attempt(first) is True
    assert service.release_attempt(first) is False
    assert service.reserve_attempt(uuid4()) is True
    assert service.status().claimed_attempts == 1


def test_v1_claimed_attempts_migrate_without_resetting_quota(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    service.state_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "enabled": True,
                "claimedAttempts": 1,
            }
        ),
        encoding="utf-8",
    )

    reloaded = TrialAccessService(workspace, key_provider=lambda: "sk-test-trial")

    status = reloaded.status()
    assert status.enabled is True
    assert status.claimed_attempts == 1
    assert status.remaining == TRIAL_GENERATION_LIMIT - 1
    payload = json.loads(reloaded.state_path.read_text(encoding="utf-8"))
    assert payload == {
        "committedAttempts": {},
        "consumedAttempts": 1,
        "enabled": True,
        "providerPreference": "TRIAL_FIRST",
        "reservations": [],
        "schemaVersion": 2,
    }


def test_trial_state_personal_preference_round_trips_without_public_exposure(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    state = TrialState(provider_preference=TrialProviderPreference.PERSONAL)
    payload = state.model_dump(by_alias=True, mode="json")

    parsed = TrialState.model_validate(payload)
    service.state_path.write_text(json.dumps(payload), encoding="utf-8")
    reloaded = TrialAccessService(workspace, key_provider=lambda: "sk-test-trial")

    assert parsed.provider_preference is TrialProviderPreference.PERSONAL
    assert reloaded._state.provider_preference is TrialProviderPreference.PERSONAL
    assert "providerPreference" not in reloaded.status().model_dump(by_alias=True)


def test_reloading_clears_unconfirmed_reservations(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    attempt_id = uuid4()
    assert service.reserve_attempt(attempt_id) is True
    assert service.status().claimed_attempts == 0

    reloaded = TrialAccessService(workspace, key_provider=lambda: "sk-test-trial")

    assert reloaded.status().claimed_attempts == 0
    assert reloaded.status().remaining == TRIAL_GENERATION_LIMIT
    payload = json.loads(reloaded.state_path.read_text(encoding="utf-8"))
    assert payload["reservations"] == []


def test_concurrent_reservations_never_exceed_unconsumed_limit(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    attempt_ids = [uuid4() for _ in range(20)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(service.reserve_attempt, attempt_ids))

    assert results.count(True) == TRIAL_GENERATION_LIMIT
    assert results.count(False) == len(attempt_ids) - TRIAL_GENERATION_LIMIT
    assert service.status().claimed_attempts == 0
    assert service.status().remaining == TRIAL_GENERATION_LIMIT

    for attempt_id, reserved in zip(attempt_ids, results, strict=True):
        if reserved:
            assert service.release_attempt(attempt_id) is True


def test_is_active_reflects_enabled(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    assert service.is_active() is False
    service.enable()
    assert service.is_active() is True
    service.disable()
    assert service.is_active() is False


def test_trial_opportunity_true_when_available_and_fresh(tmp_path: Path) -> None:
    """R-09: a fresh (not yet opted-in) trial still offers an opportunity.

    ``trial_opportunity`` deliberately does not require ``enabled`` so a
    configured user can burn the free allowance without clicking opt-in.
    """
    service, _ = _service(tmp_path)

    assert service.trial_opportunity() is True


def test_trial_opportunity_true_while_quota_remains(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.enable()
    service.claim_attempt()

    assert service.trial_opportunity() is True


def test_trial_opportunity_false_when_exhausted(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.enable()
    service.claim_attempt()
    service.claim_attempt()

    assert service.trial_opportunity() is False
    assert service.status().remaining == 0


def test_trial_opportunity_false_when_key_missing(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, key=None)

    assert service.trial_opportunity() is False


def test_disable_is_idempotent_and_preserves_claimed(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.enable()
    service.claim_attempt()

    status = service.disable()
    assert status.enabled is False
    # Second disable is a no-op and must not raise.
    second_status = service.disable()
    assert second_status.enabled is False
    assert second_status.claimed_attempts == 1


def test_status_reports_unavailable_when_key_missing(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, key=None)

    assert service.status().available is False
    assert service.available is False


def test_enable_raises_trial_unavailable_when_key_missing(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, key=None)

    with pytest.raises(AppError) as raised:
        service.enable()

    assert raised.value.code == "PTS_TRIAL_UNAVAILABLE"
    assert raised.value.http_status == 409
    assert raised.value.retryable is False
    assert raised.value.details == {}


def test_concurrent_claims_never_exceed_limit(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.enable()
    attempt_count = 20

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: service.claim_attempt(), range(attempt_count))
        )

    assert results.count(True) == TRIAL_GENERATION_LIMIT
    assert results.count(False) == attempt_count - TRIAL_GENERATION_LIMIT
    assert service.status().claimed_attempts == TRIAL_GENERATION_LIMIT
    assert service.status().remaining == 0


def test_corrupted_state_file_degrades_to_disabled(tmp_path: Path) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    service = TrialAccessService(workspace, key_provider=lambda: "sk-test-trial")
    service.enable()
    # No backup exists yet (first write), so corrupting the main file forces
    # the loader to degrade to a fresh disabled state.
    service.state_path.write_text("{ not json", encoding="utf-8")

    reloaded = TrialAccessService(workspace, key_provider=lambda: "sk-test-trial")

    status = reloaded.status()
    assert status.enabled is False
    assert status.claimed_attempts == 0
    assert status.remaining == TRIAL_GENERATION_LIMIT


def test_file_key_provider_reads_strips_and_returns_none_when_missing(
    tmp_path: Path,
) -> None:
    key_path = tmp_path / "trial_api_key.txt"
    key_path.write_text("  sk-test-trial  \n", encoding="ascii")

    provider = FileTrialKeyProvider(key_path)

    assert provider() == "sk-test-trial"
    assert provider() == "sk-test-trial"  # cached
    assert FileTrialKeyProvider(tmp_path / "missing.txt")() is None


def test_static_secret_store_exposes_secret_and_environment_source() -> None:
    store = StaticSecretStore("sk-test-trial")

    assert store.get_api_key() is not None
    assert store.get_api_key().get_secret_value() == "sk-test-trial"
    assert store.get_source() is ApiKeySource.ENVIRONMENT


def test_trial_provider_settings_use_frozen_preset(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    settings = service.trial_provider_settings()

    assert settings.base_url == TRIAL_BASE_URL
    assert settings.vision_model == TRIAL_VISION_MODEL
    assert settings.text_model == TRIAL_TEXT_MODEL
    assert settings.image_model == TRIAL_IMAGE_MODEL
    assert settings.chat_timeout_seconds == TRIAL_CHAT_TIMEOUT_SECONDS
    assert settings.image_timeout_seconds == TRIAL_IMAGE_TIMEOUT_SECONDS
    assert settings.max_automatic_retries == TRIAL_MAX_AUTOMATIC_RETRIES


def test_trial_secret_store_is_static_and_environment_sourced(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    store = service.trial_secret_store()

    assert store.get_api_key() is not None
    assert store.get_api_key().get_secret_value() == "sk-test-trial"
    assert store.get_source() is ApiKeySource.ENVIRONMENT


def test_trial_limit_error_code_and_recommended_action() -> None:
    error = AppError(
        code="PTS_TRIAL_LIMIT_REACHED",
        message="你已经达到试用额度，请配置自己的服务。",
        http_status=409,
        details={},
        retryable=False,
    )

    assert error.code == "PTS_TRIAL_LIMIT_REACHED"
    assert error.http_status == 409
    assert error.retryable is False
    assert recommended_action("PTS_TRIAL_LIMIT_REACHED") == "CHECK_LOCAL_CONFIGURATION"
    assert recommended_action("PTS_TRIAL_UNAVAILABLE") == "CHECK_LOCAL_CONFIGURATION"


# ---------------------------------------------------------------------------
# TrialSafeGateway (T30-TRIAL-001): provider internals must never reach the
# client on the trial path. The wrapper strips AppError details (which may echo
# the trial Base URL / model ID / key) while preserving the rest of the error;
# successful results and non-AppError exceptions pass through unchanged.
# ---------------------------------------------------------------------------

_METHODS = ("analyze_dish", "design_ask_gus", "generate_image")
_RESULT_ATTR = {
    "analyze_dish": "analyze_result",
    "design_ask_gus": "design_result",
    "generate_image": "image_result",
}


class _StubGateway:
    """Deterministic ModelGateway stub with a configurable outcome per method."""

    def __init__(self) -> None:
        self.analyze_result: DishAnalysis | BaseException = analysis_fixture()
        self.design_result: GeneratedDishCore | BaseException = core_fixture()
        self.image_result: GeneratedImage | BaseException = GeneratedImage(
            data=_png_bytes(), media_type=ImageMediaType.PNG
        )

    async def analyze_dish(
        self, request, *, json_only: bool = False
    ) -> DishAnalysis:
        if isinstance(self.analyze_result, BaseException):
            raise self.analyze_result
        return self.analyze_result

    async def design_ask_gus(
        self, request, *, json_only: bool = False
    ) -> GeneratedDishCore:
        if isinstance(self.design_result, BaseException):
            raise self.design_result
        return self.design_result

    async def generate_image(self, request) -> GeneratedImage:
        if isinstance(self.image_result, BaseException):
            raise self.image_result
        return self.image_result


def _echoing_provider_error() -> AppError:
    """Provider error whose details echo the trial URL / model ID / key."""
    return AppError(
        code="PTS_PROVIDER_REQUEST_FAILED",
        message="Provider 返回了无法处理的响应。",
        http_status=502,
        details={
            "providerError": "https://yibuapi.com/v1 gpt-5.6-luna sk-test-trial",
            "providerHttpStatus": 502,
        },
        retryable=True,
    )


def _set_result(stub: _StubGateway, method: str, result: object) -> None:
    setattr(stub, _RESULT_ATTR[method], result)


async def _invoke(gateway: TrialSafeGateway, method: str) -> object:
    if method == "analyze_dish":
        return await gateway.analyze_dish(
            DishAnalysisRequest(
                image=ProviderImageInput(
                    data=_png_bytes(), media_type=ImageMediaType.PNG
                ),
                language=Language.ZH_CN,
                request_id=uuid4(),
            )
        )
    if method == "design_ask_gus":
        return await gateway.design_ask_gus(
            AskGusDesignRequest(
                analysis=analysis_fixture(),
                language=Language.ZH_CN,
                request_id=uuid4(),
            )
        )
    return await gateway.generate_image(
        ImageGenerationRequest(
            operation=ImageOperation.GENERATION,
            prompt="A dish icon",
            request_id=uuid4(),
        )
    )


async def test_trial_safe_gateway_strips_app_error_details() -> None:
    for method in _METHODS:
        stub = _StubGateway()
        _set_result(stub, method, _echoing_provider_error())
        gateway = TrialSafeGateway(stub)

        with pytest.raises(AppError) as raised:
            await _invoke(gateway, method)

        error = raised.value
        assert error.code == "PTS_PROVIDER_REQUEST_FAILED"
        assert error.message == "Provider 返回了无法处理的响应。"
        assert error.http_status == 502
        assert error.retryable is True
        assert error.details == {}
        assert "yibuapi" not in str(error.details)
        assert "sk-test-trial" not in str(error.details)


async def test_trial_safe_gateway_passes_results_through() -> None:
    for method in _METHODS:
        stub = _StubGateway()
        expected = getattr(stub, _RESULT_ATTR[method])
        gateway = TrialSafeGateway(stub)

        result = await _invoke(gateway, method)

        assert result is expected


async def test_trial_safe_gateway_passes_non_app_errors_through() -> None:
    for method in _METHODS:
        stub = _StubGateway()
        inner_error = RuntimeError("boom")
        _set_result(stub, method, inner_error)
        gateway = TrialSafeGateway(stub)

        with pytest.raises(RuntimeError) as raised:
            await _invoke(gateway, method)

        assert raised.value is inner_error
