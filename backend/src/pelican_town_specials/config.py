from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_workspace_path() -> Path:
    return Path(user_data_dir("PelicanTownSpecials")) / "workspace"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PTS_", extra="ignore")

    workspace_path: Path = Field(default_factory=_default_workspace_path)
    ask_gus_min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
