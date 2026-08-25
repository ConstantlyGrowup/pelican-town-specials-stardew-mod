from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from backend.tests.domain.factories import (
    archived_dish_fixture,
    blueprint_reviewable_fixture,
    make_draft,
)

from pelican_town_specials.application.canonical_memory import (
    CanonicalRegistrationService,
)
from pelican_town_specials.application.cookbook import CookbookService
from pelican_town_specials.application.drafts import DraftService
from pelican_town_specials.domain.assets import AssetKind
from pelican_town_specials.domain.canonical import CanonicalIconKind
from pelican_town_specials.domain.common import DraftMode
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.canonical_registry import (
    SQLiteCanonicalRegistry,
)

from .conftest import AppServices, make_reviewable_draft, put_png


def _registry_service(
    services: AppServices,
) -> tuple[SQLiteCanonicalRegistry, CanonicalRegistrationService]:
    registry = SQLiteCanonicalRegistry(services.workspace)
    registration = CanonicalRegistrationService(
        registry=registry,
        archive_repository=services.archive_repository,
        draft_repository=services.draft_repository,
        asset_store=services.asset_store,
    )
    return registry, registration


def _draft_service(
    services: AppServices,
    registration: CanonicalRegistrationService | object | None = None,
) -> DraftService:
    return DraftService(
        draft_repository=services.draft_repository,
        archive_repository=services.archive_repository,
        asset_store=services.asset_store,
        catalog=services.catalog,
        attempt_repository=services.attempt_repository,
        canonical_registration_service=registration,
    )


def _blueprint_reviewable_with_icons(services: AppServices):
    preview_ref = put_png(
        services.asset_store,
        kind=AssetKind.PREVIEW,
        color="purple",
    )
    source_icon_ref = put_png(
        services.asset_store,
        kind=AssetKind.ICON_SOURCE,
        size=32,
        color="green",
    )
    icon_ref = put_png(
        services.asset_store,
        kind=AssetKind.ICON_16,
        color="gold",
    )
    draft = blueprint_reviewable_fixture()
    visuals = draft.visuals.model_copy(
        update={
            "preview_asset_id": preview_ref.asset_id,
            "icon_source_asset_id": source_icon_ref.asset_id,
            "icon_16_asset_id": icon_ref.asset_id,
        }
    )
    return services.draft_repository.save(
        draft.model_copy(update={"visuals": visuals}),
        expected_revision=None,
    )


def _future_hit_archive(archive, canonical_id: UUID):
    provenance = archive.internal_provenance.model_copy(deep=True)
    object.__setattr__(provenance, "generation_source", "CANONICAL_REUSED")
    object.__setattr__(provenance, "canonical_dish_id", canonical_id)
    return archive.__class__.model_construct(
        schema_version=archive.schema_version,
        dish_id=uuid4(),
        archive_revision=archive.archive_revision,
        archived_at=archive.archived_at,
        presentation=archive.presentation,
        gameplay=archive.gameplay,
        visuals=archive.visuals,
        content_hash=archive.content_hash,
        internal_provenance=provenance,
        source_draft_id=archive.source_draft_id,
    )


def test_registration_runs_only_after_archive_success(
    services: AppServices,
) -> None:
    calls: list[object] = []

    class SpyRegistration:
        def register_archive(self, archive: object) -> None:
            calls.append(archive)

    service = _draft_service(services, SpyRegistration())
    reviewable = make_reviewable_draft(services)

    assert calls == []
    with pytest.raises(AppError):
        service.archive_draft(uuid4(), "missing-draft")
    assert calls == []

    archive = service.archive_draft(reviewable.draft_id, "archive-key")
    assert calls == [archive]

    failed = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.FAILED)
    services.draft_repository.save(failed, expected_revision=None)
    with pytest.raises(AppError):
        service.archive_draft(failed.draft_id, "failed-key")
    assert calls == [archive]


