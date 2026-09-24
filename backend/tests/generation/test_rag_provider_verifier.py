from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from backend.tests.domain.factories import make_draft

from pelican_town_specials.catalog.models import CatalogCandidate, CatalogItem
from pelican_town_specials.domain.common import DraftMode
from pelican_town_specials.domain.draft import DraftStatus
from pelican_town_specials.generation import orchestrator as orchestrator_module
from pelican_town_specials.generation.attempt_registry import AttemptRegistry
from pelican_town_specials.generation.orchestrator import (
    DEFAULT_INGREDIENT_RETRIEVAL_BACKEND,
    GenerationOrchestrator,
    IngredientRetrievalBackend,
)
from pelican_town_specials.ingredient_rag.errors import IngredientRagNoMatch
from pelican_town_specials.ingredient_rag.retriever import IngredientRetrievalEvidence
from pelican_town_specials.providers.contracts import (
    IngredientVerifierCandidate,
    IngredientVerifierRequest,
    IngredientVerifierResponse,
    IngredientVerifierSelection,
)

from .conftest import (
    FakeGateway,
    GenerationHarness,
    initial_command,
    put_original_image,
)


class _VerifierGateway(FakeGateway):
    def __init__(
        self,
        response_factory: Callable[
            [IngredientVerifierRequest], IngredientVerifierResponse
        ],
    ) -> None:
        super().__init__()
        self.response_factory = response_factory
        self.verifier_requests: list[IngredientVerifierRequest] = []
        self.verifier_error: Exception | None = None
        self.cancel_verifier = False

    async def verify_ingredient_candidates(
        self, request: IngredientVerifierRequest
    ) -> IngredientVerifierResponse:
        self.verifier_requests.append(request)
        if self.cancel_verifier:
            raise asyncio.CancelledError
        if self.verifier_error is not None:
            raise self.verifier_error
        return self.response_factory(request)


class _FakeRetriever:
    def __init__(
        self,
        catalog,
        *,
        egg_id: str,
        onion_id: str,
        no_match_query: str | None = None,
    ) -> None:
        self.catalog = catalog
        self.egg_id = egg_id
        self.onion_id = onion_id
        self.no_match_query = no_match_query
        self.calls: list[tuple[str, frozenset[str]]] = []

    def retrieve_with_evidence(
        self, query: str, *, used_item_ids: frozenset[str]
    ) -> IngredientRetrievalEvidence:
        self.calls.append((query, used_item_ids))
        if query == self.no_match_query:
            raise IngredientRagNoMatch(
                semantic_family="land_animal_meat",
                evidence=IngredientRetrievalEvidence((), (), (), ()),
            )
        item_ids = (
            [self.onion_id, self.egg_id]
            if query == "egg"
            else [self.egg_id, self.onion_id]
        )
        candidates = tuple(
            CatalogCandidate(item_id=item_id, score=1.0 - index / 5)
            for index, item_id in enumerate(item_ids)
            if item_id not in used_item_ids
        )
        return IngredientRetrievalEvidence(candidates, (), (), ())


def _candidate(catalog, item_id: str) -> IngredientVerifierCandidate:
    item: CatalogItem = catalog.require(item_id)
    return IngredientVerifierCandidate(
        itemId=item_id,
        displayNameEn=item.display_name_en,
        displayNameZh=item.display_name_zh,
    )


def _selected_response(request: IngredientVerifierRequest) -> IngredientVerifierResponse:
    return IngredientVerifierResponse(
        items=[
            IngredientVerifierSelection(
                index=item.index,
                selectedItemId=item.candidates[0].item_id if item.candidates else None,
            )
            for item in request.ingredients
        ]
    )


def _explicit_rag_orchestrator(
    harness: GenerationHarness, gateway: _VerifierGateway
) -> GenerationOrchestrator:
    return GenerationOrchestrator(
        draft_repository=harness.draft_repository,
        attempt_repository=harness.attempt_repository,
        asset_store=harness.asset_store,
        catalog=harness.catalog,
        gateway_factory=lambda: gateway,
        registry=AttemptRegistry(),
        min_confidence=0.5,
        ingredient_retrieval_backend=IngredientRetrievalBackend.RAG,
    )


