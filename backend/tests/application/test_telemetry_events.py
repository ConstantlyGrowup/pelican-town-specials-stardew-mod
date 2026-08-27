"""Task 38 application telemetry: archive/export terminal facts and replay."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.application.exports import (
    ExportService,
    _dish_count_bucket,
)
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.export import ExportSpec, ExportStatus
from pelican_town_specials.domain.telemetry import (
    DishCountBucket,
    ExportOutcome,
    TelemetryEvent,
    TelemetryEventName,
    TelemetryMode,
)
from pelican_town_specials.mod_compiler.compiler import ContentPatcherCompiler
from pelican_town_specials.persistence.repositories import ExportRepository

from .conftest import AppServices, make_reviewable_draft


@dataclass
class RecordingTelemetryRecorder:
    enabled: bool = True
    events: list[TelemetryEvent] = field(default_factory=list)

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)


@dataclass
class FailingTelemetryRecorder:
    enabled: bool = True

    def record(self, _event: TelemetryEvent) -> None:
        raise RuntimeError("collector failure must not affect archive/export")


def _draft_service(
    services: AppServices,
    recorder: object,
) -> DraftService:
    return DraftService(
        draft_repository=services.draft_repository,
        archive_repository=services.archive_repository,
        asset_store=services.asset_store,
        catalog=services.catalog,
        attempt_repository=services.attempt_repository,
        canonical_registration_service=services.canonical_registration,
        telemetry=recorder,
    )


def _export_service(
    services: AppServices,
    recorder: object,
) -> ExportService:
    return ExportService(
        export_repository=ExportRepository(services.workspace),
        archive_repository=services.archive_repository,
        asset_store=services.asset_store,
        catalog=services.catalog,
        compiler=ContentPatcherCompiler(
            asset_store=services.asset_store,
            author_name=services.workspace.author_name,
        ),
        workspace=services.workspace,
        telemetry=recorder,
    )


def _spec(dish_ids: list[UUID]) -> ExportSpec:
    return ExportSpec(
        dishIds=dish_ids,
        packDisplayName="家庭菜单",
        packSlug="telemetry_pack",
        version="1.0.0",
        description="一份用于测试的菜单。",
        language=Language.ZH_CN,
    )


def _exportable_reviewable_draft(services: AppServices):
    draft = make_reviewable_draft(services)
    assert draft.gameplay is not None
    assert draft.visuals is not None
    ingredients = list(draft.gameplay.ingredients)
    ingredients[0] = ingredients[0].model_copy(update={"display_name": "Parsnip"})
    gameplay = draft.gameplay.model_copy(update={"ingredients": ingredients})
    visuals = draft.visuals.model_copy(
        update={"source_revision": draft.revision + 1}
    )
    return services.draft_repository.save(
        draft.model_copy(update={"gameplay": gameplay, "visuals": visuals}),
        expected_revision=draft.revision,
    )


def _zip_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w") as archive:
        archive.writestr("manifest.json", "{}")
    return output.getvalue()


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, DishCountBucket.ONE),
        (2, DishCountBucket.TWO_TO_FIVE),
        (5, DishCountBucket.TWO_TO_FIVE),
        (6, DishCountBucket.SIX_TO_TEN),
        (10, DishCountBucket.SIX_TO_TEN),
        (11, DishCountBucket.ELEVEN_PLUS),
    ],
)
def test_dish_count_bucket_boundaries(count: int, expected: DishCountBucket) -> None:
    assert _dish_count_bucket(count) is expected


def test_archive_and_export_replays_emit_only_first_terminal_events(
    services: AppServices,
) -> None:
    recorder = RecordingTelemetryRecorder()
    drafts = _draft_service(services, recorder)
    exports = _export_service(services, recorder)
    draft = _exportable_reviewable_draft(services)

    archive = drafts.archive_draft(draft.draft_id, "archive-telemetry")
    replayed_archive = drafts.archive_draft(draft.draft_id, "archive-telemetry")
    assert replayed_archive.dish_id == archive.dish_id

    with patch.object(exports, "_compile", return_value=_zip_bytes()):
        succeeded = exports.create_export(
            _spec([archive.dish_id]),
            idempotency_key="export-success-telemetry",
        )
        replayed_success = exports.create_export(
            _spec([archive.dish_id]),
            idempotency_key="export-success-telemetry",
        )
    assert succeeded.status is ExportStatus.SUCCEEDED
    assert replayed_success.export_id == succeeded.export_id

    failed = exports.create_export(
        _spec([uuid4()]),
        idempotency_key="export-failed-telemetry",
    )
    replayed_failed = exports.create_export(
        _spec([uuid4()]),
        idempotency_key="export-failed-telemetry",
    )
    assert failed.status is ExportStatus.FAILED
    assert replayed_failed.export_id == failed.export_id

    assert [event.event for event in recorder.events] == [
        TelemetryEventName.DISH_ARCHIVED,
        TelemetryEventName.MENU_EXPORT_FINISHED,
        TelemetryEventName.MENU_EXPORT_FINISHED,
    ]
    assert recorder.events[0].properties.mode is TelemetryMode.ASK_GUS
    assert recorder.events[1].properties.outcome is ExportOutcome.SUCCEEDED
    assert recorder.events[1].properties.dish_count_bucket is DishCountBucket.ONE
    assert recorder.events[2].properties.outcome is ExportOutcome.FAILED
    assert recorder.events[2].properties.dish_count_bucket is DishCountBucket.ONE


def test_archive_and_export_ignore_recorder_failure(
    services: AppServices,
) -> None:
    recorder = FailingTelemetryRecorder()
    draft = _exportable_reviewable_draft(services)
    archive = _draft_service(services, recorder).archive_draft(
        draft.draft_id,
        "archive-failing-telemetry",
    )
    exports = _export_service(services, recorder)
    with patch.object(exports, "_compile", return_value=_zip_bytes()):
        exported = exports.create_export(
            _spec([archive.dish_id]),
            idempotency_key="export-failing-telemetry",
        )

    assert archive.dish_id in {
        item.dish_id for item in services.archive_repository.list_active()
    }
    assert exported.status is ExportStatus.SUCCEEDED


def test_application_telemetry_contains_only_frozen_bounded_values(
    services: AppServices,
) -> None:
    recorder = RecordingTelemetryRecorder()
    draft = _exportable_reviewable_draft(services)
    archive = _draft_service(services, recorder).archive_draft(
        draft.draft_id,
        "archive-private-telemetry",
    )
    exports = _export_service(services, recorder)
    with patch.object(exports, "_compile", return_value=_zip_bytes()):
        exports.create_export(
            _spec([archive.dish_id]),
            idempotency_key="export-private-telemetry",
        )

    serialized = json.dumps(
        [event.model_dump(mode="json") for event in recorder.events],
        ensure_ascii=False,
    ).lower()
    for forbidden in (
        "draft_id",
        "attempt_id",
        "canonical_id",
        "archive_id",
        "export_id",
        "display_name",
        "ingredient",
        "prompt",
        "provider",
        "model",
        "api_key",
        "exception",
    ):
        assert forbidden not in serialized
