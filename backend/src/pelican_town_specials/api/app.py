from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from starlette.middleware.base import RequestResponseEndpoint

from pelican_town_specials.api.error_handlers import (
    handle_app_error,
    register_error_handlers,
)
from pelican_town_specials.api.routes import app_control, health, session, settings
from pelican_town_specials.api.routes.app_control import ActivityTracker
from pelican_town_specials.api.routes.settings import ProviderKeyStore
from pelican_town_specials.api.security import (
    SecurityState,
    is_safe_method,
    require_mutation_security,
    require_session,
)
from pelican_town_specials.application.settings import ProviderSettingsService
from pelican_town_specials.config import AppConfig
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.secret_store import WindowsEnvironmentSecretStore
from pelican_town_specials.persistence.workspace import WorkspacePaths


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
) -> FastAPI:
    app_config = config if config is not None else AppConfig()
    resolved_workspace = workspace_paths or WorkspacePaths.create(
        app_config.workspace_path
    )
    resolved_secret_store = secret_store or WindowsEnvironmentSecretStore()

    resolved_activity_tracker = activity_tracker or ActivityTracker()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
    app.state.provider_settings_service = ProviderSettingsService(
        resolved_workspace,
        resolved_secret_store,
    )
    register_error_handlers(app)
    app.include_router(session.router)
    app.include_router(app_control.router)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")

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
