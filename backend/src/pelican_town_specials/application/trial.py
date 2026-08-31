"""Local soft-quota trial access service (Task 30).

A lightweight, local-only newcomer trial: a hidden trial profile with a soft
local quota (``app-state/trial-state.json``) and a frozen provider preset. The
trial API key is delivered as a gitignored resource file injected from the CI
secret ``PTS_TRIAL_API_KEY``; when the resource is absent the trial reports
``available=false`` and other functionality is unaffected.

This module intentionally does not extend the core domain layer (R-08): the
trial state/status models and preset constants live here in the application
layer.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, SecretStr, field_validator

from pelican_town_specials.application.settings import (
    ProviderSettings,
    SecretStore,
)
from pelican_town_specials.domain.common import StrictModel
from pelican_town_specials.domain.errors import (
    AppError,
    trial_unavailable_error,
)
from pelican_town_specials.persistence.atomic import (
    atomic_write_json,
    read_json_with_backup,
)
from pelican_town_specials.persistence.secret_store import ApiKeySource
from pelican_town_specials.persistence.workspace import WorkspacePaths
from pelican_town_specials.providers.contracts import (
    AskGusDesignRequest,
    CanonicalMatchRequest,
    CanonicalMatchResponse,
    DishAnalysis,
    DishAnalysisRequest,
    GeneratedDishCore,
    GeneratedImage,
    ImageGenerationRequest,
    ModelGateway,
)

TRIAL_GENERATION_LIMIT = 2
TRIAL_BASE_URL = "https://yibuapi.com/v1"
TRIAL_VISION_MODEL = "gpt-5.6-luna"
TRIAL_TEXT_MODEL = "gpt-5.6-luna"
TRIAL_IMAGE_MODEL = "gpt-image-2-max"
TRIAL_CHAT_TIMEOUT_SECONDS = 120
TRIAL_IMAGE_TIMEOUT_SECONDS = 300
TRIAL_MAX_AUTOMATIC_RETRIES = 0


class TrialProviderPreference(str, Enum):
    """Internal routing preference reserved for Task 40/Task 41."""

    TRIAL_FIRST = "TRIAL_FIRST"
    PERSONAL = "PERSONAL"


class TrialState(StrictModel):
    """Persisted local trial state for reserve-then-commit accounting.

    Reservations are intentionally ephemeral: the service clears every
    unconfirmed reservation during startup, while committed attempts retain a
    fixed ``remainingAfterCommit`` snapshot for idempotent retries.
    """

    schema_version: Literal[2] = 2
    enabled: bool = False
    consumed_attempts: int = Field(default=0, ge=0)
    reservations: list[str] = Field(default_factory=list)
    committed_attempts: dict[str, int] = Field(default_factory=dict)
    provider_preference: TrialProviderPreference = TrialProviderPreference.TRIAL_FIRST

    @field_validator("provider_preference", mode="before")
    @classmethod
    def _validate_provider_preference(
        cls, value: TrialProviderPreference | str
    ) -> TrialProviderPreference:
        if isinstance(value, TrialProviderPreference):
            return value
        try:
            return TrialProviderPreference(value)
        except ValueError as exc:
            raise ValueError("invalid trial provider preference") from exc

    @property
    def claimed_attempts(self) -> int:
        """Compatibility view for the unchanged public Settings contract."""

        return self.consumed_attempts


class TrialStatus(StrictModel):
    """Safe public trial status exposed to the Settings UI."""

    available: bool
    enabled: bool
    claimed_attempts: int
    limit: int
    remaining: int
    provider_preference: TrialProviderPreference = TrialProviderPreference.TRIAL_FIRST


class FileTrialKeyProvider:
    """Read the trial API key from a gitignored resource file, caching the result.

    Any read failure (missing file, unreadable path, empty value) degrades to
    ``None`` so the trial simply reports unavailable instead of crashing.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._cached: str | None = None
        self._read = False

    def __call__(self) -> str | None:
        if not self._read:
            self._read = True
            try:
                value = self._path.read_text(encoding="ascii").strip()
            except OSError:
                value = ""
            self._cached = value or None
        return self._cached


