"""Task 9 Draft create/convert/patch/discard/archive use-case tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from backend.tests.domain.factories import (
    ask_gus_reviewable_fixture,
    blueprint_reviewable_fixture,
)
from pydantic import ValidationError

from pelican_town_specials.application.drafts import (
    BlueprintGameplayInput,
    BlueprintIngredientInput,
    BlueprintPresentationInput,
    BlueprintRecoveryInput,
    DraftCreateRequest,
    DraftCreateSource,
    DraftPatchRequest,
    DraftService,
    DraftSortBy,
    DraftSortOrder,
)
from pelican_town_specials.domain.assets import AssetKind
from pelican_town_specials.domain.common import DraftMode, Language, utc_now
from pelican_town_specials.domain.dish import FieldAuthority, GenerationSource
from pelican_town_specials.domain.draft import (
    AttemptStatus,
    DraftRecord,
    DraftStatus,
    GenerationAttempt,
    GenerationAttemptKind,
    GenerationStage,
    StageAttempt,
    StageStatus,
)
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.persistence.asset_store import AssetNotFoundError

from .conftest import AppServices, make_reviewable_draft, put_png


def _service(services: AppServices) -> DraftService:
    return DraftService(
        draft_repository=services.draft_repository,
        archive_repository=services.archive_repository,
        asset_store=services.asset_store,
        catalog=services.catalog,
        attempt_repository=services.attempt_repository,
        canonical_registration_service=services.canonical_registration,
    )


def _presentation() -> BlueprintPresentationInput:
    return BlueprintPresentationInput(
        displayName="南瓜汤",
        internalName="PumpkinSoup",
        categoryLabel="汤类",
        description="香甜的南瓜汤。",
        tags=["fall", "soup"],
    )


def _gameplay() -> BlueprintGameplayInput:
    return BlueprintGameplayInput(
        ingredients=[
            BlueprintIngredientInput(
                itemId="24",
                displayName="Parsnip",
                quantity=1,
                mappingReason="catalog match",
                catalogVersion="stardew-1.6.15-v1",
            )
        ],
        recovery=BlueprintRecoveryInput(edibility=20),
        sellPrice=35,
        isDrink=False,
    )


def _create_blueprint(services: AppServices) -> tuple[DraftService, object, object]:
    service = _service(services)
    asset_ref = put_png(services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
    record = service.create_draft(
        DraftCreateRequest(
            mode=DraftMode.BLUEPRINT,
            language=Language.ZH_CN,
            source=DraftCreateSource(originalImageAssetId=asset_ref.asset_id),
        )
    )
    return service, record, asset_ref


def _succeeded_attempt(draft_id: object) -> GenerationAttempt:
    now = utc_now()
    return GenerationAttempt(
        attemptId=uuid4(),
        draftId=draft_id,
        kind=GenerationAttemptKind.INITIAL,
        sourceRevision=1,
        status=AttemptStatus.SUCCEEDED,
        currentStage=GenerationStage.ATOMIC_PROMOTION,
        stages=[
            StageAttempt(
                stage=GenerationStage.ATOMIC_PROMOTION,
                status=StageStatus.SUCCEEDED,
                retryCount=0,
                startedAt=now,
                finishedAt=now,
                error=None,
            )
        ],
        candidateRecordPath=None,
        startedAt=now,
        finishedAt=now,
        error=None,
    )


def test_create_blueprint_draft_has_blueprint_template(services: AppServices) -> None:
    service = _service(services)
    asset_ref = put_png(services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
    record = service.create_draft(
        DraftCreateRequest(
            mode=DraftMode.BLUEPRINT,
            language=Language.ZH_CN,
            source=DraftCreateSource(
                originalImageAssetId=asset_ref.asset_id,
                contextText="seasonal",
            ),
        )
    )

    assert record.mode is DraftMode.BLUEPRINT
    assert record.base_template_version == "blueprint-v1"
    assert record.status is DraftStatus.DRAFT
    assert record.revision == 1
    assert record.analysis is None
    assert record.presentation is None
    assert record.gameplay is None
    assert record.visuals is None
    assert record.provenance.mode is DraftMode.BLUEPRINT
    assert record.provenance.generation_source is GenerationSource.USER_AUTHORED
    assert record.provenance.cache_eligibility is False
    assert record.provenance.vision_model is None
    assert record.provenance.text_model is None
    assert record.provenance.image_model is None
    assert record.provenance.prompt_versions == {}
    assert record.provenance.canonical_dish_signature is None
    assert (
        record.provenance.authority_by_field["presentation.display_name"]
        is FieldAuthority.USER_ASSIGNED
    )
    assert (
        record.provenance.authority_by_field["gameplay.buff"]
        is FieldAuthority.USER_ASSIGNED
    )

    loaded = services.draft_repository.get(record.draft_id)
    assert loaded.base_template_version == "blueprint-v1"
    assert loaded.source.context_text == "seasonal"


def test_create_ask_gus_draft_has_no_template(services: AppServices) -> None:
    service = _service(services)
    asset_ref = put_png(services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
    record = service.create_draft(
        DraftCreateRequest(
            mode=DraftMode.ASK_GUS,
            language=Language.EN_US,
            source=DraftCreateSource(originalImageAssetId=asset_ref.asset_id),
        )
    )

    assert record.mode is DraftMode.ASK_GUS
    assert record.base_template_version is None
    assert record.status is DraftStatus.DRAFT
    assert record.provenance.cache_eligibility is True


def test_create_draft_rejects_missing_source_image(services: AppServices) -> None:
    service = _service(services)
    with pytest.raises(AppError) as excinfo:
        service.create_draft(
            DraftCreateRequest(
                mode=DraftMode.BLUEPRINT,
                language=Language.ZH_CN,
                source=DraftCreateSource(originalImageAssetId=uuid4()),
            )
        )
    assert excinfo.value.code == "PTS_INPUT_SOURCE_IMAGE_MISSING"


def test_create_draft_rejects_non_original_image_asset(
    services: AppServices,
) -> None:
    service = _service(services)
    preview_ref = put_png(services.asset_store, kind=AssetKind.PREVIEW)

    with pytest.raises(AppError) as excinfo:
        service.create_draft(
            DraftCreateRequest(
                mode=DraftMode.BLUEPRINT,
                language=Language.ZH_CN,
                source=DraftCreateSource(originalImageAssetId=preview_ref.asset_id),
            )
        )
    assert excinfo.value.code == "PTS_INPUT_SOURCE_IMAGE_MISSING"


def test_context_text_over_500_rejected_at_request_boundary() -> None:
    with pytest.raises(ValidationError):
        DraftCreateSource(originalImageAssetId=uuid4(), contextText="x" * 501)

    trimmed = DraftCreateSource(
        originalImageAssetId=uuid4(),
        contextText="  " + "x" * 498 + "  ",
    )
    assert trimmed.context_text == "x" * 498


def test_patch_gameplay_marks_buff_user_assigned(services: AppServices) -> None:
    service, record, _ = _create_blueprint(services)

    updated = service.patch_draft(
        record.draft_id,
        DraftPatchRequest(
            expected_revision=record.revision,
            gameplay=_gameplay(),
        ),
    )

    assert updated.gameplay is not None
    assert updated.gameplay.sell_price == 35
    assert (
        updated.provenance.authority_by_field["gameplay.buff"]
        is FieldAuthority.USER_ASSIGNED
    )
    assert (
        updated.provenance.authority_by_field["gameplay.sell_price"]
        is FieldAuthority.USER_ASSIGNED
    )


def test_list_and_get_draft(services: AppServices) -> None:
    service, record, asset_ref = _create_blueprint(services)

    page = service.list_drafts()

    assert page.total == 1
    assert page.items[0].draft_id == record.draft_id
    assert page.items[0].mode is DraftMode.BLUEPRINT
    assert page.items[0].status is DraftStatus.DRAFT
    assert page.items[0].original_image_asset_id == asset_ref.asset_id
    assert page.items[0].display_name == ""

    got = service.get_draft(record.draft_id)
    assert got.draft_id == record.draft_id
    assert got.base_template_version == "blueprint-v1"


def test_get_draft_unknown_raises_not_found(services: AppServices) -> None:
    with pytest.raises(AppError) as excinfo:
        _service(services).get_draft(uuid4())
    assert excinfo.value.code == "PTS_DRAFT_NOT_FOUND"


def test_convert_to_blueprint_copies_only_original_image(services: AppServices) -> None:
    reviewable = make_reviewable_draft(services)
    service = _service(services)

    blueprint = service.convert_to_blueprint(reviewable.draft_id)

    assert blueprint.mode is DraftMode.BLUEPRINT
    assert blueprint.base_template_version == "blueprint-v1"
    assert blueprint.status is DraftStatus.DRAFT
    assert (
        blueprint.source.original_image_asset_id
        == reviewable.source.original_image_asset_id
    )
    assert blueprint.source.context_text is None
    assert blueprint.source.language == reviewable.source.language
    assert blueprint.analysis is None
    assert blueprint.presentation is None
    assert blueprint.gameplay is None
    assert blueprint.visuals is None
    assert blueprint.provenance.vision_model is None
    assert blueprint.provenance.text_model is None
    assert blueprint.provenance.image_model is None
    assert blueprint.provenance.prompt_versions == {}
    assert blueprint.provenance.canonical_dish_signature is None

    unchanged = services.draft_repository.get(reviewable.draft_id)
    assert unchanged.status is DraftStatus.REVIEWABLE
    assert unchanged.analysis is not None


def test_convert_to_blueprint_rejects_blueprint_source(services: AppServices) -> None:
    service, record, _ = _create_blueprint(services)

    with pytest.raises(AppError) as excinfo:
        service.convert_to_blueprint(record.draft_id)
    assert excinfo.value.code == "PTS_STATE_ILLEGAL_TRANSITION"


def test_patch_blueprint_updates_fields_and_bumps_revision(
    services: AppServices,
) -> None:
    service, record, _ = _create_blueprint(services)
    presentation = _presentation()

    updated = service.patch_draft(
        record.draft_id,
        DraftPatchRequest(
            expected_revision=record.revision,
            presentation=presentation,
        ),
    )

    assert updated.revision == record.revision + 1
    assert updated.presentation is not None
    assert updated.presentation.display_name == "南瓜汤"
    assert updated.status is DraftStatus.DRAFT
    assert (
        updated.provenance.authority_by_field["presentation.display_name"]
        is FieldAuthority.USER_ASSIGNED
    )


def test_patch_reviewable_blueprint_becomes_stale_preview(
    services: AppServices,
) -> None:
    blueprint = blueprint_reviewable_fixture()
    services.draft_repository.save(blueprint, expected_revision=None)
    service = _service(services)

    updated = service.patch_draft(
        blueprint.draft_id,
        DraftPatchRequest(
            expected_revision=blueprint.revision,
            presentation=_presentation(),
        ),
    )

    assert updated.status is DraftStatus.STALE_PREVIEW


def test_patch_ask_gus_is_rejected(services: AppServices) -> None:
    reviewable = make_reviewable_draft(services)
    service = _service(services)

    with pytest.raises(AppError) as excinfo:
        service.patch_draft(
            reviewable.draft_id,
            DraftPatchRequest(
                expected_revision=reviewable.revision,
                presentation=_presentation(),
            ),
        )
    assert excinfo.value.code == "PTS_STATE_ILLEGAL_TRANSITION"


def test_patch_revision_conflict_leaves_record_unchanged(services: AppServices) -> None:
    service, record, _ = _create_blueprint(services)

    with pytest.raises(AppError) as excinfo:
        service.patch_draft(
            record.draft_id,
            DraftPatchRequest(
                expected_revision=99,
                presentation=_presentation(),
            ),
        )
    assert excinfo.value.code == "PTS_STATE_REVISION_CONFLICT"
    assert services.draft_repository.get(record.draft_id).revision == 1


def test_patch_requires_presentation_or_gameplay() -> None:
    with pytest.raises(ValidationError):
        DraftPatchRequest(expected_revision=1)


async def test_discard_draft_deletes_record(services: AppServices) -> None:
    service, record, _ = _create_blueprint(services)

    await service.discard_draft(record.draft_id)

    with pytest.raises(AppError) as excinfo:
        service.get_draft(record.draft_id)
    assert excinfo.value.code == "PTS_DRAFT_NOT_FOUND"
    assert [item.draft_id for item in service.list_drafts().items] == []
    assert not (services.workspace.drafts_dir / str(record.draft_id)).exists()


async def test_discard_draft_removes_attempt_directory(
    services: AppServices,
) -> None:
    service, record, _ = _create_blueprint(services)
    attempt = _succeeded_attempt(record.draft_id)
    services.attempt_repository.save(attempt)

    await service.discard_draft(record.draft_id)

    assert not (
        services.workspace.staging_dir / f"attempt-{attempt.attempt_id}"
    ).exists()


async def test_discard_draft_deletes_unshared_assets(
    services: AppServices,
) -> None:
    service, record, asset_ref = _create_blueprint(services)

    await service.discard_draft(record.draft_id)

    with pytest.raises(AssetNotFoundError):
        services.asset_store.stat(asset_ref.asset_id)


async def test_discard_source_draft_keeps_shared_original_image(
    services: AppServices,
) -> None:
    original_ref = put_png(
        services.asset_store, kind=AssetKind.ORIGINAL_IMAGE, color="green"
    )
    preview_ref = put_png(
        services.asset_store, kind=AssetKind.PREVIEW, color="purple"
    )
    icon_ref = put_png(services.asset_store, kind=AssetKind.ICON_16, color="gold")
    draft = ask_gus_reviewable_fixture()
    source = draft.source.model_copy(
        update={"original_image_asset_id": original_ref.asset_id}
    )
    visuals = draft.visuals.model_copy(
        update={
            "preview_asset_id": preview_ref.asset_id,
            "icon_16_asset_id": icon_ref.asset_id,
        }
    )
    draft = draft.model_copy(update={"source": source, "visuals": visuals})
    services.draft_repository.save(draft, expected_revision=None)
    service = _service(services)
    blueprint = service.convert_to_blueprint(draft.draft_id)
    assert blueprint.source.original_image_asset_id == original_ref.asset_id

    await service.discard_draft(draft.draft_id)

    assert services.asset_store.stat(original_ref.asset_id) is not None
    with pytest.raises(AssetNotFoundError):
        services.asset_store.stat(preview_ref.asset_id)
    with pytest.raises(AssetNotFoundError):
        services.asset_store.stat(icon_ref.asset_id)


async def test_discard_archived_draft_is_rejected(services: AppServices) -> None:
    reviewable = make_reviewable_draft(services)
    service = _service(services)
    service.archive_draft(reviewable.draft_id, "archive-key")

    with pytest.raises(AppError) as excinfo:
        await service.discard_draft(reviewable.draft_id)
    assert excinfo.value.code == "PTS_STATE_ILLEGAL_TRANSITION"


def test_archive_reviewable_draft_links_archived_status(services: AppServices) -> None:
    reviewable = make_reviewable_draft(services)
    service = _service(services)

    archive = service.archive_draft(reviewable.draft_id, "archive-key")

    assert archive.source_draft_id == reviewable.draft_id
    assert len(archive.content_hash) == 64
    stored = services.draft_repository.get(reviewable.draft_id)
    assert stored.status is DraftStatus.ARCHIVED
    assert stored.archived_dish_id == archive.dish_id


def test_archive_is_idempotent_for_same_key_and_draft(services: AppServices) -> None:
    reviewable = make_reviewable_draft(services)
    service = _service(services)

    first = service.archive_draft(reviewable.draft_id, "same-key")
    second = service.archive_draft(reviewable.draft_id, "same-key")

    assert second.dish_id == first.dish_id
    assert second.content_hash == first.content_hash
    assert len(services.archive_repository.list_active()) == 1


def test_archive_same_key_different_draft_conflicts(services: AppServices) -> None:
    first = make_reviewable_draft(services)
    second = make_reviewable_draft(services)
    service = _service(services)
    service.archive_draft(first.draft_id, "shared-key")

    with pytest.raises(AppError) as excinfo:
        service.archive_draft(second.draft_id, "shared-key")
    assert excinfo.value.code == "PTS_IDEMPOTENCY_CONFLICT"


def test_archive_non_reviewable_draft_rejected(services: AppServices) -> None:
    service, record, _ = _create_blueprint(services)

    with pytest.raises(AppError) as excinfo:
        service.archive_draft(record.draft_id, "key")
    assert excinfo.value.code == "PTS_STATE_ILLEGAL_TRANSITION"


def test_archive_missing_idempotency_key_rejected(services: AppServices) -> None:
    reviewable = make_reviewable_draft(services)
    service = _service(services)

    with pytest.raises(AppError) as excinfo:
        service.archive_draft(reviewable.draft_id, "  ")
    assert excinfo.value.code == "PTS_INPUT_IDEMPOTENCY_KEY_REQUIRED"


def test_archive_rejects_missing_visual_asset(services: AppServices) -> None:
    draft = ask_gus_reviewable_fixture()
    services.draft_repository.save(draft, expected_revision=None)
    service = _service(services)

    with pytest.raises(AppError) as excinfo:
        service.archive_draft(draft.draft_id, "key")
    assert excinfo.value.code == "PTS_ARCHIVE_VALIDATION_FAILED"


def test_archive_retry_repairs_missing_draft_association(
    services: AppServices,
) -> None:
    reviewable = make_reviewable_draft(services)
    service = _service(services)
    first = service.archive_draft(reviewable.draft_id, "retry-key")

    current = services.draft_repository.get(reviewable.draft_id)
    reset = current.model_copy(
        update={
            "status": DraftStatus.REVIEWABLE,
            "archived_dish_id": None,
        }
    )
    services.draft_repository.save(reset, expected_revision=current.revision)

    retried = service.archive_draft(reviewable.draft_id, "retry-key")

    assert retried.dish_id == first.dish_id
    stored = services.draft_repository.get(reviewable.draft_id)
    assert stored.status is DraftStatus.ARCHIVED
    assert stored.archived_dish_id == first.dish_id
    assert len(services.archive_repository.list_active()) == 1


def test_list_drafts_filters_orphaned_archived(services: AppServices) -> None:
    """ARCHIVED drafts whose dish was deleted (before the cascade fix) are
    hidden from the homepage listing immediately."""
    reviewable = make_reviewable_draft(services)
    service = _service(services)
    archive = service.archive_draft(reviewable.draft_id, "orphan-key")

    # Simulate a pre-fix deletion: tombstone the dish without the cascade, so
    # the source draft is left behind with a dangling archived_dish_id.
    services.archive_repository.delete(archive.dish_id)

    page = service.list_drafts()

    assert page.total == 0


async def test_list_drafts_keeps_archived_when_dish_active(
    services: AppServices,
) -> None:
    """An ARCHIVED draft with an active dish still shows as archived and remains
    non-discardable (DEL-003 unchanged)."""
    reviewable = make_reviewable_draft(services)
    service = _service(services)
    service.archive_draft(reviewable.draft_id, "active-key")

    page = service.list_drafts()

    assert page.total == 1
    assert page.items[0].draft_id == reviewable.draft_id
    assert page.items[0].status is DraftStatus.ARCHIVED
    with pytest.raises(AppError) as excinfo:
        await service.discard_draft(reviewable.draft_id)
    assert excinfo.value.code == "PTS_STATE_ILLEGAL_TRANSITION"


# --- M13 Task 57: homepage pagination and time sorting ---


def _persisted_draft(
    services: AppServices,
    *,
    created_at: datetime,
    updated_at: datetime,
    name: str,
) -> DraftRecord:
    source_ref = put_png(
        services.asset_store,
        kind=AssetKind.ORIGINAL_IMAGE,
        size=32,
    )
    base = ask_gus_reviewable_fixture(revision=1)
    presentation = base.presentation.model_copy(update={"display_name": name})
    draft = base.model_copy(
        update={
            "source": base.source.model_copy(
                update={"original_image_asset_id": source_ref.asset_id}
            ),
            "created_at": created_at,
            "updated_at": updated_at,
            "presentation": presentation,
        }
    )
    return services.draft_repository.save(draft, expected_revision=None)


def _seed_paginated_drafts(
    services: AppServices,
    *,
    count: int = 11,
) -> list[DraftRecord]:
    base = datetime(2026, 9, 1, tzinfo=UTC)
    saved: list[DraftRecord] = []
    for index in range(count):
        created = base.replace(hour=0) + timedelta(hours=index)
        updated = base.replace(hour=1) + timedelta(hours=index)
        draft = _persisted_draft(
            services,
            created_at=created,
            updated_at=updated,
            name=f"排序草稿-{index}",
        )
        saved.append(draft)
    return saved


def test_list_drafts_paginates_over_globally_sorted_set(
    services: AppServices,
) -> None:
    drafts = _seed_paginated_drafts(services)
    service = _service(services)

    first = service.list_drafts(page=1, page_size=10)

    assert first.total == 11
    assert first.page_size == 10
    assert first.total_pages == 2
    assert first.page == 1
    assert first.has_running_generation is False
    assert [item.draft_id for item in first.items] == [
        draft.draft_id for draft in reversed(drafts)
    ][:10]
    # The default sort is updatedAt desc; the newest draft is first.
    assert first.items[0].display_name == "排序草稿-10"

    last = service.list_drafts(page=2, page_size=10)
    assert last.page == 2
    assert [item.draft_id for item in last.items] == [
        drafts[0].draft_id
    ]
    # An out-of-range page normalizes back to the last valid page (a page can
    # become empty after deleting the final item of the previous page).
    clamped = service.list_drafts(page=99, page_size=10)
    assert clamped.page == 2
    assert [item.draft_id for item in clamped.items] == [drafts[0].draft_id]

    # pageSize 1 walks the full set without duplicates or gaps.
    walked: list[UUID] = []
    for page_number in range(1, 12):
        page = service.list_drafts(page=page_number, page_size=1)
        assert page.page == page_number
        assert len(page.items) == 1
        walked.append(page.items[0].draft_id)
    assert sorted(walked) == sorted(draft.draft_id for draft in drafts)


def test_list_drafts_sorts_by_field_and_direction_over_full_set(
    services: AppServices,
) -> None:
    drafts = _seed_paginated_drafts(services)
    service = _service(services)

    # updatedAt desc (default): reversed insertion order (hour fields increase).
    page = service.list_drafts(page=1, page_size=10)
    assert [item.draft_id for item in page.items] == [
        draft.draft_id for draft in reversed(drafts)
    ][:10]

    # updatedAt asc: oldest first.
    page = service.list_drafts(
        sort_by=DraftSortBy.UPDATED_AT,
        sort_order=DraftSortOrder.ASC,
    )
    assert [item.draft_id for item in page.items] == [
        draft.draft_id for draft in drafts
    ][:10]

    # createdAt asc vs desc differ when updated order diverges from creation
    # order: swap updatedAt on one draft so the two orders disagree.
    first = drafts[0]
    services.draft_repository.save(
        first.model_copy(
            update={"updated_at": drafts[-1].updated_at + timedelta(hours=1)}
        ),
        expected_revision=1,
    )
    by_updated = service.list_drafts(page=1, page_size=10)
    by_created = service.list_drafts(
        sort_by=DraftSortBy.CREATED_AT,
        sort_order=DraftSortOrder.ASC,
    )
    assert by_updated.items[0].draft_id == first.draft_id
    assert by_created.items[0].draft_id == drafts[0].draft_id
    assert by_created.items[0].display_name == "排序草稿-0"
    # createdAt desc puts the newest-created draft first.
    by_created_desc = service.list_drafts(
        sort_by=DraftSortBy.CREATED_AT,
        sort_order=DraftSortOrder.DESC,
    )
    assert by_created_desc.items[0].draft_id == drafts[-1].draft_id


def test_list_drafts_sorts_stably_when_times_are_equal(
    services: AppServices,
) -> None:
    """Drafts sharing one timestamp order by draftId ascending as a stable
    secondary key so pagination never duplicates or drops items."""
    source_ref = put_png(services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
    saved: list[DraftRecord] = []
    shared_time = datetime(2026, 9, 2, tzinfo=UTC)
    for index in range(3):
        base = ask_gus_reviewable_fixture(revision=1)
        draft = base.model_copy(
            update={
                "source": base.source.model_copy(
                    update={"original_image_asset_id": source_ref.asset_id}
                ),
                "created_at": shared_time,
                "updated_at": shared_time,
            }
        )
        saved.append(services.draft_repository.save(draft, expected_revision=None))

    page = _service(services).list_drafts(
        page=1,
        page_size=10,
        sort_by=DraftSortBy.UPDATED_AT,
        sort_order=DraftSortOrder.DESC,
    )
    # The timestamp direction must not change the stable draftId tiebreaker.
    by_id_asc = sorted(str(record.draft_id) for record in saved)
    assert [str(item.draft_id) for item in page.items] == by_id_asc


@pytest.mark.parametrize(
    ("count", "expected_pages"),
    [(0, 0), (1, 1), (10, 1), (11, 2), (21, 3)],
)
def test_list_drafts_page_boundaries(
    services: AppServices,
    count: int,
    expected_pages: int,
) -> None:
    drafts = _seed_paginated_drafts(services, count=count)
    service = _service(services)

    page = service.list_drafts(page=1, page_size=10)

    assert page.total == count
    assert page.total_pages == expected_pages
    assert page.page == 1
    assert len(page.items) == min(count, 10)
    if count:
        assert page.items[0].draft_id == drafts[-1].draft_id

    if count > 10:
        last = service.list_drafts(page=expected_pages, page_size=10)
        assert last.page == expected_pages
        assert len(last.items) == count - ((expected_pages - 1) * 10)


def test_list_drafts_filters_before_pagination(services: AppServices) -> None:
    visible = _seed_paginated_drafts(services, count=11)
    service = _service(services)
    orphan = make_reviewable_draft(services)
    archive = service.archive_draft(orphan.draft_id, "orphan-pagination-key")
    services.archive_repository.delete(archive.dish_id)

    page = service.list_drafts(page=2, page_size=10)

    assert page.total == len(visible)
    assert page.total_pages == 2
    assert page.page == 2
    assert [item.draft_id for item in page.items] == [visible[0].draft_id]


def test_list_drafts_empty_set_uses_page_one(
    services: AppServices,
) -> None:
    page = _service(services).list_drafts(page=1, page_size=10)
    assert page.total == 0
    assert page.total_pages == 0
    assert page.page == 1
    assert page.items == []


def test_list_drafts_has_running_generation_without_registry(
    services: AppServices,
) -> None:
    """A draft the service still believes is generating (no live registry) keeps
    the homepage polling flag on; a terminal draft clears it."""
    source_ref = put_png(services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
    base = ask_gus_reviewable_fixture(revision=1)
    generating = base.model_copy(
        update={
            "source": base.source.model_copy(
                update={"original_image_asset_id": source_ref.asset_id}
            ),
            "status": DraftStatus.GENERATING,
            "active_attempt_id": uuid4(),
            "updated_at": datetime(2026, 9, 3, tzinfo=UTC),
        }
    )
    services.draft_repository.save(generating, expected_revision=None)
    service = _service(services)

    page = service.list_drafts(page=1, page_size=10)
    assert page.has_running_generation is True


def _service_with_registry(
    services: AppServices,
    registry: AttemptRegistry,
) -> DraftService:
    return DraftService(
        draft_repository=services.draft_repository,
        archive_repository=services.archive_repository,
        asset_store=services.asset_store,
        catalog=services.catalog,
        attempt_repository=services.attempt_repository,
        attempt_registry=registry,
        canonical_registration_service=services.canonical_registration,
    )


def test_list_drafts_has_running_generation_follows_live_registry(
    services: AppServices,
) -> None:
    """The flag reflects the live registry, so an off-page draft that finishes
    (owner released) stops the poll without another page read."""
    source_ref = put_png(services.asset_store, kind=AssetKind.ORIGINAL_IMAGE)
    base = ask_gus_reviewable_fixture(revision=1)
    attempt_id = uuid4()
    generating = base.model_copy(
        update={
            "source": base.source.model_copy(
                update={"original_image_asset_id": source_ref.asset_id}
            ),
            "status": DraftStatus.REGENERATING,
            "active_attempt_id": attempt_id,
            "updated_at": datetime(2026, 9, 3, tzinfo=UTC),
        }
    )
    record = services.draft_repository.save(generating, expected_revision=None)
    registry = AttemptRegistry()
    assert registry.reserve_slot(record.draft_id, attempt_id)
    try:
        page = _service_with_registry(services, registry).list_drafts()
        assert page.has_running_generation is True
        assert page.items[0].draft_id == record.draft_id
        assert page.items[0].created_at is not None
    finally:
        registry.release_slot(attempt_id)
