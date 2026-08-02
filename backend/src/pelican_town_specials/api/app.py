from __future__ import annotations

from fastapi import FastAPI

from pelican_town_specials.api.error_handlers import register_error_handlers
from pelican_town_specials.api.routes import health, settings
from pelican_town_specials.api.routes.settings import ProviderKeyStore
from pelican_town_specials.application.settings import ProviderSettingsService
from pelican_town_specials.config import AppConfig
from pelican_town_specials.persistence.secret_store import WindowsEnvironmentSecretStore
from pelican_town_specials.persistence.workspace import WorkspacePaths


def create_app(
    config: AppConfig | None = None,
    *,
    workspace_paths: WorkspacePaths | None = None,
    secret_store: ProviderKeyStore | None = None,
) -> FastAPI:
    app_config = config if config is not None else AppConfig()
    resolved_workspace = workspace_paths or WorkspacePaths.create(
        app_config.workspace_path
    )
    resolved_secret_store = secret_store or WindowsEnvironmentSecretStore()

    app = FastAPI(title="PelicanTownSpecials API", version="1.0.0")
    app.state.config = app_config
    app.state.workspace_paths = resolved_workspace
    app.state.secret_store = resolved_secret_store
    app.state.provider_settings_service = ProviderSettingsService(
        resolved_workspace,
        resolved_secret_store,
    )
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")
    return app


app = create_app()