def test_blueprint_archive_is_ignored_and_ask_gus_fresh_is_idempotent(
    services: AppServices,
) -> None:
    registry, registration = _registry_service(services)
    service = _draft_service(services, registration)

    blueprint = _blueprint_reviewable_with_icons(services)
    blueprint_archive = service.archive_draft(blueprint.draft_id, "blueprint-key")
    assert blueprint_archive.internal_provenance.mode is DraftMode.BLUEPRINT
    assert registry.count_valid() == 0

    reviewable = make_reviewable_draft(services)
    first = service.archive_draft(reviewable.draft_id, "fresh-key")
    second = service.archive_draft(reviewable.draft_id, "fresh-key")

    assert second.dish_id == first.dish_id
    assert registry.count_valid() == 1
    assert registry.get_by_source_archive_id(first.dish_id) is not None


def test_canonical_reused_archive_records_one_usage_without_duplicate(
    services: AppServices,
) -> None:
    registry, registration = _registry_service(services)
    service = _draft_service(services, registration)
    reviewable = make_reviewable_draft(services)
    archive = service.archive_draft(reviewable.draft_id, "fresh-key")
    canonical = registry.get_by_source_archive_id(archive.dish_id)
    assert canonical is not None

    hit = _future_hit_archive(archive, canonical.canonical_id)
    registration.register_archive(hit)
    registration.register_archive(hit)

    stored = registry.get_valid(canonical.canonical_id)
    assert stored is not None
    assert stored.use_count == 1
    assert registry.count_valid() == 1


def test_registration_copies_recall_and_frozen_archive_fields_only(
    services: AppServices,
) -> None:
    registry, registration = _registry_service(services)
    service = _draft_service(services, registration)
    reviewable = make_reviewable_draft(services)
    archive = service.archive_draft(reviewable.draft_id, "content-key")
    canonical = registry.get_by_source_archive_id(archive.dish_id)
    assert canonical is not None

    source_draft = services.draft_repository.get(archive.source_draft_id)
    assert source_draft.analysis is not None
    assert canonical.recall_document.recognized_dish == (
        source_draft.analysis.recognized_dish
    )
    assert canonical.recall_document.normalized_name == "spring noodles"
    assert canonical.presentation == archive.presentation
    assert canonical.gameplay == archive.gameplay
    assert canonical.visual_brief == archive.visuals.visual_brief
    assert canonical.icon_source.byte_size > 0
    assert canonical.icon_16.width == 16
    payload = canonical.model_dump(by_alias=True, mode="json")
    assert "originalImageAssetId" not in payload
    assert "previewAssetId" not in payload
    assert "contextText" not in payload
    assert len(canonical.dish_signature) == 64
    assert canonical.dish_signature == canonical.dish_signature.lower()


