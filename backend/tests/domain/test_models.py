import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid1, uuid4

import pytest
from pydantic import ValidationError

from pelican_town_specials.domain.archive import (
    CookbookDishDetail,
    CookbookDishSummary,
    CookbookVisuals,
)
from pelican_town_specials.domain.assets import (
    AssetKind,
    AssetRef,
    MediaType,
    SourceInput,
)
from pelican_town_specials.domain.common import DraftMode, GenerationStage, Language
from pelican_town_specials.domain.dish import (
    BuffAttributes,
    BuffSpec,
    FieldAuthority,
    GameIngredient,
    GameplaySpec,
    Provenance,
    RecoverySpec,
)
from pelican_town_specials.domain.draft import DraftStatus, GenerationAttemptPublic
from pelican_town_specials.domain.errors import AppError, ErrorSummary
from pelican_town_specials.domain.export import ExportSpec
from pelican_town_specials.domain.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    validate_draft,
)

from .factories import (
    archived_dish_fixture,
    blueprint_draft_fixture,
    initial_attempt_fixture,
)

EXPECTED_ASSET_KINDS = {
    AssetKind.ORIGINAL_IMAGE,
    AssetKind.GENERATED_ART,
    AssetKind.PREVIEW,
    AssetKind.ICON_SOURCE,
    AssetKind.ICON_16,
    AssetKind.MOD_SPRITESHEET,
    AssetKind.EXPORT_ZIP,
}

EXPECTED_MEDIA_TYPES = {
    MediaType.PNG,
    MediaType.JPEG,
    MediaType.WEBP,
    MediaType.ZIP,
}


def test_strict_models_reject_unknown_fields_and_coercion() -> None:
    with pytest.raises(ValidationError):
        SourceInput(originalImageAssetId=uuid4(), language="zh-CN", unexpected=True)
    with pytest.raises(ValidationError):
        AssetRef(
            assetId=uuid4(),
            kind="ORIGINAL_IMAGE",
            mediaType="image/png",
            relativePath="assets/a.png",
            sha256="a" * 64,
            byteSize="10",
            createdAt=datetime.now(UTC),
            width=1,
            height=1,
        )


def test_uuid_v4_fields_reject_v1_uuids() -> None:
    v1_uuid = uuid1()
    with pytest.raises(ValidationError):
        SourceInput(originalImageAssetId=v1_uuid, language=Language.ZH_CN)
    with pytest.raises(ValidationError):
        AssetRef(
            assetId=v1_uuid,
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            relativePath="assets/original.png",
            sha256="a" * 64,
            byteSize=10,
            createdAt=datetime.now(UTC),
            width=1,
            height=1,
        )
    with pytest.raises(ValidationError):
        ErrorSummary(
            code="PTS_STATE_ILLEGAL_TRANSITION",
            message="not allowed",
            retryable=False,
            requestId=v1_uuid,
            occurredAt=datetime.now(UTC),
        )
    with pytest.raises(ValidationError):
        AssetRef(
            assetId=uuid4(),
            kind=AssetKind.GENERATED_ART,
            mediaType=MediaType.PNG,
            relativePath="assets/generated.png",
            sha256="b" * 64,
            byteSize=10,
            createdAt=datetime.now(UTC),
            width=1,
            height=1,
            attemptId=v1_uuid,
        )


def test_asset_kind_and_media_type_whitelists_are_complete() -> None:
    assert set(AssetKind) == EXPECTED_ASSET_KINDS
    assert set(MediaType) == EXPECTED_MEDIA_TYPES


