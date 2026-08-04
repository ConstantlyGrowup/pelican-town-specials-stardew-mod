"""Type-safe accessors for Task 9 services and repositories wired in app.state."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from pelican_town_specials.application.assets import AssetService
from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.persistence.asset_store import FileAssetStore
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
)


def file_asset_store(request: Request) -> FileAssetStore:
    return cast(FileAssetStore, request.app.state.asset_store)


def draft_repository(request: Request) -> DraftRepository:
    return cast(DraftRepository, request.app.state.draft_repository)


def archive_repository(request: Request) -> ArchiveRepository:
    return cast(ArchiveRepository, request.app.state.archive_repository)


def vanilla_catalog(request: Request) -> VanillaCatalog:
    return cast(VanillaCatalog, request.app.state.vanilla_catalog)


def asset_service(request: Request) -> AssetService:
    return cast(AssetService, request.app.state.asset_service)


def draft_service(request: Request) -> DraftService:
    return cast(DraftService, request.app.state.draft_service)


def cookbook_service(request: Request) -> CookbookService:
    return cast(CookbookService, request.app.state.cookbook_service)
