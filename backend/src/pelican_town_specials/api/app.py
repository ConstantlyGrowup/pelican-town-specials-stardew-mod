from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from uuid import UUID

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from starlette.middleware.base import RequestResponseEndpoint

from pelican_town_specials.api.error_handlers import (
    handle_app_error,
    register_error_handlers,
)
from pelican_town_specials.api.routes import (
    app_control,
    assets,
    catalog,
    cookbook,
    diagnostics,
    drafts,
    exports,
    generation,
    health,
    meta,
    session,
    settings,
)
from pelican_town_specials.api.routes.app_control import ActivityTracker
from pelican_town_specials.api.routes.settings import ProviderKeyStore
from pelican_town_specials.api.security import (
    SecurityState,
    is_safe_method,
    require_mutation_security,
    require_session,
)
from pelican_town_specials.application.assets import AssetService
from pelican_town_specials.application.canonical_memory import (
    CanonicalRegistrationService,
)
from pelican_town_specials.application.catalog import CatalogService
from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.application.exports import ExportService
from pelican_town_specials.application.generation import GenerationService
from pelican_town_specials.application.meta import MetaService
from pelican_town_specials.application.settings import (
    ProviderSettings,
    ProviderSettingsService,
    SecretStore,
)
from pelican_town_specials.application.telemetry import (
    TelemetryRecorder,
    TelemetryService,
)
from pelican_town_specials.application.trial import (
    FileTrialKeyProvider,
    TrialAccessService,
    TrialSafeGateway,
)
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.config import AppConfig
from pelican_town_specials.domain.canonical import CanonicalRepository
from pelican_town_specials.domain.draft import AttemptStatus, DraftStatus
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import GenerationOrchestrator
from pelican_town_specials.mod_compiler.compiler import ContentPatcherCompiler
from pelican_town_specials.observability.diagnostics import DiagnosticsBuilder
from pelican_town_specials.observability.logging import configure_logging, log_event
from pelican_town_specials.observability.posthog_telemetry import (
    build_telemetry_recorder,
)
from pelican_town_specials.persistence.asset_store import FileAssetStore
from pelican_town_specials.persistence.canonical_registry import (
    CanonicalRegistryUnavailableError,
    SQLiteCanonicalRegistry,
)
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
    ExportRepository,
    GenerationAttemptRepository,
)
from pelican_town_specials.persistence.secret_store import WindowsEnvironmentSecretStore
from pelican_town_specials.persistence.telemetry_state import TelemetryStateStore
from pelican_town_specials.persistence.workspace import WorkspacePaths
from pelican_town_specials.providers.contracts import ModelGateway
from pelican_town_specials.providers.openai_compatible import OpenAICompatibleGateway

_CATALOG_RELATIVE_PATH = (
    Path("resources")
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)
_TELEMETRY_CONFIG_RELATIVE_PATH = (
    Path("resources") / "telemetry" / "telemetry.json"
)


