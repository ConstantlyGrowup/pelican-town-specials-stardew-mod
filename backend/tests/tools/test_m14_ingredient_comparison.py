from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from scripts import compare_ingredient_rag as comparison


def _has_task64_artifacts(output_dir: Path) -> bool:
    return any(
        (output_dir / name).exists() or (output_dir / name).is_symlink()
        for name in comparison.TASK64_ARTIFACT_NAMES
    )


def _fixture() -> dict[str, Any]:
    return {
        "dishes": [
            {
                "dish_id": "dish-a",
                "name_en": "Dish A",
                "name_zh": "菜甲",
                "ingredients": [
                    {"query_id": f"a-{index}", "acceptable_item_ids": [str(index)]}
                    for index in range(1, 4)
                ],
            },
            {
                "dish_id": "dish-b",
                "name_en": "Dish B",
                "name_zh": "菜乙",
                "ingredients": [
                    {"query_id": f"b-{index}", "acceptable_item_ids": [str(index + 3)]}
                    for index in range(1, 4)
                ],
            },
        ]
    }


def _side_rows(*, new: bool) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: dict[str, dict[str, Any]] = {}
    decisions: dict[str, dict[str, Any]] = {}
    for dish_index, dish_id in enumerate(("dish-a", "dish-b")):
        for ingredient_index in range(1, 4):
            query_id = f"{'a' if dish_index == 0 else 'b'}-{ingredient_index}"
            is_last = dish_index == 1 and ingredient_index == 3
            candidates = [] if (new and is_last) else [str(dish_index * 3 + ingredient_index)]
            selected_id = str(dish_index * 3 + ingredient_index)
            rows[query_id] = (
                {
                    "query_id": query_id,
                    "dish_id": dish_id,
                    "mapping_status": "mapped",
                    "is_fallback": is_last,
                    "selected_id": selected_id,
                    "rag_candidate_ids": candidates,
                    "mapper_candidate_ids": [selected_id],
                    "candidate_source": "legacy_error_fallback" if is_last else "rag",
                    "retrieval_status": "error" if is_last else "success",
                }
                if new
                else {
                    "query_id": query_id,
                    "dish_id": dish_id,
                    "status": "mapped",
                    "is_fallback": is_last,
                    "selected_id": selected_id,
                    "candidate_ids": candidates,
                }
            )
            decision = "reasonable"
            if dish_index == 1 and ingredient_index == 2:
                decision = "undecidable"
            decisions[query_id] = {
                "query_id": query_id,
                "status": "completed",
                "decision": decision,
                "model": "typesafe/jev-1.13-20260917",
            }
    return rows, decisions


def test_jev_state_is_blind_and_uses_only_the_mapped_game_item() -> None:
    fixture = _fixture()
    dish = fixture["dishes"][0]
    ingredient = {
        "query_id": "a-1",
        "name": "tomato",
        "normalized_name": "tomato",
        "acceptable_item_ids": ["256"],
    }
    baseline_row = {
        "mapping_status": "mapped",
        "is_fallback": False,
        "selected_id": "256",
    }

    state = comparison.build_jev_state(dish, ingredient, baseline_row, _catalog_stub())
    encoded = str(state).casefold()

    assert set(state) == {"dish_context", "semantic_ingredient", "mapped_game_ingredient"}
    assert "acceptable_item_ids" not in encoded
    assert "old" not in encoded and "new" not in encoded
    assert state["mapped_game_ingredient"]["item_id"] == "256"


def _catalog_stub() -> Any:
    class Item:
        item_id = "256"
        display_name_en = "Tomato"
        display_name_zh = "西红柿"

    class Catalog:
        def require(self, item_id: str) -> Item:
            assert item_id == "256"
            return Item()

    return Catalog()


def test_task64_decision_reuse_requires_exact_state_same_model_and_unambiguous_choice() -> None:
    state = {"dish_context": {"name_en": "Dish", "name_zh": "菜"}}
    completed = {
        "query_id": "old-1",
        "status": "completed",
        "request_state": state,
        "decision": "reasonable",
        "model": "typesafe/jev-1.13-20260917",
    }

    assert comparison.reusable_task64_decision(
        state, [completed], expected_model=completed["model"]
    ) == completed
    assert comparison.reusable_task64_decision(
        state, [completed], expected_model="typesafe/jev-1.13-20260918"
    ) is None
    changed_state = {"dish_context": {"name_en": "Other Dish", "name_zh": "菜"}}
    assert comparison.reusable_task64_decision(
        changed_state, [completed], expected_model=completed["model"]
    ) is None
    conflicting = {**completed, "decision": "unreasonable"}
    assert comparison.reusable_task64_decision(
        state, [completed, conflicting], expected_model=completed["model"]
    ) is None


