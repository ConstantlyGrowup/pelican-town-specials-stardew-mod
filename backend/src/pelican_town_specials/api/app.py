from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

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
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.config import AppConfig
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import GenerationOrchestrator
from pelican_town_specials.mod_compiler.compiler import ContentPatcherCompiler
from pelican_town_specials.observability.diagnostics import DiagnosticsBuilder
from pelican_town_specials.observability.logging import configure_logging
from pelican_town_specials.persistence.asset_store import FileAssetStore
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
    ExportRepository,
    GenerationAttemptRepository,
)
from pelican_town_specials.persistence.secret_store import WindowsEnvironmentSecretStore
from pelican_town_specials.persistence.workspace import WorkspacePaths
from pelican_town_specials.providers.contracts import ModelGateway
from pelican_town_specials.providers.openai_compatible import OpenAICompatibleGateway

_CATALOG_RELATIVE_PATH = (
    Path("resources")
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
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
    attempt_repository: GenerationAttemptRepository | None = None,
    generation_service: GenerationService | None = None,
    export_service: ExportService | None = None,
) -> FastAPI:
    app_config = config if config is not None else AppConfig()
    resolved_workspace = workspace_paths or WorkspacePaths.create(
        app_config.workspace_path
    )
    resolved_secret_store = secret_store or WindowsEnvironmentSecretStore()
    logs_dir = resolved_workspace.app_state_dir / "logs"
    configure_logging(logs_dir)
    diagnostics_builder = DiagnosticsBuilder(workspace=resolved_workspace)

    resolved_asset_store = asset_store or FileAssetStore(resolved_workspace)
    resolved_draft_repository = draft_repository or DraftRepository(resolved_workspace)
    resolved_archive_repository = archive_repository or ArchiveRepository(
        resolved_workspace
    )
    resolved_catalog = vanilla_catalog or _load_default_catalog()
    resolved_asset_service = asset_service or AssetService(resolved_asset_store)
    resolved_attempt_repository = attempt_repository or GenerationAttemptRepository(
        resolved_workspace
    )
    resolved_draft_service = draft_service or DraftService(
        draft_repository=resolved_draft_repository,
        archive_repository=resolved_archive_repository,
        asset_store=resolved_asset_store,
        catalog=resolved_catalog,
        attempt_repository=resolved_attempt_repository,
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
    )
    resolved_catalog_service = CatalogService(resolved_catalog)
    resolved_meta_service = MetaService()
    resolved_provider_settings_service = ProviderSettingsService(
        resolved_workspace,
        resolved_secret_store,
    )

    resolved_activity_tracker = activity_tracker or ActivityTracker()

    attempt_registry = AttemptRegistry()
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
        ),
        draft_repository=resolved_draft_repository,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Recover attempts interrupted by a previous process crash; never
        # resume provider calls automatically after a restart.
        resolved_attempt_repository.interrupt_running()
        monitor_task: asyncio.Task[None] | None = None
        if resolved_activity_tracker.has_shutdown_callback:
            monitor_task = asyncio.create_task(
                _monitor_activity(resolved_activity_tracker)
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

    app = FastAPI(
        title="PelicanTownSpecials API",
        version="1.0.0",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
        lifespan=lifespan,
    )
    app.state.config = app_config
    app.state.workspace_paths = resolved_workspace
    app.state.secret_store = resolved_secret_store
    app.state.security = security_state or SecurityState()
    app.state.static_dir = static_dir
    app.state.activity_tracker = resolved_activity_tracker
    app.state.enforce_local_host = enforce_local_host
    app.state.provider_settings_service = resolved_provider_settings_service
    app.state.asset_store = resolved_asset_store
    app.state.draft_repository = resolved_draft_repository
    app.state.archive_repository = resolved_archive_repository
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


def _load_default_catalog() -> VanillaCatalog:
    if getattr(sys, "frozen", False):
        # PyInstaller onedir (contents_directory disabled): application data
        # lives next to the executable (sys._MEIPASS == exe directory).
        meipass = getattr(sys, "_MEIPASS", None)
        repo_root = Path(meipass) if meipass else Path(sys.executable).resolve().parent
    else:
        repo_root = Path(__file__).resolve().parents[4]
    return VanillaCatalog.from_json(repo_root / _CATALOG_RELATIVE_PATH)


def _default_open_folder() -> Callable[[Path], None] | None:
    """Return the OS file explorer opener on Windows; None elsewhere.

    The export service always verifies the target stays inside the registered
    exports directory before invoking this adapter (ruling R17-3).
    """
    if os.name == "nt":
        return os.startfile  # type: ignore[return-value]
    return None


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


async def _monitor_activity(tracker: ActivityTracker) -> None:
    while not tracker.shutdown_requested:
        if tracker.should_shutdown():
            tracker.request_shutdown()
            return
        await asyncio.sleep(tracker.poll_interval_seconds)

app = create_app()
