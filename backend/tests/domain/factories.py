from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.assets import SourceInput
from pelican_town_specials.domain.canonical import (
    CanonicalDishRegistration,
    RecallDocument,
    RecallIngredient,
)
from pelican_town_specials.domain.common import DraftMode, Language, utc_now
from pelican_town_specials.domain.dish import (
    DishAnalysis,
    FieldAuthority,
    GameIngredient,
    GameplaySpec,
    GenerationSource,
    PresentationSpec,
    Provenance,
    RecoverySpec,
    SemanticIngredient,
    VisualSpec,
)
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


def _source_input() -> SourceInput:
    return SourceInput(
        originalImageAssetId=uuid4(),
        contextText="Seasonal noodle bowl",
        language=Language.ZH_CN,
    )


def _analysis() -> DishAnalysis:
    return DishAnalysis(
        recognizedDish="Spring Noodles",
        summary="A warm spring noodle bowl with greens.",
        cuisine="Farmhouse",
        cookingMethods=["boiled"],
        flavorProfile=["savory", "fresh"],
        semanticIngredients=[
            SemanticIngredient(
                name="Noodles",
                normalizedName="noodles",
                visibleConfidence=0.98,
            ),
            SemanticIngredient(
                name="Greens",
                normalizedName="greens",
                visibleConfidence=0.87,
            ),
        ],
        confidence=0.94,
    )


def _presentation_spec() -> PresentationSpec:
    return PresentationSpec(
        displayName="春日面碗",
        internalName="SpringNoodleBowl",
        categoryLabel="主菜",
        description="一碗带着春天气息的热汤面。",
        gusComment="Gus 会想再来一碗。",
        tags=["spring", "noodles"],
    )


def _gameplay_spec() -> GameplaySpec:
    return GameplaySpec(
        ingredients=[
            GameIngredient(
                itemId="24",
                displayName="Egg",
                quantity=1,
                mappingReason="catalog match",
                catalogVersion="stardew-1.6.15-v1",
            ),
            GameIngredient(
                itemId="399",
                displayName="Spring Onion",
                quantity=1,
                mappingReason="catalog match",
                catalogVersion="stardew-1.6.15-v1",
            ),
        ],
        recovery=RecoverySpec(edibility=80),
        sellPrice=220,
        isDrink=False,
        recipeUnlock="DEFAULT",
    )


def _visual_spec(*, source_revision: int) -> VisualSpec:
    return VisualSpec(
        visualBrief="Warm ceramic bowl on a rustic tavern table.",
        generatedArtAssetId=uuid4(),
        previewAssetId=uuid4(),
        iconSourceAssetId=uuid4(),
        icon16AssetId=uuid4(),
        sourceRevision=source_revision,
        promptVersion="visual-v1",
    )


def _provenance(*, mode: DraftMode) -> Provenance:
    return Provenance(
        mode=mode,
        authorityByField={
            "presentation.display_name": FieldAuthority.AGENT_ASSIGNED,
            "gameplay.ingredients": FieldAuthority.SYSTEM_GENERATED,
        },
        visionModel="vision-model-v1",
        textModel="text-model-v1",
        imageModel="image-model-v1",
        promptVersions={"dish": "dish-v1", "visual": "visual-v1"},
        generationSource=(
            GenerationSource.FRESH_GENERATION
            if mode is DraftMode.ASK_GUS
            else GenerationSource.USER_AUTHORED
        ),
        canonicalDishSignature="spring-noodle-bowl",
        cacheEligibility=(mode is DraftMode.ASK_GUS),
    )


def make_draft(
    *,
    mode: DraftMode,
    status: DraftStatus,
    revision: int = 1,
    visual_source_revision: int | None = None,
) -> DraftRecord:
    now = utc_now()
    current_visual_revision = (
        visual_source_revision if visual_source_revision is not None else revision
    )
    return DraftRecord(
        schemaVersion=1,
        draftId=uuid4(),
        mode=mode,
        baseTemplateVersion=(
            "blueprint-v1" if mode is DraftMode.BLUEPRINT else None
        ),
        status=status,
        revision=revision,
        source=_source_input(),
        analysis=_analysis(),
        presentation=_presentation_spec(),
        gameplay=_gameplay_spec(),
        visuals=_visual_spec(source_revision=current_visual_revision),
        provenance=_provenance(mode=mode),
        activeAttemptId=None,
        lastAttemptId=None,
        lastError=None,
        createdAt=now,
        updatedAt=now,
        archivedDishId=None,
    )


