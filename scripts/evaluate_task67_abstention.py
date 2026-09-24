"""Reproduce the frozen Task67 positive-set RAG mapping comparison locally.

The runner has no Provider/API path. It runs the 24-dish Task64 set and the
96-dish Task66.1 set through the explicit retrieval seam, preserves every item
row, and writes only to a new ignored output directory. Negative-case execution
is intentionally supplied as explicit query records by the parent after code
freeze so the implementer does not inspect the reserved challenge texts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "backend" / "src")]

from pelican_town_specials.catalog.mapping import map_ingredient
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation import orchestrator
from pelican_town_specials.generation.orchestrator import (
    IngredientRetrievalBackend,
    _build_candidates,
)
from pelican_town_specials.ingredient_rag import (
    IngredientRagNoMatch,
    IngredientRagRetriever,
    IngredientRagUnavailable,
)

from scripts import compare_ingredient_rag as task66
from scripts import evaluate_ingredient_holdout as task66_1
from scripts import evaluate_ingredients as task64

CONTRACT_ID = "m14-task67-rag-abstention-v2"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "m14-task67-positive"
RESULTS_NAME = "positive_results.jsonl"
METRICS_NAME = "positive_metrics.json"
MANIFEST_NAME = "positive_manifest.json"
TASK66_1_OUTPUT_DIR = REPO_ROOT / "output" / "m14-task66-1"


class Task67EvaluationError(RuntimeError):
    """Raised when a frozen input or prior result cannot be reproduced."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Task67EvaluationError(f"missing local evaluation artifact: {path.name}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Task67EvaluationError(
                f"invalid JSONL artifact row: {path.name}:{line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise Task67EvaluationError(f"invalid JSONL object: {path.name}:{line_number}")
        rows.append(row)
    return rows


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_jsonl_exclusive(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _candidate_detail(candidate: Any, catalog: Any) -> dict[str, Any]:
    item = catalog.require(candidate.item_id)
    return {
        "item_id": candidate.item_id,
        "rank_score": float(candidate.score),
        "name_en": item.display_name_en,
        "name_zh": item.display_name_zh,
        "type": item.type,
        "category": item.category,
    }


class _ObservedRetriever:
    def __init__(self, retriever: IngredientRagRetriever) -> None:
        self.retriever = retriever
        self.status = "not_called"
        self.error_code: str | None = None
        self.semantic_family: str | None = None
        self.evidence: Any | None = None
        self.elapsed_ms: float | None = None

    def retrieve(self, query: str, *, used_item_ids: frozenset[str] = frozenset()):
        started = time.perf_counter()
        try:
            self.evidence = self.retriever.retrieve_with_evidence(
                query, used_item_ids=used_item_ids
            )
        except IngredientRagNoMatch as exc:
            self.status = "no_match"
            self.error_code = exc.reason_code
            self.semantic_family = exc.semantic_family
            self.evidence = exc.evidence
            raise
        except IngredientRagUnavailable as exc:
            self.status = "error"
            self.error_code = exc.reason_code
            raise
        except Exception:
            self.status = "error"
            self.error_code = "rag_query_failed"
            raise
        else:
            self.status = "success" if self.evidence.candidates else "empty"
            self.error_code = None
            return list(self.evidence.candidates)
        finally:
            self.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)


def _evidence_detail(evidence: Any | None, catalog: Any) -> dict[str, Any] | None:
    if evidence is None:
        return None
    semantic_hits = []
    for item_id, cosine in evidence.semantic_hits:
        item = catalog.require(item_id)
        semantic_hits.append(
            {
                "item_id": item_id,
                "cosine_similarity": float(cosine),
                "name_en": item.display_name_en,
                "name_zh": item.display_name_zh,
                "type": item.type,
                "category": item.category,
            }
        )
    return {
        "semantic_top5": semantic_hits,
        "lexical_item_ids": list(evidence.lexical_item_ids),
        "exact_item_ids": list(evidence.exact_item_ids),
        "ranked_candidates_before_semantic_verification": [
            _candidate_detail(candidate, catalog) for candidate in evidence.candidates
        ],
    }


def _historical_hashes() -> dict[str, str]:
    paths = [
        task64.DEFAULT_OUTPUT_DIR / name
        for name in task66.TASK64_ARTIFACT_NAMES
    ] + [
        task66.DEFAULT_OUTPUT_DIR / name
        for name in ("manifest.json", "rag_results.jsonl", "jev.jsonl", "metrics.json")
    ] + [
        TASK66_1_OUTPUT_DIR / name
        for name in ("manifest.json", "legacy_results.jsonl", "rag_results.jsonl", "jev.jsonl", "metrics.json")
    ]
    result: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            raise Task67EvaluationError(f"historical Task64/66 artifact is missing: {path.name}")
        result[path.relative_to(REPO_ROOT).as_posix()] = _sha256_file(path)
    return result


def _verify_inputs() -> dict[str, Any]:
    task64_data = task64.load_frozen_inputs()
    task64_artifacts = task66.verify_task64_artifacts()
    task66_manifest = task66.verify_task66_run_inputs(
        task66.DEFAULT_OUTPUT_DIR, task64=task64_artifacts
    )
    task66_1_data = task66_1.load_frozen_inputs()
    holdout_fixture = task66_1_data["fixture"]
    holdout_queries = task66_1.iter_fixture_queries(holdout_fixture)
    if len(holdout_queries) != 288:
        raise Task67EvaluationError("Task66.1 frozen positive fixture must contain 288 rows")
    prior_manifest = task66_1._read_json(TASK66_1_OUTPUT_DIR / "manifest.json")
    historical = task66_1._historical_artifact_hashes()
    flat_historical = {
        f"{task}/{name}": digest
        for task, artifact_map in historical.items()
        for name, digest in artifact_map.items()
    }
    if prior_manifest.get("historical_artifact_hashes") != flat_historical:
        raise Task67EvaluationError("Task66.1 historical artifact hashes do not match")
    task66_1_rows: dict[str, dict[str, dict[str, Any]]] = {}
    for side in ("legacy", "rag"):
        rows = _read_jsonl(TASK66_1_OUTPUT_DIR / f"{side}_results.jsonl")
        expected_ids = {ingredient["query_id"] for _, ingredient in holdout_queries}
        if len(rows) != 288 or {row.get("query_id") for row in rows} != expected_ids:
            raise Task67EvaluationError(f"Task66.1 {side} rows differ from frozen input IDs")
        expected_hash = prior_manifest.get(f"{side}_run", {}).get("result_sha256")
        if expected_hash != _sha256_file(TASK66_1_OUTPUT_DIR / f"{side}_results.jsonl"):
            raise Task67EvaluationError(f"Task66.1 {side} artifact hash differs from manifest")
        task66_1_rows[side] = {row["query_id"]: row for row in rows}
    return {
        "task64_fixture": task64_data[0],
        "catalog": task64_data[1],
        "task64_fixture_sha256": task64_data[2],
        "catalog_sha256": task64_data[3],
        "task64_artifacts": task64_artifacts,
        "task66_manifest": task66_manifest,
        "task66_1_fixture": holdout_fixture,
        "task66_1_fixture_sha256": task66_1_data["fixture_sha256"],
        "task66_1_rows": task66_1_rows,
        "historical_hashes": _historical_hashes(),
    }


def _historical_row(row: dict[str, Any], side: str) -> dict[str, Any]:
    if "mapping_status" in row:
        mapping_status = row.get("mapping_status")
        selected_id = row.get("selected_id")
        is_fallback = bool(row.get("is_fallback"))
        candidate_ids = (
            row.get("rag_candidate_ids", [])
            if side == "rag" and row.get("candidate_source") == "rag"
            else row.get("mapper_candidate_ids", [])
        )
        latency = row.get("total_elapsed_ms")
    else:
        mapping_status = row.get("status")
        selected_id = row.get("selected_id")
        is_fallback = bool(row.get("is_fallback"))
        candidate_ids = row.get("candidate_ids", [])
        latency = row.get("elapsed_ms")
    return {
        "mapping_status": "mapped" if mapping_status == "mapped" else "failed",
        "selected_id": selected_id,
        "is_fallback": is_fallback,
        "candidate_ids": list(candidate_ids) if isinstance(candidate_ids, list) else [],
        "elapsed_ms": float(latency) if isinstance(latency, (int, float)) else None,
    }


def _score_side(
    fixture_pairs: list[tuple[str, dict[str, Any], dict[str, Any]]],
    mappings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_dish: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    item_gold_hits = candidate_gold_hits = fallback_count = failure_count = 0
    latencies: list[float] = []
    for _set_name, dish, ingredient in fixture_pairs:
        row = mappings[ingredient["query_id"]]
        gold_ids = set(ingredient["acceptable_item_ids"])
        candidate_gold = bool(set(row.get("candidate_ids", [])) & gold_ids)
        selected_gold = (
            row.get("mapping_status") == "mapped"
            and not row.get("is_fallback")
            and row.get("selected_id") in gold_ids
        )
        row["gold_candidate_hit"] = candidate_gold
        row["selected_gold_hit"] = selected_gold
        item_gold_hits += selected_gold
        candidate_gold_hits += candidate_gold
        fallback_count += row.get("mapping_status") == "mapped" and row.get("is_fallback", False)
        failure_count += row.get("mapping_status") != "mapped"
        if isinstance(row.get("elapsed_ms"), (int, float)):
            latencies.append(float(row["elapsed_ms"]))
        by_dish[dish["dish_id"]].append((dish, row))
    dish_passes = {
        dish_id: len(rows) == 3 and all(
            row["mapping_status"] == "mapped"
            and not row.get("is_fallback", False)
            and row.get("selected_gold_hit", False)
            for _dish, row in rows
        )
        for dish_id, rows in by_dish.items()
    }
    query_count = len(fixture_pairs)
    dish_count = len(by_dish)
    ordered_latencies = sorted(latencies)
    p95 = ordered_latencies[max(0, int(0.95 * len(ordered_latencies) + 0.999999) - 1)] if ordered_latencies else None
    return {
        "dish_count": dish_count,
        "query_occurrence_count": query_count,
        "mapping_failure_count": failure_count,
        "catalog_fallback_count": fallback_count,
        "selected_gold_hit": {
            "numerator": item_gold_hits,
            "denominator": query_count,
            "value": item_gold_hits / query_count if query_count else None,
        },
        "candidate_gold_recall_at_5": {
            "numerator": candidate_gold_hits,
            "denominator": query_count,
            "value": candidate_gold_hits / query_count if query_count else None,
        },
        "dish_all_gold": {
            "numerator": sum(dish_passes.values()),
            "denominator": dish_count,
            "value": sum(dish_passes.values()) / dish_count if dish_count else None,
        },
        "elapsed_ms": {
            "count": len(latencies),
            "median": statistics.median(latencies) if latencies else None,
            "p95": p95,
            "max": max(latencies) if latencies else None,
        },
    }


def _read_negative_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(path)
    if any(
        not isinstance(row.get("query_id"), str)
        or not isinstance(row.get("query"), str)
        or not row["query"].strip()
        for row in rows
    ):
        raise Task67EvaluationError(
            "negative JSONL rows require non-empty string query_id and query fields"
        )
    if len({row["query_id"] for row in rows}) != len(rows):
        raise Task67EvaluationError("negative JSONL query IDs must be unique")
    return rows


def run_negative_queries(
    cases: list[dict[str, Any]],
    catalog: Any,
    retriever: IngredientRagRetriever,
) -> list[dict[str, Any]]:
    """Run caller-supplied negatives through the production RAG-to-mapper seam."""
    observed = _ObservedRetriever(retriever)
    dynamic_orchestrator = cast(Any, orchestrator)
    original_getter = dynamic_orchestrator._get_default_ingredient_rag_retriever
    dynamic_orchestrator._get_default_ingredient_rag_retriever = lambda _catalog: observed
    rows: list[dict[str, Any]] = []
    try:
        for case in cases:
            query_id = case["query_id"]
            query = case["query"]
            semantic = SimpleNamespace(name=query, normalized_name=query)
            observed.status = "not_called"
            observed.error_code = None
            observed.semantic_family = None
            observed.evidence = None
            started = time.perf_counter()
            try:
                candidates = _build_candidates(
                    semantic,
                    catalog,
                    backend=IngredientRetrievalBackend.RAG,
                )
                mapping_error = None
            except (AppError, TypeError, ValueError) as exc:
                candidates = []
                mapping_error = exc
            candidate_elapsed = round((time.perf_counter() - started) * 1000, 3)
            mapped = None
            if mapping_error is None:
                try:
                    mapped = map_ingredient(semantic, candidates, catalog, language=Language.EN_US)
                except (AppError, TypeError, ValueError) as exc:
                    mapping_error = exc
            item = catalog.require(mapped.item_id) if mapped is not None else None
            is_fallback = bool(
                mapped is not None
                and mapped.mapping_reason.startswith(task64.FALLBACK_PREFIX)
            )
            rows.append(
                {
                    "query_id": query_id,
                    "query": query,
                    "retrieval_status": observed.status,
                    "retrieval_reason_code": observed.error_code,
                    "semantic_family": observed.semantic_family,
                    "retrieval_evidence": _evidence_detail(observed.evidence, catalog),
                    "mapper_candidate_ids": [candidate.item_id for candidate in candidates],
                    "mapping_status": "mapped" if mapped is not None else "failed",
                    "selected_id": mapped.item_id if mapped is not None else None,
                    "selected_name_en": item.display_name_en if item else None,
                    "selected_name_zh": item.display_name_zh if item else None,
                    "mapping_reason": mapped.mapping_reason if mapped else None,
                    "is_fallback": is_fallback,
                    "expected_fallback": bool(case.get("expected_fallback", True)),
                    "fallback_correct": is_fallback if case.get("expected_fallback", True) else None,
                    "mapping_error_type": type(mapping_error).__name__ if mapping_error else None,
                    "mapping_error_code": getattr(mapping_error, "code", None),
                    "elapsed_ms": round(candidate_elapsed, 3),
                }
            )
    finally:
        dynamic_orchestrator._get_default_ingredient_rag_retriever = original_getter
    return rows


def run_positive_evaluation(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    negative_jsonl: Path | None = None,
) -> dict[str, Any]:
    """Run current explicit RAG on 120 fixed dishes and retain per-item evidence."""
    output_dir = output_dir.resolve()
    if any(
        (output_dir / name).exists()
        for name in (RESULTS_NAME, METRICS_NAME, MANIFEST_NAME, "negative_results.jsonl")
    ):
        raise Task67EvaluationError("Task67 output already exists; refusing to overwrite")
    inputs = _verify_inputs()
    catalog = inputs["catalog"]
    resources = task66.verify_task65_resources(task66.TASK65_RESOURCE_DIR)
    current_retriever = IngredientRagRetriever(catalog, resource_dir=task66.TASK65_RESOURCE_DIR)
    observed = _ObservedRetriever(current_retriever)
    previous: dict[str, dict[str, dict[str, Any]]] = {"legacy": {}, "rag": {}}
    for row in task66._read_jsonl(task64.DEFAULT_OUTPUT_DIR / "baseline.jsonl"):
        previous["legacy"][row["query_id"]] = _historical_row(row, "legacy")
    for row in task66._read_jsonl(task66.DEFAULT_OUTPUT_DIR / "rag_results.jsonl"):
        previous["rag"][row["query_id"]] = _historical_row(row, "rag")
    for side, rows in inputs["task66_1_rows"].items():
        previous[side].update(
            {
                query_id: _historical_row(row, side)
                for query_id, row in rows.items()
            }
        )

    fixture_pairs: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    fixture_pairs.extend(
        ("task64", dish, ingredient)
        for dish, ingredient in task64.iter_fixture_queries(inputs["task64_fixture"])
    )
    fixture_pairs.extend(
        ("task66_1", dish, ingredient)
        for dish, ingredient in task66_1.iter_fixture_queries(inputs["task66_1_fixture"])
    )
    if len(fixture_pairs) != 360:
        raise Task67EvaluationError("positive set must contain exactly 360 item occurrences")
    fixture_ids = {ingredient["query_id"] for _, _, ingredient in fixture_pairs}
    if len(fixture_ids) != 360:
        raise Task67EvaluationError("positive set query IDs are not unique")
    if set(previous["legacy"]) != fixture_ids or set(previous["rag"]) != fixture_ids:
        raise Task67EvaluationError("historical mapping rows do not cover the fixed positive set")

    baseline_mappings = {
        side: {query_id: dict(row) for query_id, row in rows.items()}
        for side, rows in previous.items()
    }
    current_rows: list[dict[str, Any]] = []
    current_by_id: dict[str, dict[str, Any]] = {}
    used_by_dish: dict[str, set[str]] = defaultdict(set)
    dynamic_orchestrator = cast(Any, orchestrator)
    original_getter = dynamic_orchestrator._get_default_ingredient_rag_retriever
    dynamic_orchestrator._get_default_ingredient_rag_retriever = lambda _catalog: observed
    started_at = datetime.now(UTC).isoformat()
    try:
        for set_name, dish, ingredient in fixture_pairs:
            query_id = ingredient["query_id"]
            used = frozenset(used_by_dish[dish["dish_id"]])
            semantic = SimpleNamespace(
                name=ingredient["name"], normalized_name=ingredient["normalized_name"]
            )
            observed.status = "not_called"
            observed.error_code = None
            observed.semantic_family = None
            observed.evidence = None
            candidate_started = time.perf_counter()
            try:
                candidates = _build_candidates(
                    semantic,
                    catalog,
                    used_item_ids=used,
                    backend=IngredientRetrievalBackend.RAG,
                )
                mapping_error = None
            except (AppError, TypeError, ValueError) as exc:
                candidates = []
                mapping_error = exc
            retrieval_elapsed = round((time.perf_counter() - candidate_started) * 1000, 3)
            mapping_started = time.perf_counter()
            mapped = None
            if mapping_error is None:
                try:
                    mapped = map_ingredient(
                        semantic, candidates, catalog, used_item_ids=used, language=Language.EN_US
                    )
                except (AppError, TypeError, ValueError) as exc:
                    mapping_error = exc
            mapping_elapsed = round((time.perf_counter() - mapping_started) * 1000, 3)
            item = catalog.require(mapped.item_id) if mapped is not None else None
            is_fallback = bool(
                mapped is not None
                and mapped.mapping_reason.startswith(task64.FALLBACK_PREFIX)
            )
            candidate_ids = [candidate.item_id for candidate in candidates]
            gold_ids = ingredient["acceptable_item_ids"]
            record: dict[str, Any] = {
                "dataset": set_name,
                "query_id": query_id,
                "dish_id": dish["dish_id"],
                "dish_name_en": dish["name_en"],
                "dish_name_zh": dish["name_zh"],
                "query": ingredient["name"],
                "normalized_query": ingredient["normalized_name"],
                "gold_item_ids": gold_ids,
                "historical_legacy": baseline_mappings["legacy"][query_id],
                "historical_rag": baseline_mappings["rag"][query_id],
                "retrieval_status": observed.status,
                "retrieval_reason_code": observed.error_code,
                "semantic_family": observed.semantic_family,
                "candidate_source": (
                    "rag"
                    if observed.status == "success"
                    else "semantic_no_match_fallback"
                    if observed.status == "no_match"
                    else "legacy_error_fallback"
                    if observed.status == "error"
                    else "legacy_empty_result_fallback"
                    if observed.status == "empty"
                    else "not_retrieved"
                ),
                "retrieval_evidence": _evidence_detail(observed.evidence, catalog),
                "mapper_candidates": [
                    _candidate_detail(candidate, catalog) for candidate in candidates
                ],
                "mapping_status": "mapped" if mapped is not None else "failed",
                "selected_id": mapped.item_id if mapped is not None else None,
                "selected_name_en": item.display_name_en if item else None,
                "selected_name_zh": item.display_name_zh if item else None,
                "mapping_reason": mapped.mapping_reason if mapped else None,
                "is_fallback": is_fallback,
                "selected_gold_hit": bool(
                    mapped is not None and not is_fallback and mapped.item_id in gold_ids
                ),
                "gold_candidate_hit": bool(set(candidate_ids) & set(gold_ids)),
                "mapping_error_type": type(mapping_error).__name__ if mapping_error else None,
                "mapping_error_code": getattr(mapping_error, "code", None),
                "retrieval_elapsed_ms": observed.elapsed_ms,
                "candidate_selection_elapsed_ms": retrieval_elapsed,
                "mapping_elapsed_ms": mapping_elapsed,
                "total_elapsed_ms": round(retrieval_elapsed + mapping_elapsed, 3),
                "used_item_ids_before": sorted(used),
            }
            if mapped is not None:
                used_by_dish[dish["dish_id"]].add(mapped.item_id)
            current_rows.append(record)
            current_by_id[query_id] = {
                "mapping_status": record["mapping_status"],
                "selected_id": record["selected_id"],
                "is_fallback": is_fallback,
                "candidate_ids": candidate_ids,
                "elapsed_ms": record["total_elapsed_ms"],
            }
    finally:
        dynamic_orchestrator._get_default_ingredient_rag_retriever = original_getter

    negative_rows = (
        run_negative_queries(_read_negative_jsonl(negative_jsonl), catalog, current_retriever)
        if negative_jsonl is not None
        else []
    )

    history_after = _historical_hashes()
    if history_after != inputs["historical_hashes"]:
        raise Task67EvaluationError("historical Task64/66 artifacts changed during Task67 run")
    metrics_by_dataset: dict[str, Any] = {}
    for dataset in ("task64", "task66_1", "combined"):
        pairs = [pair for pair in fixture_pairs if dataset == "combined" or pair[0] == dataset]
        ids = {ingredient["query_id"] for _, _, ingredient in pairs}
        metrics_by_dataset[dataset] = {
            side: _score_side(pairs, {query_id: rows[query_id] for query_id in ids})
            for side, rows in (
                ("legacy_historical", baseline_mappings["legacy"]),
                ("rag_historical", baseline_mappings["rag"]),
                ("rag_task67", current_by_id),
            )
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / RESULTS_NAME
    _write_jsonl_exclusive(result_path, current_rows)
    metrics = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "acceptance_contract_id": CONTRACT_ID,
        "dish_count": 120,
        "query_occurrence_count": len(current_rows),
        "gold_rule": "fallback does not count as correct; every fixed dish and item remains in denominator",
        "metrics": metrics_by_dataset,
    }
    if negative_jsonl is not None:
        _write_jsonl_exclusive(output_dir / "negative_results.jsonl", negative_rows)
        expected_fallbacks = sum(row["expected_fallback"] for row in negative_rows)
        correct_fallbacks = sum(
            row["expected_fallback"] and row["is_fallback"] for row in negative_rows
        )
        metrics["negative"] = {
            "query_count": len(negative_rows),
            "expected_fallback_count": expected_fallbacks,
            "correct_fallback_count": correct_fallbacks,
            "fallback_rate_on_expected_negative": (
                correct_fallbacks / expected_fallbacks if expected_fallbacks else None
            ),
            "semantic_no_match_count": sum(
                row["retrieval_status"] == "no_match" for row in negative_rows
            ),
            "infrastructure_failure_count": sum(
                row["retrieval_status"] == "error" for row in negative_rows
            ),
            "forced_candidate_count": sum(
                row["retrieval_status"] == "success" and not row["is_fallback"]
                for row in negative_rows
            ),
        }
    _write_json_exclusive(output_dir / METRICS_NAME, metrics)
    manifest = {
        "acceptance_contract_id": CONTRACT_ID,
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "fixture_sha256": {
            "task64": inputs["task64_fixture_sha256"],
            "task66_1": inputs["task66_1_fixture_sha256"],
        },
        "catalog_sha256": inputs["catalog_sha256"],
        "task65_asset_hashes": resources["asset_hashes"],
        "historical_artifact_hashes": inputs["historical_hashes"],
        "historical_artifact_hashes_after": history_after,
        "positive_result_sha256": _sha256_file(result_path),
        "positive_result_rows": len(current_rows),
        "negative_inputs_read": negative_jsonl is not None,
        "negative_input_sha256": (
            _sha256_file(negative_jsonl) if negative_jsonl is not None else None
        ),
        "negative_result_sha256": (
            _sha256_file(output_dir / "negative_results.jsonl")
            if negative_jsonl is not None
            else None
        ),
        "negative_result_rows": len(negative_rows),
        "paid_provider_calls": 0,
    }
    _write_json_exclusive(output_dir / MANIFEST_NAME, manifest)
    return {"manifest": manifest, "metrics": metrics}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--negative-jsonl",
        type=Path,
        help="Optional parent-prepared JSONL with query_id/query fields; never calls a Provider.",
    )
    args = parser.parse_args(argv)
    result = run_positive_evaluation(args.output_dir, negative_jsonl=args.negative_jsonl)
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
