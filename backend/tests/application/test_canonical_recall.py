from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from pelican_town_specials.application.canonical_memory import (
    CandidateRetriever,
    RecallService,
    context_similarity,
    ingredient_similarity,
    name_similarity,
    weighted_similarity,
)
from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.canonical import (
    CanonicalDish,
    CanonicalIconMetadata,
    CanonicalRecallCandidate,
    RecallDecision,
    RecallDocument,
    RecallIngredient,
)
from pelican_town_specials.domain.common import DraftMode, Language
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.providers.contracts import CanonicalMatchResponse
from tests.domain.factories import canonical_registration_fixture, make_draft


def _analysis() -> Any:
    return make_draft(
        mode=DraftMode.ASK_GUS,
        status=DraftStatus.REVIEWABLE,
    ).analysis


def _document(
    *,
    name: str = "Spring Noodles",
    ingredients: tuple[str, ...] = ("noodles",),
    cuisine: str | None = "Farmhouse",
    methods: tuple[str, ...] = ("boiled",),
) -> RecallDocument:
    return RecallDocument(
        recognizedDish=name,
        normalizedName=name,
        summary="A warm dish.",
        cuisine=cuisine,
        semanticIngredients=[
            RecallIngredient(
                name=ingredient,
                normalizedName=ingredient,
                visibleConfidence=0.9,
            )
            for ingredient in ingredients
        ],
        cookingMethods=list(methods),
        flavorProfile=[],
    )


def _candidate(
    *,
    canonical_id: UUID | None = None,
    document: RecallDocument | None = None,
    registered_at: datetime | None = None,
    display_name: str = "Spring Noodles",
) -> CanonicalRecallCandidate:
    registration = canonical_registration_fixture(
        canonical_id=canonical_id,
        language=Language.ZH_CN,
        catalog_version="catalog-v1",
    )
    return CanonicalRecallCandidate(
        canonicalId=registration.canonical_id,
        dishSignature=registration.dish_signature,
        language=registration.language,
        catalogVersion=registration.catalog_version,
        recallDocument=document or registration.recall_document,
        displayName=display_name,
        registeredAt=registered_at or datetime(2026, 8, 25, tzinfo=UTC),
        useCount=0,
        lastUsedAt=None,
    )


def _canonical(candidate: CanonicalRecallCandidate) -> CanonicalDish:
    registration = canonical_registration_fixture(
        canonical_id=candidate.canonical_id,
        language=candidate.language,
        catalog_version=candidate.catalog_version,
    )
    return CanonicalDish(
        canonicalId=registration.canonical_id,
        sourceArchiveId=registration.source_archive_id,
        dishSignature=registration.dish_signature,
        language=registration.language,
        reuseContractVersion=registration.reuse_contract_version,
        recallDocument=registration.recall_document,
        presentation=registration.presentation,
        gameplay=registration.gameplay,
        visualBrief=registration.visual_brief,
        catalogVersion=registration.catalog_version,
        iconSource=CanonicalIconMetadata(
            relativePath=f"{candidate.canonical_id}/icon-source.png",
            mediaType=MediaType.PNG,
            sha256="a" * 64,
            byteSize=1,
            width=1,
            height=1,
        ),
        icon16=CanonicalIconMetadata(
            relativePath=f"{candidate.canonical_id}/icon-16.png",
            mediaType=MediaType.PNG,
            sha256="b" * 64,
            byteSize=1,
            width=16,
            height=16,
        ),
        registeredAt=candidate.registered_at,
        lastUsedAt=None,
        useCount=0,
    )