def test_asset_ref_requires_safe_path_positive_size_and_image_bounds() -> None:
    base = {
        "assetId": uuid4(),
        "kind": AssetKind.ORIGINAL_IMAGE,
        "mediaType": MediaType.PNG,
        "relativePath": "assets/original.png",
        "sha256": "a" * 64,
        "byteSize": 10,
        "createdAt": datetime.now(UTC),
        "width": 1,
        "height": 1,
    }
    assert AssetRef(**base).relative_path == "assets/original.png"
    assert AssetRef(**{**base, "sourceRevision": 3, "attemptId": uuid4()}).source_revision == 3
    with pytest.raises(ValidationError):
        AssetRef(**{**base, "relativePath": "../escape.png"})
    with pytest.raises(ValidationError):
        AssetRef(**{**base, "relativePath": "/absolute.png"})
    with pytest.raises(ValidationError):
        AssetRef(**{**base, "relativePath": "assets\\escape.png"})
    with pytest.raises(ValidationError):
        AssetRef(**{**base, "byteSize": 0})
    with pytest.raises(ValidationError):
        AssetRef(**{**base, "width": 0})
    with pytest.raises(ValidationError):
        AssetRef(**{**base, "height": 8193})


def test_asset_ref_allows_zip_assets_without_image_dimensions() -> None:
    asset = AssetRef(
        assetId=uuid4(),
        kind=AssetKind.EXPORT_ZIP,
        mediaType=MediaType.ZIP,
        relativePath="exports/final.zip",
        sha256="b" * 64,
        byteSize=1,
        createdAt=datetime.now(UTC),
        sourceRevision=7,
        attemptId=uuid4(),
    )
    assert asset.width is None
    assert asset.height is None


def test_validation_report_enforces_both_directions_of_error_invariant() -> None:
    error_issue = ValidationIssue(
        code="PTS_INPUT_BAD",
        severity=ValidationSeverity.ERROR,
        path="source",
        message="invalid",
        details={},
    )
    warning_issue = ValidationIssue(
        code="PTS_INPUT_NOTE",
        severity=ValidationSeverity.WARNING,
        path="source",
        message="note",
        details={},
    )
    with pytest.raises(ValidationError):
        ValidationReport(
            valid=True,
            issues=[error_issue],
            validatedAt=datetime.now(UTC),
            validatorVersion="v1",
        )
    with pytest.raises(ValidationError):
        ValidationReport(
            valid=False,
            issues=[warning_issue],
            validatedAt=datetime.now(UTC),
            validatorVersion="v1",
        )
    assert ValidationReport(
        valid=True,
        issues=[warning_issue],
        validatedAt=datetime.now(UTC),
        validatorVersion="v1",
    ).valid


def test_error_details_and_validation_details_reject_nested_payloads() -> None:
    with pytest.raises(TypeError):
        AppError(
            code="PTS_STATE_ILLEGAL_TRANSITION",
            message="not allowed",
            http_status=409,
            details={"currentState": {"bad": True}},
            retryable=False,
        )
    with pytest.raises(TypeError):
        ValidationIssue(
            code="PTS_INPUT_BAD",
            severity=ValidationSeverity.ERROR,
            path="source",
            message="invalid",
            details={"currentState": {"bad": True}},
        )


def test_error_summary_is_serializable_without_provider_payload() -> None:
    summary = ErrorSummary(
        code="PTS_STATE_ILLEGAL_TRANSITION",
        message="not allowed",
        retryable=False,
        requestId=uuid4(),
        occurredAt=datetime.now(UTC),
    )
    assert summary.model_dump(by_alias=True)["requestId"]
    assert "stack" not in summary.model_dump()
    with pytest.raises(AppError):
        raise AppError(
            code="PTS_STATE_ILLEGAL_TRANSITION",
            message="not allowed",
            http_status=409,
            details={"currentState": "DRAFT"},
            retryable=False,
        )


def test_error_summary_normalizes_aware_time_and_rejects_naive_time() -> None:
    normalized = ErrorSummary(
        code="PTS_STATE_ILLEGAL_TRANSITION",
        message="not allowed",
        retryable=False,
        requestId=uuid4(),
        occurredAt=datetime(2026, 8, 2, 10, 0, tzinfo=UTC),
    )
    assert normalized.occurred_at.tzinfo == UTC
    with pytest.raises(ValidationError):
        ErrorSummary(
            code="PTS_STATE_ILLEGAL_TRANSITION",
            message="not allowed",
            retryable=False,
            requestId=uuid4(),
            occurredAt=datetime.fromisoformat("2026-08-02T10:00:00"),
        )


