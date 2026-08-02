from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import Field, field_validator

from pelican_town_specials.domain.common import StrictModel, ensure_utc, ensure_uuid4


class CookbookTombstone(StrictModel):
    dish_id: UUID = Field(alias="dishId")
    deleted_at: datetime = Field(alias="deletedAt")
    content_hash: str = Field(alias="contentHash", min_length=64, max_length=64)

    @field_validator("dish_id", mode="before")
    @classmethod
    def _validate_dish_id(cls, value: UUID) -> UUID:
        return ensure_uuid4(value)

    @field_validator("deleted_at", mode="before")
    @classmethod
    def _validate_deleted_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


def move_directory_to_trash(source_dir: Path, trash_root: Path) -> Path:
    trash_root.mkdir(parents=True, exist_ok=True)
    destination = trash_root / source_dir.name
    if destination.exists():
        raise FileExistsError(f"trash destination already exists: {destination}")
    shutil.move(str(source_dir), str(destination))
    return destination
