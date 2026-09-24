from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import evaluate_task67_abstention as task67

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.ingredient_rag.errors import IngredientRagNoMatch

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = (
    REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


def test_gold_metrics_keep_fixed_dish_and_item_denominators_and_exclude_fallback() -> None:
    pairs = []
    mappings = {}
    for dish_index in range(2):
        dish = {"dish_id": f"dish-{dish_index}"}
        for ingredient_index in range(3):
            query_id = f"q-{dish_index}-{ingredient_index}"
            ingredient = {"query_id": query_id, "acceptable_item_ids": ["176"]}
            pairs.append(("test", dish, ingredient))
            fallback = dish_index == 1 and ingredient_index == 0
            mappings[query_id] = {
                "mapping_status": "mapped",
                "selected_id": "176",
                "is_fallback": fallback,
                "candidate_ids": ["176"],
                "elapsed_ms": 2.0,
            }

    metrics = task67._score_side(pairs, mappings)

    assert metrics["dish_count"] == 2
    assert metrics["query_occurrence_count"] == 6
    assert metrics["selected_gold_hit"] == {
        "numerator": 5,
        "denominator": 6,
        "value": pytest.approx(5 / 6),
    }
    assert metrics["candidate_gold_recall_at_5"]["numerator"] == 6
    assert metrics["dish_all_gold"]["numerator"] == 1
    assert metrics["catalog_fallback_count"] == 1


def test_negative_runner_reports_semantic_no_match_and_catalog_fallback() -> None:
    catalog = VanillaCatalog.from_json(CATALOG_PATH)
    evidence = SimpleNamespace(
        candidates=(), semantic_hits=(), lexical_item_ids=(), exact_item_ids=()
    )

    class StubRetriever:
        def retrieve_with_evidence(self, _query, *, used_item_ids=frozenset()):
            del used_item_ids
            raise IngredientRagNoMatch(
                semantic_family="land_animal_meat", evidence=evidence
            )

    rows = task67.run_negative_queries(
        [{"query_id": "n1", "query": "a query held by the caller"}],
        catalog,
        StubRetriever(),  # type: ignore[arg-type]
    )

    assert len(rows) == 1
    assert rows[0]["retrieval_status"] == "no_match"
    assert rows[0]["retrieval_reason_code"] == "rag_no_semantic_match"
    assert rows[0]["semantic_family"] == "land_animal_meat"
    assert rows[0]["is_fallback"] is True
    assert rows[0]["fallback_correct"] is True


def test_negative_input_requires_unique_ids_and_query_text(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"query_id":"n1","query":"sample"}\n'
        '{"query_id":"n1","query":"duplicate"}\n',
        encoding="utf-8",
    )

    with pytest.raises(task67.Task67EvaluationError, match="unique"):
        task67._read_negative_jsonl(path)
