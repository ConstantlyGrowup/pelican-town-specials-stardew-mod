"""Shared application-layer test fixtures for Task 9 use-case tests."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pytest
from backend.tests.domain.factories import ask_gus_reviewable_fixture
from PIL import Image

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.draft import DraftRecord
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    FileAssetStore,
)
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
    GenerationAttemptRepository,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = (
    _REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


@dataclass
class AppServices:
    workspace: WorkspacePaths
    asset_store: FileAssetStore
    draft_repository: DraftRepository
    archive_repository: ArchiveRepository
    attempt_repository: GenerationAttemptRepository
    catalog: VanillaCatalog


@pytest.fixture
def services(tmp_path: Path) -> AppServices:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    asset_store = FileAssetStore(workspace)
    draft_repository = DraftRepository(workspace)
    archive_repository = ArchiveRepository(workspace)
    attempt_repository = GenerationAttemptRepository(workspace)
    catalog = VanillaCatalog.from_json(_CATALOG_PATH)
    return AppServices(
        workspace=workspace,
        asset_store=asset_store,
        draft_repository=draft_repository,
        archive_repository=archive_repository,
        attempt_repository=attempt_repository,
        catalog=catalog,
    )


def put_png(
    store: FileAssetStore,
    *,
    kind: AssetKind,
    size: int = 16,
    color: str = "blue",
) -> AssetRef:
    output = io.BytesIO()
    Image.new("RGB", (size, size), color).save(output, format="PNG")
    return store.put(
        output.getvalue(),
        AssetMetadata(
            kind=kind,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=size,
            height=size,
        ),
    )


def make_reviewable_draft(services: AppServices, *, revision: int = 1) -> DraftRecord:
    preview_ref = put_png(services.asset_store, kind=AssetKind.PREVIEW, color="purple")
    icon_ref = put_png(services.asset_store, kind=AssetKind.ICON_16, color="gold")
    draft = ask_gus_reviewable_fixture(revision=revision)
    visuals = draft.visuals.model_copy(
        update={
            "preview_asset_id": preview_ref.asset_id,
            "icon_16_asset_id": icon_ref.asset_id,
        }
    )
    draft = draft.model_copy(update={"visuals": visuals})
    return services.draft_repository.save(draft, expected_revision=None)
