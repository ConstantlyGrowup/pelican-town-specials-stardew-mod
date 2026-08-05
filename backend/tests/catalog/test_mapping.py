from __future__ import annotations

from pathlib import Path

import pytest

from pelican_town_specials.catalog.mapping import map_ingredient
from pelican_town_specials.catalog.models import CatalogCandidate
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.dish import SemanticIngredient
from pelican_town_specials.domain.errors import AppError

ROOT = Path(__file__).parents[3]
CATALOG_PATH = ROOT / "resources/catalogs/stardew-1.6.15/vanilla-ingredients.json"


@pytest.fixture
def catalog() -> VanillaCatalog:
    return VanillaCatalog.from_json(CATALOG_PATH)


@pytest.fixture
def semantic() -> SemanticIngredient:
    return SemanticIngredient(
        name="番茄",
        normalized_name="tomato",
        visible_confidence=0.9,
    )


def test_mapping_cannot_return_id_outside_candidates(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    with pytest.raises(AppError, match="PTS_VALIDATION_INGREDIENT_ID_UNKNOWN") as caught:
        map_ingredient(
            semantic,
            [CatalogCandidate(item_id="NotReal", score=1.0)],
            catalog,
        )

    assert caught.value.code == "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN"
    assert caught.value.http_status == 422
    assert caught.value.retryable is False
    assert "NotReal" not in caught.value.message
    assert "番茄" not in caught.value.message
    assert caught.value.details == {}


def test_mapping_empty_candidates_returns_fallback(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    mapped = map_ingredient(semantic, [], catalog)

    assert mapped.item_id == "176"
    assert mapped.display_name == catalog.require("176").display_name_en
    assert mapped.quantity == 1
    assert mapped.catalog_version == catalog.version
    assert "catalog fallback" in mapped.mapping_reason


def test_mapping_unusable_candidate_returns_fallback(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    mapped = map_ingredient(
        semantic,
        [CatalogCandidate(item_id="349", score=1.0)],
        catalog,
    )

    assert mapped.item_id == "176"
    assert mapped.display_name == catalog.require("176").display_name_en
    assert mapped.quantity == 1
    assert mapped.catalog_version == catalog.version
    assert "catalog fallback" in mapped.mapping_reason


def test_mapping_two_unmatched_candidates_get_distinct_fallbacks(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    first = map_ingredient(semantic, [], catalog)
    second = map_ingredient(
        semantic, [], catalog, used_item_ids=frozenset({first.item_id})
    )

    assert first.item_id == "176"
    assert second.item_id != first.item_id
    assert "catalog fallback" in first.mapping_reason
    assert "catalog fallback" in second.mapping_reason
    assert second.display_name == catalog.require(second.item_id).display_name_en


def test_mapping_unmatched_after_egg_uses_non_egg_fallback(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    egg = map_ingredient(
        semantic,
        [CatalogCandidate(item_id="176", score=1.0)],
        catalog,
    )
    assert egg.item_id == "176"
    assert egg.mapping_reason == "selected validated vanilla candidate"

    unmatched = map_ingredient(
        semantic, [], catalog, used_item_ids=frozenset({egg.item_id})
    )

    assert unmatched.item_id != "176"
    assert "catalog fallback" in unmatched.mapping_reason


def test_mapping_selects_highest_score_and_catalog_facts(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    mapped = map_ingredient(
        semantic,
        [
            CatalogCandidate(item_id="256", score=0.8),
            CatalogCandidate(item_id="Broccoli", score=0.95),
        ],
        catalog,
    )

    assert mapped.item_id == "Broccoli"
    assert mapped.display_name == catalog.require("Broccoli").display_name_en
    assert mapped.quantity == 1
    assert mapped.catalog_version == catalog.version
    assert 1 <= len(mapped.mapping_reason) <= 200
    assert "番茄" not in mapped.mapping_reason


def test_mapping_breaks_score_ties_by_item_id(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    mapped = map_ingredient(
        semantic,
        [
            CatalogCandidate(item_id="256", score=0.9),
            CatalogCandidate(item_id="24", score=0.9),
        ],
        catalog,
    )

    assert mapped.item_id == "24"
    assert mapped.display_name == catalog.require("24").display_name_en


def _unchecked_candidate(score: float) -> CatalogCandidate:
    candidate = object.__new__(CatalogCandidate)
    object.__setattr__(candidate, "item_id", "256")
    object.__setattr__(candidate, "score", score)
    return candidate


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_mapping_rejects_non_finite_candidate_scores(
    semantic: SemanticIngredient, catalog: VanillaCatalog, score: float
) -> None:
    with pytest.raises(AppError) as caught:
        map_ingredient(semantic, [_unchecked_candidate(score)], catalog)

    assert caught.value.code == "PTS_VALIDATION_INGREDIENT_CANDIDATE_INVALID"
    assert caught.value.http_status == 422
    assert caught.value.retryable is False


def test_mapping_checks_all_candidates_before_selecting(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    with pytest.raises(AppError) as caught:
        map_ingredient(
            semantic,
            [
                CatalogCandidate(item_id="256", score=1.0),
                CatalogCandidate(item_id="NotReal", score=0.0),
            ],
            catalog,
        )

    assert caught.value.code == "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN"
    assert "NotReal" not in caught.value.message

def test_mapping_all_unusable_candidates_return_fallback(
    semantic: SemanticIngredient, catalog: VanillaCatalog
) -> None:
    mapped = map_ingredient(
        semantic,
        [
            CatalogCandidate(item_id="349", score=0.9),
            CatalogCandidate(item_id="351", score=0.8),
        ],
        catalog,
    )

    assert mapped.item_id == "176"
    assert mapped.display_name == catalog.require("176").display_name_en
    assert mapped.quantity == 1
    assert mapped.catalog_version == catalog.version
    assert "catalog fallback" in mapped.mapping_reason
