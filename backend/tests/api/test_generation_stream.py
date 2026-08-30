"""API-level NDJSON generation stream and cancel endpoints."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from backend.tests.api.conftest import ApiClient, put_png
from backend.tests.generation.conftest import FakeGateway
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

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
    attempt_repository = GenerationAttemptRepository(workspace)

    orchestrator = GenerationOrchestrator(
        draft_repository=draft_repository,
        attempt_repository=attempt_repository,
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
                attempt_repository=attempt_repository,
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


def _create_ask_gus_draft(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> str:
    ref = put_png(gen_services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
    response = gen_auth_client.client.post(
        "/api/v1/drafts",
        json={
            "mode": "ASK_GUS",
            "language": "zh-CN",
            "source": {"originalImageAssetId": str(ref.asset_id)},
        },
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 201
    return response.json()["draftId"]


def test_generate_streams_ndjson_to_success(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    draft_id = _create_ask_gus_draft(gen_services, gen_auth_client)

    response = gen_auth_client.client.post(
        f"/api/v1/drafts/{draft_id}/generate",
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/x-ndjson"
    )
    events = [
        json.loads(line)
        for line in response.text.strip().splitlines()
        if line
    ]
    types = [event["type"] for event in events]
    assert types[0] == "attempt.started"
    assert types[-1] == "attempt.succeeded"
    assert "stage.succeeded" in types
    assert gen_services.gateway.calls == [
        "analyze",
        "design",
        "image",
        "image",
    ]

    progress = gen_auth_client.client.get(
        f"/api/v1/drafts/{draft_id}/generation",
        headers=gen_auth_client.session_headers,
    )
    assert progress.status_code == 200
    assert progress.json()["attempt"]["trialUsed"] is False
    assert progress.json()["attempt"]["trialRemaining"] is None

    saved = gen_services.draft_repository.get(draft_id)
    assert saved.status.value == "REVIEWABLE"


def test_generate_missing_draft_returns_404(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    response = gen_auth_client.client.post(
        f"/api/v1/drafts/{uuid4()}/generate",
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PTS_DRAFT_NOT_FOUND"


def test_cancel_without_active_attempt_returns_202(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    draft_id = _create_ask_gus_draft(gen_services, gen_auth_client)
    response = gen_auth_client.client.post(
        f"/api/v1/drafts/{draft_id}/cancel",
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 202


async def test_cancel_awaits_rollback_then_immediate_regenerate_succeeds(
    gen_services: GenServices,
) -> None:
    """Regression for F19-1-001: /cancel returns 202 only after rollback.

    Uses an AsyncClient + ASGITransport so the generate and cancel requests
    share one event loop, exactly like the real uvicorn server. Without the
    ``await_cancelled`` rollback wait, the 202 would race the async rollback
    and an immediate regenerate would hit PTS_GEN_BUSY /
    PTS_STATE_ILLEGAL_TRANSITION.
    """
    from pelican_town_specials.domain.assets import AssetKind

    app = gen_services.client.app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        launch_token = gen_services.security.issue_launch_token()
        bootstrap = await client.post(
            "/session/bootstrap",
            json={"launchToken": launch_token},
            headers={"Host": "testserver"},
        )
        assert bootstrap.status_code == 204
        csrf = bootstrap.headers["x-pts-csrf"]
        assert bootstrap.cookies.get("PTS_SESSION")
        mutation_headers = {
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": csrf,
        }

        ref = put_png(gen_services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
        create = await client.post(
            "/api/v1/drafts",
            json={
                "mode": "ASK_GUS",
                "language": "zh-CN",
                "source": {"originalImageAssetId": str(ref.asset_id)},
            },
            headers=mutation_headers,
        )
        assert create.status_code == 201
        draft_id = create.json()["draftId"]

        gen_services.gateway.delay = 0.4

        generate_task = asyncio.create_task(
            client.post(
                f"/api/v1/drafts/{draft_id}/generate",
                headers=mutation_headers,
            )
        )
        try:
            # Wait until the attempt reaches the first provider call so the
            # cancel is delivered inside _run's stage execution (deterministic
            # CancelledError rollback rather than a transient stream send
            # boundary).
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if gen_services.gateway.calls:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("generation attempt never reached the provider")

            cancel_response = await client.post(
                f"/api/v1/drafts/{draft_id}/cancel",
                headers=mutation_headers,
            )
            assert cancel_response.status_code == 202

            # The generate stream completed before /cancel returned: rollback
            # (active_attempt_id cleared, slot released) is synchronous with 202.
            generate_response = await generate_task
            assert generate_response.status_code == 200
            events = [
                json.loads(line)
                for line in generate_response.text.strip().splitlines()
                if line
            ]
            assert events[-1]["type"] == "attempt.failed"
            assert events[-1]["error"]["code"] == "PTS_GEN_CANCELLED"

            saved = gen_services.draft_repository.get(draft_id)
            assert saved.active_attempt_id is None
            assert saved.status.value == "READY"

            # Immediate regenerate succeeds: no 409 busy / illegal state.
            gen_services.gateway.delay = 0.0
            second = await client.post(
                f"/api/v1/drafts/{draft_id}/generate",
                headers=mutation_headers,
            )
            assert second.status_code == 200
            second_events = [
                json.loads(line)
                for line in second.text.strip().splitlines()
                if line
            ]
            assert second_events[-1]["type"] == "attempt.succeeded"
        finally:
            if not generate_task.done():
                generate_task.cancel()
                with suppress(BaseException):
                    await generate_task


async def test_closing_streaming_response_closes_iterator_on_disconnect() -> None:
    """Regression: Starlette 1.3 (ASGI spec >= 2.4) raises from stream_response
    on client disconnect WITHOUT closing the body iterator. The generate route's
    _ClosingStreamingResponse must still close it deterministically so the
    response teardown is clean (Task 19.2: the server-owned generation itself
    keeps running regardless; closing the body iterator only detaches the
    subscriber)."""
    from pelican_town_specials.api.routes.generation import (
        _ClosingStreamingResponse,
    )

    class ProbeIterator:
        def __init__(self) -> None:
            self.closed = False

        def __aiter__(self) -> ProbeIterator:
            return self

        async def __anext__(self) -> str:
            return "line\n"

        async def aclose(self) -> None:
            self.closed = True

    probe = ProbeIterator()
    response = _ClosingStreamingResponse(probe, media_type="application/x-ndjson")

    async def send(message: dict[str, object]) -> None:
        if message["type"] == "http.response.body":
            raise OSError("client disconnected")

    with pytest.raises(OSError):
        await response.stream_response(send)

    assert probe.closed is True


async def test_cancel_orphaned_attempt_rolls_back(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    """Regression: /cancel must clear a draft stuck in GENERATING whose attempt
    has no live in-process task (client disconnect / page reload). Previously the
    cancel route returned 202 but did nothing, leaving the draft permanently
    GENERATING and the generation unusable."""
    from pelican_town_specials.domain.common import utc_now
    from pelican_town_specials.domain.draft import DraftStatus

    draft_id = _create_ask_gus_draft(gen_services, gen_auth_client)
    attempt_id = uuid4()
    saved = gen_services.draft_repository.get(draft_id)
    staged = saved.model_copy(
        update={
            "status": DraftStatus.GENERATING,
            "active_attempt_id": attempt_id,
            "updated_at": utc_now(),
        }
    )
    gen_services.draft_repository.control_write(
        staged,
        expected_revision=saved.revision,
        expected_attempt_id=None,
    )

    response = gen_auth_client.client.post(
        f"/api/v1/drafts/{draft_id}/cancel",
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 202

    restored = gen_services.draft_repository.get(draft_id)
    assert restored.status is DraftStatus.READY
    assert restored.active_attempt_id is None

    # The draft is recoverable and the slot is free: a fresh generation works.
    gen_services.gateway.delay = 0.0
    second = gen_auth_client.client.post(
        f"/api/v1/drafts/{draft_id}/generate",
        headers=gen_auth_client.mutation_headers,
    )
    assert second.status_code == 200
    events = [
        json.loads(line)
        for line in second.text.strip().splitlines()
        if line
    ]
    assert events[-1]["type"] == "attempt.succeeded"


async def test_fourth_concurrent_generation_returns_409_busy_with_details(
    gen_services: GenServices,
) -> None:
    """M8 Task 28 (M8-D02/D03): with three generations in flight the fourth
    generate request is rejected with a stable 409 PTS_GEN_BUSY carrying
    activeCount/maxConcurrent, before any attempt record, draft change or
    provider call."""
    from pelican_town_specials.domain.assets import AssetKind

    app = gen_services.client.app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        launch_token = gen_services.security.issue_launch_token()
        bootstrap = await client.post(
            "/session/bootstrap",
            json={"launchToken": launch_token},
            headers={"Host": "testserver"},
        )
        assert bootstrap.status_code == 204
        csrf = bootstrap.headers["x-pts-csrf"]
        mutation_headers = {
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": csrf,
        }

        draft_ids = []
        for _ in range(4):
            ref = put_png(gen_services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
            create = await client.post(
                "/api/v1/drafts",
                json={
                    "mode": "ASK_GUS",
                    "language": "zh-CN",
                    "source": {"originalImageAssetId": str(ref.asset_id)},
                },
                headers=mutation_headers,
            )
            assert create.status_code == 201
            draft_ids.append(create.json()["draftId"])

        gen_services.gateway.delay = 0.5
        gen_services.gateway.hold = asyncio.Event()
        generate_tasks = [
            asyncio.create_task(
                client.post(
                    f"/api/v1/drafts/{draft_id}/generate",
                    headers=mutation_headers,
                )
            )
            for draft_id in draft_ids[:3]
        ]
        try:
            # Wait until all three attempts are inside their first provider
            # call and frozen there on the hold gate. The snapshot below is
            # then stable for the rejection: the frozen generations cannot
            # append further calls, so the no-additional-call assertion is
            # deterministic rather than racing CI scheduling jitter.
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if gen_services.gateway.calls.count("analyze") >= 3:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("three generations never reached the provider")

            analyze_before = gen_services.gateway.calls.count("analyze")
            calls_before = len(gen_services.gateway.calls)
            staging = gen_services.client.app.state.workspace_paths.staging_dir
            attempt_dirs_before = len(list(staging.glob("attempt-*")))

            fourth = await client.post(
                f"/api/v1/drafts/{draft_ids[3]}/generate",
                headers=mutation_headers,
            )
            assert fourth.status_code == 409
            body = fourth.json()
            assert body["error"]["code"] == "PTS_GEN_BUSY"
            assert body["error"]["details"]["activeCount"] == 3
            assert body["error"]["details"]["maxConcurrent"] == 3

            # Zero side effects: no new attempt record, draft unchanged, no
            # additional provider call.
            assert len(list(staging.glob("attempt-*"))) == attempt_dirs_before
            saved = gen_services.draft_repository.get(draft_ids[3])
            assert saved.status.value == "DRAFT"
            assert saved.active_attempt_id is None
            assert gen_services.gateway.calls.count("analyze") == analyze_before
            assert len(gen_services.gateway.calls) == calls_before
        finally:
            # Release any generations frozen on the hold gate so cancellation
            # lands cleanly instead of mid-wait.
            hold = gen_services.gateway.hold
            if hold is not None and not hold.is_set():
                hold.set()
            for task in generate_tasks:
                if not task.done():
                    task.cancel()
                    with suppress(BaseException):
                        await task


# --- Task 19.3: read-only generation progress endpoint -----------------------


def _progress(
    gen_services: GenServices, gen_auth_client: ApiClient, draft_id: str
) -> tuple[int, dict]:
    response = gen_auth_client.client.get(
        f"/api/v1/drafts/{draft_id}/generation",
        headers={"Host": "testserver"},
    )
    body = response.json() if response.content else {}
    return response.status_code, body


def test_progress_missing_draft_returns_404(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    status, body = _progress(gen_services, gen_auth_client, str(uuid4()))
    assert status == 404
    assert body["error"]["code"] == "PTS_DRAFT_NOT_FOUND"


def test_progress_without_active_attempt_is_clear(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    """A READY draft with no running generation reports no progress (200 with a
    null attempt), not a 404 — the draft exists, only the generation is idle."""
    draft_id = _create_ask_gus_draft(gen_services, gen_auth_client)
    status, body = _progress(gen_services, gen_auth_client, draft_id)
    assert status == 200
    assert body["draftId"] == draft_id
    assert body["active"] is False
    assert body["attempt"] is None


async def test_progress_while_generating_returns_current_attempt(
    gen_services: GenServices,
) -> None:
    """Task 19.3: while a server-owned generation runs, the read-only progress
    endpoint returns the persisted attempt's stage/status so the frontend can
    hydrate after a refresh or page nav."""
    from pelican_town_specials.domain.assets import AssetKind

    app = gen_services.client.app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        launch_token = gen_services.security.issue_launch_token()
        bootstrap = await client.post(
            "/session/bootstrap",
            json={"launchToken": launch_token},
            headers={"Host": "testserver"},
        )
        assert bootstrap.status_code == 204
        csrf = bootstrap.headers["x-pts-csrf"]
        mutation_headers = {
            "Host": "testserver",
            "Origin": "http://testserver",
            "X-PTS-CSRF": csrf,
        }

        ref = put_png(gen_services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
        create = await client.post(
            "/api/v1/drafts",
            json={
                "mode": "ASK_GUS",
                "language": "zh-CN",
                "source": {"originalImageAssetId": str(ref.asset_id)},
            },
            headers=mutation_headers,
        )
        assert create.status_code == 201
        draft_id = create.json()["draftId"]

        gen_services.gateway.delay = 0.4

        generate_task = asyncio.create_task(
            client.post(
                f"/api/v1/drafts/{draft_id}/generate",
                headers=mutation_headers,
            )
        )
        try:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if gen_services.gateway.calls:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("generation attempt never reached the provider")

            progress = await client.get(
                f"/api/v1/drafts/{draft_id}/generation",
                headers={"Host": "testserver"},
            )
            assert progress.status_code == 200
            body = progress.json()
            assert body["draftId"] == draft_id
            assert body["active"] is True
            assert body["attempt"] is not None
            attempt = body["attempt"]
            assert attempt["kind"] == "INITIAL"
            assert attempt["status"] in (
                "RUNNING",
                "SUCCEEDED",
            )  # first stage runs quickly
            assert "attemptId" in attempt
            assert "currentStage" in attempt
            assert "stages" in attempt
            # totalStages is the full run total, not the count reached so far
            # (the frontend renders "completed/total" from this pair).
            assert attempt["totalStages"] == 9
            assert len(attempt["stages"]) <= attempt["totalStages"]
            # Internal field must never leak to the client.
            assert "candidateRecordPath" not in attempt
            assert "candidate_record_path" not in attempt
            # Every response key is camelCase.
            assert "draftId" in body
            assert "attemptId" in attempt
        finally:
            if not generate_task.done():
                generate_task.cancel()
                with suppress(BaseException):
                    await generate_task


def test_progress_reflects_finished_terminal_state(
    gen_services: GenServices, gen_auth_client: ApiClient
) -> None:
    """After a successful generation the draft is no longer active but the last
    attempt's terminal status is still surfaced for history/hydration."""
    draft_id = _create_ask_gus_draft(gen_services, gen_auth_client)
    response = gen_auth_client.client.post(
        f"/api/v1/drafts/{draft_id}/generate",
        headers=gen_auth_client.mutation_headers,
    )
    assert response.status_code == 200

    status, body = _progress(gen_services, gen_auth_client, draft_id)
    assert status == 200
    assert body["active"] is False
    assert body["attempt"] is not None
    assert body["attempt"]["status"] == "SUCCEEDED"