def test_error_summary_stage_accepts_only_generation_stages() -> None:
    valid = ErrorSummary(
        code="PTS_STATE_ILLEGAL_TRANSITION",
        message="not allowed",
        retryable=False,
        requestId=uuid4(),
        occurredAt=datetime.now(UTC),
        stage=GenerationStage.DISH_ANALYSIS,
    )
    assert valid.stage is GenerationStage.DISH_ANALYSIS

    with pytest.raises(ValidationError):
        ErrorSummary(
            code="PTS_STATE_ILLEGAL_TRANSITION",
            message="not allowed",
            retryable=False,
            requestId=uuid4(),
            occurredAt=datetime.now(UTC),
            stage="NOT_A_GENERATION_STAGE",
        )

def test_source_input_trims_context_and_enforces_length_and_language() -> None:
    source = SourceInput(
        originalImageAssetId=uuid4(),
        contextText="  ramen  ",
        language=Language.ZH_CN,
    )
    assert source.context_text == "ramen"
    assert DraftMode.ASK_GUS.value == "ASK_GUS"
    assert SourceInput(
        originalImageAssetId=uuid4(),
        contextText="x" * 500,
        language=Language.EN_US,
    ).context_text == "x" * 500
    with pytest.raises(ValidationError):
        SourceInput(originalImageAssetId=uuid4(), contextText="x" * 501, language=Language.EN_US)
    with pytest.raises(ValidationError):
        SourceInput(originalImageAssetId=uuid4(), contextText="x", language="ja-JP")


def test_recovery_values_are_derived_and_not_overridable() -> None:
    recovery = RecoverySpec(edibility=80)
    assert (recovery.energy_restore, recovery.health_restore) == (200, 90)
    assert recovery.calculation_version == "stardew-1.6"
    with pytest.raises(ValidationError):
        RecoverySpec(edibility=80, energyRestore=1)


def test_recovery_derived_fields_are_immutable_after_construction() -> None:
    recovery = RecoverySpec(edibility=80)
    assert (recovery.energy_restore, recovery.health_restore, recovery.calculation_version) == (
        200,
        90,
        "stardew-1.6",
    )
    with pytest.raises(ValidationError):
        recovery.energy_restore = 1
    with pytest.raises(ValidationError):
        recovery.health_restore = 2
    with pytest.raises(ValidationError):
        recovery.calculation_version = "custom"


def test_field_authority_rejects_removed_legacy_value() -> None:
    with pytest.raises(ValueError):
        FieldAuthority("COPIED_FROM_SIMPLE")


def test_gameplay_requires_unique_one_to_eight_ingredients() -> None:
    ingredient = GameIngredient(
        itemId="24",
        displayName="Egg",
        quantity=1,
        mappingReason="catalog match",
        catalogVersion="stardew-1.6.15-v1",
    )
    base = {
        "ingredients": [ingredient],
        "recovery": RecoverySpec(edibility=80),
        "sellPrice": 100,
        "isDrink": False,
        "recipeUnlock": "DEFAULT",
    }
    GameplaySpec(**base)
    with pytest.raises(ValidationError):
        GameplaySpec(**{**base, "ingredients": [ingredient, ingredient]})


def test_buff_requires_ten_minute_multiple_and_nonzero_attribute() -> None:
    with pytest.raises(ValidationError):
        BuffSpec(id="food", durationMinutes=15, attributes=BuffAttributes(speed=1))
    with pytest.raises(ValidationError):
        BuffSpec(id="food", durationMinutes=20, attributes=BuffAttributes())


