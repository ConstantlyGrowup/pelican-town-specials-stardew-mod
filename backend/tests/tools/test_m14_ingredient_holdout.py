from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
from scripts import evaluate_ingredient_holdout as holdout

from pelican_town_specials.catalog.models import CatalogCandidate
from pelican_town_specials.generation.orchestrator import (
    IngredientRetrievalBackend,
    _build_candidates,
)


def _raw_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    fixture, old_fixture, catalog_items = holdout.load_raw_inputs()
    return deepcopy(fixture), old_fixture, catalog_items


def test_expanded_holdout_matches_the_frozen_sample_plan() -> None:
    inputs = holdout.load_frozen_inputs()
    summary = inputs["summary"]

    assert summary["dish_count"] == 96
    assert summary["query_count"] == 288
    assert summary["dishes_by_stratum"] == {
        "direct_name": 24,
        "bilingual_or_synonym": 24,
        "ambiguous_name": 24,
        "raw_vs_prepared": 24,
    }
    assert summary["distinct_normalized_query_count"] >= 80
    assert summary["queries_absent_from_task64"] >= 40
    assert summary["queries_by_language"]["en"] >= 90
    assert summary["queries_by_language"]["zh"] >= 90
    assert summary["all_gold_ids_usable"] is True


def test_fixture_rejects_a_gold_id_that_is_not_an_ingredient() -> None:
    fixture, old_fixture, catalog_items = _raw_inputs()
    ingredient = fixture["dishes"][0]["ingredients"][0]
    ingredient["acceptable_item_ids"] = ["-5"]

    with pytest.raises(holdout.HoldoutFixtureError, match="usable ingredient"):
        holdout.validate_fixture(fixture, old_fixture, catalog_items)


def test_fixture_rejects_a_dish_name_reused_from_task64() -> None:
    fixture, old_fixture, catalog_items = _raw_inputs()
    fixture["dishes"][0]["name_en"] = old_fixture["dishes"][0]["name_en"]

    with pytest.raises(holdout.HoldoutFixtureError, match="dish name overlaps Task64"):
        holdout.validate_fixture(fixture, old_fixture, catalog_items)


def test_fixture_rejects_an_invalid_language_label() -> None:
    fixture, old_fixture, catalog_items = _raw_inputs()
    fixture["dishes"][0]["ingredients"][0]["input_language"] = "zh"

    with pytest.raises(holdout.HoldoutFixtureError, match="does not match input_language"):
        holdout.validate_fixture(fixture, old_fixture, catalog_items)


def test_fixture_rejects_insufficient_query_diversity() -> None:
    fixture, old_fixture, catalog_items = _raw_inputs()
    for dish in fixture["dishes"]:
        for ingredient in dish["ingredients"]:
            ingredient["name"] = "egg"
            ingredient["normalized_name"] = "egg"
            ingredient["input_language"] = "en"

    with pytest.raises(holdout.HoldoutFixtureError, match="80 distinct normalized queries"):
        holdout.validate_fixture(fixture, old_fixture, catalog_items)


def test_jev_payload_is_blind_and_uses_only_frozen_context() -> None:
    state = {
        "dish_context": {"name_en": "Apple millet porridge", "name_zh": "苹果小米粥"},
        "semantic_ingredient": {"name": "millet", "normalized_name": "millet"},
        "mapped_game_ingredient": {"item_id": "270", "name_en": "Corn", "name_zh": "玉米"},
    }

    payload = holdout._blind_request_payload(state)
    serialized = json.dumps(payload, ensure_ascii=False).casefold()

    assert set(payload) == {"model", "state", "questions"}
    assert payload["state"] == state
    assert not any(term in serialized for term in ("gold", "acceptable_item_ids", "score", "side", "候选", "方案"))