def ask_gus_reviewable_fixture(*, revision: int = 1) -> DraftRecord:
    return make_draft(
        mode=DraftMode.ASK_GUS,
        status=DraftStatus.REVIEWABLE,
        revision=revision,
    )


def blueprint_reviewable_fixture() -> DraftRecord:
    return make_draft(
        mode=DraftMode.BLUEPRINT,
        status=DraftStatus.REVIEWABLE,
    )


def blueprint_draft_fixture(
    *,
    revision: int = 1,
    visual_source_revision: int | None = None,
) -> DraftRecord:
    return make_draft(
        mode=DraftMode.BLUEPRINT,
        status=DraftStatus.DRAFT,
        revision=revision,
        visual_source_revision=visual_source_revision,
    )


def initial_attempt_fixture(
    *,
    candidate_record_path: str | None = None,
) -> GenerationAttempt:
    now = utc_now()
    return GenerationAttempt(
        attemptId=uuid4(),
        draftId=uuid4(),
        kind=GenerationAttemptKind.INITIAL,
        sourceRevision=1,
        status=AttemptStatus.RUNNING,
        currentStage=GenerationStage.INPUT_VALIDATION,
        stages=[
            StageAttempt(
                stage=GenerationStage.INPUT_VALIDATION,
                status=StageStatus.RUNNING,
                retryCount=0,
                startedAt=now,
                finishedAt=None,
                error=None,
            )
        ],
        candidateRecordPath=candidate_record_path,
        startedAt=now,
        finishedAt=None,
        error=None,
    )


def canonical_registration_fixture(
    *,
    canonical_id: UUID | None = None,
    source_archive_id: UUID | None = None,
    dish_signature: str = "a" * 64,
    language: Language = Language.ZH_CN,
    catalog_version: str = "stardew-1.6.15-v1",
) -> CanonicalDishRegistration:
    gameplay = _gameplay_spec().model_copy(
        update={
            "ingredients": [
                ingredient.model_copy(
                    update={"catalog_version": catalog_version}
                )
                for ingredient in _gameplay_spec().ingredients
            ]
        }
    )
    return CanonicalDishRegistration(
        canonicalId=canonical_id or uuid4(),
        sourceArchiveId=source_archive_id or uuid4(),
        dishSignature=dish_signature,
        language=language,
        recallDocument=RecallDocument(
            recognizedDish="Spring Noodles",
            normalizedName="spring noodle bowl",
            summary="A warm spring noodle bowl with greens.",
            cuisine="Farmhouse",
            semanticIngredients=[
                RecallIngredient(
                    name="Egg",
                    normalizedName="egg",
                    visibleConfidence=0.98,
                ),
                RecallIngredient(
                    name="Spring Onion",
                    normalizedName="spring onion",
                    visibleConfidence=0.87,
                ),
            ],
            cookingMethods=["boiled"],
            flavorProfile=["savory", "fresh"],
        ),
        presentation=_presentation_spec(),
        gameplay=gameplay,
        visualBrief="Warm ceramic bowl on a rustic tavern table.",
        catalogVersion=catalog_version,
    )


def archived_dish_fixture(
    *,
    mode: DraftMode | str = DraftMode.ASK_GUS,
    source_draft_id: UUID | None = None,
    dish_id: UUID | None = None,
    archived_at: datetime | None = None,
) -> ArchivedDish:
    current_mode = DraftMode(mode)
    return ArchivedDish(
        schemaVersion=1,
        dishId=dish_id or uuid4(),
        archiveRevision=1,
        archivedAt=archived_at or utc_now(),
        presentation=_presentation_spec(),
        gameplay=_gameplay_spec(),
        visuals=_visual_spec(source_revision=1),
        contentHash="a" * 64,
        internalProvenance=_provenance(mode=current_mode),
        sourceDraftId=source_draft_id or uuid4(),
    )