def test_blueprint_provenance_cannot_reuse_cache() -> None:
    with pytest.raises(ValidationError):
        Provenance(
            mode="BLUEPRINT",
            authorityByField={},
            promptVersions={},
            generationSource="USER_AUTHORED",
            cacheEligibility=True,
        )


def test_archived_dish_rejects_top_level_and_nested_mutation() -> None:
    archive = archived_dish_fixture()

    with pytest.raises(ValidationError):
        archive.content_hash = "b" * 64
    with pytest.raises(ValidationError):
        archive.presentation.display_name = "Mutated"
    with pytest.raises(ValidationError):
        archive.gameplay.sell_price = 1
    with pytest.raises(ValidationError):
        archive.gameplay.ingredients[0].display_name = "Mutated"
    with pytest.raises(ValidationError):
        archive.gameplay.recovery.edibility = 1
    with pytest.raises(ValidationError):
        archive.visuals.prompt_version = "mutated"
    with pytest.raises(ValidationError):
        archive.internal_provenance.mode = DraftMode.BLUEPRINT

    with pytest.raises((AttributeError, TypeError)):
        archive.presentation.tags.append("mutated")
    with pytest.raises(TypeError):
        archive.presentation.tags[0] = "mutated"
    with pytest.raises((AttributeError, TypeError)):
        archive.gameplay.ingredients.append(archive.gameplay.ingredients[0])
    with pytest.raises(TypeError):
        archive.internal_provenance.authority_by_field["mutated"] = FieldAuthority.USER_ASSIGNED
    with pytest.raises(TypeError):
        archive.internal_provenance.prompt_versions["mutated"] = "v2"


def test_archived_dish_rejects_model_copy_updates() -> None:

    archive = archived_dish_fixture()

    with pytest.raises(ValueError, match="immutable"):
        archive.model_copy(update={"content_hash": "b" * 64})

    copied = archive.model_copy()
    assert copied.content_hash == archive.content_hash

def test_archived_dish_deep_model_copy_is_independent_and_immutable() -> None:
    archive = archived_dish_fixture()
    copied = archive.model_copy(deep=True)

    assert copied is not archive
    assert copied.presentation is not archive.presentation
    assert copied.gameplay is not archive.gameplay
    assert copied.presentation.tags is not archive.presentation.tags
    assert copied.gameplay.ingredients is not archive.gameplay.ingredients
    assert copied.gameplay.ingredients[0] is not archive.gameplay.ingredients[0]
    assert (
        copied.internal_provenance.authority_by_field
        is not archive.internal_provenance.authority_by_field
    )
    assert json.loads(copied.model_dump_json(by_alias=True)) == json.loads(
        archive.model_dump_json(by_alias=True)
    )

    with pytest.raises((AttributeError, TypeError)):
        copied.presentation.tags.append("mutated")
    with pytest.raises(ValidationError):
        copied.gameplay.ingredients[0].display_name = "mutated"
    with pytest.raises(TypeError):
        copied.internal_provenance.authority_by_field["mutated"] = (
            FieldAuthority.USER_ASSIGNED
        )

def test_draft_record_mode_is_immutable_after_creation_and_model_copy() -> None:
    draft = blueprint_draft_fixture()
    with pytest.raises(ValidationError):
        draft.mode = DraftMode.ASK_GUS
    assert draft.mode is DraftMode.BLUEPRINT

    with pytest.raises(ValueError, match="mode"):
        draft.model_copy(update={"mode": DraftMode.ASK_GUS})

    mismatched_provenance = draft.provenance.model_copy(update={"mode": DraftMode.ASK_GUS})
    with pytest.raises(ValueError, match="mode"):
        draft.model_copy(update={"provenance": mismatched_provenance})

    updated = draft.model_copy(update={"status": DraftStatus.READY, "revision": 2})
    assert updated.status is DraftStatus.READY
    assert updated.revision == 2
    assert updated.mode is DraftMode.BLUEPRINT

