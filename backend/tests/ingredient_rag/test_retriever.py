from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.ingredient_rag import retriever as retriever_module
from pelican_town_specials.ingredient_rag.errors import (
    IngredientRagNoMatch,
    IngredientRagUnavailable,
)
from pelican_town_specials.ingredient_rag.index import StaticIngredientIndex
from pelican_town_specials.ingredient_rag.retriever import (
    IngredientRagRetriever,
    build_passage,
    normalize_ingredient_name,
    rank_candidates,
)
from pelican_town_specials.ingredient_rag.semantic_types import (
    catalog_family_item_ids,
    classify_catalog_family,
    classify_ingredient_family,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = (
    _REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


@pytest.fixture
def catalog() -> VanillaCatalog:
    return VanillaCatalog.from_json(_CATALOG_PATH)


def _index_with_one_semantic_hit(catalog: VanillaCatalog) -> StaticIngredientIndex:
    item_ids = tuple(item.item_id for item in catalog.ingredients)
    vectors = np.zeros((len(item_ids), 384), dtype=np.float32)
    vectors[:, 1] = 1.0
    vectors[item_ids.index(item_ids[-1]), 0] = 1.0
    vectors[item_ids.index(item_ids[-1]), 1] = 0.0
    return StaticIngredientIndex(item_ids=item_ids, vectors=vectors)


def test_normalization_uses_nfkc_latin_casefold_and_whitespace() -> None:
    assert normalize_ingredient_name("  ＥＧＧ　　white  ") == "egg white"
    assert normalize_ingredient_name(" 鳕鱼 ") == "鳕鱼"


def test_passage_contains_bilingual_names_aliases_and_catalog_traits(
    catalog: VanillaCatalog,
) -> None:
    egg = catalog.require("176")

    passage = build_passage(egg)

    assert passage.startswith("passage: ")
    assert egg.display_name_zh in passage
    assert egg.display_name_en in passage
    assert "别名" in passage
    assert egg.type in passage
    assert egg.category in passage


def test_unique_exact_alias_precedes_semantic_candidates_with_rank_scores(
    catalog: VanillaCatalog,
) -> None:
    index = _index_with_one_semantic_hit(catalog)
    query_vectors: list[str] = []

    def encode(text: str) -> np.ndarray:
        query_vectors.append(text)
        vector = np.zeros(384, dtype=np.float32)
        vector[0] = 1.0
        return vector

    candidates = rank_candidates("  ＥＧＧ  ", catalog, index, encode)

    assert query_vectors == ["query: egg"]
    assert candidates[0].item_id == "176"
    assert len(candidates) == 5
    assert all(
        left.score > right.score
        for left, right in pairwise(candidates)
    )


def test_already_used_item_ids_are_removed_before_mapper_candidates(
    catalog: VanillaCatalog,
) -> None:
    item_ids = tuple(item.item_id for item in catalog.ingredients)
    vectors = np.zeros((len(item_ids), 384), dtype=np.float32)
    vectors[:, 0] = 1.0
    index = StaticIngredientIndex(item_ids=item_ids, vectors=vectors)
    vector = np.eye(1, 384, 0, dtype=np.float32)[0]
    top_hit = index.search(vector, top_k=1)[0][0]

    candidates = rank_candidates(
        "qqqqzztask65notacatalogitem",
        catalog,
        index,
        lambda _text: vector,
        used_item_ids=frozenset({top_hit}),
    )

    assert len(candidates) == 5
    assert top_hit not in {candidate.item_id for candidate in candidates}


def test_semantic_ties_are_stable_and_ignore_edibility(
    catalog: VanillaCatalog,
) -> None:
    item_ids = tuple(item.item_id for item in catalog.ingredients)
    vectors = np.zeros((len(item_ids), 384), dtype=np.float32)
    vectors[:, 0] = 1.0
    index = StaticIngredientIndex(item_ids=item_ids, vectors=vectors)
    encode = lambda _text: np.eye(1, 384, 0, dtype=np.float32)[0]

    query = "qqqqzztask65notacatalogitem"
    first = rank_candidates(query, catalog, index, encode)
    second = rank_candidates(query, catalog, index, encode)

    assert first == second
    semantic_top_five = index.search(encode(f"query: {query}"), top_k=5)
    assert [candidate.item_id for candidate in first] == sorted(
        (item_id for item_id, _score in semantic_top_five),
        key=lambda item_id: (
            catalog.require(item_id).category,
            _item_id_sort_key(item_id),
        ),
    )
    assert all(
        left.score > right.score
        for left, right in pairwise(first)
    )


def test_static_index_can_serve_three_concurrent_queries(catalog: VanillaCatalog) -> None:
    index = _index_with_one_semantic_hit(catalog)
    vector = np.eye(1, 384, 0, dtype=np.float32)[0]

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(
            executor.map(lambda _slot: index.search(vector, top_k=5), range(3))
        )

    assert results[0] == results[1] == results[2]


def test_missing_manifest_disables_rag_with_safe_reason_code(
    catalog: VanillaCatalog, tmp_path: Path
) -> None:
    retriever = IngredientRagRetriever(
        catalog,
        catalog_path=_CATALOG_PATH,
        resource_dir=tmp_path,
    )

    with pytest.raises(IngredientRagUnavailable) as caught:
        retriever.retrieve("private query text")

    assert caught.value.reason_code == "rag_index_invalid"
    assert str(caught.value) == "rag_index_invalid"
    assert "private query text" not in str(caught.value)
    assert retriever.disabled_reason == "rag_index_invalid"

    with pytest.raises(IngredientRagUnavailable) as repeated:
        retriever.retrieve("another private query")
    assert repeated.value.reason_code == "rag_index_invalid"


def test_model_load_failure_uses_model_reason_code(
    catalog: VanillaCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = _index_with_one_semantic_hit(catalog)

    monkeypatch.setattr(retriever_module, "load_static_index", lambda **_kwargs: index)

    def fail_model_load(**_kwargs):
        raise IngredientRagUnavailable("rag_model_unavailable")

    monkeypatch.setattr(retriever_module, "OnnxE5Encoder", fail_model_load)
    retriever = IngredientRagRetriever(
        catalog,
        catalog_path=_CATALOG_PATH,
        resource_dir=tmp_path,
    )

    with pytest.raises(IngredientRagUnavailable) as caught:
        retriever.retrieve("egg")

    assert caught.value.reason_code == "rag_model_unavailable"
    assert retriever.disabled_reason == "rag_model_unavailable"


@pytest.mark.parametrize(
    "query",
    ["鸡肉", "牛肉", "羊肉", "猪肉", "chicken meat", "beef", "lamb", "pork"],
)
def test_unavailable_land_meat_family_is_a_semantic_no_match(
    catalog: VanillaCatalog, query: str
) -> None:
    class StubEncoder:
        def encode(self, _text: str) -> np.ndarray:
            return np.eye(1, 384, 0, dtype=np.float32)[0]

    retriever = IngredientRagRetriever(
        catalog,
        encoder=StubEncoder(),
        index=_index_with_one_semantic_hit(catalog),
    )

    with pytest.raises(IngredientRagNoMatch) as caught:
        retriever.retrieve(query)

    assert caught.value.reason_code == "rag_no_semantic_match"
    assert caught.value.semantic_family == "land_animal_meat"
    assert caught.value.evidence.semantic_hits
    assert retriever.disabled_reason is None


def test_prepared_soy_family_is_distinct_from_raw_bean_and_not_catalog_backed(
    catalog: VanillaCatalog,
) -> None:
    assert classify_ingredient_family("豆腐") == "prepared_soy"
    assert classify_ingredient_family("tofu") == "prepared_soy"
    assert catalog_family_item_ids(catalog.ingredients, "prepared_soy") == ()
    assert catalog_family_item_ids(catalog.ingredients, "land_animal_meat") == ()
    assert classify_catalog_family(catalog.require("442")) is None
    assert classify_catalog_family(catalog.require("426")) is None


def test_unrecognized_and_catalog_backed_queries_remain_retrievable(
    catalog: VanillaCatalog,
) -> None:
    assert classify_ingredient_family("salmon") is None
    assert classify_ingredient_family("potato") is None
    assert classify_ingredient_family("豆腐皮") is None
    assert classify_ingredient_family("fish meat") is None


def test_query_encoding_failure_uses_query_reason_code(
    catalog: VanillaCatalog,
) -> None:
    class FailingEncoder:
        def encode(self, text: str) -> np.ndarray:
            raise RuntimeError(f"private input: {text}")

    retriever = IngredientRagRetriever(
        catalog,
        encoder=FailingEncoder(),
        index=_index_with_one_semantic_hit(catalog),
    )

    with pytest.raises(IngredientRagUnavailable) as caught:
        retriever.retrieve("private query text")

    assert caught.value.reason_code == "rag_query_failed"
    assert str(caught.value) == "rag_query_failed"
    assert "private query text" not in str(caught.value)
    assert retriever.disabled_reason == "rag_query_failed"


def _item_id_sort_key(item_id: str) -> tuple[int, int | str]:
    try:
        return (0, int(item_id))
    except ValueError:
        return (1, item_id)