class _Registry:
    def __init__(
        self,
        *,
        valid_count: int = 2,
        pool: list[CanonicalRecallCandidate] | None = None,
        valid: dict[UUID, CanonicalDish] | None = None,
        error: Exception | None = None,
        icon_error: Exception | None = None,
    ) -> None:
        self.valid_count = valid_count
        self.pool = pool or []
        self.valid = valid or {}
        self.error = error
        self.icon_error = icon_error
        self.pool_calls = 0
        self.valid_calls: list[UUID] = []
        self.icon_calls: list[UUID] = []

    def count_valid(self) -> int:
        if self.error is not None:
            raise self.error
        return self.valid_count

    def list_recall_candidate_pool(
        self,
        *,
        language: Language,
        catalog_version: str,
    ) -> list[CanonicalRecallCandidate]:
        self.pool_calls += 1
        return [
            candidate
            for candidate in self.pool
            if candidate.language is language
            and candidate.catalog_version == catalog_version
        ]

    def get_valid(self, canonical_id: UUID) -> CanonicalDish | None:
        self.valid_calls.append(canonical_id)
        return self.valid.get(canonical_id)

    def load_owned_icon(self, canonical_id: UUID, kind: object) -> bytes:
        del kind
        self.icon_calls.append(canonical_id)
        if self.icon_error is not None:
            raise self.icon_error
        return b"validated"


class _RegistryWithoutIconLoader:
    def __init__(
        self,
        *,
        candidate: CanonicalRecallCandidate,
        canonical: CanonicalDish,
    ) -> None:
        self.candidate = candidate
        self.canonical = canonical

    def count_valid(self) -> int:
        return 2

    def list_recall_candidate_pool(
        self,
        *,
        language: Language,
        catalog_version: str,
    ) -> list[CanonicalRecallCandidate]:
        if (
            self.candidate.language is language
            and self.candidate.catalog_version == catalog_version
        ):
            return [self.candidate]
        return []

    def get_valid(self, canonical_id: UUID) -> CanonicalDish | None:
        if canonical_id == self.canonical.canonical_id:
            return self.canonical
        return None


class _Matcher:
    def __init__(
        self,
        response: CanonicalMatchResponse | Exception,
    ) -> None:
        self.response = response
        self.calls: list[Any] = []

    async def match_canonical(
        self,
        request: Any,
        *,
        json_only: bool = False,
    ) -> CanonicalMatchResponse:
        self.calls.append((request, json_only))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _service(
    registry: _Registry,
    matcher: _Matcher,
) -> RecallService:
    return RecallService(
        registry=registry,
        matcher=matcher,
        clock=lambda: 100.0,
    )


@pytest.mark.asyncio
async def test_below_global_minimum_does_not_call_matcher() -> None:
    candidate = _candidate()
    matcher = _Matcher(CanonicalMatchResponse(candidateId=candidate.canonical_id, confidence=1.0))
    registry = _Registry(valid_count=1, pool=[candidate])

    result = await _service(registry, matcher).recall(
        _analysis(),
        "current context",
        Language.ZH_CN,
        "catalog-v1",
        uuid4(),
    )

    assert result.canonical_dish is None
    assert result.trace.outcome is RecallDecision.NOT_ATTEMPTED_BELOW_MINIMUM
    assert result.trace.candidate_count == 0
    assert matcher.calls == []
    assert registry.pool_calls == 0


@pytest.mark.asyncio
async def test_empty_eligible_pool_does_not_call_matcher() -> None:
    matcher = _Matcher(CanonicalMatchResponse(candidateId=None, confidence=0.0))
    registry = _Registry(valid_count=2, pool=[])

    result = await _service(registry, matcher).recall(
        _analysis(),
        None,
        Language.ZH_CN,
        "catalog-v1",
        uuid4(),
    )

    assert result.trace.outcome is RecallDecision.NO_CANDIDATES
    assert result.trace.candidate_count == 0
    assert matcher.calls == []


def test_scoring_normalization_and_weighting_are_exact() -> None:
    assert ingredient_similarity(["Egg", "Onion"], ["egg", "pepper"]) == 0.5
    assert name_similarity("ＡＢ", "ab") == 1.0
    assert name_similarity("A", "A") == 1.0
    assert name_similarity("A", "B") == 0.0
    assert context_similarity("Farmhouse", ["boiled"], "farmhouse", ["boiled"]) == 1.0
    assert context_similarity(None, [], None, []) == 0.0
    assert weighted_similarity(0.5, 0.25, 1.0) == pytest.approx(0.5)


