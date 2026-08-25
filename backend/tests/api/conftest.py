"""Task 9 API test fixtures: temp workspace, real catalog, auth_client."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pytest
from backend.tests.domain.factories import ask_gus_reviewable_fixture
from fastapi.testclient import TestClient
from PIL import Image

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.security import SecurityConfig, SecurityState
from pelican_town_specials.application.assets import AssetService
from pelican_town_specials.application.canonical_memory import (
    CanonicalRegistrationService,
)
from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.application.trial import TrialAccessService
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.draft import DraftRecord
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    FileAssetStore,
)
from pelican_town_specials.persistence.canonical_registry import (
    SQLiteCanonicalRegistry,
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
class ApiServices:
    workspace: WorkspacePaths
    asset_store: FileAssetStore
    draft_repository: DraftRepository
    archive_repository: ArchiveRepository
    attempt_repository: GenerationAttemptRepository
    catalog: VanillaCatalog
    security: SecurityState
    trial_service: TrialAccessService
    canonical_registry: SQLiteCanonicalRegistry
    client: TestClient


@dataclass
class ApiClient:
    client: TestClient
    session_headers: dict[str, str]
    mutation_headers: dict[str, str]


@pytest.fixture
def services(tmp_path: Path) -> ApiServices:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    asset_store = FileAssetStore(workspace)
    draft_repository = DraftRepository(workspace)
    archive_repository = ArchiveRepository(workspace)
    catalog = VanillaCatalog.from_json(_CATALOG_PATH)
    canonical_registry = SQLiteCanonicalRegistry(workspace)

    attempt_repository = GenerationAttemptRepository(workspace)
    asset_service = AssetService(asset_store)
    canonical_registration = CanonicalRegistrationService(
        registry=canonical_registry,
        archive_repository=archive_repository,
        draft_repository=draft_repository,
        asset_store=asset_store,
    )
    draft_service = DraftService(
        draft_repository=draft_repository,
        archive_repository=archive_repository,
        asset_store=asset_store,
        catalog=catalog,
        attempt_repository=attempt_repository,
        canonical_registration_service=canonical_registration,
    )
    cookbook_service = CookbookService(archive_repository)

    trial_service = TrialAccessService(
        workspace,
        key_provider=lambda: "sk-test-trial",
    )

    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=None,
            allowed_origins=frozenset({"http://testserver"}),
        )
    )
    client = TestClient(
        create_app(
            workspace_paths=workspace,
            asset_service=asset_service,
            draft_service=draft_service,
            cookbook_service=cookbook_service,
            asset_store=asset_store,
            draft_repository=draft_repository,
            archive_repository=archive_repository,
            canonical_registry=canonical_registry,
            vanilla_catalog=catalog,
            security_state=security,
            trial_access_service=trial_service,
        )
    )
    return ApiServices(
        workspace=workspace,
        asset_store=asset_store,
        draft_repository=draft_repository,
        archive_repository=archive_repository,
        attempt_repository=attempt_repository,
        catalog=catalog,
        security=security,
        trial_service=trial_service,
        canonical_registry=canonical_registry,
        client=client,
    )


@pytest.fixture
def auth_client(services: ApiServices) -> ApiClient:
    launch_token = services.security.issue_launch_token()
    bootstrap = services.client.post(
        "/session/bootstrap",
        json={"launchToken": launch_token},
        headers={"Host": "testserver"},
    )
    assert bootstrap.status_code == 204
    csrf_token = bootstrap.headers["x-pts-csrf"]
    return ApiClient(
        client=services.client,
        session_headers={"Host": "testserver"},
        mutation_headers={
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": csrf_token,
        },
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


def make_reviewable_draft(services: ApiServices, *, revision: int = 1) -> DraftRecord:
    preview_ref = put_png(services.asset_store, kind=AssetKind.PREVIEW, color="purple")
    source_icon_ref = put_png(
        services.asset_store,
        kind=AssetKind.ICON_SOURCE,
        size=32,
        color="green",
    )
    icon_ref = put_png(services.asset_store, kind=AssetKind.ICON_16, color="gold")
    draft = ask_gus_reviewable_fixture(revision=revision)
    visuals = draft.visuals.model_copy(
        update={
            "preview_asset_id": preview_ref.asset_id,
            "icon_source_asset_id": source_icon_ref.asset_id,
            "icon_16_asset_id": icon_ref.asset_id,
        }
    )
    draft = draft.model_copy(update={"visuals": visuals})
    return services.draft_repository.save(draft, expected_revision=None)