class StaticSecretStore:
    """A minimal SecretStore fixed to the trial key and an ENVIRONMENT source."""

    def __init__(self, api_key: str) -> None:
        self._api_key = SecretStr(api_key)

    def get_api_key(self) -> SecretStr | None:
        return self._api_key

    def get_source(self) -> ApiKeySource:
        return ApiKeySource.ENVIRONMENT


class TrialSafeGateway:
    """ModelGateway wrapper that strips provider internals from trial errors.

    The trial preset (Base URL, model ID, API key) must never reach the client.
    Any ``AppError`` raised by the inner gateway is re-raised with empty
    ``details`` while preserving ``code`` / ``message`` / ``http_status`` /
    ``retryable``; successful results and non-``AppError`` exceptions pass
    through unchanged. This wrapper is applied only on the trial path (see the
    app's ``_trial_gateway_factory``); the personal provider path keeps its
    full diagnostics.
    """

    def __init__(self, inner: ModelGateway) -> None:
        self._inner = inner

    async def analyze_dish(
        self, request: DishAnalysisRequest, *, json_only: bool = False
    ) -> DishAnalysis:
        try:
            return await self._inner.analyze_dish(request, json_only=json_only)
        except AppError as exc:
            raise _trial_safe_error(exc) from exc

    async def design_ask_gus(
        self, request: AskGusDesignRequest, *, json_only: bool = False
    ) -> GeneratedDishCore:
        try:
            return await self._inner.design_ask_gus(request, json_only=json_only)
        except AppError as exc:
            raise _trial_safe_error(exc) from exc

    async def match_canonical(
        self,
        request: CanonicalMatchRequest,
        *,
        json_only: bool = False,
    ) -> CanonicalMatchResponse:
        try:
            return await self._inner.match_canonical(request, json_only=json_only)
        except AppError as exc:
            raise _trial_safe_error(exc) from exc

    async def generate_image(self, request: ImageGenerationRequest) -> GeneratedImage:
        try:
            return await self._inner.generate_image(request)
        except AppError as exc:
            raise _trial_safe_error(exc) from exc


def _trial_safe_error(error: AppError) -> AppError:
    """Rebuild an AppError with empty details for the trial path.

    Preserves the error contract (code/message/http_status/retryable) while
    dropping ``details`` that may echo the trial Base URL, model ID or key.
    """
    return AppError(
        code=error.code,
        message=error.message,
        http_status=error.http_status,
        details={},
        retryable=error.retryable,
    )


