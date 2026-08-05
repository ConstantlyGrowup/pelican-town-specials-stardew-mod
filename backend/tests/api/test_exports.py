"""Export API tests: idempotency, failure isolation, and all five endpoints.

The ExportService is injected with a fake open_folder adapter so no real OS
folder is ever opened. Dishes are seeded through the ArchiveRepository with
real icon assets so the Task 16 compiler can build spritesheets.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.security import SecurityConfig, SecurityState
from pelican_town_specials.application.assets import AssetService
from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.application.exports import ExportService
from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.assets import AssetKind, MediaType
from pelican_town_specials.mod_compiler.compiler import ContentPatcherCompiler
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    FileAssetStore,
)
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    ExportRepository,
    _validate_model_payload,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths

_ARCHIVES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "archives"

_PACK_SLUG = "TestPack"
_ZIP_FILENAME = f"[CP] Pelican Town Specials - {_PACK_SLUG}.zip"


@dataclass
class ExportApiFixture:
    client: TestClient
    workspace: WorkspacePaths
    asset_store: FileAssetStore
    archive_repository: ArchiveRepository
    export_repository: ExportRepository
    security: SecurityState
    opened_targets: list[str]


def _put_icon(asset_store: FileAssetStore) -> UUID:
    buffer = io.BytesIO()
    Image.new("RGBA", (16, 16), "seagreen").save(buffer, format="PNG")
    ref = asset_store.put(
        buffer.getvalue(),
        AssetMetadata(
            kind=AssetKind.ICON_16,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=16,
            height=16,
        ),
    )
    return ref.asset_id


def _content_hash(doc: dict) -> str:
    dish = _validate_model_payload(ArchivedDish)({**doc, "contentHash": "a" * 64})
    payload = {
        "presentation": dish.presentation.model_dump(by_alias=True, mode="json"),
        "gameplay": dish.gameplay.model_dump(by_alias=True, mode="json"),
        "visuals": dish.visuals.model_dump(by_alias=True, mode="json"),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _seed_archived_dish(
    archive_repository: ArchiveRepository,
    asset_store: FileAssetStore,
    name: str,
    key: str,
) -> ArchivedDish:
    doc = json.loads(
        (_ARCHIVES_DIR / f"{name}.json").read_text(encoding="utf-8")
    )
    doc["visuals"]["icon16AssetId"] = str(_put_icon(asset_store))
    doc["contentHash"] = _content_hash(doc)
    dish = _validate_model_payload(ArchivedDish)(doc)
    archive_repository.add_immutable(dish, idempotency_key=key)
    return dish


def _export_body(dish_ids: list[UUID]) -> dict:
    return {
        "dishIds": [str(dish_id) for dish_id in dish_ids],
        "packDisplayName": "家庭菜单",
        "packSlug": _PACK_SLUG,
        "version": "1.0.0",
        "description": "一份装满鹈鹕镇风味的菜单。",
        "language": "zh-CN",
    }


def _count_export_zip_assets(export_services: ExportApiFixture) -> int:
    return len(list(export_services.workspace.assets_dir.rglob("*.zip")))


@pytest.fixture
def export_services(services) -> ExportApiFixture:
    opened_targets: list[str] = []

    def fake_open_folder(target: Path) -> None:
        opened_targets.append(str(target))

    workspace = services.workspace
    asset_store = services.asset_store
    archive_repository = services.archive_repository
    export_repository = ExportRepository(workspace)
    compiler = ContentPatcherCompiler(
        asset_store=asset_store, author_name=workspace.author_name
    )
    export_service = ExportService(
        export_repository=export_repository,
        archive_repository=archive_repository,
        asset_store=asset_store,
        catalog=services.catalog,
        compiler=compiler,
        workspace=workspace,
        open_folder=fake_open_folder,
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
                draft_repository=services.draft_repository,
                archive_repository=archive_repository,
                asset_store=asset_store,
                catalog=services.catalog,
                attempt_repository=services.attempt_repository,
            ),
            cookbook_service=CookbookService(archive_repository),
            export_service=export_service,
            asset_store=asset_store,
            draft_repository=services.draft_repository,
            archive_repository=archive_repository,
            vanilla_catalog=services.catalog,
            security_state=security,
        )
    )
    return ExportApiFixture(
        client=client,
        workspace=workspace,
        asset_store=asset_store,
        archive_repository=archive_repository,
        export_repository=export_repository,
        security=security,
        opened_targets=opened_targets,
    )


@pytest.fixture
def auth_client(export_services: ExportApiFixture) -> dict[str, dict[str, str]]:
    launch_token = export_services.security.issue_launch_token()
    bootstrap = export_services.client.post(
        "/session/bootstrap",
        json={"launchToken": launch_token},
        headers={"Host": "testserver"},
    )
    assert bootstrap.status_code == 204
    csrf_token = bootstrap.headers["x-pts-csrf"]
    return {
        "session": {"Host": "testserver"},
        "mutation": {
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": csrf_token,
        },
    }


def _create_export(
    export_services: ExportApiFixture,
    auth_client: dict[str, dict[str, str]],
    dish_ids: list[UUID],
    *,
    idempotency_key: str,
):
    headers = {**auth_client["mutation"], "Idempotency-Key": idempotency_key}
    response = export_services.client.post(
        "/api/v1/exports",
        headers=headers,
        json=_export_body(dish_ids),
    )
    return response


# --- T17-IDEMPOTENCY-001 ------------------------------------------------------


def test_export_idempotency_does_not_create_second_zip(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    dish = _seed_archived_dish(
        export_services.archive_repository,
        export_services.asset_store,
        "ask-gus-dish",
        "seed-1",
    )
    first = _create_export(
        export_services,
        auth_client,
        [dish.dish_id],
        idempotency_key="export-fixture-001",
    )
    assert first.status_code == 201
    second = _create_export(
        export_services,
        auth_client,
        [dish.dish_id],
        idempotency_key="export-fixture-001",
    )
    assert second.status_code == 201
    assert second.json()["exportId"] == first.json()["exportId"]
    assert _count_export_zip_assets(export_services) == 1


def test_export_requires_idempotency_key(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    dish = _seed_archived_dish(
        export_services.archive_repository,
        export_services.asset_store,
        "ask-gus-dish",
        "seed-1",
    )
    response = export_services.client.post(
        "/api/v1/exports",
        headers=auth_client["mutation"],
        json=_export_body([dish.dish_id]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PTS_INPUT_IDEMPOTENCY_KEY_REQUIRED"


# --- T17-FAILURE-ISOLATION-001 ------------------------------------------------


def test_failed_export_never_downloads_and_stores_report(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    dish = _seed_archived_dish(
        export_services.archive_repository,
        export_services.asset_store,
        "ask-gus-dish",
        "seed-1",
    )
    response = _create_export(
        export_services,
        auth_client,
        [dish.dish_id, uuid4()],
        idempotency_key="export-fail-001",
    )
    assert response.status_code == 201
    record = response.json()
    assert record["status"] == "FAILED"
    assert record["artifactAssetId"] is None
    assert record["validation"]["valid"] is False
    codes = {issue["code"] for issue in record["validation"]["issues"]}
    assert "PTS_VALIDATION_DISH_MISSING" in codes
    assert record["error"] is not None
    assert record["error"]["code"] == "PTS_EXPORT_VALIDATION_FAILED"
    assert _count_export_zip_assets(export_services) == 0

    download = export_services.client.get(
        f"/api/v1/exports/{record['exportId']}/download",
        headers=auth_client["session"],
    )
    assert download.status_code == 409
    assert download.json()["error"]["code"] == "PTS_EXPORT_NOT_READY"


# --- T17-VALIDATE-001 ---------------------------------------------------------


def test_validate_endpoint_returns_report(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    dish = _seed_archived_dish(
        export_services.archive_repository,
        export_services.asset_store,
        "ask-gus-dish",
        "seed-1",
    )
    response = export_services.client.post(
        "/api/v1/exports/validate",
        headers=auth_client["mutation"],
        json=_export_body([dish.dish_id]),
    )
    assert response.status_code == 200
    report = response.json()
    assert report["valid"] is True
    assert report["validatorVersion"] == "task16-export-validator-v1"
    assert report["issues"] == []


def test_validate_endpoint_reports_unknown_ingredient(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    doc = json.loads(
        (_ARCHIVES_DIR / "ask-gus-dish.json").read_text(encoding="utf-8")
    )
    doc["gameplay"]["ingredients"][0]["itemId"] = "NotReal"
    doc["visuals"]["icon16AssetId"] = str(_put_icon(export_services.asset_store))
    doc["contentHash"] = _content_hash(doc)
    dish = _validate_model_payload(ArchivedDish)(doc)
    export_services.archive_repository.add_immutable(
        dish, idempotency_key="seed-unknown"
    )

    response = export_services.client.post(
        "/api/v1/exports/validate",
        headers=auth_client["mutation"],
        json=_export_body([dish.dish_id]),
    )
    assert response.status_code == 200
    report = response.json()
    assert report["valid"] is False
    codes = {issue["code"] for issue in report["issues"]}
    assert "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN" in codes


# --- T17-SYNC-001 / T17-DOWNLOAD-001 ------------------------------------------


def test_successful_export_creates_zip_and_downloads(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    dish = _seed_archived_dish(
        export_services.archive_repository,
        export_services.asset_store,
        "ask-gus-dish",
        "seed-1",
    )
    response = _create_export(
        export_services,
        auth_client,
        [dish.dish_id],
        idempotency_key="export-ok-001",
    )
    assert response.status_code == 201
    record = response.json()
    assert record["status"] == "SUCCEEDED"
    assert record["artifactAssetId"] is not None
    assert record["error"] is None
    assert _count_export_zip_assets(export_services) == 1

    download = export_services.client.get(
        f"/api/v1/exports/{record['exportId']}/download",
        headers=auth_client["session"],
    )
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert _ZIP_FILENAME in download.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(download.content)) as handle:
        names = handle.namelist()
        assert names
        root = names[0].partition("/")[0]
        assert root == f"[CP] Pelican Town Specials - {_PACK_SLUG}"
        assert f"{root}/manifest.json" in names
        assert f"{root}/content.json" in names
        assert f"{root}/i18n/default.json" in names
        assert f"{root}/assets/objects.png" in names


# --- T17-RECORD-001 -----------------------------------------------------------


def test_get_export_record_returns_aligned_fields(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    dish = _seed_archived_dish(
        export_services.archive_repository,
        export_services.asset_store,
        "ask-gus-dish",
        "seed-1",
    )
    created = _create_export(
        export_services,
        auth_client,
        [dish.dish_id],
        idempotency_key="export-rec-001",
    ).json()

    response = export_services.client.get(
        f"/api/v1/exports/{created['exportId']}",
        headers=auth_client["session"],
    )
    assert response.status_code == 200
    record = response.json()
    assert record["exportId"] == created["exportId"]
    assert record["status"] == "SUCCEEDED"
    assert record["authorName"] == export_services.workspace.author_name
    assert (
        record["uniqueId"]
        == f"{export_services.workspace.author_name}.PelicanTownSpecials.{_PACK_SLUG}"
    )
    assert record["spec"]["packSlug"] == _PACK_SLUG
    assert set(record["dishContentHashes"]) == {str(dish.dish_id)}
    assert record["compilerVersion"]
    assert record["gameVersion"] == "1.6.15"
    assert record["contentPatcherFormat"] == "2.9.0"
    assert record["validation"]["valid"] is True
    assert record["createdAt"]
    assert record["finishedAt"]


def test_get_missing_export_returns_404(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    response = export_services.client.get(
        f"/api/v1/exports/{uuid4()}",
        headers=auth_client["session"],
    )
    assert response.status_code == 404


# --- T17-OPENFOLDER-001 -------------------------------------------------------


def test_open_folder_opens_registered_export_directory(
    auth_client: dict[str, dict[str, str]],
    export_services: ExportApiFixture,
) -> None:
    dish = _seed_archived_dish(
        export_services.archive_repository,
        export_services.asset_store,
        "ask-gus-dish",
        "seed-1",
    )
    created = _create_export(
        export_services,
        auth_client,
        [dish.dish_id],
        idempotency_key="export-folder-001",
    ).json()

    response = export_services.client.post(
        f"/api/v1/exports/{created['exportId']}/open-folder",
        headers=auth_client["mutation"],
    )
    assert response.status_code == 204
    assert len(export_services.opened_targets) == 1
    target = Path(export_services.opened_targets[0])
    assert target.is_relative_to(export_services.workspace.exports_dir)


# --- T17-OPENFOLDER-001 / production default assembly -------------------------


def test_default_assembly_open_folder_is_usable(services, monkeypatch) -> None:
    """The production create_app path wires os.startfile on Windows.

    On non-Windows the adapter stays None and the endpoint returns the
    controlled error instead of opening a folder. The resolve/is_relative_to
    guard in ExportService.open_export_folder is untouched.
    """
    opened: list[str] = []
    if os.name == "nt":
        monkeypatch.setattr(
            "os.startfile", lambda path: opened.append(str(path))
        )

    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=None,
            allowed_origins=frozenset({"http://testserver"}),
        )
    )
    app = create_app(
        workspace_paths=services.workspace,
        asset_service=AssetService(services.asset_store),
        draft_service=DraftService(
            draft_repository=services.draft_repository,
            archive_repository=services.archive_repository,
            asset_store=services.asset_store,
            catalog=services.catalog,
            attempt_repository=services.attempt_repository,
        ),
        cookbook_service=CookbookService(services.archive_repository),
        asset_store=services.asset_store,
        draft_repository=services.draft_repository,
        archive_repository=services.archive_repository,
        vanilla_catalog=services.catalog,
        security_state=security,
    )
    client = TestClient(app)
    launch_token = security.issue_launch_token()
    bootstrap = client.post(
        "/session/bootstrap",
        json={"launchToken": launch_token},
        headers={"Host": "testserver"},
    )
    assert bootstrap.status_code == 204
    mutation = {
        "Host": "testserver",
        "Origin": "http://testserver",
        "X-PTS-CSRF": bootstrap.headers["x-pts-csrf"],
    }

    dish = _seed_archived_dish(
        services.archive_repository,
        services.asset_store,
        "ask-gus-dish",
        "seed-default-open-folder",
    )
    created = client.post(
        "/api/v1/exports",
        headers={**mutation, "Idempotency-Key": "default-open-folder-001"},
        json=_export_body([dish.dish_id]),
    )
    assert created.status_code == 201

    response = client.post(
        f"/api/v1/exports/{created.json()['exportId']}/open-folder",
        headers=mutation,
    )
    if os.name == "nt":
        assert response.status_code == 204
        assert len(opened) == 1
        assert Path(opened[0]).is_relative_to(
            services.workspace.exports_dir
        )
    else:
        assert response.status_code == 500
