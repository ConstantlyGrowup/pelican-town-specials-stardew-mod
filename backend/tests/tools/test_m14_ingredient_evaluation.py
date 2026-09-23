from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path
from typing import Any, Self

import pytest
from scripts import evaluate_ingredients as evaluation


def _baseline(tmp_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    summary = evaluation.run_baseline(tmp_path)
    rows = evaluation._read_jsonl(tmp_path / "baseline.jsonl")
    return summary, {row["query_id"]: row for row in rows}


def test_frozen_fixture_covers_minimums_languages_aliases_and_catalog_ids() -> None:
    fixture, catalog, fixture_sha, catalog_sha = evaluation.load_frozen_inputs()
    queries = evaluation.iter_fixture_queries(fixture)
    assert len(fixture["dishes"]) == 24
    assert len(queries) == 72
    assert len({ingredient["normalized_name"] for _, ingredient in queries}) >= 40
    assert fixture_sha == evaluation.EXPECTED_FIXTURE_SHA256
    assert catalog_sha == evaluation.EXPECTED_CATALOG_SHA256
    assert catalog.version == "stardew-1.6.15-v1"

    query_names = [ingredient["normalized_name"].casefold() for _, ingredient in queries]
    assert any(any("\u4e00" <= character <= "\u9fff" for character in name) for name in query_names)
    assert any(name.isascii() for name in query_names)
    assert {"cherry tomatoes", "button mushroom", "green onion", "aubergine", "white rice"} <= set(query_names)
    for _, ingredient in queries:
        assert all(catalog.require(item_id).usable_as_ingredient for item_id in ingredient["acceptable_item_ids"])


def test_fixture_lf_checkout_and_staged_blob_keep_frozen_sha() -> None:
    fixture_path = evaluation.FIXTURE_PATH
    relative_path = fixture_path.relative_to(evaluation.REPO_ROOT).as_posix()
    checkout_bytes = fixture_path.read_bytes()
    assert b"\r" not in checkout_bytes
    assert hashlib.sha256(checkout_bytes).hexdigest().upper() == evaluation.EXPECTED_FIXTURE_SHA256

    attributes = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", relative_path],
        cwd=evaluation.REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    assert f"{relative_path}: text: set" in attributes
    assert f"{relative_path}: eol: lf" in attributes

    staged_blob = subprocess.run(
        ["git", "show", f":{relative_path}"],
        cwd=evaluation.REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if staged_blob.returncode != 0:
        pytest.skip("fixture is not staged yet; committed checkout is checked in CI")
    staged_sha = hashlib.sha256(staged_blob.stdout).hexdigest().upper()
    assert staged_sha == evaluation.EXPECTED_FIXTURE_SHA256

    checkout_blob = subprocess.run(
        ["git", "cat-file", "--filters", f"--path={relative_path}", f":{relative_path}"],
        cwd=evaluation.REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    assert b"\r" not in checkout_blob
    assert hashlib.sha256(checkout_blob).hexdigest().upper() == evaluation.EXPECTED_FIXTURE_SHA256

    cleaned_blob_id = subprocess.run(
        ["git", "hash-object", "--path", relative_path, str(fixture_path)],
        cwd=evaluation.REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    staged_blob_id = subprocess.run(
        ["git", "rev-parse", f":{relative_path}"],
        cwd=evaluation.REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    assert cleaned_blob_id == staged_blob_id


def test_baseline_reproduces_known_old_chain_confusions_and_fallback(tmp_path: Path) -> None:
    summary, rows = _baseline(tmp_path)
    assert summary["dish_count"] == 24
    assert summary["query_count"] == 72
    assert rows["d02-i01"]["selected_id"] == "209"  # Carp Surprise, not Carp.
    assert rows["d02-i02"]["selected_id"] == "232"  # Rice Pudding, not Rice.
    assert rows["d02-i03"]["selected_id"] == "153"  # Green Algae, not Spring Onion.
    assert rows["d03-i01"]["selected_id"] == "638"  # Cherry, not Tomato.
    assert rows["d03-i02"]["selected_id"] == "205"  # Fried Mushroom, not raw mushroom.
    assert rows["d09-i01"]["is_fallback"] is True  # Aubergine is a valid Gold alias, but old search misses it.
    assert all(len(row["candidate_ids"]) <= 5 for row in rows.values())
    assert all(
        isinstance(candidate["score"], float)
        for row in rows.values()
        for candidate in row["candidates"]
    )


def test_jev_state_contains_candidate_context_without_gold_or_scheme_label(tmp_path: Path) -> None:
    _, rows = _baseline(tmp_path)
    fixture, catalog, _, _ = evaluation.load_frozen_inputs()
    dish, ingredient = next(
        (dish, ingredient)
        for dish, ingredient in evaluation.iter_fixture_queries(fixture)
        if ingredient["query_id"] == "d02-i01"
    )
    state = evaluation.build_jev_state(dish, ingredient, rows["d02-i01"], catalog)
    encoded = json.dumps(state, ensure_ascii=False).casefold()
    assert set(state) == {"dish_context", "semantic_ingredient", "mapped_game_ingredient"}
    assert "acceptable_item_ids" not in encoded
    assert "gold_note" not in encoded
    assert '"old"' not in encoded and '"new"' not in encoded
    assert state["mapped_game_ingredient"]["item_id"] == "209"
    request = evaluation.build_decisions_request(state)
    assert request["model"] == "typesafe/jev-1.13"
    assert request["questions"][evaluation.QUESTION_ID]["type"] == "choice"
    assert set(request["questions"][evaluation.QUESTION_ID]["criteria"]) == set(evaluation.DECISIONS)


def test_decisions_parser_accepts_documented_typed_choice_and_rejects_chat_shape() -> None:
    payload = {
        "answers": {
            evaluation.QUESTION_ID: {
                "type": "choice",
                "choice": "unreasonable",
                "confidence": 0.93,
                "probabilities": {"reasonable": 0.02, "unreasonable": 0.93, "undecidable": 0.05},
            }
        },
        "model": "typesafe/jev-1.13-20260917",
        "provider": "TypeSafe",
        "usage": {"cost": 0.00001, "inputTokens": 88, "outputTokens": 8},
    }
    parsed = evaluation.parse_decisions_response(payload)
    assert parsed["decision"] == "unreasonable"
    assert parsed["confidence"] == 0.93
    assert parsed["provider"] == "TypeSafe"
    with pytest.raises(evaluation.EvaluationError, match="typed answers"):
        evaluation.parse_decisions_response({"choices": [{"message": {"content": "{}"}}]})


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"model": "openai/gpt-example"}, "model"),
        ({"answers": {evaluation.QUESTION_ID: {"type": "choice", "choice": "maybe", "confidence": 0.8}}}, "unknown option"),
        ({"answers": {evaluation.QUESTION_ID: {"type": "choice", "choice": "reasonable"}}}, "confidence"),
        ({"provider": "Other"}, "provider"),
    ],
)
def test_decisions_parser_fails_closed_on_protocol_drift(
    changes: dict[str, Any], message: str
) -> None:
    payload: dict[str, Any] = {
        "answers": {
            evaluation.QUESTION_ID: {
                "type": "choice",
                "choice": "reasonable",
                "confidence": 0.9,
                "probabilities": {"reasonable": 0.9, "unreasonable": 0.05, "undecidable": 0.05},
            }
        },
        "model": "typesafe/jev-1.13-20260917",
        "provider": "TypeSafe",
    }
    payload.update(changes)
    with pytest.raises(evaluation.EvaluationError, match=message):
        evaluation.parse_decisions_response(payload)


def test_api_adapter_uses_decisions_endpoint_and_typed_request_without_gold() -> None:
    payload = {
        "answers": {
            evaluation.QUESTION_ID: {"type": "choice", "choice": "reasonable", "confidence": 0.88}
        },
        "model": "typesafe/jev-1.13-20260917",
        "provider": "TypeSafe",
    }
    captured: dict[str, Any] = {}

    class FakeResponse(io.BytesIO):
        status = 200

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

    def opener(request: Any, *, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    state = {
        "dish_context": {"name_en": "Example", "name_zh": "示例"},
        "semantic_ingredient": {"name": "tomato", "normalized_name": "tomato"},
        "mapped_game_ingredient": {"item_id": "256", "name_en": "Tomato", "name_zh": "西红柿"},
    }
    parsed, raw, elapsed = evaluation.call_jev(state, "test-secret", opener=opener)
    assert captured["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert captured["body"]["model"] == evaluation.MODEL
    assert captured["body"]["state"] == state
    assert captured["body"]["questions"][evaluation.QUESTION_ID]["type"] == "choice"
    assert captured["auth"] == "Bearer test-secret"
    assert "acceptable_item_ids" not in json.dumps(captured["body"])
    assert parsed["decision"] == "reasonable"
    assert raw == payload
    assert elapsed >= 0


def test_metrics_exclude_fallback_and_undecidable_from_primary_denominator(tmp_path: Path) -> None:
    _, baseline = _baseline(tmp_path)
    fixture, _, fixture_sha, catalog_sha = evaluation.load_frozen_inputs()
    jev_records = []
    for index, row in enumerate(baseline.values()):
        if row["is_fallback"]:
            continue
        decision = "undecidable" if index == 0 else "reasonable"
        jev_records.append(
            {
                "query_id": row["query_id"],
                "status": "completed",
                "decision": decision,
                "confidence": 0.7,
                "fixture_sha256": fixture_sha,
                "catalog_sha256": catalog_sha,
            }
        )
    evaluation._write_jsonl(tmp_path / "jev.jsonl", jev_records)
    report = evaluation.build_metrics(tmp_path)
    expected_fallbacks = sum(row["is_fallback"] for row in baseline.values())
    expected_determinate = 72 - expected_fallbacks - 1
    assert report["query_occurrence_count"] == 72
    assert report["baseline"]["fallback_count_excluded_from_accuracy"] == expected_fallbacks
    assert report["jev"]["undecidable_count"] == 1
    assert report["jev"]["nonfallback_reasonable_rate"]["denominator"] == expected_determinate
    assert report["jev"]["reasonable_coverage_of_fixed_query_set"]["denominator"] == 72
    cross_tab = report["baseline"]["jev_choice_by_gold_selected_id_cross_tab"]
    assert sum(sum(bucket.values()) for bucket in cross_tab.values()) == expected_determinate
    assert report["baseline"]["jev_gold_disagreement_count"] == len(
        report["baseline"]["jev_gold_disagreements"]
    )
    assert all(
        set(row) == {"query_id", "dish_id", "jev_choice", "confidence", "selected_id_in_gold"}
        for row in report["baseline"]["jev_gold_disagreements"]
    )
    assert len(fixture["dishes"]) == 24