def test_retriever_ranks_full_pool_before_taking_five_and_stabilizes_ties() -> None:
    base_time = datetime(2026, 8, 25, tzinfo=UTC)
    candidates = [
        _candidate(
            canonical_id=UUID(f"00000000-0000-4000-8000-{index:012d}"),
            registered_at=base_time + timedelta(minutes=index),
            document=_document(
                name="Other",
                ingredients=("noodles",),
                cuisine=None,
                methods=(),
            ),
        )
        for index in range(1, 8)
    ]

    ranked = CandidateRetriever().retrieve(
        _analysis(),
        candidates,
        language=Language.ZH_CN,
        catalog_version="catalog-v1",
    )

    assert len(ranked) == 5
    assert [item.candidate.canonical_id for item in ranked] == [
        candidate.canonical_id for candidate in candidates[:5]
    ]
    assert all(item.score == pytest.approx(0.7) for item in ranked)


@pytest.mark.asyncio
async def test_exact_name_is_only_eligibility_and_matcher_adopts_one_valid_hit_at_threshold() -> None:
    candidate = _candidate(document=_document(name="Spring Noodles", ingredients=("pepper",)))
    canonical = _canonical(candidate)
    matcher = _Matcher(
        CanonicalMatchResponse(candidateId=candidate.canonical_id, confidence=0.85)
    )
    registry = _Registry(
        pool=[candidate],
        valid={candidate.canonical_id: canonical},
    )

    result = await _service(registry, matcher).recall(
        _analysis(),
        "current context",
        Language.ZH_CN,
        "catalog-v1",
        uuid4(),
    )

    assert result.canonical_dish == canonical
    assert result.trace.outcome is RecallDecision.MATCH_HIT
    assert result.trace.canonical_dish_id == candidate.canonical_id
    assert len(matcher.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("confidence", [0.849, 0.80, 0.799])
async def test_legal_candidate_below_calibrated_threshold_is_a_miss(
    confidence: float,
) -> None:
    candidate = _candidate()
    canonical = _canonical(candidate)
    matcher = _Matcher(
        CanonicalMatchResponse(
            candidateId=candidate.canonical_id,
            confidence=confidence,
        )
    )
    registry = _Registry(
        pool=[candidate],
        valid={candidate.canonical_id: canonical},
    )

    result = await _service(registry, matcher).recall(
        _analysis(),
        None,
        Language.ZH_CN,
        "catalog-v1",
        uuid4(),
    )

    assert result.canonical_dish is None
    assert result.trace.outcome is RecallDecision.MATCH_MISS
    assert result.trace.confidence == pytest.approx(confidence)


@pytest.mark.asyncio
async def test_match_request_contains_current_context_and_bounded_recall_only() -> None:
    candidate = _candidate()
    canonical = _canonical(candidate)
    matcher = _Matcher(CanonicalMatchResponse(candidateId=None, confidence=0.2))
    registry = _Registry(
        pool=[candidate],
        valid={candidate.canonical_id: canonical},
    )
    request_id = uuid4()

    result = await _service(registry, matcher).recall(
        _analysis(),
        "fresh current context",
        Language.ZH_CN,
        "catalog-v1",
        request_id,
    )

    assert result.canonical_dish is None
    request, json_only = matcher.calls[0]
    assert request.analysis.recognized_dish == "Spring Noodles"
    assert request.context_text == "fresh current context"
    assert request.language is Language.ZH_CN
    assert request.request_id == request_id
    assert len(request.candidates) == 1
    assert request.candidates[0].canonical_id == candidate.canonical_id
    assert request.candidates[0].display_name == candidate.display_name
    assert request.candidates[0].recall_document == candidate.recall_document
    assert "contextText" not in request.candidates[0].recall_document.model_dump(by_alias=True)
    assert json_only is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        CanonicalMatchResponse(candidateId=None, confidence=0.99),
        CanonicalMatchResponse(candidateId=UUID("00000000-0000-4000-8000-000000000099"), confidence=0.99),
        CanonicalMatchResponse(candidateId=None, confidence=0.799),
    ],
)
async def test_invalid_match_response_is_internal_miss(
    response: CanonicalMatchResponse,
) -> None:
    candidate = _candidate()
    canonical = _canonical(candidate)
    matcher = _Matcher(response)
    registry = _Registry(pool=[candidate], valid={candidate.canonical_id: canonical})

    result = await _service(registry, matcher).recall(
        _analysis(),
        None,
        Language.ZH_CN,
        "catalog-v1",
        uuid4(),
    )

    assert result.canonical_dish is None
    assert result.trace.outcome is RecallDecision.MATCH_MISS