def _jev_test_pair(
    side: str, query_id: str, selected_id: str
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    dish = {"dish_id": "dish-1", "name_en": "Rice bowl", "name_zh": "米饭碗"}
    ingredient = {"query_id": query_id, "name": "rice", "normalized_name": "rice"}
    mapping = {"mapping_status": "mapped", "is_fallback": False, "selected_id": selected_id}
    return side, dish, ingredient, mapping


def _test_state(selected_id: str) -> dict[str, Any]:
    return {
        "dish_context": {"name_en": "Rice bowl", "name_zh": "米饭碗"},
        "semantic_ingredient": {"name": "rice", "normalized_name": "rice"},
        "mapped_game_ingredient": {"item_id": selected_id, "name_en": "Rice", "name_zh": "米"},
    }


def _write_rows(path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_full_jev_reuses_only_an_exact_completed_state(tmp_path, monkeypatch) -> None:
    state = _test_state("423")
    pairs = [_jev_test_pair("legacy", "q1", "423"), _jev_test_pair("rag", "q1", "423")]
    manifest = {"acceptance_contract_id": holdout.CONTRACT_ID}
    monkeypatch.setattr(holdout, "_run_manifest", lambda _path: manifest)
    monkeypatch.setattr(holdout, "_runtime_inputs", lambda: ({}, None, {}))
    monkeypatch.setattr(holdout, "_ordered_jev_pairs", lambda *_args: pairs)
    monkeypatch.setattr(holdout, "_jev_state", lambda *_args: state)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _write_rows(tmp_path / holdout.LEGACY_RESULT_NAME, [])
    _write_rows(tmp_path / holdout.RAG_RESULT_NAME, [])
    _write_rows(
        tmp_path / holdout.JEV_RESULT_NAME,
        [
            {
                "side": "legacy",
                "query_id": "probe-query",
                "pair_key": "legacy:probe-query",
                "status": "completed",
                "stage": "protocol_probe",
                "provider_call": True,
                "request_state": state,
                "request_state_sha256": holdout._canonical_state_sha256(state),
                "decision": "reasonable",
                "confidence": 0.8,
                "model": holdout.JEV_BASELINE_MODEL,
                "provider": "TypeSafe",
                "usage": {"cost": 0.01},
            }
        ],
    )

    result = holdout.run_full_jev(tmp_path)
    rows = holdout._read_jsonl(tmp_path / holdout.JEV_RESULT_NAME)
    reused = [row for row in rows if row.get("stage") == "same_state_reuse"]

    assert result["provider_call_count"] == 1
    assert len(reused) == 2
    assert all(row["decision"] == "reasonable" for row in reused)
    assert {row["side"] for row in reused} == {"legacy", "rag"}


def test_full_jev_stops_after_returned_model_version_drifts(tmp_path, monkeypatch) -> None:
    pairs = [_jev_test_pair("legacy", "q1", "423"), _jev_test_pair("rag", "q2", "424")]
    states = {"423": _test_state("423"), "424": _test_state("424")}
    manifest = {"acceptance_contract_id": holdout.CONTRACT_ID}
    monkeypatch.setattr(holdout, "_run_manifest", lambda _path: manifest)
    monkeypatch.setattr(holdout, "_runtime_inputs", lambda: ({}, None, {}))
    monkeypatch.setattr(holdout, "_ordered_jev_pairs", lambda *_args: pairs)
    monkeypatch.setattr(holdout, "_jev_state", lambda _d, _i, mapping, _c: states[mapping["selected_id"]])
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-not-a-real-key")
    calls = []

    def call_with_drift(state, api_key):
        calls.append((state, api_key))
        parsed = {
            "decision": "reasonable",
            "confidence": 0.7,
            "probabilities": None,
            "model": "typesafe/jev-1.13-20990917",
            "provider": "TypeSafe",
            "usage": {"cost": 0.001},
        }
        return parsed, {"model": parsed["model"]}, 10.0

    monkeypatch.setattr(holdout.jev_protocol, "call_jev", call_with_drift)
    probe_state = _test_state("probe")
    _write_rows(tmp_path / holdout.LEGACY_RESULT_NAME, [])
    _write_rows(tmp_path / holdout.RAG_RESULT_NAME, [])
    _write_rows(
        tmp_path / holdout.JEV_RESULT_NAME,
        [
            {
                "side": "legacy",
                "query_id": "probe-query",
                "pair_key": "legacy:probe-query",
                "status": "completed",
                "stage": "protocol_probe",
                "provider_call": True,
                "request_state": probe_state,
                "request_state_sha256": holdout._canonical_state_sha256(probe_state),
                "decision": "reasonable",
                "model": holdout.JEV_BASELINE_MODEL,
                "provider": "TypeSafe",
            }
        ],
    )

    result = holdout.run_full_jev(tmp_path)
    rows = holdout._read_jsonl(tmp_path / holdout.JEV_RESULT_NAME)
    after_probe = [row for row in rows if row.get("stage") != "protocol_probe"]

    assert len(calls) == 1
    assert result["stopped_after_version_drift"] is True
    assert after_probe[0]["status"] == "completed"
    assert after_probe[1]["status"] == "not_attempted"
    assert after_probe[1]["reason"] == "stopped_after_jev_model_version_drift"


def test_side_metrics_keep_fixed_dish_denominator_and_use_mapper_candidates() -> None:
    fixture = {"dishes": []}
    mapping_by_id: dict[str, dict[str, Any]] = {}
    jev_by_pair: dict[str, dict[str, Any]] = {}
    for dish_index in range(2):
        dish_id = f"dish-{dish_index}"
        dish = {
            "dish_id": dish_id,
            "name_en": f"Dish {dish_index}",
            "name_zh": f"菜品 {dish_index}",
            "stratum": "direct_name",
            "ingredients": [],
        }
        for ingredient_index in range(3):
            query_id = f"{dish_id}-q{ingredient_index}"
            ingredient = {
                "query_id": query_id,
                "name": "rice",
                "input_language": "en",
                "acceptable_item_ids": ["423"],
            }
            dish["ingredients"].append(ingredient)
            mapping_by_id[query_id] = {
                "mapping_status": "mapped",
                "is_fallback": dish_index == 1 and ingredient_index == 0,
                "selected_id": "423",
                "mapper_candidate_ids": ["423"],
            }
            jev_by_pair[holdout._pair_key("legacy", query_id)] = {
                "status": "not_attempted" if dish_index == 1 and ingredient_index == 0 else "completed",
                "decision": None if dish_index == 1 and ingredient_index == 0 else "reasonable",
            }
        fixture["dishes"].append(dish)

    metrics, dish_pass, per_item = holdout._side_metrics(
        fixture, mapping_by_id, jev_by_pair, side="legacy"
    )

    assert metrics["dish_all_reasonable_rate"]["numerator"] == 1
    assert metrics["dish_all_reasonable_rate"]["denominator"] == 2
    assert metrics["reasonable_coverage_fixed_query_set"]["denominator"] == 6
    assert metrics["gold_recall_at_5"]["mean"] == 1.0
    assert dish_pass == {"dish-0": True, "dish-1": False}
    assert len(per_item) == 6


def test_legacy_mapping_side_uses_real_production_candidates(tmp_path, monkeypatch) -> None:
    frozen_fixture = holdout.load_frozen_inputs()["fixture"]
    dish, ingredient = holdout.iter_fixture_queries(frozen_fixture)[0]
    _task64_fixture, catalog, _fixture_sha, _catalog_sha = holdout.jev_protocol.load_frozen_inputs()
    manifest = {"acceptance_contract_id": holdout.CONTRACT_ID}
    monkeypatch.setattr(holdout, "_run_manifest", lambda _path: manifest)
    monkeypatch.setattr(holdout, "_runtime_inputs", lambda: (frozen_fixture, catalog, {}))
    monkeypatch.setattr(holdout, "_verify_historical_unchanged", lambda _before: None)
    monkeypatch.setattr(holdout, "iter_fixture_queries", lambda _fixture: [(dish, ingredient)])
    monkeypatch.setattr(holdout, "EXPECTED_QUERY_COUNT", 1)

    holdout.run_mapping_side("legacy", tmp_path)
    row = holdout._read_jsonl(tmp_path / holdout.LEGACY_RESULT_NAME)[0]
    semantic = SimpleNamespace(
        name=ingredient["name"], normalized_name=ingredient["normalized_name"]
    )
    expected = _build_candidates(
        semantic, catalog, backend=IngredientRetrievalBackend.LEGACY
    )

    assert row["candidate_source"] == "legacy"
    assert row["mapper_candidate_ids"] == [candidate.item_id for candidate in expected]
    assert all(catalog.require(item_id).usable_as_ingredient for item_id in row["mapper_candidate_ids"])


def test_rag_mapping_side_records_candidates_from_the_retriever_seam(tmp_path, monkeypatch) -> None:
    frozen_fixture = holdout.load_frozen_inputs()["fixture"]
    dish, ingredient = holdout.iter_fixture_queries(frozen_fixture)[0]
    _task64_fixture, catalog, _fixture_sha, _catalog_sha = holdout.jev_protocol.load_frozen_inputs()
    candidate = CatalogCandidate(item_id="256", score=0.99)
    calls = []

    class StubRetriever:
        disabled_reason = None

        def retrieve(self, query: str, *, used_item_ids=frozenset()):
            calls.append((query, used_item_ids))
            return [candidate]

    retriever = StubRetriever()
    resource_hashes = {"asset_hashes": {"manifest": "frozen-test-hash"}}
    manifest = {"acceptance_contract_id": holdout.CONTRACT_ID}
    monkeypatch.setattr(holdout, "_run_manifest", lambda _path: manifest)
    monkeypatch.setattr(holdout, "_runtime_inputs", lambda: (frozen_fixture, catalog, {}))
    monkeypatch.setattr(holdout, "_verify_historical_unchanged", lambda _before: None)
    monkeypatch.setattr(holdout, "iter_fixture_queries", lambda _fixture: [(dish, ingredient)])
    monkeypatch.setattr(holdout, "EXPECTED_QUERY_COUNT", 1)
    monkeypatch.setattr(holdout, "IngredientRagRetriever", lambda *_args, **_kwargs: retriever)
    monkeypatch.setattr(
        holdout.previous_comparison,
        "verify_task65_resources",
        lambda _resource_dir: resource_hashes,
    )

    holdout.run_mapping_side("rag", tmp_path)
    row = holdout._read_jsonl(tmp_path / holdout.RAG_RESULT_NAME)[0]

    assert calls == [(ingredient["normalized_name"], frozenset())]
    assert row["candidate_source"] == "rag"
    assert row["retrieval_status"] == "success"
    assert row["rag_candidate_ids"] == [candidate.item_id]
    assert row["mapper_candidate_ids"] == [candidate.item_id]
    assert row["selected_id"] == candidate.item_id