def test_generation_attempt_public_dto_hides_staging_path() -> None:
    attempt = initial_attempt_fixture(candidate_record_path="staging/candidate.json")
    public = GenerationAttemptPublic.from_attempt(attempt)
    assert "candidateRecordPath" not in public.model_dump(by_alias=True)


def test_generation_attempt_public_direct_construction_rejects_v1_uuid_and_naive_time() -> None:
    payload = initial_attempt_fixture().model_dump(exclude={"candidate_record_path"})
    payload["attempt_id"] = uuid1()
    with pytest.raises(ValidationError):
        GenerationAttemptPublic(**payload)

    payload = initial_attempt_fixture().model_dump(exclude={"candidate_record_path"})
    payload["started_at"] = datetime.fromisoformat("2026-08-02T10:00:00")
    with pytest.raises(ValidationError):
        GenerationAttemptPublic(**payload)


def test_generation_attempt_public_direct_construction_normalizes_non_utc_time() -> None:
    payload = initial_attempt_fixture().model_dump(exclude={"candidate_record_path"})
    payload["started_at"] = datetime(
        2026,
        8,
        2,
        20,
        30,
        tzinfo=timezone(timedelta(hours=10)),
    )
    public = GenerationAttemptPublic(**payload)
    assert public.started_at == datetime(2026, 8, 2, 10, 30, tzinfo=UTC)
    assert public.started_at.tzinfo == UTC


def test_cookbook_public_dtos_reject_string_and_malformed_uuid_input() -> None:
    archive = archived_dish_fixture()

    detail_payload = CookbookDishDetail.from_archived_dish(archive).model_dump()
    detail_payload["dish_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        CookbookDishDetail(**detail_payload)

    summary_payload = CookbookDishSummary.from_archived_dish(archive).model_dump()
    summary_payload["dish_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        CookbookDishSummary(**summary_payload)

    visuals_payload = CookbookVisuals.from_visuals(archive.visuals).model_dump()
    visuals_payload["generated_art_asset_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        CookbookVisuals(**visuals_payload)


def test_cookbook_dto_public_json_uses_canonical_uuid_and_z_timestamp_and_hides_private_fields() -> None:
    archived_at = datetime(2026, 8, 2, 12, 34, 56, tzinfo=UTC)
    archive = archived_dish_fixture(
        mode="ASK_GUS",
        source_draft_id=uuid4(),
        dish_id=uuid4(),
        archived_at=archived_at,
    )
    detail = CookbookDishDetail.from_archived_dish(archive)
    serialized = detail.model_dump_json(by_alias=True)
    payload = json.loads(serialized)
    assert payload["dishId"] == str(archive.dish_id)
    assert payload["archivedAt"] == "2026-08-02T12:34:56Z"
    assert payload["visuals"]["generatedArtAssetId"] == str(
        archive.visuals.generated_art_asset_id
    )
    for private_name in (
        "mode",
        "sourceDraftId",
        "gusComment",
        "visionModel",
        "textModel",
        "imageModel",
    ):
        assert private_name not in serialized


def test_validate_draft_reports_stale_visual_revision_as_error() -> None:
    draft = blueprint_draft_fixture(revision=3, visual_source_revision=2)
    report = validate_draft(draft)
    assert report.valid is False
    assert any(
        issue.code == "PTS_VALIDATION_SOURCE_REVISION_MISMATCH"
        for issue in report.issues
    )


def test_export_spec_rejects_duplicate_dishes_and_invalid_slug() -> None:
    dish_id = uuid4()
    with pytest.raises(ValidationError):
        ExportSpec(
            dishIds=[dish_id, dish_id],
            packDisplayName="Pack",
            packSlug="bad-slug",
            version="1.0.0",
            description="x",
            language="zh-CN",
        )


def test_export_spec_rejects_leading_zero_semver() -> None:
    with pytest.raises(ValidationError):
        ExportSpec(
            dishIds=[uuid4()],
            packDisplayName="Pack",
            packSlug="Pack_slug",
            version="01.0.0",
            description="x",
            language="zh-CN",
        )