@pytest.mark.asyncio
async def test_conflicting_supplemental_context_is_a_recall_miss() -> None:
    candidate = _candidate()
    canonical = _canonical(candidate)

    class _ConflictAwareMatcher(_Matcher):
        async def match_canonical(
            self,
            request: Any,
            *,
            json_only: bool = False,
        ) -> CanonicalMatchResponse:
            assert request.context_text == "make this a dessert without noodles"
            # The provider-facing contract requires a conflicting supplemental
            # request to fall below the calibrated 0.85 reuse threshold.
            self.calls.append((request, json_only))
            return CanonicalMatchResponse(
                candidateId=candidate.canonical_id,
                confidence=0.799,
            )

    matcher = _ConflictAwareMatcher(CanonicalMatchResponse(candidateId=None, confidence=0.0))
    registry = _Registry(pool=[candidate], valid={candidate.canonical_id: canonical})

    result = await _service(registry, matcher).recall(
        _analysis(),
        "make this a dessert without noodles",
        Language.ZH_CN,
        "catalog-v1",
        uuid4(),
    )

    assert result.canonical_dish is None
    assert result.trace.outcome is RecallDecision.MATCH_MISS
    assert len(matcher.calls) == 1


@pytest.mark.asyncio
async def test_registry_and_matcher_failures_fail_open_to_fallback_error() -> None:
    count_failure = _Registry(error=RuntimeError("registry unavailable"))
    count_result = await _service(
        count_failure,
        _Matcher(CanonicalMatchResponse(candidateId=None, confidence=0.0)),
    ).recall(_analysis(), None, Language.ZH_CN, "catalog-v1", uuid4())
    assert count_result.trace.outcome is RecallDecision.FALLBACK_ERROR

    candidate = _candidate()
    matcher = _Matcher(TimeoutError("provider timeout"))
    registry = _Registry(pool=[candidate])
    matcher_result = await _service(registry, matcher).recall(
        _analysis(), None, Language.ZH_CN, "catalog-v1", uuid4()
    )
    assert matcher_result.canonical_dish is None
    assert matcher_result.trace.outcome is RecallDecision.FALLBACK_ERROR


@pytest.mark.asyncio
async def test_post_match_icon_invalidation_is_an_internal_miss() -> None:
    candidate = _candidate()
    matcher = _Matcher(
        CanonicalMatchResponse(candidateId=candidate.canonical_id, confidence=0.99)
    )
    registry = _Registry(
        pool=[candidate],
        valid={candidate.canonical_id: _canonical(candidate)},
        icon_error=ValueError("icon hash changed"),
    )

    result = await _service(registry, matcher).recall(
        _analysis(), None, Language.ZH_CN, "catalog-v1", uuid4()
    )

    assert result.canonical_dish is None
    assert result.trace.outcome is RecallDecision.MATCH_MISS


@pytest.mark.asyncio
async def test_registry_without_required_icon_loader_cannot_yield_match_hit() -> None:
    candidate = _candidate()
    canonical = _canonical(candidate)
    matcher = _Matcher(
        CanonicalMatchResponse(candidateId=candidate.canonical_id, confidence=0.99)
    )
    registry = _RegistryWithoutIconLoader(candidate=candidate, canonical=canonical)
    service = RecallService(  # type: ignore[arg-type]
        registry=registry,
        matcher=matcher,
        clock=lambda: 100.0,
    )

    result = await service.recall(
        _analysis(), None, Language.ZH_CN, "catalog-v1", uuid4()
    )

    assert result.canonical_dish is None
    assert result.trace.outcome in {
        RecallDecision.MATCH_MISS,
        RecallDecision.FALLBACK_ERROR,
    }
