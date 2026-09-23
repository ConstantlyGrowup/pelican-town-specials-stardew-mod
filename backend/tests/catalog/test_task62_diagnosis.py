"""Deterministic Task 62 examples for the current ingredient-mapping path."""

from __future__ import annotations

from pathlib import Path

import pytest

from pelican_town_specials.catalog.mapping import map_ingredient
from pelican_town_specials.catalog.models import CatalogCandidate
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.orchestrator import _build_candidates
from pelican_town_specials.providers.contracts import SemanticRecipeIngredient

ROOT = Path(__file__).parents[3]
CATALOG_PATH = ROOT / "resources/catalogs/stardew-1.6.15/vanilla-ingredients.json"


@pytest.fixture(scope="module")
def catalog() -> VanillaCatalog:
    return VanillaCatalog.from_json(CATALOG_PATH)


def _semantic(name: str, normalized_name: str) -> SemanticRecipeIngredient:
    return SemanticRecipeIngredient(name=name, normalizedName=normalized_name)


def test_carp_top_five_is_reselected_by_edibility_weight(catalog: VanillaCatalog) -> None:
    semantic = _semantic("Carp", "Carp")

    searched = catalog.search_ingredients("Carp", limit=5)
    candidates = _build_candidates(semantic, catalog)
    mapped = map_ingredient(semantic, candidates, catalog)

    assert [item.item_id for item in searched] == ["142", "209", "269", "682", "901"]
    scores = {candidate.item_id: candidate.score for candidate in candidates}
    assert scores["209"] > scores["142"]
    assert mapped.item_id == "209"
    assert catalog.require("142").display_name_en == "Carp"
    assert catalog.require("209").display_name_en == "Carp Surprise"


def test_compound_cherry_tomatoes_search_omits_tomato(catalog: VanillaCatalog) -> None:
    semantic = _semantic("cherry tomatoes", "cherry tomatoes")

    searched = catalog.search_ingredients("cherry tomatoes", limit=5)
    candidates = _build_candidates(semantic, catalog)
    mapped = map_ingredient(semantic, candidates, catalog)

    assert [item.item_id for item in searched] == ["638"]
    assert catalog.require("638").display_name_en == "Cherry"
    assert catalog.require("256").display_name_en == "Tomato"
    assert "256" not in [item.item_id for item in searched]
    assert mapped.item_id == "638"


def test_chinese_compound_name_misses_and_uses_fallback(catalog: VanillaCatalog) -> None:
    semantic = _semantic("樱桃番茄", "樱桃番茄")

    candidates = _build_candidates(semantic, catalog)
    mapped = map_ingredient(semantic, candidates, catalog)

    assert catalog.search_ingredients("樱桃番茄", limit=5) == []
    assert candidates == []
    assert mapped.item_id == "176"
    assert mapped.mapping_reason.startswith("catalog fallback:")


def test_unknown_candidate_id_is_rejected_before_mapping(
    catalog: VanillaCatalog,
) -> None:
    semantic = _semantic("tomato", "tomato")

    with pytest.raises(AppError) as caught:
        map_ingredient(
            semantic,
            [CatalogCandidate(item_id="NotReal", score=1.0)],
            catalog,
        )

    assert caught.value.code == "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN"
    assert caught.value.http_status == 422
    assert caught.value.retryable is False