def test_registry_failure_is_fail_open_and_startup_repair_can_retry(
    services: AppServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    class FailingRegistry:
        def get_by_source_archive_id(self, _source_archive_id: UUID):
            raise RuntimeError("sk-live-secret")

        def register(self, *_args: object, **_kwargs: object):
            raise RuntimeError("sk-live-secret")

        def record_usage(self, *_args: object, **_kwargs: object):
            raise RuntimeError("sk-live-secret")

    monkeypatch.setattr(
        "pelican_town_specials.application.canonical_memory.log_event",
        lambda _level, **fields: captured.append(fields),
    )
    failed_registration = CanonicalRegistrationService(
        registry=FailingRegistry(),
        archive_repository=services.archive_repository,
        draft_repository=services.draft_repository,
        asset_store=services.asset_store,
    )
    service = _draft_service(services, failed_registration)
    reviewable = make_reviewable_draft(services)

    archive = service.archive_draft(reviewable.draft_id, "fail-open-key")
    assert archive.dish_id
    assert captured
    assert "sk-live-secret" not in repr(captured)
    assert all("message" not in fields for fields in captured)

    registry = SQLiteCanonicalRegistry(services.workspace)
    repaired = CanonicalRegistrationService(
        registry=registry,
        archive_repository=services.archive_repository,
        draft_repository=services.draft_repository,
        asset_store=services.asset_store,
    )
    repaired.reconcile_active_archives()
    assert registry.get_by_source_archive_id(archive.dish_id) is not None


def test_startup_reconciliation_is_bounded_idempotent_and_skips_bad_inputs(
    services: AppServices,
) -> None:
    registry, registration = _registry_service(services)
    service = _draft_service(services, registration)
    valid_draft = make_reviewable_draft(services)
    valid_archive = service.archive_draft(valid_draft.draft_id, "valid-key")

    missing_draft_archive = archived_dish_fixture(
        source_draft_id=uuid4(),
        dish_id=uuid4(),
    )
    services.archive_repository.add_immutable(
        missing_draft_archive,
        idempotency_key="missing-draft-key",
    )
    missing_analysis = make_reviewable_draft(services)
    services.draft_repository.save(
        missing_analysis.model_copy(update={"analysis": None}),
        expected_revision=missing_analysis.revision,
    )
    missing_analysis_archive = archived_dish_fixture(
        source_draft_id=missing_analysis.draft_id,
        dish_id=uuid4(),
    )
    services.archive_repository.add_immutable(
        missing_analysis_archive,
        idempotency_key="missing-analysis-key",
    )

    registration.reconcile_active_archives()
    registration.reconcile_active_archives()

    assert registry.count_valid() == 1
    assert registry.get_by_source_archive_id(valid_archive.dish_id) is not None


@pytest.mark.asyncio
async def test_cookbook_delete_keeps_registered_canonical_and_owned_icons(
    services: AppServices,
) -> None:
    registry, registration = _registry_service(services)
    draft_service = _draft_service(services, registration)
    reviewable = make_reviewable_draft(services)
    archive = draft_service.archive_draft(reviewable.draft_id, "delete-key")
    canonical = registry.get_by_source_archive_id(archive.dish_id)
    assert canonical is not None
    source_bytes = registry.load_owned_icon(
        canonical.canonical_id,
        CanonicalIconKind.SOURCE,
    )

    await CookbookService(
        services.archive_repository,
        draft_service=draft_service,
    ).delete(archive.dish_id)

    assert registry.get_valid(canonical.canonical_id) is not None
    assert (
        registry.load_owned_icon(canonical.canonical_id, CanonicalIconKind.SOURCE)
        == source_bytes
    )


def test_archive_idempotency_retry_does_not_increment_usage_or_registration(
    services: AppServices,
) -> None:
    registry, registration = _registry_service(services)
    service = _draft_service(services, registration)
    reviewable = make_reviewable_draft(services)

    first = service.archive_draft(reviewable.draft_id, "retry-key")
    current = services.draft_repository.get(reviewable.draft_id)
    services.draft_repository.save(
        current.model_copy(
            update={"status": DraftStatus.REVIEWABLE, "archived_dish_id": None}
        ),
        expected_revision=current.revision,
    )
    second = service.archive_draft(reviewable.draft_id, "retry-key")

    assert second.dish_id == first.dish_id
    canonical = registry.get_by_source_archive_id(first.dish_id)
    assert canonical is not None
    assert canonical.use_count == 0
    assert registry.count_valid() == 1


def test_archive_uses_repository_result_when_idempotency_check_races(
    services: AppServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, registration = _registry_service(services)
    service = _draft_service(services, registration)
    reviewable = make_reviewable_draft(services)

    first = service.archive_draft(reviewable.draft_id, "race-key")
    current = services.draft_repository.get(reviewable.draft_id)
    services.draft_repository.save(
        current.model_copy(
            update={
                "status": DraftStatus.REVIEWABLE,
                "archived_dish_id": None,
                "visuals": current.visuals.model_copy(
                    update={"source_revision": current.revision + 1}
                ),
            }
        ),
        expected_revision=current.revision,
    )

    monkeypatch.setattr(
        services.archive_repository,
        "get_by_idempotency_key",
        lambda _key: None,
    )
    monkeypatch.setattr(
        services.archive_repository,
        "add_immutable",
        lambda _archive, *, idempotency_key: first,
    )

    second = service.archive_draft(reviewable.draft_id, "race-key")

    assert second.dish_id == first.dish_id
    assert services.draft_repository.get(reviewable.draft_id).archived_dish_id == (
        first.dish_id
    )
    assert registry.count_valid() == 1


def test_normalization_removes_punctuation_and_collapses_unicode_whitespace() -> None:
    from pelican_town_specials.application.canonical_memory import normalize_recall_text

    assert normalize_recall_text("  Spring—Noodles！\nBowl  ") == (
        "spring noodles bowl"
    )