class TrialAccessService:
    """Local trial enrollment and soft-quota accounting.

    ``enable()`` marks the trial profile active; ``reserve_attempt()`` records
    an in-flight reservation before the first possibly-paid provider call;
    ``commit_attempt()`` consumes it only after the complete generation attempt
    succeeds and the Draft has been promoted. ``release_attempt()`` returns an
    unconfirmed reservation. Saving personal provider settings or an API key
    calls ``disable()``, which preserves the consumed count so re-enabling
    reuses the remaining quota (R-05, T30-TRIAL-004).
    """

    def __init__(
        self,
        workspace: WorkspacePaths,
        *,
        key_provider: Callable[[], str | None],
        limit: int = TRIAL_GENERATION_LIMIT,
    ) -> None:
        self._workspace = workspace
        self._key_provider = key_provider
        self._limit = limit
        self._lock = threading.Lock()
        self._state = self._load()

    @property
    def state_path(self) -> Path:
        return self._workspace.app_state_dir / "trial-state.json"

    @property
    def available(self) -> bool:
        key = self._key_provider()
        return bool(key and key.strip())

    def is_active(self) -> bool:
        with self._lock:
            return self._state.enabled

    def trial_opportunity(self) -> bool:
        """True when the trial is ready and still has quota to reserve.

        R-09 trial-first routing: a user who already configured their own
        provider reserves the free trial allowance before their personal
        provider is billed. The opt-in ``enabled`` flag is deliberately not
        required here — the trial is preferred automatically while an
        opportunity exists.
        """
        if not self.available:
            return False
        with self._lock:
            return self._capacity_available(self._state)

    def reserve_attempt(self, attempt_id: UUID) -> bool:
        """Atomically reserve one attempt, without consuming quota.

        The opt-in ``enabled`` gate is enforced by the orchestrator's
        non-configured path (``is_active()``) before any reservation is
        attempted.
        R-09: a configured user drains the free allowance automatically without
        clicking the opt-in, so an active quota is reservable regardless of the
        ``enabled`` flag. An exhausted quota always returns ``False``.

        Repeating a reservation for the same attempt is a successful no-op;
        this makes request retries safe before the provider call starts.
        """
        with self._lock:
            key = str(attempt_id)
            if key in self._state.committed_attempts:
                return True
            if key in self._state.reservations:
                return True
            if not self._capacity_available(self._state):
                return False
            reserved = self._state.model_copy(
                update={"reservations": [*self._state.reservations, key]}
            )
            self._save(reserved)
            self._state = reserved
            return True

    def commit_attempt(self, attempt_id: UUID) -> int | None:
        """Consume a reservation and return its fixed remaining snapshot.

        A repeated commit returns the original snapshot. Unknown attempts are
        a no-op and return ``None``; callers only commit attempts they
        successfully reserved.
        """
        with self._lock:
            key = str(attempt_id)
            committed = self._state.committed_attempts.get(key)
            if committed is not None:
                return committed
            if key not in self._state.reservations:
                return None
            consumed = self._state.consumed_attempts + 1
            remaining = max(self._limit - consumed, 0)
            committed_state = self._state.model_copy(
                update={
                    "consumed_attempts": consumed,
                    "reservations": [
                        item for item in self._state.reservations if item != key
                    ],
                    "committed_attempts": {
                        **self._state.committed_attempts,
                        key: remaining,
                    },
                }
            )
            self._save(committed_state)
            self._state = committed_state
            return remaining

    def release_attempt(self, attempt_id: UUID) -> bool:
        """Release an unconfirmed reservation; committed attempts are final."""
        with self._lock:
            key = str(attempt_id)
            if key not in self._state.reservations:
                return False
            released = self._state.model_copy(
                update={
                    "reservations": [
                        item for item in self._state.reservations if item != key
                    ]
                }
            )
            self._save(released)
            self._state = released
            return True

    def claim_attempt(self) -> bool:
        """Legacy v1 compatibility shim for non-orchestrator callers.

        Task 40 routing uses the explicit reserve/commit/release API. Existing
        application-level callers retain the old one-shot behavior through a
        private synthetic attempt ID, so the public Settings contract remains
        unchanged while old tests and integrations continue to work.
        """
        attempt_id = uuid4()
        if not self.reserve_attempt(attempt_id):
            return False
        return self.commit_attempt(attempt_id) is not None

    def enable(self) -> TrialStatus:
        if not self.available:
            raise trial_unavailable_error()
        with self._lock:
            enabled_state = self._state.model_copy(
                update={
                    "enabled": True,
                    "provider_preference": TrialProviderPreference.TRIAL_FIRST,
                }
            )
            self._save(enabled_state)
            self._state = enabled_state
            return self._to_status(enabled_state)

    def disable(self) -> TrialStatus:
        with self._lock:
            if self._state.enabled:
                disabled_state = self._state.model_copy(update={"enabled": False})
                self._save(disabled_state)
                self._state = disabled_state
                return self._to_status(disabled_state)
            return self._to_status(self._state)

    def status(self) -> TrialStatus:
        with self._lock:
            return self._to_status(self._state)

    def preference(self) -> TrialProviderPreference:
        """Return the persisted gateway preference without touching quota."""
        with self._lock:
            return self._state.provider_preference

    def set_preference(
        self, mode: TrialProviderPreference | str
    ) -> TrialStatus:
        """Persist an explicit gateway preference without changing trial state."""
        preference = (
            mode
            if isinstance(mode, TrialProviderPreference)
            else TrialProviderPreference(mode)
        )
        with self._lock:
            if self._state.provider_preference is preference:
                return self._to_status(self._state)
            updated = self._state.model_copy(
                update={"provider_preference": preference}
            )
            self._save(updated)
            self._state = updated
            return self._to_status(updated)

    def trial_provider_settings(self) -> ProviderSettings:
        return ProviderSettings(
            base_url=TRIAL_BASE_URL,
            vision_model=TRIAL_VISION_MODEL,
            text_model=TRIAL_TEXT_MODEL,
            image_model=TRIAL_IMAGE_MODEL,
            chat_timeout_seconds=TRIAL_CHAT_TIMEOUT_SECONDS,
            image_timeout_seconds=TRIAL_IMAGE_TIMEOUT_SECONDS,
            max_automatic_retries=TRIAL_MAX_AUTOMATIC_RETRIES,
        )

    def trial_secret_store(self) -> SecretStore:
        key = self._key_provider()
        if not key:
            raise trial_unavailable_error()
        return StaticSecretStore(key)

    def _to_status(self, state: TrialState) -> TrialStatus:
        return TrialStatus(
            available=self.available,
            enabled=state.enabled,
            claimed_attempts=state.claimed_attempts,
            limit=self._limit,
            remaining=max(self._limit - state.claimed_attempts, 0),
            provider_preference=state.provider_preference,
        )

    def _capacity_available(self, state: TrialState) -> bool:
        return state.consumed_attempts + len(state.reservations) < self._limit

    def _load(self) -> TrialState:
        try:
            state_path = self.state_path
            if not state_path.exists():
                backup = state_path.with_suffix(f"{state_path.suffix}.bak")
                if not backup.exists():
                    return TrialState()
            state, changed = self._normalize_state_payload(
                read_json_with_backup(state_path, lambda payload: payload)
            )
            if changed:
                self._save(state)
            return state
        except Exception:  # noqa: BLE001 - soft local quota: any read failure degrades to a fresh disabled trial state.
            return TrialState()

    def _normalize_state_payload(self, payload: object) -> tuple[TrialState, bool]:
        if not isinstance(payload, Mapping):
            raise TypeError("trial state must be an object")
        schema_version = payload.get("schemaVersion", payload.get("schema_version"))
        if schema_version == 1:
            allowed = {
                "schemaVersion",
                "schema_version",
                "enabled",
                "claimedAttempts",
                "claimed_attempts",
            }
            if set(payload) - allowed:
                raise ValueError("unknown v1 trial state fields")
            enabled = payload.get("enabled", False)
            claimed = payload.get(
                "claimedAttempts", payload.get("claimed_attempts", 0)
            )
            if not isinstance(enabled, bool) or not isinstance(claimed, int):
                raise TypeError("invalid v1 trial state")
            if isinstance(claimed, bool) or claimed < 0:
                raise ValueError("invalid v1 claimed attempts")
            return (
                TrialState(enabled=enabled, consumed_attempts=claimed),
                True,
            )
        if schema_version != 2:
            raise ValueError("unknown trial state schema")
        normalized = dict(payload)
        preference = normalized.get(
            "providerPreference", normalized.get("provider_preference")
        )
        if isinstance(preference, str):
            normalized[
                "providerPreference"
            ] = TrialProviderPreference(preference)
        state = TrialState.model_validate(normalized)
        if state.reservations:
            return state.model_copy(update={"reservations": []}), True
        return state, False

    def _save(self, state: TrialState) -> None:
        atomic_write_json(
            self.state_path,
            state.model_dump(by_alias=True, mode="json"),
        )


__all__ = [
    "TRIAL_BASE_URL",
    "TRIAL_CHAT_TIMEOUT_SECONDS",
    "TRIAL_GENERATION_LIMIT",
    "TRIAL_IMAGE_MODEL",
    "TRIAL_IMAGE_TIMEOUT_SECONDS",
    "TRIAL_MAX_AUTOMATIC_RETRIES",
    "TRIAL_TEXT_MODEL",
    "TRIAL_VISION_MODEL",
    "FileTrialKeyProvider",
    "StaticSecretStore",
    "TrialAccessService",
    "TrialProviderPreference",
    "TrialSafeGateway",
    "TrialState",
    "TrialStatus",
]