def create_app(
    config: AppConfig | None = None,
    *,
    workspace_paths: WorkspacePaths | None = None,
    secret_store: ProviderKeyStore | None = None,
    security_state: SecurityState | None = None,
    static_dir: Path | None = None,
    activity_tracker: ActivityTracker | None = None,
    enable_docs: bool = True,
    enforce_local_host: bool = False,
    asset_store: FileAssetStore | None = None,
    draft_repository: DraftRepository | None = None,
    archive_repository: ArchiveRepository | None = None,
    vanilla_catalog: VanillaCatalog | None = None,
    asset_service: AssetService | None = None,
    draft_service: DraftService | None = None,
    cookbook_service: CookbookService | None = None,
    canonical_registry: CanonicalRepository | None = None,
    canonical_registration_service: CanonicalRegistrationService | None = None,
    attempt_repository: GenerationAttemptRepository | None = None,
    attempt_registry: AttemptRegistry | None = None,
    generation_service: GenerationService | None = None,
    export_service: ExportService | None = None,
    trial_access_service: TrialAccessService | None = None,
    telemetry_recorder: TelemetryRecorder | None = None,
    telemetry_state_store: TelemetryStateStore | None = None,
    telemetry_service: TelemetryService | None = None,
    telemetry_clock: Callable[[], object] | None = None,
) -> FastAPI:
    app_config = config if config is not None else AppConfig()
    resolved_workspace = workspace_paths or WorkspacePaths.create(
        app_config.workspace_path
    )
    resolved_telemetry_state_store = telemetry_state_store or TelemetryStateStore(
        resolved_workspace.telemetry_state_path
    )
    resolved_telemetry_service = telemetry_service
    if resolved_telemetry_service is None:
        telemetry_state = resolved_telemetry_state_store.ensure_state()
        resolved_telemetry_recorder = telemetry_recorder
        if resolved_telemetry_recorder is None:
            resolved_telemetry_recorder = build_telemetry_recorder(
                config_path=_resolve_telemetry_config_path(),
                installation_id=(
                    telemetry_state.installation_id if telemetry_state else None
                ),
            )
        resolved_telemetry_service = TelemetryService(
            resolved_telemetry_recorder,
            resolved_telemetry_state_store,
            clock=(
                telemetry_clock  # type: ignore[arg-type]
                if telemetry_clock is not None
                else None
            ),
        )
    else:
        resolved_telemetry_state_store = resolved_telemetry_service.state_store
    business_telemetry = cast(TelemetryRecorder, resolved_telemetry_service)
    resolved_secret_store = secret_store or WindowsEnvironmentSecretStore()
    logs_dir = resolved_workspace.app_state_dir / "logs"
    configure_logging(logs_dir)
    diagnostics_builder = DiagnosticsBuilder(workspace=resolved_workspace)

    resolved_asset_store = asset_store or FileAssetStore(resolved_workspace)
    resolved_draft_repository = draft_repository or DraftRepository(resolved_workspace)
    resolved_archive_repository = archive_repository or ArchiveRepository(
        resolved_workspace
    )
    resolved_canonical_registry = canonical_registry
    if resolved_canonical_registry is None and canonical_registration_service is None:
        try:
            resolved_canonical_registry = SQLiteCanonicalRegistry(resolved_workspace)
        except Exception as exc:  # noqa: BLE001 - registry must fail open
            log_event(
                logging.WARNING,
                error_code="PTS_CANONICAL_REGISTRY_DISABLED",
                usage={
                    "operation": "registry_initialization",
                    "reason": (
                        "REGISTRY_UNAVAILABLE"
                        if isinstance(exc, CanonicalRegistryUnavailableError)
                        else "INITIALIZATION_FAILED"
                    ),
                },
            )
            resolved_canonical_registry = None
    resolved_canonical_registration = canonical_registration_service
    if resolved_canonical_registration is None and resolved_canonical_registry is not None:
        resolved_canonical_registration = CanonicalRegistrationService(
            registry=resolved_canonical_registry,
            archive_repository=resolved_archive_repository,
            draft_repository=resolved_draft_repository,
            asset_store=resolved_asset_store,
        )
    resolved_catalog = vanilla_catalog or _load_default_catalog()
    resolved_asset_service = asset_service or AssetService(resolved_asset_store)
    resolved_attempt_repository = attempt_repository or GenerationAttemptRepository(
        resolved_workspace
    )
    attempt_registry = attempt_registry or AttemptRegistry(
        attempt_status_resolver=_attempt_status_resolver(resolved_attempt_repository)
    )
    resolved_draft_service = draft_service or DraftService(
        draft_repository=resolved_draft_repository,
        archive_repository=resolved_archive_repository,
        asset_store=resolved_asset_store,
        catalog=resolved_catalog,
        attempt_repository=resolved_attempt_repository,
        attempt_registry=attempt_registry,
        canonical_registration_service=resolved_canonical_registration,
        telemetry=business_telemetry,
    )
    resolved_cookbook_service = cookbook_service or CookbookService(
        resolved_archive_repository,
        draft_service=resolved_draft_service,
    )
    resolved_export_repository = ExportRepository(resolved_workspace)
    resolved_compiler = ContentPatcherCompiler(
        asset_store=resolved_asset_store,
        author_name=resolved_workspace.author_name,
    )
    resolved_export_service = export_service or ExportService(
        export_repository=resolved_export_repository,
        archive_repository=resolved_archive_repository,
        asset_store=resolved_asset_store,
        catalog=resolved_catalog,
        compiler=resolved_compiler,
        workspace=resolved_workspace,
        open_folder=_default_open_folder(),
        telemetry=business_telemetry,
    )
    resolved_catalog_service = CatalogService(resolved_catalog)
    resolved_meta_service = MetaService()
    resolved_provider_settings_service = ProviderSettingsService(
        resolved_workspace,
        resolved_secret_store,
    )

    resolved_trial_service = trial_access_service or TrialAccessService(
        workspace=resolved_workspace,
        key_provider=FileTrialKeyProvider(_resolve_trial_key_path()),
    )

    resolved_activity_tracker = activity_tracker or ActivityTracker()

    resolved_generation_service = generation_service or GenerationService(
        orchestrator=GenerationOrchestrator(
            draft_repository=resolved_draft_repository,
            attempt_repository=resolved_attempt_repository,
            asset_store=resolved_asset_store,
            catalog=resolved_catalog,
            gateway_factory=_gateway_factory(
                settings_service=resolved_provider_settings_service,
                secret_store=resolved_secret_store,
            ),
            registry=attempt_registry,
            min_confidence=app_config.ask_gus_min_confidence,
            trial_access=resolved_trial_service,
            trial_gateway_factory=_trial_gateway_factory(resolved_trial_service),
            personal_configured=_personal_provider_configured(
                resolved_provider_settings_service
            ),
            canonical_repository=resolved_canonical_registry,
            telemetry=business_telemetry,
        ),
        draft_repository=resolved_draft_repository,
        telemetry=business_telemetry,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Recover attempts interrupted by a previous process crash; never
        # resume provider calls automatically after a restart.
        resolved_attempt_repository.interrupt_running()
        # Task 19.6 (startup sweep narrowing): this sweep only handles truly
        # cross-process leftovers — drafts a previous process left in a
        # generating state when it died. It is deliberately NOT the cleanup
        # path for client disconnects (Task 19.2 server ownership keeps the
        # generation running) or for deleted drafts (Task 19.4 reclaims the
        # slot). Within a live process the attributable slot reconciles itself
        # (Task 19.1), so a fresh generation started here is never swept.
        for draft in resolved_draft_repository.list():
            if (
                draft.active_attempt_id is not None
                and draft.status
                in (
                    DraftStatus.GENERATING,
                    DraftStatus.REGENERATING,
                    DraftStatus.STALE_PREVIEW,
                )
            ):
                resolved_generation_service.recover_interrupted(draft.draft_id)
        if resolved_canonical_registration is not None:
            try:
                resolved_canonical_registration.reconcile_active_archives()
            except Exception:  # noqa: BLE001 - reconciliation must not block startup
                log_event(
                    logging.WARNING,
                    error_code="PTS_CANONICAL_RECONCILIATION_FAILED",
                    usage={
                        "operation": "startup_reconciliation",
                        "reason": "UNEXPECTED_FAILURE",
                    },
                )
        try:
            await resolved_telemetry_service.startup()
        except Exception:  # noqa: BLE001 - telemetry must never block startup
            log_event(
                logging.WARNING,
                error_code="PTS_TELEMETRY_STARTUP_FAILED",
                usage={
                    "operation": "telemetry_startup",
                    "reason": "UNEXPECTED_FAILURE",
                },
            )
        monitor_task: asyncio.Task[None] | None = None
        if resolved_activity_tracker.has_shutdown_callback:
            monitor_task = asyncio.create_task(
                _monitor_activity(resolved_activity_tracker, attempt_registry)
            )
        try:
            yield
        finally:
            if monitor_task is not None:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            try:
                await resolved_telemetry_service.shutdown(timeout_seconds=1.0)
            except Exception:  # noqa: BLE001 - telemetry must never block shutdown
                log_event(
                    logging.WARNING,
                    error_code="PTS_TELEMETRY_SHUTDOWN_FAILED",
                    usage={
                        "operation": "telemetry_shutdown",
                        "reason": "UNEXPECTED_FAILURE",
                    },
                )

    app = FastAPI(
        title="PelicanTownSpecials API",
        version="1.5.0",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
        lifespan=lifespan,
    )
    app.state.config = app_config
    app.state.workspace_paths = resolved_workspace
    app.state.telemetry_state_store = resolved_telemetry_state_store
    app.state.telemetry_service = resolved_telemetry_service
    app.state.telemetry_recorder = resolved_telemetry_service.recorder
    app.state.telemetry = resolved_telemetry_service
    app.state.secret_store = resolved_secret_store
    app.state.security = security_state or SecurityState()
    app.state.static_dir = static_dir
    app.state.activity_tracker = resolved_activity_tracker
    app.state.enforce_local_host = enforce_local_host
    app.state.provider_settings_service = resolved_provider_settings_service
    app.state.trial_service = resolved_trial_service
    app.state.asset_store = resolved_asset_store
    app.state.draft_repository = resolved_draft_repository
    app.state.archive_repository = resolved_archive_repository
    app.state.canonical_registry = resolved_canonical_registry
    app.state.canonical_registration_service = resolved_canonical_registration
    app.state.vanilla_catalog = resolved_catalog
    app.state.asset_service = resolved_asset_service
    app.state.draft_service = resolved_draft_service
    app.state.cookbook_service = resolved_cookbook_service
    app.state.catalog_service = resolved_catalog_service
    app.state.meta_service = resolved_meta_service
    app.state.attempt_repository = resolved_attempt_repository
    app.state.generation_service = resolved_generation_service
    app.state.attempt_registry = attempt_registry
    app.state.export_repository = resolved_export_repository
    app.state.export_service = resolved_export_service
    app.state.diagnostics_builder = diagnostics_builder
    register_error_handlers(app)
    app.include_router(session.router)
    app.include_router(app_control.router)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")
    app.include_router(assets.router, prefix="/api/v1")
    app.include_router(drafts.router, prefix="/api/v1")
    app.include_router(generation.router, prefix="/api/v1")
    app.include_router(cookbook.router, prefix="/api/v1")
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(meta.router, prefix="/api/v1")
    app.include_router(exports.router, prefix="/api/v1")
    app.include_router(diagnostics.router, prefix="/api/v1")

    @app.middleware("http")
    async def enforce_local_session(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        try:
            if app.state.enforce_local_host:
                app.state.security.require_allowed_host(request.headers.get("host"))
            if not request.url.path.startswith("/api/v1/"):
                return await call_next(request)
            if request.url.path == "/api/v1/health":
                app.state.security.require_allowed_host(request.headers.get("host"))
            elif is_safe_method(request.method):
                require_session(request)
            else:
                require_mutation_security(request)
        except AppError as exc:
            return await handle_app_error(request, exc)
        return await call_next(request)

    @app.get("/{static_path:path}", include_in_schema=False)
    def serve_static_frontend(request: Request, static_path: str = "") -> Response:
        app.state.security.require_allowed_host(request.headers.get("host"))
        configured_static_dir = app.state.static_dir
        if configured_static_dir is None:
            return Response(status_code=404)
        if not configured_static_dir.is_dir():
            raise AppError(
                code="PTS_SYSTEM_WEB_ASSETS_MISSING",
                message="应用界面资源不可用，请重新安装应用后再试。",
                http_status=500,
                details={},
                retryable=False,
            )

        root_dir = configured_static_dir.resolve()
        index_candidate = _static_candidate(root_dir, "index.html")
        if index_candidate is None or not index_candidate.is_file():
            raise AppError(
                code="PTS_SYSTEM_WEB_ASSETS_MISSING",
                message="应用界面资源不可用，请重新安装应用后再试。",
                http_status=500,
                details={},
                retryable=False,
            )

        if _is_reserved_static_path(static_path):
            return Response(status_code=404)
        candidate = _static_candidate(root_dir, static_path)
        if candidate is not None and candidate.is_file():
            return FileResponse(candidate)
        if _accepts_html(request) and not static_path.startswith("assets/"):
            return FileResponse(index_candidate)
        return Response(status_code=404)

    return app


def _attempt_status_resolver(
    repository: GenerationAttemptRepository,
) -> Callable[[UUID], AttemptStatus | None]:
    """Return a resolver that maps an attempt id to its persisted status.

    A missing attempt record resolves to None so the attributable slot can
    reclaim a holder whose attempt was never persisted or was deleted (e.g.
    after the owning draft was removed).
    """

    def _resolve(attempt_id: UUID) -> AttemptStatus | None:
        try:
            attempt = repository.get(attempt_id)
        except (FileNotFoundError, OSError):
            return None
        return attempt.status

    return _resolve


def _resolve_repo_root() -> Path:
    """Resolve the application data root in dev and in the frozen bundle.

    PyInstaller onedir (contents_directory disabled): application data lives
    next to the executable (sys._MEIPASS == exe directory). In dev the root is
    the repository checkout.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        return Path(meipass) if meipass else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[4]


_TRIAL_KEY_RELATIVE_PATH = Path("resources") / "trial" / "trial_api_key.txt"


def _resolve_trial_key_path() -> Path:
    return _resolve_repo_root() / _TRIAL_KEY_RELATIVE_PATH


def _resolve_telemetry_config_path() -> Path:
    return _resolve_repo_root() / _TELEMETRY_CONFIG_RELATIVE_PATH


def _load_default_catalog() -> VanillaCatalog:
    return VanillaCatalog.from_json(_resolve_repo_root() / _CATALOG_RELATIVE_PATH)


def _default_open_folder() -> Callable[[Path], None] | None:
    """Return the OS file explorer opener on Windows; None elsewhere.

    The export service always verifies the target stays inside the registered
    exports directory before invoking this adapter (ruling R17-3).
    """
    if os.name == "nt":
        return os.startfile  # type: ignore[return-value]
    return None


def _personal_provider_configured(
    settings_service: ProviderSettingsService,
) -> Callable[[], bool]:
    """True when the latest safe provider settings view has a configured key.

    The callback is evaluated lazily at the first provider call of each
    attempt so a freshly saved or deleted key is honored without any reload.
    Settings read failures and malformed local state fail closed to ``False``
    because this predicate is also used to shape the redacted trial error.
    """

    def is_configured() -> bool:
        try:
            return bool(settings_service.get().api_key_configured)
        except Exception:  # noqa: BLE001 - configuration state must not leak through trial errors
            return False

    return is_configured


def _gateway_factory(
    *,
    settings_service: ProviderSettingsService,
    secret_store: SecretStore,
) -> Callable[[], ModelGateway]:
    """Build a fresh provider gateway from the latest settings on each attempt."""

    def _build() -> ModelGateway:
        view = settings_service.get()
        settings = ProviderSettings.model_validate(
            view.model_dump(exclude={"api_key_configured", "api_key_source"})
        )
        return OpenAICompatibleGateway(
            settings=settings,
            secret_store=secret_store,
        )

    return _build


def _trial_gateway_factory(
    trial_service: TrialAccessService,
) -> Callable[[], ModelGateway]:
    """Build a gateway fixed to the frozen trial preset and the injected key.

    The gateway is wrapped in ``TrialSafeGateway`` so provider internals (the
    trial Base URL, model ID, or key echoes) can never reach the client: any
    ``AppError`` raised on the trial path is re-raised with empty ``details``.
    """

    def _build() -> ModelGateway:
        return TrialSafeGateway(
            OpenAICompatibleGateway(
                settings=trial_service.trial_provider_settings(),
                secret_store=trial_service.trial_secret_store(),
            )
        )

    return _build


def _is_reserved_static_path(static_path: str) -> bool:
    return static_path.split("/", maxsplit=1)[0] in {
        "api", "app", "session", "docs", "redoc", "openapi.json"
    }


def _static_candidate(root_dir: Path, static_path: str) -> Path | None:
    relative_path = Path(static_path or "index.html")
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    candidate = (root_dir / relative_path).resolve()
    if not candidate.is_relative_to(root_dir):
        return None
    return candidate


def _accepts_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "").lower()


async def _monitor_activity(
    tracker: ActivityTracker, attempt_registry: AttemptRegistry
) -> None:
    while not tracker.shutdown_requested:
        # Task 19.6 (D5.1-3): an occupied generation slot counts as activity, so
        # the app never idle-shuts-down mid-generation. The server owns the
        # generation task independently of any browser heartbeat.
        tracker.set_busy(attempt_registry.active_count() > 0)
        if tracker.should_shutdown():
            tracker.request_shutdown()
            return
        await asyncio.sleep(tracker.poll_interval_seconds)

app = create_app()
