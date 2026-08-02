from fastapi import FastAPI

from pelican_town_specials.api.routes import health
from pelican_town_specials.config import AppConfig


def create_app(config: AppConfig | None = None) -> FastAPI:
    app_config = config if config is not None else AppConfig()
    app = FastAPI(title="PelicanTownSpecials API", version="1.0.0")
    app.state.config = app_config
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
