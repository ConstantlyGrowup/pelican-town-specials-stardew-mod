"""API-level Blueprint generation: PATCH to STALE_PREVIEW, NDJSON stream, illegal state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from backend.tests.api.conftest import ApiClient, put_png
from backend.tests.generation.conftest import FakeGateway
from fastapi.testclient import TestClient

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.security import SecurityConfig, SecurityState
from pelican_town_specials.application.assets import AssetService
from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.application.generation import GenerationService
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import GenerationOrchestrator
from pelican_town_specials.persistence.asset_store import FileAssetStore
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

_BLUEPRINT_PRESENTATION = {
    "displayName": "春日面碗",
    "internalName": "SpringNoodleBowl",
    "categoryLabel": "主菜",
    "description": "一碗带着春天气息的热汤面。",
    "tags": ["spring", "noodles"],
}

_BLUEPRINT_GAMEPLAY = {
    "ingredients": [
        {
            "itemId": "24",
            "displayName": "Egg",
            "quantity": 1,
            "mappingReason": "catalog match",
            "catalogVersion": "stardew-1.6.15-v1",
        },
        {
            "itemId": "399",
            "displayName": "Spring Onion",
            "quantity": 1,
            "mappingReason": "catalog match",
            "catalogVersion": "stardew-1.6.15-v1",
        },
    ],
    "recovery": {"edibility": 80},
    "sellPrice": 220,
    "isDrink": False,
    "recipeUnlock": "DEFAULT",
}


@dataclass
class GenServices:
    asset_store: FileAssetStore
    draft_repository: DraftRepository
    catalog: VanillaCatalog
    security: SecurityState
    gateway: FakeGateway
    client: TestClient


@pytest.fixture
def gen_services(tmp_path: Path) -> GenServices:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    asset_store = FileAssetStore(workspace)
    draft_repository = DraftRepository(workspace)
    archive_repository = ArchiveRepository(workspace)
    catalog = VanillaCatalog.from_json(_CATALOG_PATH)
    gateway = FakeGateway()

    orchestrator = GenerationOrchestrator(
        draft_repository=draft_repository,
        attempt_repository=GenerationAttemptRepository(workspace),
        asset_store=asset_store,
        catalog=catalog,
        gateway_factory=lambda: gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
    )
    generation_service = GenerationService(
        orchestrator=orchestrator,
        draft_repository=draft_repository,
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
            asset_service=AssetService(asset_store),
            draft_service=DraftService(
                draft_repository=draft_repository,
                archive_repository=archive_repository,
                asset_store=asset_store,
                catalog=catalog,
            ),
            cookbook_service=CookbookService(archive_repository),
            asset_store=asset_store,
            draft_repository=draft_repository,
            archive_repository=archive_repository,
            vanilla_catalog=catalog,
            security_state=security,
            generation_service=generation_service,
        )
    )
    return GenServices(
        asset_store=asset_store,
        draft_repository=draft_repository,
        catalog=catalog,
        security=security,
        gateway=gateway,
        client=client,
    )


@pytest.fixture
def gen_auth_client(gen_services: GenServices) -> ApiClient:
    launch_token = gen_services.security.issue_launch_token()
    bootstrap = gen_services.client.post(
        "/session/bootstrap",
        json={"launchToken": launch_token},
        headers={"Host": "testserver"},
    )
    assert bootstrap.status_code == 204
    csrf_token = bootstrap.headers["x-pts-csrf"]
    return ApiClient(
        client=gen_services.client,
        session_headers={"Host": "testserver"},
        mutation_headers={
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": csrf_token,
        },
    )


def _create_blueprint_draft(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> str:
    ref = put_png(gen_services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
    response = gen_auth_client.client.post(
        "/api/v1/drafts",
        json={
            "mode": "BLUEPRINT",
            "language": "zh-CN",
            "source": {"originalImageAssetId": str(ref.asset_id)},
        },
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 201
    return response.json()["draftId"]


def _patch_blueprint(
    gen_auth_client: ApiClient,
    draft_id: str,
    *,
    expected_revision: int,
) -> dict:
    response = gen_auth_client.client.patch(
        f"/api/v1/drafts/{draft_id}",
        json={
            "expectedRevision": expected_revision,
            "presentation": _BLUEPRINT_PRESENTATION,
            "gameplay": _BLUEPRINT_GAMEPLAY,
        },
        headers=gen_auth_client.mutation_headers,
    )
    return response.json()


def _generate(
    gen_services: GenServices,
    gen_auth_client: ApiClient,
    draft_id: str,
) -> list[dict]:
    response = gen_auth_client.client.post(
        f"/api/v1/drafts/{draft_id}/generate",
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [
        json.loads(line)
        for line in response.text.strip().splitlines()
        if line
    ]


def test_blueprint_patch_stale_then_generate_preview(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    draft_id = _create_blueprint_draft(gen_services, gen_auth_client)

    # 1. Fill blueprint user fields while the draft is still DRAFT.
    first = _patch_blueprint(gen_auth_client, draft_id, expected_revision=1)
    assert first["status"] == "DRAFT"
    assert first["revision"] == 2

    # 2. Initial blueprint generation reaches REVIEWABLE with matching visuals.
    events = _generate(gen_services, gen_auth_client, draft_id)
    assert events[0]["type"] == "attempt.started"
    assert events[-1]["type"] == "attempt.succeeded"
    assert gen_services.gateway.calls == ["image", "image"]
    reviewable = gen_services.draft_repository.get(draft_id)
    assert reviewable.status.value == "REVIEWABLE"
    assert reviewable.visuals is not None
    assert reviewable.visuals.source_revision == reviewable.revision

    # 3. PATCH marks STALE_PREVIEW and bumps revision; old visuals stay behind.
    stale = _patch_blueprint(
        gen_auth_client, draft_id, expected_revision=reviewable.revision
    )
    assert stale["status"] == "STALE_PREVIEW"
    assert stale["revision"] == reviewable.revision + 1
    assert stale["visuals"]["sourceRevision"] == reviewable.revision
    assert stale["visuals"]["sourceRevision"] != stale["revision"]

    # 4. Blueprint preview generation returns to REVIEWABLE with a new revision.
    stale_revision = stale["revision"]
    events = _generate(gen_services, gen_auth_client, draft_id)
    assert events[-1]["type"] == "attempt.succeeded"
    assert gen_services.gateway.calls == ["image", "image", "image", "image"]
    previewed = gen_services.draft_repository.get(draft_id)
    assert previewed.status.value == "REVIEWABLE"
    assert previewed.revision == stale_revision + 1
    assert previewed.visuals is not None
    assert previewed.visuals.source_revision == previewed.revision


def test_blueprint_reviewable_generate_returns_409(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    draft_id = _create_blueprint_draft(gen_services, gen_auth_client)
    _patch_blueprint(gen_auth_client, draft_id, expected_revision=1)
    _generate(gen_services, gen_auth_client, draft_id)

    response = gen_auth_client.client.post(
        f"/api/v1/drafts/{draft_id}/generate",
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PTS_STATE_ILLEGAL_TRANSITION"
