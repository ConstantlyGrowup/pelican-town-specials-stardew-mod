"""Draft creation, conversion, editing, discard, and archive accept use cases."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from pelican_town_specials.catalog.gameplay_rules import validate_gameplay
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.assets import AssetKind, SourceInput
from pelican_town_specials.domain.common import (
    DraftMode,
    Language,
    StrictModel,
    ensure_utc,
    ensure_uuid4,
    utc_now,
)
from pelican_town_specials.domain.dish import (
    BuffAttributes,
    BuffSpec,
    DishAnalysis,
    FieldAuthority,
    GameIngredient,
    GameplaySpec,
    GenerationSource,
    PresentationSpec,
    Provenance,
    RecipeUnlock,
    RecoverySpec,
    VisualSpec,
)
from pelican_town_specials.domain.draft import DraftRecord, DraftStatus
from pelican_town_specials.domain.errors import AppError, ErrorSummary
from pelican_town_specials.domain.state_machine import DraftAction, transition
from pelican_town_specials.domain.validation import ValidationSeverity, validate_draft
from pelican_town_specials.persistence.asset_store import (
    AssetNotFoundError,
    FileAssetStore,
)
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
    IdempotencyConflictError,
    TombstonedDishError,
)

from .common import Page

_BLUEPRINT_TEMPLATE_VERSION: Literal["blueprint-v1"] = "blueprint-v1"
_BLUEPRINT_USER_ASSIGNED_FIELDS = frozenset(
    {
        "presentation.display_name",
        "presentation.internal_name",
        "presentation.category_label",
        "presentation.description",
        "presentation.tags",
        "gameplay.ingredients",
        "gameplay.recovery",
        "gameplay.sell_price",
        "gameplay.is_drink",
        "gameplay.buff",
        "gameplay.recipe_unlock",
    }
)
_PATCH_USER_ASSIGNED_PRESENTATION = frozenset(
    {"display_name", "internal_name", "category_label", "description", "tags"}
)
_PATCH_USER_ASSIGNED_GAMEPLAY = frozenset(
    {"ingredients", "recovery", "sell_price", "is_drink", "buff", "recipe_unlock"}
)
_TERMINAL_OR_FAILED = frozenset(
    {DraftStatus.ARCHIVED, DraftStatus.DISCARDED, DraftStatus.FAILED}
)


class DraftCreateSource(StrictModel):
    original_image_asset_id: UUID = Field(alias="originalImageAssetId")
    context_text: str | None = Field(default=None, alias="contextText")

    @field_validator("original_image_asset_id", mode="before")
    @classmethod
    def _validate_original_image_asset_id(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        try:
            return ensure_uuid4(UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(
                "originalImageAssetId must be a valid UUID v4"
            ) from exc

    @field_validator("context_text", mode="before")
    @classmethod
    def _validate_context_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("contextText must be a string")
        stripped = value.strip()
        if len(stripped) > 500:
            raise ValueError("contextText must be 500 characters or fewer")
        return stripped


class DraftCreateRequest(StrictModel):
    mode: DraftMode
    language: Language
    source: DraftCreateSource

    @field_validator("mode", mode="before")
    @classmethod
    def _coerce_mode(cls, value: object) -> object:
        if isinstance(value, DraftMode):
            return value
        try:
            return DraftMode(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("mode must be ASK_GUS or BLUEPRINT") from exc

    @field_validator("language", mode="before")
    @classmethod
    def _coerce_language(cls, value: object) -> object:
        if isinstance(value, Language):
            return value
        try:
            return Language(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("language must be zh-CN or en-US") from exc


class BlueprintIngredientInput(StrictModel):
    item_id: str = Field(alias="itemId", min_length=1, max_length=80)
    display_name: str = Field(alias="displayName", min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=99)
    mapping_reason: str = Field(alias="mappingReason", min_length=1, max_length=200)
    catalog_version: str = Field(alias="catalogVersion", min_length=1, max_length=80)

    def to_domain(self) -> GameIngredient:
        return GameIngredient.model_validate(self.model_dump())


class BlueprintRecoveryInput(StrictModel):
    edibility: int = Field(ge=0, le=500)

    def to_domain(self) -> RecoverySpec:
        return RecoverySpec(edibility=self.edibility)


class BlueprintBuffAttributesInput(StrictModel):
    farming_level: int = Field(default=0, alias="farmingLevel", ge=0, le=10)
    fishing_level: int = Field(default=0, alias="fishingLevel", ge=0, le=10)
    mining_level: int = Field(default=0, alias="miningLevel", ge=0, le=10)
    foraging_level: int = Field(default=0, alias="foragingLevel", ge=0, le=10)
    combat_level: int = Field(default=0, alias="combatLevel", ge=0, le=10)
    luck_level: int = Field(default=0, alias="luckLevel", ge=0, le=10)
    attack: int = Field(default=0, ge=0, le=10)
    defense: int = Field(default=0, ge=0, le=10)
    immunity: int = Field(default=0, ge=0, le=10)
    magnetic_radius: int = Field(default=0, alias="magneticRadius", ge=0, le=10)
    max_stamina: int = Field(default=0, alias="maxStamina", ge=0, le=10)
    speed: int = Field(default=0, ge=0, le=10)

    def to_domain(self) -> BuffAttributes:
        return BuffAttributes.model_validate(self.model_dump())


class BlueprintBuffInput(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    duration_minutes: int = Field(alias="durationMinutes", ge=10, le=1440)
    is_debuff: bool = Field(default=False, alias="isDebuff")
    attributes: BlueprintBuffAttributesInput

    def to_domain(self) -> BuffSpec:
        return BuffSpec.model_validate(self.model_dump())


class BlueprintGameplayInput(StrictModel):
    ingredients: list[BlueprintIngredientInput] = Field(min_length=1, max_length=8)
    recovery: BlueprintRecoveryInput
    sell_price: int = Field(alias="sellPrice", ge=0, le=50000)
    is_drink: bool = Field(alias="isDrink")
    recipe_unlock: RecipeUnlock = Field(
        default=RecipeUnlock.DEFAULT, alias="recipeUnlock"
    )
    buff: BlueprintBuffInput | None = None

    def to_domain(self) -> GameplaySpec:
        return GameplaySpec.model_validate(
            {
                "ingredients": [
                    ingredient.to_domain() for ingredient in self.ingredients
                ],
                "recovery": self.recovery.to_domain(),
                "sellPrice": self.sell_price,
                "isDrink": self.is_drink,
                "recipeUnlock": self.recipe_unlock,
                "buff": self.buff.to_domain() if self.buff is not None else None,
            }
        )


class BlueprintPresentationInput(StrictModel):
    display_name: str = Field(alias="displayName", min_length=1, max_length=60)
    internal_name: str = Field(
        alias="internalName",
        min_length=3,
        max_length=48,
        pattern=r"^[A-Za-z][A-Za-z0-9_]{2,47}$",
    )
    category_label: str = Field(alias="categoryLabel", min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=400)
    tags: list[str] = Field(default_factory=list, max_length=12)

    def to_domain(self) -> PresentationSpec:
        return PresentationSpec.model_validate(self.model_dump())


class DraftPatchRequest(StrictModel):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    presentation: BlueprintPresentationInput | None = None
    gameplay: BlueprintGameplayInput | None = None

    @model_validator(mode="after")
    def _require_one_field(self) -> DraftPatchRequest:
        if self.presentation is None and self.gameplay is None:
            raise ValueError(
                "at least one of presentation or gameplay is required"
            )
        return self


class DraftView(StrictModel):
    draft_id: UUID = Field(alias="draftId")
    mode: DraftMode
    base_template_version: Literal["blueprint-v1"] | None = Field(
        alias="baseTemplateVersion"
    )
    status: DraftStatus
    revision: int = Field(ge=1)
    source: SourceInput
    analysis: DishAnalysis | None = None
    presentation: PresentationSpec | None = None
    gameplay: GameplaySpec | None = None
    visuals: VisualSpec | None = None
    provenance: Provenance
    last_error: ErrorSummary | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    archived_dish_id: UUID | None = Field(alias="archivedDishId")

    @field_validator(
        "draft_id",
        "archived_dish_id",
        mode="before",
    )
    @classmethod
    def _validate_optional_uuid4(cls, value: UUID | None) -> UUID | None:
        if value is None:
            return None
        return ensure_uuid4(value)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _validate_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @classmethod
    def from_draft(cls, draft: DraftRecord) -> DraftView:
        return cls.model_validate(
            {
                "draftId": draft.draft_id,
                "mode": draft.mode,
                "baseTemplateVersion": draft.base_template_version,
                "status": draft.status,
                "revision": draft.revision,
                "source": draft.source,
                "analysis": draft.analysis,
                "presentation": draft.presentation,
                "gameplay": draft.gameplay,
                "visuals": draft.visuals,
                "provenance": draft.provenance,
                "lastError": draft.last_error,
                "createdAt": draft.created_at,
                "updatedAt": draft.updated_at,
                "archivedDishId": draft.archived_dish_id,
            }
        )


class DraftSummary(StrictModel):
    draft_id: UUID = Field(alias="draftId")
    mode: DraftMode
    status: DraftStatus
    revision: int = Field(ge=1)
    updated_at: datetime = Field(alias="updatedAt")
    display_name: str = Field(alias="displayName", max_length=60)
    original_image_asset_id: UUID = Field(alias="originalImageAssetId")

    @field_validator("draft_id", "original_image_asset_id", mode="before")
    @classmethod
    def _validate_uuid4(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        return value

    @field_validator("updated_at", mode="before")
    @classmethod
    def _validate_updated_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @classmethod
    def from_draft(cls, draft: DraftRecord) -> DraftSummary:
        return cls.model_validate(
            {
                "draftId": draft.draft_id,
                "mode": draft.mode,
                "status": draft.status,
                "revision": draft.revision,
                "updatedAt": draft.updated_at,
                "displayName": (
                    draft.presentation.display_name
                    if draft.presentation is not None
                    else ""
                ),
                "originalImageAssetId": draft.source.original_image_asset_id,
            }
        )


def _blueprint_provenance() -> Provenance:
    return Provenance(
        mode=DraftMode.BLUEPRINT,
        authorityByField={
            field: FieldAuthority.USER_ASSIGNED
            for field in _BLUEPRINT_USER_ASSIGNED_FIELDS
        },
        promptVersions={},
        generationSource=GenerationSource.USER_AUTHORED,
        cacheEligibility=False,
    )


def _ask_gus_provenance() -> Provenance:
    return Provenance(
        mode=DraftMode.ASK_GUS,
        authorityByField={},
        promptVersions={},
        generationSource=GenerationSource.FRESH_GENERATION,
        cacheEligibility=True,
    )


def _patched_authority(
    *,
    presentation: BlueprintPresentationInput | None,
    gameplay: BlueprintGameplayInput | None,
) -> dict[str, FieldAuthority]:
    authority: dict[str, FieldAuthority] = {}
    if presentation is not None:
        authority.update(
            {
                f"presentation.{field}": FieldAuthority.USER_ASSIGNED
                for field in _PATCH_USER_ASSIGNED_PRESENTATION
            }
        )
    if gameplay is not None:
        authority.update(
            {
                f"gameplay.{field}": FieldAuthority.USER_ASSIGNED
                for field in _PATCH_USER_ASSIGNED_GAMEPLAY
            }
        )
    return authority


class DraftService:
    def __init__(
        self,
        *,
        draft_repository: DraftRepository,
        archive_repository: ArchiveRepository,
        asset_store: FileAssetStore,
        catalog: VanillaCatalog,
    ) -> None:
        self._drafts = draft_repository
        self._archives = archive_repository
        self._assets = asset_store
        self._catalog = catalog

    def create_draft(self, request: DraftCreateRequest) -> DraftRecord:
        self._require_source_asset(request.source.original_image_asset_id)
        now = utc_now()
        source = SourceInput(
            originalImageAssetId=request.source.original_image_asset_id,
            contextText=request.source.context_text,
            language=request.language,
        )
        if request.mode is DraftMode.BLUEPRINT:
            record = self._new_draft(
                mode=DraftMode.BLUEPRINT,
                base_template_version=_BLUEPRINT_TEMPLATE_VERSION,
                provenance=_blueprint_provenance(),
                source=source,
                now=now,
            )
        else:
            record = self._new_draft(
                mode=DraftMode.ASK_GUS,
                base_template_version=None,
                provenance=_ask_gus_provenance(),
                source=source,
                now=now,
            )
        return self._drafts.save(record, expected_revision=None)

    def list_drafts(self) -> Page[DraftSummary]:
        records = self._drafts.list()
        items = [DraftSummary.from_draft(record) for record in records]
        return Page(items=items, nextCursor=None, total=len(items))

    def get_draft(self, draft_id: UUID) -> DraftRecord:
        try:
            return self._drafts.get(draft_id)
        except (FileNotFoundError, OSError) as exc:
            raise self._draft_not_found_error() from exc

    def convert_to_blueprint(self, source_draft_id: UUID) -> DraftRecord:
        source = self.get_draft(source_draft_id)
        if source.mode is not DraftMode.ASK_GUS:
            raise self._illegal_transition_error(source)
        if source.status in _TERMINAL_OR_FAILED:
            raise self._illegal_transition_error(source)
        blueprint = self._new_draft(
            mode=DraftMode.BLUEPRINT,
            base_template_version=_BLUEPRINT_TEMPLATE_VERSION,
            provenance=_blueprint_provenance(),
            source=SourceInput(
                originalImageAssetId=source.source.original_image_asset_id,
                contextText=None,
                language=source.source.language,
            ),
            now=utc_now(),
        )
        return self._drafts.save(blueprint, expected_revision=None)

    def patch_draft(
        self,
        draft_id: UUID,
        request: DraftPatchRequest,
    ) -> DraftRecord:
        draft = self.get_draft(draft_id)
        if draft.mode is not DraftMode.BLUEPRINT:
            raise self._illegal_transition_error(draft)
        if draft.status in _TERMINAL_OR_FAILED:
            raise self._illegal_transition_error(draft)
        if request.expected_revision != draft.revision:
            raise self._revision_conflict_error()

        update: dict[str, Any] = {"updated_at": utc_now()}
        try:
            if request.presentation is not None:
                update["presentation"] = request.presentation.to_domain()
            if request.gameplay is not None:
                update["gameplay"] = request.gameplay.to_domain()
        except (TypeError, ValueError) as exc:
            raise self._patch_input_error() from exc
        if draft.status is DraftStatus.REVIEWABLE:
            staged = transition(draft, DraftAction.MODIFY_FIELDS)
            update["status"] = staged.status

        provenance = draft.provenance.model_copy(
            update={
                "authority_by_field": {
                    **draft.provenance.authority_by_field,
                    **_patched_authority(
                        presentation=request.presentation,
                        gameplay=request.gameplay,
                    ),
                }
            }
        )
        update["provenance"] = provenance
        updated = draft.model_copy(update=update)
        return self._drafts.save(updated, expected_revision=draft.revision)

    def discard_draft(self, draft_id: UUID) -> None:
        draft = self.get_draft(draft_id)
        discarded = transition(draft, DraftAction.DISCARD)
        self._drafts.save(discarded, expected_revision=draft.revision)

    def archive_draft(
        self,
        draft_id: UUID,
        idempotency_key: str,
    ) -> ArchivedDish:
        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise self._idempotency_key_required_error()
        existing = self._archives.get_by_idempotency_key(normalized_key)
        if existing is not None:
            if existing.source_draft_id != draft_id:
                raise self._idempotency_conflict_error()
            self._repair_draft_association(
                draft_id,
                existing.dish_id,
                expected_revision=None,
            )
            return existing

        draft = self.get_draft(draft_id)
        if draft.status is not DraftStatus.REVIEWABLE:
            raise self._illegal_transition_error(draft)
        self._validate_archive_eligibility(draft)
        assert draft.presentation is not None
        assert draft.gameplay is not None
        assert draft.visuals is not None

        archive = ArchivedDish(
            schema_version=1,
            dish_id=uuid4(),
            archive_revision=1,
            archived_at=utc_now(),
            presentation=draft.presentation,
            gameplay=draft.gameplay,
            visuals=draft.visuals,
            content_hash=self._content_hash(draft),
            internal_provenance=draft.provenance,
            source_draft_id=draft_id,
        )
        try:
            self._archives.add_immutable(archive, idempotency_key=normalized_key)
        except IdempotencyConflictError as exc:
            raise self._idempotency_conflict_error() from exc
        except TombstonedDishError as exc:
            raise self._tombstoned_error() from exc

        self._repair_draft_association(
            draft_id,
            archive.dish_id,
            expected_revision=draft.revision,
        )
        return archive

    def _new_draft(
        self,
        *,
        mode: DraftMode,
        base_template_version: Literal["blueprint-v1"] | None,
        provenance: Provenance,
        source: SourceInput,
        now: datetime,
    ) -> DraftRecord:
        return DraftRecord(
            schema_version=1,
            draft_id=uuid4(),
            mode=mode,
            baseTemplateVersion=base_template_version,
            status=DraftStatus.DRAFT,
            revision=1,
            source=source,
            analysis=None,
            presentation=None,
            gameplay=None,
            visuals=None,
            provenance=provenance,
            active_attempt_id=None,
            last_attempt_id=None,
            last_error=None,
            created_at=now,
            updated_at=now,
            archived_dish_id=None,
        )

    def _require_source_asset(self, asset_id: UUID) -> None:
        try:
            ref = self._assets.stat(asset_id)
        except AssetNotFoundError as exc:
            raise self._source_image_missing_error() from exc
        except ValueError as exc:
            raise self._asset_unavailable_error() from exc
        if ref.kind is not AssetKind.ORIGINAL_IMAGE:
            raise self._source_image_missing_error()

    def _validate_archive_eligibility(self, draft: DraftRecord) -> None:
        if (
            draft.presentation is None
            or draft.gameplay is None
            or draft.visuals is None
        ):
            raise self._archive_validation_error(
                "REVIEWABLE drafts must define presentation, gameplay and visuals"
            )
        if draft.visuals.source_revision != draft.revision:
            raise self._archive_validation_error(
                "visuals.sourceRevision must match the draft revision"
            )
        self._require_visual_asset(draft, "preview_asset_id", AssetKind.PREVIEW)
        self._require_visual_asset(draft, "icon_16_asset_id", AssetKind.ICON_16)

        draft_report = validate_draft(draft)
        gameplay_report = validate_gameplay(draft.gameplay, self._catalog)
        for report in (draft_report, gameplay_report):
            if any(
                issue.severity is ValidationSeverity.ERROR for issue in report.issues
            ):
                raise self._archive_validation_error(
                    "draft has blocking validation errors"
                )

    def _require_visual_asset(
        self,
        draft: DraftRecord,
        field_name: str,
        expected_kind: AssetKind,
    ) -> None:
        assert draft.visuals is not None
        asset_id = getattr(draft.visuals, field_name)
        if asset_id is None:
            raise self._archive_validation_error(
                f"visuals.{field_name} is required for archive"
            )
        try:
            ref = self._assets.stat(asset_id)
        except AssetNotFoundError as exc:
            raise self._archive_validation_error(
                f"visuals.{field_name} references a missing asset"
            ) from exc
        except ValueError as exc:
            raise self._asset_unavailable_error() from exc
        if ref.kind is not expected_kind:
            raise self._archive_validation_error(
                f"visuals.{field_name} references the wrong asset kind"
            )

    def _repair_draft_association(
        self,
        draft_id: UUID,
        dish_id: UUID,
        *,
        expected_revision: int | None,
    ) -> None:
        try:
            draft = self.get_draft(draft_id)
        except AppError:
            return
        if draft.status is DraftStatus.ARCHIVED and draft.archived_dish_id == dish_id:
            return
        staged = draft.model_copy(
            update={
                "status": DraftStatus.ARCHIVED,
                "archived_dish_id": dish_id,
                "updated_at": utc_now(),
            }
        )
        save_revision = draft.revision if expected_revision is None else expected_revision
        self._drafts.save(staged, expected_revision=save_revision)

    @staticmethod
    def _content_hash(draft: DraftRecord) -> str:
        assert draft.presentation is not None
        assert draft.gameplay is not None
        assert draft.visuals is not None
        payload = {
            "presentation": draft.presentation.model_dump(
                by_alias=True, mode="json"
            ),
            "gameplay": draft.gameplay.model_dump(by_alias=True, mode="json"),
            "visuals": draft.visuals.model_dump(by_alias=True, mode="json"),
        }
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _draft_not_found_error() -> AppError:
        return AppError(
            code="PTS_DRAFT_NOT_FOUND",
            message="草稿不存在或已删除。",
            http_status=404,
            details={},
            retryable=False,
        )

    @staticmethod
    def _illegal_transition_error(draft: DraftRecord) -> AppError:
        return AppError(
            code="PTS_STATE_ILLEGAL_TRANSITION",
            message="草稿当前状态不允许该操作。",
            http_status=409,
            details={"currentState": draft.status.value},
            retryable=False,
        )

    @staticmethod
    def _patch_input_error() -> AppError:
        return AppError(
            code="PTS_DRAFT_PATCH_INVALID",
            message="Blueprint 字段不满足玩法约束，请检查后重试。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _revision_conflict_error() -> AppError:
        return AppError(
            code="PTS_STATE_REVISION_CONFLICT",
            message="草稿版本已变化，请刷新后重试。",
            http_status=409,
            details={},
            retryable=False,
        )

    @staticmethod
    def _idempotency_key_required_error() -> AppError:
        return AppError(
            code="PTS_INPUT_IDEMPOTENCY_KEY_REQUIRED",
            message="archive 操作需要 Idempotency-Key 请求头。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _idempotency_conflict_error() -> AppError:
        return AppError(
            code="PTS_IDEMPOTENCY_CONFLICT",
            message="该 Idempotency-Key 已关联其它草稿。",
            http_status=409,
            details={},
            retryable=False,
        )

    @staticmethod
    def _tombstoned_error() -> AppError:
        return AppError(
            code="PTS_ARCHIVE_TOMBSTONED",
            message="该收集品已被删除，不能重新创建。",
            http_status=409,
            details={},
            retryable=False,
        )

    @staticmethod
    def _archive_validation_error(message: str) -> AppError:
        return AppError(
            code="PTS_ARCHIVE_VALIDATION_FAILED",
            message=message,
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _source_image_missing_error() -> AppError:
        return AppError(
            code="PTS_INPUT_SOURCE_IMAGE_MISSING",
            message="源图片不存在或已删除。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _asset_unavailable_error() -> AppError:
        return AppError(
            code="PTS_ASSET_UNAVAILABLE",
            message="图片资源暂时不可用，请稍后重试。",
            http_status=500,
            details={},
            retryable=True,
        )