def test_fixed_dish_denominator_and_degraded_retrieval_are_preserved() -> None:
    fixture = _fixture()
    old_rows, old_decisions = _side_rows(new=False)
    new_rows, new_decisions = _side_rows(new=True)

    result = comparison.compare_metrics(
        fixture,
        old_rows,
        old_decisions,
        new_rows,
        new_decisions,
        baseline_model="typesafe/jev-1.13-20260917",
        new_models={"typesafe/jev-1.13-20260917"},
    )

    assert result["old"]["dish_all_reasonable_rate"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert result["new"]["dish_all_reasonable_rate"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert result["new"]["query_occurrence_count"] == 6
    assert result["new"]["retrieval_degraded_count"] == 1
    assert result["new"]["dish_all_reasonable_rag_attributed_rate"]["numerator"] == 1
    assert result["new"]["gold_recall_at_5"]["mean"] == pytest.approx(5 / 6)
    assert result["paired_dish_transitions"]["unchanged"] == 2
    assert len(result["per_item"]) == 6
    assert result["per_item"][-1]["query_id"] == "b-3"
    assert result["per_item"][-1]["new_gold_recall_at_5"] == 0
    assert result["adoption_gate"]["status"] == "not_met"


def test_legacy_candidates_from_retrieval_failure_do_not_count_as_rag_recall() -> None:
    fixture = _fixture()
    new_rows, new_decisions = _side_rows(new=True)
    failed = new_rows["b-3"]
    failed["rag_candidate_ids"] = []
    failed["mapper_candidate_ids"] = ["6"]
    failed["candidate_source"] = "legacy_error_fallback"
    failed["is_fallback"] = False
    old_rows, old_decisions = _side_rows(new=False)

    result = comparison.compare_metrics(
        fixture,
        old_rows,
        old_decisions,
        new_rows,
        new_decisions,
        baseline_model="typesafe/jev-1.13-20260917",
        new_models={"typesafe/jev-1.13-20260917"},
    )

    assert result["new"]["gold_recall_at_5"]["mean"] == pytest.approx(5 / 6)
    assert result["new"]["gold_hit_at_5"]["numerator"] == 5
    assert result["new"]["legacy_mapped_after_degrade_count"] == 1


def test_version_drift_blocks_comparison_and_adoption_gate() -> None:
    fixture = _fixture()
    old_rows, old_decisions = _side_rows(new=False)
    new_rows, new_decisions = _side_rows(new=True)

    result = comparison.compare_metrics(
        fixture,
        old_rows,
        old_decisions,
        new_rows,
        new_decisions,
        baseline_model="typesafe/jev-1.13-20260917",
        new_models={"typesafe/jev-1.13-20260918"},
    )

    assert result["model_comparable"] is False
    assert result["paired_dish_transitions"]["status"] == "not_comparable_model_version"
    assert result["adoption_gate"]["status"] == "not_evaluable"


def test_task64_raw_outputs_match_frozen_input_hashes_and_historical_baseline() -> None:
    if not _has_task64_artifacts(comparison.TASK64_OUTPUT_DIR):
        pytest.skip("Task64 ignored historical artifacts are absent in this checkout")

    verified = comparison.verify_task64_artifacts()

    assert verified["fixture_sha256"] == comparison.evaluation.EXPECTED_FIXTURE_SHA256
    assert verified["catalog_sha256"] == comparison.evaluation.EXPECTED_CATALOG_SHA256
    assert verified["model_version"] == "typesafe/jev-1.13-20260917"
    assert len(verified["baseline_by_id"]) == 72
    assert len(verified["jev_by_id"]) == 71
    assert set(verified["artifact_hashes"]) == set(comparison.TASK64_ARTIFACT_NAMES)
    assert verified["metrics"]["jev"]["dish_all_reasonable_rate"]["numerator"] == 14
    assert verified["metrics"]["jev"]["dish_all_reasonable_rate"]["denominator"] == 24


def test_task64_audit_guard_treats_all_artifacts_absent_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "exists", lambda _path: False)
    monkeypatch.setattr(Path, "is_symlink", lambda _path: False)

    assert _has_task64_artifacts(Path("ignored-output-dir")) is False


def test_task64_audit_guard_treats_partial_artifact_set_as_present(monkeypatch: pytest.MonkeyPatch) -> None:
    present_name = comparison.TASK64_ARTIFACT_NAMES[0]
    monkeypatch.setattr(Path, "exists", lambda path: path.name == present_name)
    monkeypatch.setattr(Path, "is_symlink", lambda _path: False)

    assert _has_task64_artifacts(Path("ignored-output-dir")) is True


def test_task65_resource_gate_uses_reported_limits_and_measurements() -> None:
    gate = comparison.evaluate_task65_resource_gate()

    assert gate["all_passed"] is True
    assert all(gate["checks"].values())
    assert gate["observed"]["added_distribution_bytes"] == 159_489_831


def test_jev_cost_summary_excludes_historical_task64_reuse_from_task66_cost() -> None:
    rows = [
        {
            "status": "completed",
            "stage": "protocol_probe",
            "decision": "reasonable",
            "model": "typesafe/jev-1.13-20260917",
            "usage": {"cost": 0.2},
        },
        {
            "status": "completed",
            "stage": "full",
            "decision": "unreasonable",
            "model": "typesafe/jev-1.13-20260917",
            "usage": {"cost": 0.3},
        },
        {
            "status": "completed",
            "stage": "task64_state_reuse",
            "decision": "reasonable",
            "model": "typesafe/jev-1.13-20260917",
            "usage": {"cost": 0.4},
        },
        {"status": "failed", "stage": "full"},
    ]

    summary = comparison._jev_run_summary(rows)

    assert summary["provider_call_count"] == 3
    assert summary["provider_success_count"] == 2
    assert summary["provider_failure_count"] == 1
    assert summary["provider_cost_usd"] == pytest.approx(0.5)
    assert summary["task64_state_reuse_count"] == 1
    assert summary["task64_reused_historical_cost_usd"] == pytest.approx(0.4)
