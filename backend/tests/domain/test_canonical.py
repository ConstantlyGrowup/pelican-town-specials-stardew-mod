from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.canonical import (
    CANONICAL_CANDIDATE_LIMIT,
    CANONICAL_MATCH_PROMPT_VERSION,
    CANONICAL_MATCH_THRESHOLD,
    CANONICAL_MIN_VALID_COUNT,
    CANONICAL_REGISTRY_SCHEMA_VERSION,
    CANONICAL_REUSE_CONTRACT_VERSION,
    CanonicalDish,
    CanonicalIconMetadata,
    RecallDecision,
    RecallDocument,
    RecallIngredient,
    RecallTrace,
)
from pelican_town_specials.domain.dish import GameIngredient
from tests.domain.factories import canonical_registration_fixture


def _canonical_dish() -> CanonicalDish:
    registration = canonical_registration_fixture()
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
        icon_source=CanonicalIconMetadata(
            relativePath=f"{registration.canonical_id}/icon-source.png",
            mediaType=MediaType.PNG,
            sha256="a" * 64,
            byteSize=100,
            width=32,
            height=24,
        ),
        icon_16=CanonicalIconMetadata(
            relativePath=f"{registration.canonical_id}/icon-16.png",
            mediaType=MediaType.PNG,
            sha256="b" * 64,
            byteSize=80,
            width=16,
            height=16,
        ),
        registeredAt=datetime(2026, 8, 25, tzinfo=UTC),
        lastUsedAt=None,
        useCount=0,
    )


def test_canonical_contract_constants_are_frozen() -> None:
    assert CANONICAL_REGISTRY_SCHEMA_VERSION == 1
    assert CANONICAL_MIN_VALID_COUNT == 2
    assert CANONICAL_CANDIDATE_LIMIT == 5
    assert CANONICAL_MATCH_THRESHOLD == 0.85
    assert CANONICAL_REUSE_CONTRACT_VERSION == "canonical-reuse-v1"
    assert CANONICAL_MATCH_PROMPT_VERSION == "canonical-match-v1"


def test_recall_trace_keeps_only_bounded_internal_outcome_fields() -> None:
    trace = RecallTrace(
        outcome=RecallDecision.MATCH_HIT,
        candidateCount=5,
        confidence=0.95,
        canonicalDishId=uuid4(),
        elapsedMs=12,
    )

    assert set(trace.model_dump(by_alias=True)) == {
        "outcome",
        "candidateCount",
        "confidence",
        "canonicalDishId",
        "elapsedMs",
    }
    with pytest.raises(ValidationError):
        RecallTrace(
            outcome=RecallDecision.MATCH_MISS,
            candidateCount=0,
            elapsedMs=0,
            explanation="must not be persisted",
        )


def test_registration_is_strict_and_rejects_mixed_gameplay_catalog_versions() -> None:
    registration = canonical_registration_fixture()
    mixed_ingredient = GameIngredient(
        itemId="256",
        displayName="Tomato",
        quantity=1,
        mappingReason="catalog match",
        catalogVersion="different-catalog",
    )

    with pytest.raises(ValidationError, match="catalog_version"):
        registration.__class__(
            **{
                **registration.model_dump(),
                "gameplay": registration.gameplay.model_copy(
                    update={
                        "ingredients": [
                            registration.gameplay.ingredients[0],
                            mixed_ingredient,
                        ]
                    }
                ),
            }
        )

    with pytest.raises(ValidationError):
        registration.__class__(
            **{**registration.model_dump(), "canonical_id": str(uuid4())}
        )


@pytest.mark.parametrize(
    "dish_signature",
    ["spring-noodle-bowl", "A" * 64, "a" * 63, "g" * 64],
)
def test_registration_rejects_non_sha256_dish_signatures(
    dish_signature: str,
) -> None:
    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        canonical_registration_fixture(dish_signature=dish_signature)


def test_recall_document_copies_and_freezes_nested_ingredient_values() -> None:
    ingredient = RecallIngredient(
        name="Spring Onion",
        normalizedName="spring onion",
        visibleConfidence=0.87,
    )
    source = [ingredient]
    document = RecallDocument(
        recognizedDish="Spring Noodles",
        normalizedName="spring noodle bowl",
        summary="A fresh noodle bowl.",
        cuisine="Farmhouse",
        semanticIngredients=source,
        cookingMethods=["boiled"],
        flavorProfile=["savory"],
    )

    source.append(
        RecallIngredient(name="Egg", normalizedName="egg", visibleConfidence=0.98)
    )
    object.__setattr__(ingredient, "normalized_name", "mutated")

    assert [item.normalized_name for item in document.semantic_ingredients] == [
        "spring onion"
    ]
    with pytest.raises(TypeError, match="immutable"):
        document.semantic_ingredients.append(
            RecallIngredient(
                name="Egg",
                normalizedName="egg",
                visibleConfidence=0.98,
            )
        )
    with pytest.raises(TypeError, match="immutable"):
        document.cooking_methods[0] = "fried"


def test_canonical_dish_is_deeply_immutable_and_blocks_copy_updates() -> None:
    dish = _canonical_dish()

    with pytest.raises(ValidationError, match="frozen"):
        dish.use_count = 1
    with pytest.raises(ValueError, match="immutable"):
        dish.model_copy(update={"use_count": 1})
    with pytest.raises(TypeError, match="immutable"):
        dish.presentation.tags.append("changed")
    with pytest.raises(TypeError, match="immutable"):
        dish.gameplay.ingredients.append(dish.gameplay.ingredients[0])
    with pytest.raises(TypeError, match="immutable"):
        dish.recall_document.semantic_ingredients.append(
            RecallIngredient(
                name="Egg",
                normalizedName="egg",
                visibleConfidence=0.98,
            )
        )


def test_canonical_dish_rejects_non_v4_ids_naive_time_and_contract_drift() -> None:
    dish = _canonical_dish()
    payload = dish.model_dump()

    with pytest.raises(ValidationError, match="version 4"):
        CanonicalDish(**{**payload, "canonical_id": dish.canonical_id.__class__(int=0)})
    with pytest.raises(ValidationError, match="timezone-aware"):
        CanonicalDish(
            **{**payload, "registered_at": datetime(2026, 8, 25)}  # noqa: DTZ001
        )
    with pytest.raises(ValidationError, match="reuse_contract_version"):
        CanonicalDish(**{**payload, "reuse_contract_version": "future-contract"})
