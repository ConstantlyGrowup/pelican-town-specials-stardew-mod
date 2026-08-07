from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from pelican_town_specials.api.app import create_app
from pelican_town_specials.api.security import SecurityConfig, SecurityState
from pelican_town_specials.persistence.secret_store import (
    API_KEY_ENVIRONMENT_VARIABLE,
    WindowsEnvironmentSecretStore,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths


@dataclass
class FakeEnvironmentAdapter:
    process: dict[str, str] = field(default_factory=dict)
    current_user: dict[str, str] = field(default_factory=dict)

    def get_process(self, name: str) -> str | None:
        return self.process.get(name)

    def set_process(self, name: str, value: str) -> None:
        self.process[name] = value

    def delete_process(self, name: str) -> None:
        self.process.pop(name, None)

    def get_current_user(self, name: str) -> str | None:
        return self.current_user.get(name)

    def set_current_user(self, name: str, value: str) -> None:
        self.current_user[name] = value

    def delete_current_user(self, name: str) -> None:
        self.current_user.pop(name, None)


def _valid_settings() -> dict[str, object]:
    return {
        "providerKind": "OPENAI_COMPATIBLE",
        "baseUrl": "https://example.test/v1",
        "visionModel": "vision-model",
        "textModel": "text-model",
        "imageModel": "image-model",
        "chatTimeoutSeconds": 120,
        "imageTimeoutSeconds": 300,
        "maxAutomaticRetries": 2,
    }


def test_create_app_registers_settings_and_preserves_health(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    adapter = FakeEnvironmentAdapter()
    secret_store = WindowsEnvironmentSecretStore(adapter)
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
            secret_store=secret_store,
            security_state=security,
        )
    )
    launch_token = security.issue_launch_token()
    bootstrap_response = client.post(
        "/session/bootstrap",
        json={"launchToken": launch_token},
        headers={"Host": "testserver"},
    )
    csrf_token = bootstrap_response.headers["x-pts-csrf"]
    session_headers = {"Host": "testserver"}
    mutation_headers = {
        **session_headers,
        "Origin": "http://testserver",
        "X-PTS-CSRF": csrf_token,
    }

    assert client.get("/api/v1/health").status_code == 200
    assert bootstrap_response.status_code == 204
    settings_response = client.get(
        "/api/v1/settings/provider",
        headers=session_headers,
    )

    assert settings_response.status_code == 200
    assert settings_response.json()["apiKeyConfigured"] is False

    key = "sk-create-app-wiring-sentinel"
    put_key = client.put(
        "/api/v1/settings/provider/key",
        json={"apiKey": key},
        headers=mutation_headers,
    )
    assert put_key.status_code == 200
    assert key not in put_key.text
    assert adapter.current_user[API_KEY_ENVIRONMENT_VARIABLE] == key

    saved = client.put(
        "/api/v1/settings/provider",
        json=_valid_settings(),
        headers=mutation_headers,
    )
    assert saved.status_code == 200
    assert client.get(
        "/api/v1/settings/provider",
        headers=session_headers,
    ).json() == {
        **_valid_settings(),
        "apiKeyConfigured": True,
        "apiKeySource": "ENVIRONMENT",
    }


def test_create_app_wires_task9_services_and_routes(tmp_path: Path) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    adapter = FakeEnvironmentAdapter()
    secret_store = WindowsEnvironmentSecretStore(adapter)
    security = SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=None,
            allowed_origins=frozenset({"http://testserver"}),
        )
    )
    app = create_app(
        workspace_paths=workspace,
        secret_store=secret_store,
        security_state=security,
    )

    assert hasattr(app.state, "asset_service")
    assert hasattr(app.state, "draft_service")
    assert hasattr(app.state, "cookbook_service")
    assert hasattr(app.state, "asset_store")
    assert hasattr(app.state, "draft_repository")
    assert hasattr(app.state, "archive_repository")
    assert hasattr(app.state, "vanilla_catalog")

    paths = set(app.openapi()["paths"])
    for path in (
        "/api/v1/assets/images",
        "/api/v1/assets/{asset_id}",
        "/api/v1/drafts",
        "/api/v1/drafts/{draft_id}",
        "/api/v1/drafts/{draft_id}/convert-to-blueprint",
        "/api/v1/drafts/{draft_id}/archive",
        "/api/v1/drafts/{draft_id}/discard",
        "/api/v1/drafts/{draft_id}/generation",
        "/api/v1/cookbook",
        "/api/v1/cookbook/{dish_id}",
    ):
        assert path in paths


def test_startup_sweep_recovers_orphaned_generating_draft(
    tmp_path: Path,
) -> None:
    """Task 19.6: the startup sweep recovers a draft a previous process left in
    a generating state (a genuine cross-process orphan), so the app is not stuck
    on restart. It is scoped to orphans only — a live in-process generation is
    never swept."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from backend.tests.domain.factories import make_draft as make_domain_draft

    from pelican_town_specials.domain.assets import AssetKind, MediaType
    from pelican_town_specials.domain.common import DraftMode
    from pelican_town_specials.domain.draft import (
        AttemptStatus,
        DraftStatus,
        GenerationAttempt,
        GenerationAttemptKind,
        GenerationStage,
        StageAttempt,
        StageStatus,
    )
    from pelican_town_specials.persistence.asset_store import (
        AssetMetadata,
        FileAssetStore,
    )
    from pelican_town_specials.persistence.repositories import (
        DraftRepository,
        GenerationAttemptRepository,
    )

    workspace = WorkspacePaths.create(tmp_path / "workspace")
    asset_store = FileAssetStore(workspace)
    draft_repository = DraftRepository(workspace)
    attempt_repository = GenerationAttemptRepository(workspace)

    import io

    from PIL import Image

    png_bytes = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(png_bytes, format="PNG")
    ref = asset_store.put(
        png_bytes.getvalue(),
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=16,
            height=16,
        ),
    )
    draft = make_domain_draft(
        mode=DraftMode.ASK_GUS, status=DraftStatus.GENERATING, revision=1
    )
    source = draft.source.model_copy(
        update={"original_image_asset_id": ref.asset_id}
    )
    draft = draft.model_copy(
        update={"source": source, "active_attempt_id": uuid4()}
    )
    draft = draft_repository.save(draft, expected_revision=None)
    now = datetime.now(UTC)
    attempt_id = draft.active_attempt_id
    assert attempt_id is not None
    attempt_repository.save(
        GenerationAttempt(
            attempt_id=attempt_id,
            draft_id=draft.draft_id,
            kind=GenerationAttemptKind.INITIAL,
            source_revision=draft.revision,
            status=AttemptStatus.RUNNING,
            current_stage=GenerationStage.DISH_ANALYSIS,
            stages=[
                StageAttempt(
                    stage=GenerationStage.DISH_ANALYSIS,
                    status=StageStatus.RUNNING,
                    retry_count=0,
                    started_at=now,
                    finished_at=None,
                )
            ],
            candidate_record_path=None,
            started_at=now,
            finished_at=None,
            error=None,
        )
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
            security_state=security,
            enable_docs=False,
        )
    )
    with client:
        pass  # lifespan startup runs the sweep

    restored = draft_repository.get(draft.draft_id)
    assert restored.status is DraftStatus.READY
    assert restored.active_attempt_id is None
    assert restored.last_attempt_id == attempt_id
    persisted = attempt_repository.get(attempt_id)
    assert persisted.status is AttemptStatus.INTERRUPTED