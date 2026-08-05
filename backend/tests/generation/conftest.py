"""Task 13 generation orchestrator test fixtures: fake gateway and drafts."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from backend.tests.domain.factories import make_draft as make_domain_draft
from PIL import Image

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.assets import AssetKind, AssetRef, MediaType
from pelican_town_specials.domain.common import DraftMode, GenerationStage
from pelican_town_specials.domain.dish import (
    DishAnalysis,
    FieldAuthority,
    GenerationSource,
    PresentationSpec,
    Provenance,
    RecoverySpec,
    SemanticIngredient,
)
from pelican_town_specials.domain.draft import (
    DraftRecord,
    DraftStatus,
    GenerationAttemptKind,
)
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import (
    GenerationCommand,
    GenerationOrchestrator,
)
from pelican_town_specials.persistence.asset_store import (
    AssetMetadata,
    FileAssetStore,
)
from pelican_town_specials.persistence.repositories import (
    DraftRepository,
    GenerationAttemptRepository,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths
from pelican_town_specials.providers.contracts import (
    GeneratedDishCore,
    GeneratedImage,
    ImageGenerationRequest,
    ImageMediaType,
    ImageOperation,
    SemanticRecipeIngredient,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = (
    _REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


EXPECTED_ASK_GUS_STAGES = [
    GenerationStage.INPUT_VALIDATION,
    GenerationStage.DISH_ANALYSIS,
    GenerationStage.GAMEPLAY_DESIGN,
    GenerationStage.INGREDIENT_MAPPING,
    GenerationStage.VISUAL_BRIEF,
    GenerationStage.ICON_GENERATION_AND_NORMALIZATION,
    GenerationStage.PREVIEW_ART_GENERATION_AND_COMPOSITION,
    GenerationStage.RESULT_VALIDATION,
    GenerationStage.ATOMIC_PROMOTION,
]


def _png_bytes(
    *, size: int | tuple[int, int] = 128, color: str = "tomato"
) -> bytes:
    output = io.BytesIO()
    dimensions = (size, size) if isinstance(size, int) else size
    Image.new("RGB", dimensions, color).save(output, format="PNG")
    return output.getvalue()


def analysis_fixture(*, confidence: float = 0.9) -> DishAnalysis:
    return DishAnalysis(
        recognizedDish="Spring Noodles",
        summary="A warm spring noodle bowl with greens.",
        cuisine="Farmhouse",
        cookingMethods=["boiled"],
        flavorProfile=["savory", "fresh"],
        semanticIngredients=[
            SemanticIngredient(
                name="Egg", normalizedName="egg", visibleConfidence=0.98
            ),
            SemanticIngredient(
                name="Spring Onion",
                normalizedName="spring onion",
                visibleConfidence=0.87,
            ),
        ],
        confidence=confidence,
    )


def core_fixture() -> GeneratedDishCore:
    return GeneratedDishCore(
        presentation=PresentationSpec(
            displayName="春日面碗",
            internalName="SpringNoodleBowl",
            categoryLabel="主菜",
            description="一碗带着春天气息的热汤面。",
            tags=["spring", "noodles"],
        ),
        ingredients=[
            SemanticRecipeIngredient(name="Egg", normalizedName="egg"),
            SemanticRecipeIngredient(
                name="Spring Onion", normalizedName="spring onion"
            ),
        ],
        recovery=RecoverySpec(edibility=80),
        sellPrice=220,
        isDrink=False,
        visualBrief="Warm ceramic bowl on a rustic tavern table.",
    )


class FakeGateway:
    """Deterministic ModelGateway substitute for orchestrator tests."""

    def __init__(
        self,
        *,
        confidence: float = 0.9,
        fail_stage: GenerationStage | None = None,
        delay: float = 0.0,
        image_edits_supported: bool | None = None,
    ) -> None:
        self.confidence = confidence
        self.fail_stage = fail_stage
        self.delay = delay
        self.image_edits_supported = image_edits_supported
        self.calls: list[str] = []
        self.image_requests: list[ImageGenerationRequest] = []

    async def analyze_dish(
        self, request, *, json_only: bool = False
    ) -> DishAnalysis:
        self.calls.append("analyze")
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_stage is GenerationStage.DISH_ANALYSIS:
            raise RuntimeError("fake dish analysis failure")
        return analysis_fixture(confidence=self.confidence)

    async def design_ask_gus(
        self, request, *, json_only: bool = False
    ) -> GeneratedDishCore:
        self.calls.append("design")
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_stage is GenerationStage.GAMEPLAY_DESIGN:
            raise RuntimeError("fake design failure")
        return core_fixture()

    async def generate_image(self, request) -> GeneratedImage:
        self.calls.append("image")
        self.image_requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if (
            self.fail_stage is GenerationStage.ICON_GENERATION_AND_NORMALIZATION
            and request.operation is ImageOperation.GENERATION
        ):
            raise RuntimeError("fake icon generation failure")
        if (
            self.fail_stage
            is GenerationStage.PREVIEW_ART_GENERATION_AND_COMPOSITION
            and request.operation is ImageOperation.EDIT
        ):
            raise RuntimeError("fake preview generation failure")
        output_size = (
            128 if request.operation is ImageOperation.GENERATION else (96, 64)
        )
        return GeneratedImage(
            data=_png_bytes(size=output_size), media_type=ImageMediaType.PNG
        )


@dataclass
class GenerationHarness:
    workspace: WorkspacePaths
    catalog: VanillaCatalog
    asset_store: FileAssetStore
    draft_repository: DraftRepository
    attempt_repository: GenerationAttemptRepository
    gateway: FakeGateway
    orchestrator: GenerationOrchestrator


@pytest.fixture
def catalog() -> VanillaCatalog:
    return VanillaCatalog.from_json(_CATALOG_PATH)


@pytest.fixture
def harness(tmp_path: Path, catalog: VanillaCatalog) -> GenerationHarness:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    asset_store = FileAssetStore(workspace)
    draft_repository = DraftRepository(workspace)
    attempt_repository = GenerationAttemptRepository(workspace)
    gateway = FakeGateway()
    orchestrator = GenerationOrchestrator(
        draft_repository=draft_repository,
        attempt_repository=attempt_repository,
        asset_store=asset_store,
        catalog=catalog,
        gateway_factory=lambda: gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
    )
    return GenerationHarness(
        workspace=workspace,
        catalog=catalog,
        asset_store=asset_store,
        draft_repository=draft_repository,
        attempt_repository=attempt_repository,
        gateway=gateway,
        orchestrator=orchestrator,
    )


@pytest.fixture
def orchestrator(harness: GenerationHarness) -> GenerationOrchestrator:
    return harness.orchestrator


@pytest.fixture
def gateway(harness: GenerationHarness) -> FakeGateway:
    return harness.gateway


def put_original_image(
    harness: GenerationHarness,
    *,
    size: int = 64,
    color: str = "seagreen",
) -> AssetRef:
    data = _png_bytes(size=size, color=color)
    return harness.asset_store.put(
        data,
        AssetMetadata(
            kind=AssetKind.ORIGINAL_IMAGE,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=size,
            height=size,
        ),
    )


def _draft_with_source(
    draft: DraftRecord,
    source_asset_id: UUID,
) -> DraftRecord:
    source = draft.source.model_copy(
        update={"original_image_asset_id": source_asset_id}
    )
    return draft.model_copy(update={"source": source})


@pytest.fixture
def ready_draft(
    harness: GenerationHarness, orchestrator: GenerationOrchestrator
) -> DraftRecord:
    ref = put_original_image(harness)
    draft = _draft_with_source(
        make_domain_draft(
            mode=DraftMode.ASK_GUS, status=DraftStatus.READY, revision=1
        ),
        ref.asset_id,
    )
    return orchestrator.drafts.save(draft, expected_revision=None)


@pytest.fixture
def reviewable_draft(
    harness: GenerationHarness, orchestrator: GenerationOrchestrator
) -> DraftRecord:
    ref = put_original_image(harness)
    draft = _draft_with_source(
        make_domain_draft(
            mode=DraftMode.ASK_GUS,
            status=DraftStatus.REVIEWABLE,
            revision=3,
        ),
        ref.asset_id,
    )
    return orchestrator.drafts.save(draft, expected_revision=None)


def initial_command(draft: DraftRecord) -> GenerationCommand:
    return GenerationCommand(
        draftId=draft.draft_id,
        kind=GenerationAttemptKind.INITIAL,
        requestId=uuid4(),
    )


def full_regen_command(draft: DraftRecord) -> GenerationCommand:
    return GenerationCommand(
        draftId=draft.draft_id,
        kind=GenerationAttemptKind.FULL_REGENERATE,
        requestId=uuid4(),
    )


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


def _blueprint_provenance_fixture() -> Provenance:
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


@pytest.fixture
def blueprint_stale(
    harness: GenerationHarness, orchestrator: GenerationOrchestrator
) -> DraftRecord:
    """BLUEPRINT draft in STALE_PREVIEW with user fields and stale visuals."""
    ref = put_original_image(harness)
    draft = _draft_with_source(
        make_domain_draft(
            mode=DraftMode.BLUEPRINT,
            status=DraftStatus.STALE_PREVIEW,
            revision=2,
            visual_source_revision=1,
        ),
        ref.asset_id,
    )
    draft = draft.model_copy(update={"provenance": _blueprint_provenance_fixture()})
    return orchestrator.drafts.save(draft, expected_revision=None)


def blueprint_preview_command(draft: DraftRecord) -> GenerationCommand:
    return GenerationCommand(
        draftId=draft.draft_id,
        kind=GenerationAttemptKind.BLUEPRINT_PREVIEW,
        requestId=uuid4(),
    )


def reviewable_draft_result_hash(draft: DraftRecord) -> str:
    payload = draft.model_dump(
        include={"analysis", "presentation", "gameplay", "visuals"},
        by_alias=True,
        mode="json",
    )
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