async def _run_explicit_rag(
    harness: GenerationHarness,
    gateway: _VerifierGateway,
    *,
    monkeypatch: pytest.MonkeyPatch,
    no_match_query: str | None = None,
) -> tuple[GenerationOrchestrator, object, _FakeRetriever]:
    egg_id = harness.catalog.search_ingredients("egg", limit=1)[0].item_id
    onion_id = harness.catalog.search_ingredients("spring onion", limit=1)[0].item_id
    assert egg_id != onion_id
    retriever = _FakeRetriever(
        harness.catalog,
        egg_id=egg_id,
        onion_id=onion_id,
        no_match_query=no_match_query,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "_get_default_ingredient_rag_retriever",
        lambda _catalog: retriever,
    )
    orchestrator = _explicit_rag_orchestrator(harness, gateway)
    original = put_original_image(harness)
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = orchestrator.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )
    events = [event async for event in orchestrator.run(initial_command(saved))]
    return orchestrator, (saved, events[-1]), retriever


async def test_explicit_rag_verifies_a_dish_once_with_minimal_top5(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _VerifierGateway(_selected_response)

    orchestrator, (saved, last_event), retriever = await _run_explicit_rag(
        harness, gateway, monkeypatch=monkeypatch
    )

    result = orchestrator.drafts.get(saved.draft_id)
    assert last_event.type == "attempt.succeeded"
    assert len(gateway.verifier_requests) == 1
    request = gateway.verifier_requests[0]
    assert request.dish_name == "春日面碗"
    assert [item.index for item in request.ingredients] == [0, 1]
    assert [item.name for item in request.ingredients] == ["egg", "spring onion"]
    assert all(len(item.candidates) <= 5 for item in request.ingredients)
    assert len(retriever.calls) == 2
    assert result.gameplay is not None
    assert len({item.item_id for item in result.gameplay.ingredients}) == 2


async def test_null_does_not_claim_a_later_explicitly_selected_id(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    egg_id = harness.catalog.search_ingredients("egg", limit=1)[0].item_id

    def response(request: IngredientVerifierRequest) -> IngredientVerifierResponse:
        return IngredientVerifierResponse(
            items=[
                IngredientVerifierSelection(index=0, selectedItemId=None),
                IngredientVerifierSelection(index=1, selectedItemId=egg_id),
            ]
        )

    gateway = _VerifierGateway(response)
    orchestrator, (saved, last_event), _retriever = await _run_explicit_rag(
        harness, gateway, monkeypatch=monkeypatch
    )

    result = orchestrator.drafts.get(saved.draft_id)
    assert last_event.type == "attempt.succeeded"
    assert len(gateway.verifier_requests) == 1
    assert result.gameplay is not None
    ingredients = result.gameplay.ingredients
    assert ingredients[1].item_id == egg_id
    assert ingredients[0].item_id != egg_id
    assert len({item.item_id for item in ingredients}) == len(ingredients)
    assert ingredients[0].mapping_reason.startswith("catalog fallback:")


async def test_local_no_match_vetoes_provider_selection_for_that_item(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def response(request: IngredientVerifierRequest) -> IngredientVerifierResponse:
        return IngredientVerifierResponse(
            items=[
                IngredientVerifierSelection(index=0, selectedItemId="176"),
                IngredientVerifierSelection(
                    index=1, selectedItemId=request.ingredients[1].candidates[0].item_id
                ),
            ]
        )

    gateway = _VerifierGateway(response)
    orchestrator, (saved, last_event), _retriever = await _run_explicit_rag(
        harness,
        gateway,
        monkeypatch=monkeypatch,
        no_match_query="egg",
    )

    result = orchestrator.drafts.get(saved.draft_id)
    assert last_event.type == "attempt.succeeded"
    assert len(gateway.verifier_requests) == 1
    assert gateway.verifier_requests[0].ingredients[0].candidates == []
    assert result.gameplay is not None
    assert result.gameplay.ingredients[0].mapping_reason.startswith(
        "catalog fallback:"
    )


async def test_verifier_failure_keeps_entire_local_rag_mapping(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _VerifierGateway(_selected_response)
    gateway.verifier_error = RuntimeError("private provider payload")

    orchestrator, (saved, last_event), retriever = await _run_explicit_rag(
        harness, gateway, monkeypatch=monkeypatch
    )

    result = orchestrator.drafts.get(saved.draft_id)
    assert last_event.type == "attempt.succeeded"
    assert len(gateway.verifier_requests) == 1
    onion_id = harness.catalog.search_ingredients("spring onion", limit=1)[0].item_id
    assert retriever.calls == [
        ("egg", frozenset()),
        ("spring onion", frozenset({onion_id})),
    ]
    assert result.gameplay is not None
    assert [item.item_id for item in result.gameplay.ingredients] == [
        harness.catalog.search_ingredients("spring onion", limit=1)[0].item_id,
        harness.catalog.search_ingredients("egg", limit=1)[0].item_id,
    ]


async def test_invalid_verdict_does_not_partially_apply_earlier_items(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    egg_id = harness.catalog.search_ingredients("egg", limit=1)[0].item_id

    def invalid_response(
        request: IngredientVerifierRequest,
    ) -> IngredientVerifierResponse:
        return IngredientVerifierResponse(
            items=[
                IngredientVerifierSelection(index=0, selectedItemId=egg_id),
                IngredientVerifierSelection(
                    index=1, selectedItemId="not-in-this-top5"
                ),
            ]
        )

    gateway = _VerifierGateway(invalid_response)
    orchestrator, (saved, last_event), _retriever = await _run_explicit_rag(
        harness, gateway, monkeypatch=monkeypatch
    )

    result = orchestrator.drafts.get(saved.draft_id)
    assert last_event.type == "attempt.succeeded"
    assert len(gateway.verifier_requests) == 1
    assert result.gameplay is not None
    # The first Provider choice differs from the local first candidate; the
    # invalid second choice therefore proves that no partial verdict leaked.
    assert result.gameplay.ingredients[0].item_id == (
        harness.catalog.search_ingredients("spring onion", limit=1)[0].item_id
    )


async def test_verifier_cancellation_propagates_to_attempt_rollback(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _VerifierGateway(_selected_response)
    gateway.cancel_verifier = True

    orchestrator, (saved, last_event), _retriever = await _run_explicit_rag(
        harness, gateway, monkeypatch=monkeypatch
    )

    assert last_event.type == "attempt.failed"
    assert last_event.error is not None
    assert last_event.error.code == "PTS_GEN_CANCELLED"
    assert orchestrator.drafts.get(saved.draft_id).status is DraftStatus.READY


async def test_legacy_default_does_not_call_verifier(
    harness: GenerationHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert DEFAULT_INGREDIENT_RETRIEVAL_BACKEND is IngredientRetrievalBackend.LEGACY
    gateway = _VerifierGateway(_selected_response)
    harness.gateway = gateway
    monkeypatch.setattr(
        orchestrator_module,
        "_get_default_ingredient_rag_retriever",
        lambda _catalog: pytest.fail("default path must not load RAG"),
    )
    original = put_original_image(harness)
    draft = make_draft(mode=DraftMode.ASK_GUS, status=DraftStatus.READY)
    saved = harness.orchestrator.drafts.save(
        draft.model_copy(
            update={
                "source": draft.source.model_copy(
                    update={"original_image_asset_id": original.asset_id}
                )
            }
        ),
        expected_revision=None,
    )

    events = [event async for event in harness.orchestrator.run(initial_command(saved))]

    assert events[-1].type == "attempt.succeeded"
    assert gateway.verifier_requests == []
