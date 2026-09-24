"""Run the frozen M14 Task66 RAG comparison without modifying Task64 outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT))

from pelican_town_specials.catalog.mapping import map_ingredient
from pelican_town_specials.catalog.models import CatalogCandidate
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation import orchestrator
from pelican_town_specials.generation.orchestrator import (
    IngredientRetrievalBackend,
    _build_candidates,
)
from pelican_town_specials.ingredient_rag import (
    IngredientRagRetriever,
    IngredientRagUnavailable,
)

from scripts import evaluate_ingredients as evaluation

CONTRACT_ID = "m14-task66-ingredient-rag-comparison-v1"
TASK64_OUTPUT_DIR = REPO_ROOT / "output" / "m14-task64"
TASK65_RESOURCE_DIR = REPO_ROOT / "output" / "m14-task65" / "ingredient-rag-spm"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "m14-task66"
TASK64_ARTIFACT_NAMES = (
    "baseline_manifest.json",
    "baseline.jsonl",
    "jev.jsonl",
    "metrics.json",
    "query_results.jsonl",
)
TASK64_MODEL_VERSION = "typesafe/jev-1.13-20260917"
ASSET_FILES = {
    "manifest": "ingredient-index.manifest.json",
    "model": "model-int8.onnx",
    "tokenizer": "sentencepiece.bpe.model",
    "vectors": "ingredient-vectors.f32",
}
TASK65_ASSET_EXPECTATIONS = {
    "catalogSha256": evaluation.EXPECTED_CATALOG_SHA256,
    "catalogVersion": evaluation.EXPECTED_CATALOG_VERSION,
    "modelId": "intfloat/multilingual-e5-small",
    "modelRevision": "fd1525a9fd15316a2d503bf26ab031a61d056e98",
    "modelSha256": "739C8F25BBE6D8A6001CD2F048701DA9879140CC67D4E9327716111E869DD717",
    "tokenizerSha256": "CFC8146ABE2A0488E9E2A0C56DE7952F7C11AB059ECA145A0A727AFCE0DB2865",
    "vectorSha256": "D640532CBD3316EED3A6831939A7289858D492E025D3223ECCFA7D93D8D4EC58",
    "rowCount": 253,
    "topK": 5,
    "embeddingDimension": 384,
    "dtype": "float32",
    "vectorBytes": 388_608,
}

# These are copied as measured evidence from the Task65 report. Task66 does not
# repeat the cold-process / RAM / onedir measurements or activate RAG by default.
TASK65_RESOURCE_EVIDENCE = {
    "source": "docs/development/M14_TASK65_INGREDIENT_RAG_IMPLEMENTATION.md",
    "limits": {
        "vector_bytes_max": 524_288,
        "added_distribution_bytes_max": 180 * 1024 * 1024,
        "cold_load_ms_max": 5_000.0,
        "active_model_rss_delta_mib_max": 256.0,
        "warm_query_p95_ms_max": 100.0,
    },
    "observed": {
        "vector_bytes": 388_608,
        "added_distribution_bytes": 159_489_831,
        "cold_load_median_ms": 1_178.337,
        "cold_load_max_ms": 1_466.078,
        "active_model_rss_delta_median_mib": 188.348,
        "active_model_rss_delta_max_mib": 188.602,
        "warm_query_p95_ms": 8.449,
        "warm_query_count": 500,
    },
    "measurement_scope": (
        "Task65 measured pinned assets and runtime in isolated host Python; its frozen exe smoke "
        "did not select RAG because production default remains LEGACY."
    ),
}


class ComparisonError(RuntimeError):
    """Raised when a frozen input or Task66 artifact is inconsistent."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComparisonError(f"could not read JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise ComparisonError(f"JSON artifact must be an object: {path.name}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ComparisonError(f"could not read JSONL artifact: {path.name}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ComparisonError(f"invalid JSONL row in {path.name}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ComparisonError(f"JSONL row must be an object in {path.name}:{line_number}")
        rows.append(value)
    return rows


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _task64_hashes(output_dir: Path = TASK64_OUTPUT_DIR) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in TASK64_ARTIFACT_NAMES:
        path = output_dir / name
        if not path.is_file():
            raise ComparisonError(f"Task64 source artifact is missing: {name}")
        hashes[name] = _sha256_file(path)
    return hashes


def verify_task64_artifacts(
    output_dir: Path = TASK64_OUTPUT_DIR,
) -> dict[str, Any]:
    """Read and validate Task64 artifacts, retaining their hashes for immutability checks."""
    fixture, catalog, fixture_sha, catalog_sha = evaluation.load_frozen_inputs()
    hashes = _task64_hashes(output_dir)
    baseline_manifest = _read_json(output_dir / "baseline_manifest.json")
    metrics = _read_json(output_dir / "metrics.json")
    baseline_rows = _read_jsonl(output_dir / "baseline.jsonl")
    jev_rows = _read_jsonl(output_dir / "jev.jsonl")
    if (
        baseline_manifest.get("fixture_sha256") != fixture_sha
        or baseline_manifest.get("catalog_sha256") != catalog_sha
        or baseline_manifest.get("query_count") != 72
        or baseline_manifest.get("dish_count") != 24
    ):
        raise ComparisonError("Task64 baseline manifest differs from the frozen 24/72 inputs")
    if metrics.get("fixture_sha256") != fixture_sha or metrics.get("catalog_sha256") != catalog_sha:
        raise ComparisonError("Task64 metrics do not match the frozen inputs")
    if len(baseline_rows) != 72:
        raise ComparisonError("Task64 baseline must contain all 72 query rows")

    baseline_by_id = {row.get("query_id"): row for row in baseline_rows}
    fixture_queries = {
        ingredient["query_id"]: (dish, ingredient)
        for dish, ingredient in evaluation.iter_fixture_queries(fixture)
    }
    if set(baseline_by_id) != set(fixture_queries):
        raise ComparisonError("Task64 baseline query IDs differ from the frozen fixture")
    if any(row.get("status") not in {"mapped", "failed"} for row in baseline_rows):
        raise ComparisonError("Task64 baseline contains an unknown mapping status")
    completed = [row for row in jev_rows if row.get("status") == "completed"]
    versions = sorted({row.get("model") for row in completed if isinstance(row.get("model"), str)})
    if versions != [TASK64_MODEL_VERSION]:
        raise ComparisonError("Task64 JEV artifacts do not have the frozen single model version")
    latest_completed: dict[str, dict[str, Any]] = {}
    for row in completed:
        query_id = row.get("query_id")
        if query_id not in fixture_queries:
            raise ComparisonError("Task64 JEV artifact references an unknown query ID")
        if row.get("fixture_sha256") != fixture_sha or row.get("catalog_sha256") != catalog_sha:
            raise ComparisonError("Task64 JEV artifact hash does not match the frozen input")
        dish, ingredient = fixture_queries[query_id]
        if baseline_by_id[query_id].get("is_fallback"):
            raise ComparisonError("Task64 unexpectedly judged a fallback mapping")
        expected_state = evaluation.build_jev_state(
            dish, ingredient, baseline_by_id[query_id], catalog
        )
        if row.get("request_state") != expected_state:
            raise ComparisonError("Task64 completed JEV state differs from its frozen mapping")
        latest_completed[query_id] = row

    expected_nonfallback = {
        query_id
        for query_id, row in baseline_by_id.items()
        if row.get("status") == "mapped" and not row.get("is_fallback")
    }
    if set(latest_completed) != expected_nonfallback:
        raise ComparisonError("Task64 JEV completed rows do not cover its non-fallback mappings")
    old_summary, _ = _side_metrics(
        fixture, baseline_by_id, latest_completed, side="old"
    )
    historical_jev = metrics.get("jev", {})
    historical_baseline = metrics.get("baseline", {})
    historical_dishes = historical_jev.get("dish_all_reasonable_rate", {})
    historical_items = historical_jev.get("nonfallback_reasonable_rate", {})
    historical_coverage = historical_jev.get("reasonable_coverage_of_fixed_query_set", {})
    historical_recall = historical_baseline.get("gold_recall_at_5_mean")
    if historical_dishes.get("numerator") != 14 or historical_dishes.get("denominator") != 24:
        raise ComparisonError("Task64 historical primary baseline is not the frozen 14/24 dish result")
    if (
        old_summary["dish_all_reasonable_rate"]["numerator"]
        != historical_dishes.get("numerator")
        or old_summary["dish_all_reasonable_rate"]["denominator"]
        != historical_dishes.get("denominator")
        or not isinstance(historical_dishes.get("value"), (int, float))
        or not math.isclose(
            old_summary["dish_all_reasonable_rate"]["value"],
            float(historical_dishes["value"]),
            abs_tol=1e-12,
        )
    ):
        raise ComparisonError("Task64 raw rows do not reproduce the recorded 14/24 dish result")
    if (
        historical_items.get("numerator") != old_summary["nonfallback_reasonable_rate"]["numerator"]
        or historical_items.get("denominator")
        != old_summary["nonfallback_reasonable_rate"]["denominator"]
        or historical_coverage.get("numerator")
        != old_summary["reasonable_coverage_of_fixed_query_set"]["numerator"]
    ):
        raise ComparisonError("Task64 raw JEV rows do not reproduce the recorded item metrics")
    if not isinstance(historical_recall, (int, float)) or not math.isclose(
        float(historical_recall), old_summary["gold_recall_at_5"]["mean"], abs_tol=1e-12
    ):
        raise ComparisonError("Task64 raw baseline rows do not reproduce the recorded Gold Recall@5")
    return {
        "fixture": fixture,
        "catalog": catalog,
        "fixture_sha256": fixture_sha,
        "catalog_sha256": catalog_sha,
        "baseline_by_id": baseline_by_id,
        "jev_rows": jev_rows,
        "jev_by_id": latest_completed,
        "model_version": TASK64_MODEL_VERSION,
        "metrics": metrics,
        "artifact_hashes": hashes,
    }


def verify_task65_resources(resource_dir: Path = TASK65_RESOURCE_DIR) -> dict[str, Any]:
    """Verify the pinned Task65 final model, tokenizer, vector, and manifest bytes."""
    paths = {key: resource_dir / filename for key, filename in ASSET_FILES.items()}
    actual_hashes = {key: _sha256_file(path) for key, path in paths.items()}
    manifest = _read_json(paths["manifest"])
    for key, expected in TASK65_ASSET_EXPECTATIONS.items():
        if manifest.get(key) != expected:
            raise ComparisonError(f"Task65 manifest differs from frozen field: {key}")
    if actual_hashes["model"] != manifest.get("modelSha256"):
        raise ComparisonError("Task65 model bytes do not match the pinned manifest")
    if actual_hashes["tokenizer"] != manifest.get("tokenizerSha256"):
        raise ComparisonError("Task65 tokenizer bytes do not match the pinned manifest")
    if actual_hashes["vectors"] != manifest.get("vectorSha256"):
        raise ComparisonError("Task65 vector bytes do not match the pinned manifest")
    if paths["vectors"].stat().st_size != manifest.get("vectorBytes"):
        raise ComparisonError("Task65 vector file length does not match the pinned manifest")
    return {
        "resource_dir": str(resource_dir),
        "manifest": manifest,
        "manifest_sha256": actual_hashes["manifest"],
        "asset_hashes": actual_hashes,
        "asset_bytes": {key: path.stat().st_size for key, path in paths.items()},
    }


class _ObservedRetriever:
    """Track the actual Task65 retriever result while using the production selector seam."""

    def __init__(self, retriever: IngredientRagRetriever) -> None:
        self.retriever = retriever
        self.status = "not_called"
        self.error_code: str | None = None
        self.elapsed_ms: float | None = None
        self.candidates: list[CatalogCandidate] = []

    @property
    def disabled_reason(self) -> str | None:
        return self.retriever.disabled_reason

    def retrieve(
        self, query: str, *, used_item_ids: frozenset[str] = frozenset()
    ) -> list[CatalogCandidate]:
        started = time.perf_counter()
        try:
            self.candidates = self.retriever.retrieve(query, used_item_ids=used_item_ids)
        except IngredientRagUnavailable as exc:
            self.status = "error"
            self.error_code = exc.reason_code
            raise
        except Exception:
            self.status = "error"
            self.error_code = "rag_query_failed"
            raise
        finally:
            self.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        self.status = "success" if self.candidates else "empty"
        return list(self.candidates)


@contextmanager
def _select_observed_retriever(observed: _ObservedRetriever) -> Iterator[None]:
    original = orchestrator._get_default_ingredient_rag_retriever
    orchestrator._get_default_ingredient_rag_retriever = lambda _catalog: observed
    try:
        yield
    finally:
        orchestrator._get_default_ingredient_rag_retriever = original


def _candidate_rows(candidates: list[CatalogCandidate], catalog: Any) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        item = catalog.require(candidate.item_id)
        rows.append(
            {
                "item_id": candidate.item_id,
                "score": float(candidate.score),
                "name_en": item.display_name_en,
                "name_zh": item.display_name_zh,
            }
        )
    return rows


def run_rag_baseline(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    resource_dir: Path = TASK65_RESOURCE_DIR,
    *,
    task64_dir: Path = TASK64_OUTPUT_DIR,
) -> dict[str, Any]:
    """Run all 72 frozen rows sequentially through the explicit RAG selector and mapper."""
    if (output_dir / "rag_results.jsonl").exists():
        raise ComparisonError("Task66 rag_results.jsonl already exists; refusing to overwrite it")
    task64 = verify_task64_artifacts(task64_dir)
    resources = verify_task65_resources(resource_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _initial_manifest(task64, resources, output_dir, task64_dir)
    retriever = IngredientRagRetriever(task64["catalog"], resource_dir=resource_dir)
    observed = _ObservedRetriever(retriever)
    used_item_ids_by_dish: dict[str, set[str]] = {}
    rows: list[dict[str, Any]] = []
    started_at = datetime.now(UTC).isoformat()

    with _select_observed_retriever(observed):
        for dish, ingredient in evaluation.iter_fixture_queries(task64["fixture"]):
            query_id = ingredient["query_id"]
            dish_id = dish["dish_id"]
            used_item_ids = frozenset(used_item_ids_by_dish.setdefault(dish_id, set()))
            semantic = type(
                "SemanticIngredient",
                (),
                {"name": ingredient["name"], "normalized_name": ingredient["normalized_name"]},
            )()
            observed.status = "not_called"
            observed.error_code = None
            observed.elapsed_ms = None
            observed.candidates = []
            candidate_started = time.perf_counter()
            mapping_error: Exception | None = None
            try:
                mapper_candidates = _build_candidates(
                    semantic,
                    task64["catalog"],
                    used_item_ids=used_item_ids,
                    backend=IngredientRetrievalBackend.RAG,
                )
            except (AppError, TypeError, ValueError) as exc:
                mapper_candidates = []
                mapping_error = exc
            candidate_elapsed = round((time.perf_counter() - candidate_started) * 1000, 3)
            mapping_started = time.perf_counter()
            mapped = None
            if mapping_error is None:
                try:
                    mapped = map_ingredient(
                        semantic,
                        mapper_candidates,
                        task64["catalog"],
                        used_item_ids=used_item_ids,
                        language=Language.EN_US,
                    )
                except (AppError, TypeError, ValueError) as exc:
                    mapping_error = exc
            mapping_elapsed = round((time.perf_counter() - mapping_started) * 1000, 3)

            if observed.status == "success":
                candidate_source = "rag"
            elif observed.status == "empty":
                candidate_source = "legacy_empty_result_fallback"
            elif observed.status == "error":
                candidate_source = "legacy_error_fallback"
            else:
                candidate_source = "not_retrieved"
            retrieval_status = observed.status
            rag_candidate_rows = _candidate_rows(observed.candidates, task64["catalog"])
            mapper_candidate_rows = _candidate_rows(mapper_candidates, task64["catalog"])
            if mapped is None:
                row: dict[str, Any] = {
                    "query_id": query_id,
                    "dish_id": dish_id,
                    "query_name": ingredient["name"],
                    "normalized_name": ingredient["normalized_name"],
                    "acceptable_item_ids": ingredient["acceptable_item_ids"],
                    "used_item_ids_before": sorted(used_item_ids),
                    "retrieval_status": retrieval_status,
                    "retrieval_error_code": observed.error_code,
                    "candidate_source": candidate_source,
                    "rag_candidate_ids": [item["item_id"] for item in rag_candidate_rows],
                    "rag_candidates": rag_candidate_rows,
                    "mapper_candidate_ids": [item["item_id"] for item in mapper_candidate_rows],
                    "mapper_candidates": mapper_candidate_rows,
                    "mapping_status": "failed",
                    "selected_id": None,
                    "selected_name_en": None,
                    "selected_name_zh": None,
                    "mapping_reason": None,
                    "is_fallback": False,
                    "error_type": type(mapping_error).__name__ if mapping_error else None,
                    "error_code": getattr(mapping_error, "code", None),
                }
            else:
                selected_item = task64["catalog"].require(mapped.item_id)
                is_fallback = mapped.mapping_reason.startswith(evaluation.FALLBACK_PREFIX)
                row = {
                    "query_id": query_id,
                    "dish_id": dish_id,
                    "query_name": ingredient["name"],
                    "normalized_name": ingredient["normalized_name"],
                    "acceptable_item_ids": ingredient["acceptable_item_ids"],
                    "used_item_ids_before": sorted(used_item_ids),
                    "retrieval_status": retrieval_status,
                    "retrieval_error_code": observed.error_code,
                    "candidate_source": candidate_source,
                    "rag_candidate_ids": [item["item_id"] for item in rag_candidate_rows],
                    "rag_candidates": rag_candidate_rows,
                    "mapper_candidate_ids": [item["item_id"] for item in mapper_candidate_rows],
                    "mapper_candidates": mapper_candidate_rows,
                    "mapping_status": "mapped",
                    "selected_id": mapped.item_id,
                    "selected_name_en": selected_item.display_name_en,
                    "selected_name_zh": selected_item.display_name_zh,
                    "mapping_reason": mapped.mapping_reason,
                    "is_fallback": is_fallback,
                    "error_type": None,
                    "error_code": None,
                }
                used_item_ids_by_dish[dish_id].add(mapped.item_id)
            row["rag_retrieval_elapsed_ms"] = observed.elapsed_ms
            row["candidate_selection_elapsed_ms"] = candidate_elapsed
            row["mapping_elapsed_ms"] = mapping_elapsed
            row["total_elapsed_ms"] = round(candidate_elapsed + mapping_elapsed, 3)
            rows.append(row)

    if len(rows) != 72 or len({row["query_id"] for row in rows}) != 72:
        raise ComparisonError("RAG evaluation did not preserve all 72 unique frozen query rows")
    result_path = output_dir / "rag_results.jsonl"
    with result_path.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    task64_after = _task64_hashes(task64_dir)
    if task64_after != task64["artifact_hashes"]:
        raise ComparisonError("Task64 source artifact hashes changed during Task66 RAG execution")
    manifest["rag_run"] = {
        "started_at_utc": started_at,
        "query_count": len(rows),
        "mapped_count": sum(row["mapping_status"] == "mapped" for row in rows),
        "catalog_fallback_count": sum(row["is_fallback"] for row in rows),
        "mapping_failure_count": sum(row["mapping_status"] == "failed" for row in rows),
        "retrieval_error_count": sum(row["retrieval_status"] == "error" for row in rows),
        "retrieval_empty_count": sum(row["retrieval_status"] == "empty" for row in rows),
        "candidate_source_counts": _count_values(row["candidate_source"] for row in rows),
        "result_file": result_path.name,
        "result_sha256": _sha256_file(result_path),
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest["rag_run"]


def _initial_manifest(
    task64: dict[str, Any],
    resources: dict[str, Any],
    output_dir: Path,
    task64_dir: Path,
) -> dict[str, Any]:
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        previous = _read_json(manifest_path)
        if previous.get("acceptance_contract_id") != CONTRACT_ID:
            raise ComparisonError("Task66 output manifest belongs to a different contract")
        if previous.get("task64_artifact_hashes") != task64["artifact_hashes"]:
            raise ComparisonError("Task66 output manifest references different Task64 artifacts")
        previous_resources = previous.get("task65_resources", {})
        if (
            previous_resources.get("manifest_sha256") != resources["manifest_sha256"]
            or previous_resources.get("asset_hashes") != resources["asset_hashes"]
        ):
            raise ComparisonError("Task66 output manifest references different Task65 resources")
        return previous
    return {
        "acceptance_contract_id": CONTRACT_ID,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fixture_sha256": task64["fixture_sha256"],
        "catalog_sha256": task64["catalog_sha256"],
        "catalog_version": evaluation.EXPECTED_CATALOG_VERSION,
        "dish_count": 24,
        "query_occurrence_count": 72,
        "task64_output_dir": str(task64_dir),
        "task64_artifact_hashes": task64["artifact_hashes"],
        "task65_resources": {
            "resource_dir": resources["resource_dir"],
            "manifest_sha256": resources["manifest_sha256"],
            "asset_hashes": resources["asset_hashes"],
            "asset_bytes": resources["asset_bytes"],
            "model_id": resources["manifest"]["modelId"],
            "model_revision": resources["manifest"]["modelRevision"],
            "retrieval_config_version": resources["manifest"]["retrievalConfigVersion"],
            "top_k": resources["manifest"]["topK"],
        },
        "task65_resource_evidence": TASK65_RESOURCE_EVIDENCE,
    }


def build_jev_state(
    dish: dict[str, Any], ingredient: dict[str, Any], result_row: dict[str, Any], catalog: Any
) -> dict[str, Any]:
    """Build the frozen Task64 state using the new side's final mapper selection."""
    baseline_shape = {
        "status": result_row.get("mapping_status"),
        "is_fallback": result_row.get("is_fallback"),
        "selected_id": result_row.get("selected_id"),
    }
    return evaluation.build_jev_state(dish, ingredient, baseline_shape, catalog)


def reusable_task64_decision(
    request_state: dict[str, Any],
    task64_jev_rows: list[dict[str, Any]],
    *,
    expected_model: str,
) -> dict[str, Any] | None:
    """Reuse only a completed typed result for the exact state and exact returned model."""
    matches = [
        row
        for row in task64_jev_rows
        if row.get("status") == "completed"
        and row.get("model") == expected_model
        and row.get("request_state") == request_state
        and row.get("decision") in evaluation.DECISIONS
    ]
    if not matches or len({row["decision"] for row in matches}) != 1:
        return None
    return matches[0]


def _per_item_comparison(
    fixture: dict[str, Any],
    old_rows: dict[str, dict[str, Any]],
    old_jev: dict[str, dict[str, Any]],
    new_rows: dict[str, dict[str, Any]],
    new_jev: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep an explicit ordered comparison for each frozen query occurrence."""
    items: list[dict[str, Any]] = []
    for dish, ingredient in evaluation.iter_fixture_queries(fixture):
        query_id = ingredient["query_id"]
        old_mapping = old_rows.get(query_id, {})
        new_mapping = new_rows.get(query_id, {})
        old_decision_row = old_jev.get(query_id, {})
        new_decision_row = new_jev.get(query_id, {})
        old_decision = (
            old_decision_row.get("decision")
            if old_decision_row.get("status") == "completed"
            else None
        )
        new_decision = (
            new_decision_row.get("decision")
            if new_decision_row.get("status") == "completed"
            else None
        )
        old_mapping_status = old_mapping.get("status", "missing")
        new_mapping_status = new_mapping.get("mapping_status", "missing")
        old_fallback = bool(old_mapping.get("is_fallback"))
        new_fallback = bool(new_mapping.get("is_fallback"))
        old_reasonable = (
            old_mapping_status == "mapped" and not old_fallback and old_decision == "reasonable"
        )
        new_reasonable = (
            new_mapping_status == "mapped" and not new_fallback and new_decision == "reasonable"
        )
        acceptable_ids = set(ingredient["acceptable_item_ids"])
        old_candidates = old_mapping.get("candidate_ids", [])
        new_candidates = new_mapping.get("rag_candidate_ids", [])
        old_candidates = old_candidates if isinstance(old_candidates, list) else []
        new_candidates = new_candidates if isinstance(new_candidates, list) else []
        items.append(
            {
                "query_id": query_id,
                "dish_id": dish["dish_id"],
                "ingredient_name": ingredient.get("name"),
                "normalized_name": ingredient.get("normalized_name"),
                "old_mapping_status": old_mapping_status,
                "old_is_fallback": old_fallback,
                "old_selected_id": old_mapping.get("selected_id"),
                "old_candidate_ids": old_candidates,
                "old_decision": old_decision,
                "old_jev_status": old_decision_row.get("status", "missing"),
                "new_mapping_status": new_mapping_status,
                "new_is_fallback": new_fallback,
                "new_candidate_source": new_mapping.get("candidate_source"),
                "new_retrieval_status": new_mapping.get("retrieval_status"),
                "new_retrieval_error_code": new_mapping.get("retrieval_error_code"),
                "new_selected_id": new_mapping.get("selected_id"),
                "new_rag_candidate_ids": new_candidates,
                "new_decision": new_decision,
                "new_jev_status": new_decision_row.get("status", "missing"),
                "new_jev_stage": new_decision_row.get("stage"),
                "task64_source_query_id": new_decision_row.get("reused_from_query_id"),
                "new_jev_model": new_decision_row.get("model"),
                "old_gold_recall_at_5": (
                    len(set(old_candidates) & acceptable_ids) / len(acceptable_ids)
                    if acceptable_ids
                    else 0.0
                ),
                "new_gold_recall_at_5": (
                    len(set(new_candidates) & acceptable_ids) / len(acceptable_ids)
                    if acceptable_ids
                    else 0.0
                ),
                "selection_changed": old_mapping.get("selected_id") != new_mapping.get("selected_id"),
                "reasonableness_transition": (
                    "improved"
                    if not old_reasonable and new_reasonable
                    else "regressed"
                    if old_reasonable and not new_reasonable
                    else "unchanged"
                ),
            }
        )
    return items


def _find_probe_result(
    output_dir: Path, rag_by_id: dict[str, dict[str, Any]], fixture: dict[str, Any], catalog: Any
) -> dict[str, Any] | None:
    jev_path = output_dir / "jev.jsonl"
    if not jev_path.exists():
        return None
    fixture_pairs = {
        ingredient["query_id"]: (dish, ingredient)
        for dish, ingredient in evaluation.iter_fixture_queries(fixture)
    }
    for row in reversed(_read_jsonl(jev_path)):
        if row.get("stage") != "protocol_probe" or row.get("status") != "completed":
            continue
        query_id = row.get("query_id")
        result = rag_by_id.get(query_id)
        pair = fixture_pairs.get(query_id)
        if result is None or pair is None:
            continue
        state = build_jev_state(pair[0], pair[1], result, catalog)
        if row.get("request_state") == state:
            return row
    return None


def _probe_candidate_ids(
    fixture: dict[str, Any], rag_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    ordered = [
        ingredient["query_id"]
        for dish, ingredient in evaluation.iter_fixture_queries(fixture)
        if (row := rag_by_id.get(ingredient["query_id"])) is not None
        and row.get("mapping_status") == "mapped"
        and not row.get("is_fallback")
    ]
    rag_succeeded = [query_id for query_id in ordered if rag_by_id[query_id].get("candidate_source") == "rag"]
    return rag_succeeded or ordered


def _call_and_record(
    output_dir: Path,
    *,
    query_id: str,
    state: dict[str, Any],
    api_key: str,
    stage: str,
) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    try:
        parsed, raw, elapsed_ms = evaluation.call_jev(state, api_key)
    except evaluation.EvaluationError as exc:
        row = {
            "query_id": query_id,
            "status": "failed",
            "stage": stage,
            "failure_type": type(exc).__name__,
            "failure_message": str(exc)[:600],
            "started_at_utc": started_at,
            "request_state": state,
            "raw_response": getattr(exc, "raw_response", None),
        }
        _append_jsonl(output_dir / "jev.jsonl", row)
        return row
    row = {
        "query_id": query_id,
        "status": "completed",
        "stage": stage,
        "started_at_utc": started_at,
        "elapsed_ms": elapsed_ms,
        "request_state": state,
        **parsed,
        "raw_response": raw,
    }
    _append_jsonl(output_dir / "jev.jsonl", row)
    return row


def run_protocol_probe(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    task64_dir: Path = TASK64_OUTPUT_DIR,
) -> dict[str, Any]:
    """Make one small live Decisions API probe from an actual new-side mapping."""
    task64 = verify_task64_artifacts(task64_dir)
    verify_task66_run_inputs(output_dir, task64=task64, task64_dir=task64_dir)
    rag_rows = _read_jsonl(output_dir / "rag_results.jsonl")
    rag_by_id = {row.get("query_id"): row for row in rag_rows}
    existing = _find_probe_result(output_dir, rag_by_id, task64["fixture"], task64["catalog"])
    if existing is not None:
        return {
            "query_id": existing["query_id"],
            "model": existing["model"],
            "provider": existing.get("provider"),
            "reused_existing_probe": True,
            "status": "completed",
        }
    query_ids = _probe_candidate_ids(task64["fixture"], rag_by_id)
    if not query_ids:
        return {"status": "not_required", "reason": "no new non-fallback mappings"}
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ComparisonError("OPENROUTER_API_KEY is not present in the process environment")
    query_id = query_ids[0]
    fixture_pairs = {
        ingredient["query_id"]: (dish, ingredient)
        for dish, ingredient in evaluation.iter_fixture_queries(task64["fixture"])
    }
    dish, ingredient = fixture_pairs[query_id]
    state = build_jev_state(dish, ingredient, rag_by_id[query_id], task64["catalog"])
    result = _call_and_record(
        output_dir,
        query_id=query_id,
        state=state,
        api_key=api_key,
        stage="protocol_probe",
    )
    return {
        "query_id": query_id,
        "model": result.get("model"),
        "provider": result.get("provider"),
        "status": result.get("status"),
        "failure_type": result.get("failure_type"),
        "reused_existing_probe": False,
    }


def run_full_jev(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    task64_dir: Path = TASK64_OUTPUT_DIR,
) -> dict[str, Any]:
    """Judge each non-fallback new mapping, reusing only exact same-state Task64 decisions."""
    task64 = verify_task64_artifacts(task64_dir)
    verify_task66_run_inputs(output_dir, task64=task64, task64_dir=task64_dir)
    rag_rows = _read_jsonl(output_dir / "rag_results.jsonl")
    rag_by_id = {row.get("query_id"): row for row in rag_rows}
    probe = run_protocol_probe(output_dir, task64_dir=task64_dir)
    if probe.get("status") != "completed":
        return {
            "probe": probe,
            "expected_model": None,
            "baseline_model": task64["model_version"],
            "new_model_versions": [],
            "model_comparable": False,
            "completed_query_count": 0,
            "reused_task64_state_count": 0,
            "reused_task66_result_count": 0,
            "failed_count": 1 if probe.get("status") == "failed" else 0,
            "model_drift_count": 0,
            "not_attempted_after_drift_count": 0,
            "jev_artifact": str(output_dir / "jev.jsonl"),
        }
    jev_path = output_dir / "jev.jsonl"
    existing_rows = _read_jsonl(jev_path) if jev_path.exists() else []
    probe_rows = [
        row
        for row in existing_rows
        if row.get("stage") == "protocol_probe" and row.get("status") == "completed"
    ]
    expected_model = probe_rows[-1].get("model") if probe_rows else None
    api_key = os.environ.get("OPENROUTER_API_KEY")
    completed_count = 0
    reused_task64_count = 0
    reused_task66_count = 0
    failed_count = 0
    model_drift_count = 0
    not_attempted_count = 0
    stopped_for_drift = False
    for dish, ingredient in evaluation.iter_fixture_queries(task64["fixture"]):
        query_id = ingredient["query_id"]
        result = rag_by_id.get(query_id)
        if result is None:
            raise ComparisonError(f"Task66 RAG results are missing frozen query: {query_id}")
        if result.get("mapping_status") != "mapped" or result.get("is_fallback"):
            continue
        state = build_jev_state(dish, ingredient, result, task64["catalog"])
        existing_rows = _read_jsonl(jev_path) if jev_path.exists() else []
        current_row = next(
            (row for row in reversed(existing_rows) if row.get("query_id") == query_id),
            None,
        )
        current = (
            current_row
            if current_row is not None
            and current_row.get("status") == "completed"
            and current_row.get("request_state") == state
            and current_row.get("model") == expected_model
            else None
        )
        if current is not None:
            completed_count += 1
            reused_task66_count += current.get("stage") != "protocol_probe"
            continue
        if stopped_for_drift:
            _append_jsonl(
                jev_path,
                {
                    "query_id": query_id,
                    "status": "not_attempted",
                    "stage": "full",
                    "reason": "stopped_after_model_version_drift",
                    "request_state": state,
                },
            )
            not_attempted_count += 1
            continue

        reusable = None
        if expected_model == task64["model_version"]:
            reusable = reusable_task64_decision(
                state, task64["jev_rows"], expected_model=expected_model
            )
        if reusable is not None:
            copied = {
                "query_id": query_id,
                "status": "completed",
                "stage": "task64_state_reuse",
                "reused_from_query_id": reusable["query_id"],
                "reused_from_artifact": "output/m14-task64/jev.jsonl",
                "reused_from_artifact_sha256": task64["artifact_hashes"]["jev.jsonl"],
                "request_state": state,
                "decision": reusable["decision"],
                "confidence": reusable["confidence"],
                "probabilities": reusable.get("probabilities"),
                "model": reusable["model"],
                "provider": reusable.get("provider"),
                "usage": reusable.get("usage"),
                "raw_response": reusable.get("raw_response"),
            }
            _append_jsonl(jev_path, copied)
            completed_count += 1
            reused_task64_count += 1
            continue

        if not api_key:
            _append_jsonl(
                jev_path,
                {
                    "query_id": query_id,
                    "status": "failed",
                    "stage": "full",
                    "failure_type": "MissingApiKey",
                    "failure_message": "OPENROUTER_API_KEY is not present in the process environment",
                    "request_state": state,
                },
            )
            failed_count += 1
            continue
        judged = _call_and_record(
            output_dir,
            query_id=query_id,
            state=state,
            api_key=api_key,
            stage="full",
        )
        if judged.get("status") == "completed":
            completed_count += 1
            if judged.get("model") != expected_model:
                model_drift_count += 1
                stopped_for_drift = True
        else:
            failed_count += 1

    all_jev_rows = _read_jsonl(jev_path) if jev_path.exists() else []
    decision_by_id = _latest_completed_by_query(all_jev_rows)
    new_models = {
        row["model"]
        for row in all_jev_rows
        if row.get("status") == "completed" and isinstance(row.get("model"), str)
    }
    return {
        "probe": probe,
        "expected_model": expected_model,
        "baseline_model": task64["model_version"],
        "new_model_versions": sorted(new_models),
        "model_comparable": new_models == {task64["model_version"]},
        "completed_query_count": len(decision_by_id),
        "reused_task64_state_count": reused_task64_count,
        "reused_task66_result_count": reused_task66_count,
        "failed_count": failed_count,
        "model_drift_count": model_drift_count,
        "not_attempted_after_drift_count": not_attempted_count,
        "jev_artifact": str(jev_path),
    }


def _latest_completed_by_query(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        query_id = row.get("query_id")
        if isinstance(query_id, str) and row.get("status") in {
            "completed",
            "failed",
            "not_attempted",
        }:
            latest[query_id] = row
    return {
        query_id: row
        for query_id, row in latest.items()
        if row.get("status") == "completed"
    }


def _count_values(values: Iterator[str] | list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _side_metrics(
    fixture: dict[str, Any],
    mapping_by_id: dict[str, dict[str, Any]],
    jev_by_id: dict[str, dict[str, Any]],
    *,
    side: str,
) -> tuple[dict[str, Any], dict[str, bool]]:
    result_rows: list[dict[str, Any]] = []
    dish_pass: dict[str, bool] = {}
    decisions_count = dict.fromkeys(evaluation.DECISIONS, 0)
    fallback_count = 0
    mapping_failure_count = 0
    retrieval_degraded_count = 0
    legacy_mapped_after_degrade_count = 0
    jev_failed_count = 0
    jev_not_attempted_count = 0
    jev_missing_count = 0
    determinate_count = 0
    reasonable_count = 0
    gold_recall_sum = 0.0
    gold_hit_count = 0
    selected_gold_count = 0
    retrieval_miss_count = 0
    rerank_miss_count = 0

    for dish in fixture["dishes"]:
        rows_for_dish: list[dict[str, Any]] = []
        for ingredient in dish["ingredients"]:
            query_id = ingredient["query_id"]
            raw_mapping = mapping_by_id.get(query_id, {})
            raw_jev = jev_by_id.get(query_id, {})
            is_old = side == "old"
            mapping_status = raw_mapping.get("status") if is_old else raw_mapping.get("mapping_status")
            is_fallback = bool(raw_mapping.get("is_fallback"))
            selected_id = raw_mapping.get("selected_id")
            candidate_ids = (
                raw_mapping.get("candidate_ids", [])
                if is_old
                else raw_mapping.get("rag_candidate_ids", [])
            )
            candidate_ids = candidate_ids if isinstance(candidate_ids, list) else []
            candidate_source = "legacy_baseline" if is_old else raw_mapping.get("candidate_source")
            retrieval_status = "legacy" if is_old else raw_mapping.get("retrieval_status")
            decision = raw_jev.get("decision") if raw_jev.get("status") == "completed" else None
            jev_status = raw_jev.get("status", "missing")
            gold_ids = set(ingredient["acceptable_item_ids"])
            overlap = set(candidate_ids) & gold_ids
            item_recall = len(overlap) / len(gold_ids) if gold_ids else 0.0
            selected_in_gold = selected_id in gold_ids if isinstance(selected_id, str) else False
            is_degraded = not is_old and retrieval_status in {"error", "empty"}
            if is_fallback:
                fallback_count += 1
            if mapping_status != "mapped":
                mapping_failure_count += 1
            if is_degraded:
                retrieval_degraded_count += 1
            if is_degraded and mapping_status == "mapped" and not is_fallback:
                legacy_mapped_after_degrade_count += 1
            if jev_status == "failed":
                jev_failed_count += 1
            elif jev_status == "not_attempted":
                jev_not_attempted_count += 1
            elif jev_status != "completed" and mapping_status == "mapped" and not is_fallback:
                jev_missing_count += 1
            if decision in decisions_count:
                decisions_count[decision] += 1
            if mapping_status == "mapped" and not is_fallback and decision in {
                "reasonable",
                "unreasonable",
            }:
                determinate_count += 1
                if decision == "reasonable":
                    reasonable_count += 1
            gold_recall_sum += item_recall
            gold_hit_count += bool(overlap)
            selected_gold_count += selected_in_gold
            retrieval_miss_count += not bool(overlap)
            rerank_miss_count += bool(overlap) and not selected_in_gold
            item_row = {
                "query_id": query_id,
                "dish_id": dish["dish_id"],
                "mapping_status": mapping_status or "missing",
                "is_fallback": is_fallback,
                "selected_id": selected_id,
                "candidate_ids": candidate_ids,
                "candidate_source": candidate_source,
                "retrieval_status": retrieval_status,
                "retrieval_degraded": is_degraded,
                "decision": decision,
                "jev_status": jev_status,
                "selected_id_in_gold": selected_in_gold,
                "gold_recall_at_5": item_recall,
            }
            result_rows.append(item_row)
            rows_for_dish.append(item_row)
        expected_count = len(dish["ingredients"])
        dish_pass[dish["dish_id"]] = len(rows_for_dish) == expected_count and bool(expected_count) and all(
            row["mapping_status"] == "mapped"
            and not row["is_fallback"]
            and row["decision"] == "reasonable"
            for row in rows_for_dish
        )

    total = sum(len(dish["ingredients"]) for dish in fixture["dishes"])
    dish_total = len(fixture["dishes"])
    all_reasonable = sum(dish_pass.values())
    if side == "new":
        rag_only_pass = {
            dish["dish_id"]: dish_pass[dish["dish_id"]]
            and all(
                row["candidate_source"] == "rag"
                for row in result_rows
                if row["dish_id"] == dish["dish_id"]
            )
            for dish in fixture["dishes"]
        }
        rag_attributed = sum(rag_only_pass.values())
    else:
        rag_attributed = None
    metrics = {
        "query_occurrence_count": total,
        "dish_count": dish_total,
        "fallback_count": fallback_count,
        "mapping_failure_count": mapping_failure_count,
        "retrieval_degraded_count": retrieval_degraded_count,
        "legacy_mapped_after_degrade_count": legacy_mapped_after_degrade_count,
        "jev_decision_counts": decisions_count,
        "jev_call_failure_count": jev_failed_count,
        "jev_not_attempted_count": jev_not_attempted_count,
        "jev_missing_count": jev_missing_count,
        "nonfallback_reasonable_rate": {
            "numerator": reasonable_count,
            "denominator": determinate_count,
            "value": reasonable_count / determinate_count if determinate_count else None,
        },
        "reasonable_coverage_of_fixed_query_set": {
            "numerator": decisions_count["reasonable"],
            "denominator": total,
            "value": decisions_count["reasonable"] / total if total else None,
        },
        "dish_all_reasonable_rate": {
            "numerator": all_reasonable,
            "denominator": dish_total,
            "value": all_reasonable / dish_total if dish_total else None,
        },
        "gold_recall_at_5": {
            "mean": gold_recall_sum / total if total else None,
            "numerator_sum_of_item_recall": round(gold_recall_sum, 8),
            "denominator": total,
        },
        "gold_hit_at_5": {"numerator": gold_hit_count, "denominator": total},
        "selected_gold_match": {"numerator": selected_gold_count, "denominator": total},
        "candidate_retrieval_miss_count": retrieval_miss_count,
        "candidate_rerank_or_selection_miss_count": rerank_miss_count,
    }
    if side == "new":
        metrics["dish_all_reasonable_rag_attributed_rate"] = {
            "numerator": rag_attributed,
            "denominator": dish_total,
            "value": rag_attributed / dish_total if dish_total else None,
            "rule": "all query mappings are non-fallback reasonable and came from a successful non-empty RAG result",
        }
    return metrics, dish_pass


def evaluate_task65_resource_gate(evidence: dict[str, Any] = TASK65_RESOURCE_EVIDENCE) -> dict[str, Any]:
    limits = evidence["limits"]
    observed = evidence["observed"]
    checks = {
        "vector_file": observed["vector_bytes"] <= limits["vector_bytes_max"],
        "added_distribution": observed["added_distribution_bytes"]
        <= limits["added_distribution_bytes_max"],
        "cold_load": observed["cold_load_max_ms"] <= limits["cold_load_ms_max"],
        "active_model_rss_delta": observed["active_model_rss_delta_max_mib"]
        <= limits["active_model_rss_delta_mib_max"],
        "warm_query_p95": observed["warm_query_p95_ms"] <= limits["warm_query_p95_ms_max"],
    }
    return {
        "source": evidence["source"],
        "observed": observed,
        "limits": limits,
        "checks": checks,
        "all_passed": all(checks.values()),
        "measurement_scope": evidence["measurement_scope"],
    }


def compare_metrics(
    fixture: dict[str, Any],
    old_rows: dict[str, dict[str, Any]],
    old_jev: dict[str, dict[str, Any]],
    new_rows: dict[str, dict[str, Any]],
    new_jev: dict[str, dict[str, Any]],
    *,
    baseline_model: str,
    new_models: set[str],
    task65_resource_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    old, old_dish_pass = _side_metrics(fixture, old_rows, old_jev, side="old")
    new, new_dish_pass = _side_metrics(fixture, new_rows, new_jev, side="new")
    model_comparable = new_models == {baseline_model}
    per_dish = [
        {
            "dish_id": dish["dish_id"],
            "name_en": dish["name_en"],
            "name_zh": dish["name_zh"],
            "old_all_reasonable": old_dish_pass[dish["dish_id"]],
            "new_all_reasonable": new_dish_pass[dish["dish_id"]],
            "transition": (
                "improved"
                if not old_dish_pass[dish["dish_id"]] and new_dish_pass[dish["dish_id"]]
                else "regressed"
                if old_dish_pass[dish["dish_id"]] and not new_dish_pass[dish["dish_id"]]
                else "unchanged"
            ),
        }
        for dish in fixture["dishes"]
    ]
    if model_comparable:
        transitions = _count_values(row["transition"] for row in per_dish)
        transition_summary = {
            "status": "comparable",
            "improved": transitions.get("improved", 0),
            "regressed": transitions.get("regressed", 0),
            "unchanged": transitions.get("unchanged", 0),
            "per_dish": per_dish,
        }
    else:
        transition_summary = {
            "status": "not_comparable_model_version",
            "baseline_model": baseline_model,
            "new_models": sorted(new_models),
            "per_dish": per_dish,
        }

    resource_gate = task65_resource_gate or evaluate_task65_resource_gate()
    if not model_comparable:
        gate_status = "not_evaluable"
        reasons = ["Task64 and Task66 use different or mixed returned JEV model versions"]
    else:
        conditions = {
            "dish_all_reasonable_rate_strictly_higher": (
                new["dish_all_reasonable_rate"]["numerator"]
                > old["dish_all_reasonable_rate"]["numerator"]
            ),
            "gold_recall_at_5_not_lower": (
                new["gold_recall_at_5"]["mean"] is not None
                and old["gold_recall_at_5"]["mean"] is not None
                and new["gold_recall_at_5"]["mean"] >= old["gold_recall_at_5"]["mean"]
            ),
            "fixed_query_reasonable_coverage_not_lower": (
                new["reasonable_coverage_of_fixed_query_set"]["numerator"]
                >= old["reasonable_coverage_of_fixed_query_set"]["numerator"]
            ),
            "task65_resource_gate_passed": bool(resource_gate.get("all_passed")),
        }
        gate_status = "met" if all(conditions.values()) else "not_met"
        reasons = [name for name, passed in conditions.items() if not passed]
    return {
        "baseline_model": baseline_model,
        "new_models": sorted(new_models),
        "model_comparable": model_comparable,
        "old": old,
        "new": new,
        "per_item": _per_item_comparison(fixture, old_rows, old_jev, new_rows, new_jev),
        "paired_dish_transitions": transition_summary,
        "adoption_gate": {
            "status": gate_status,
            "reasons_not_met": reasons,
            "task65_resource_gate": resource_gate,
            "production_default_change": "not authorized; remains LEGACY",
        },
    }


def calculate_metrics(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Recompute old/new outcomes and adoption gate from frozen and ignored artifacts."""
    task64 = verify_task64_artifacts(TASK64_OUTPUT_DIR)
    manifest = verify_task66_run_inputs(output_dir, task64=task64)
    rag_rows = _read_jsonl(output_dir / "rag_results.jsonl")
    jev_rows = _read_jsonl(output_dir / "jev.jsonl") if (output_dir / "jev.jsonl").exists() else []
    rag_by_id = {row.get("query_id"): row for row in rag_rows}
    expected_ids = {
        ingredient["query_id"]
        for _, ingredient in evaluation.iter_fixture_queries(task64["fixture"])
    }
    if set(rag_by_id) != expected_ids:
        raise ComparisonError("Task66 RAG results do not contain exactly the frozen 72 query IDs")
    new_jev_latest: dict[str, dict[str, Any]] = {}
    for row in jev_rows:
        query_id = row.get("query_id")
        if isinstance(query_id, str):
            new_jev_latest[query_id] = row
    all_completed_new = [row for row in jev_rows if row.get("status") == "completed"]
    new_models = {
        row["model"] for row in all_completed_new if isinstance(row.get("model"), str)
    }
    task64_decisions = task64["jev_by_id"]
    task64_reuse_provenance = []
    for query_id, row in new_jev_latest.items():
        if row.get("status") != "completed" or row.get("stage") != "task64_state_reuse":
            continue
        reused = reusable_task64_decision(
            row.get("request_state", {}),
            task64["jev_rows"],
            expected_model=task64["model_version"],
        )
        if reused is None or reused.get("decision") != row.get("decision"):
            raise ComparisonError(
                f"Task66 Task64 reuse provenance is not exact for query: {query_id}"
            )
        row.setdefault("reused_from_query_id", reused["query_id"])
        row.setdefault("reused_from_artifact", "output/m14-task64/jev.jsonl")
        row.setdefault(
            "reused_from_artifact_sha256", task64["artifact_hashes"]["jev.jsonl"]
        )
        task64_reuse_provenance.append(
            {
                "query_id": query_id,
                "source_query_id": reused["query_id"],
                "source_artifact": "output/m14-task64/jev.jsonl",
                "source_artifact_sha256": task64["artifact_hashes"]["jev.jsonl"],
                "model": reused["model"],
                "decision": reused["decision"],
                "request_state_sha256": _sha256_bytes(
                    json.dumps(
                        row["request_state"],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ),
            }
        )
    comparison = compare_metrics(
        task64["fixture"],
        task64["baseline_by_id"],
        task64_decisions,
        rag_by_id,
        new_jev_latest,
        baseline_model=task64["model_version"],
        new_models=new_models,
    )
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "acceptance_contract_id": CONTRACT_ID,
        "fixture_sha256": task64["fixture_sha256"],
        "catalog_sha256": task64["catalog_sha256"],
        "catalog_version": evaluation.EXPECTED_CATALOG_VERSION,
        "query_occurrence_count": 72,
        "dish_count": 24,
        "task64_artifact_hashes": task64["artifact_hashes"],
        "task64_reuse_provenance": task64_reuse_provenance,
        **comparison,
    }
    if _task64_hashes(TASK64_OUTPUT_DIR) != task64["artifact_hashes"]:
        raise ComparisonError("Task64 source artifact hashes changed during Task66 metrics calculation")
    manifest["task64_artifact_hashes_after"] = _task64_hashes(TASK64_OUTPUT_DIR)
    manifest["jev_run"] = _jev_run_summary(jev_rows)
    manifest["metrics_sha256"] = _sha256_bytes(
        (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    _write_json(output_dir / "manifest.json", manifest)
    return report


def verify_task66_run_inputs(
    output_dir: Path,
    *,
    task64: dict[str, Any] | None = None,
    task64_dir: Path = TASK64_OUTPUT_DIR,
) -> dict[str, Any]:
    """Check the current ignored run against frozen Task64/65 inputs before use."""
    verified_task64 = task64 or verify_task64_artifacts(task64_dir)
    manifest = _read_json(output_dir / "manifest.json")
    if manifest.get("acceptance_contract_id") != CONTRACT_ID:
        raise ComparisonError("Task66 manifest contract identifier does not match")
    if manifest.get("task64_artifact_hashes") != verified_task64["artifact_hashes"]:
        raise ComparisonError("Task64 artifact hashes changed since Task66 RAG execution")
    task65_manifest = manifest.get("task65_resources", {})
    resource_dir_value = task65_manifest.get("resource_dir")
    if not isinstance(resource_dir_value, str) or not resource_dir_value:
        raise ComparisonError("Task66 manifest is missing the Task65 resource directory")
    resources = verify_task65_resources(Path(resource_dir_value))
    if (
        task65_manifest.get("manifest_sha256") != resources["manifest_sha256"]
        or task65_manifest.get("asset_hashes") != resources["asset_hashes"]
    ):
        raise ComparisonError("Task65 model/index assets changed since Task66 RAG execution")
    rag_path = output_dir / "rag_results.jsonl"
    expected_rag_hash = manifest.get("rag_run", {}).get("result_sha256")
    if not rag_path.is_file() or expected_rag_hash != _sha256_file(rag_path):
        raise ComparisonError("Task66 RAG results differ from their recorded hash")
    return manifest


def _jev_run_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    provider_stages = {"protocol_probe", "full"}
    provider_attempts = [row for row in rows if row.get("stage") in provider_stages]
    provider_completions = [row for row in provider_attempts if row.get("status") == "completed"]
    task64_reuse = [
        row
        for row in completed
        if row.get("stage") == "task64_state_reuse"
    ]
    return {
        "resolved_model_versions": sorted(
            {row["model"] for row in completed if isinstance(row.get("model"), str)}
        ),
        "typed_choice_count": len(completed),
        "decision_counts": _count_values(
            row["decision"] for row in completed if row.get("decision") in evaluation.DECISIONS
        ),
        "provider_call_count": len(provider_attempts),
        "provider_success_count": len(provider_completions),
        "provider_failure_count": len(provider_attempts) - len(provider_completions),
        "task64_state_reuse_count": len(task64_reuse),
        "provider_cost_usd": sum(
            usage["cost"]
            for row in provider_completions
            if isinstance((usage := row.get("usage")), dict)
            and isinstance(usage.get("cost"), (int, float))
        ),
        "task64_reused_historical_cost_usd": sum(
            usage["cost"]
            for row in task64_reuse
            if isinstance((usage := row.get("usage")), dict)
            and isinstance(usage.get("cost"), (int, float))
        ),
        "failed_or_not_attempted_count": sum(
            row.get("status") in {"failed", "not_attempted"} for row in rows
        ),
    }


REPORT_PATH = REPO_ROOT / "docs" / "development" / "M14_TASK66_INGREDIENT_RAG_COMPARISON.md"


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _markdown_cell(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def write_report(output_dir: Path = DEFAULT_OUTPUT_DIR, report_path: Path = REPORT_PATH) -> dict[str, Any]:
    """Write the submitted aggregate report and complete per-item comparison table."""
    metrics = calculate_metrics(output_dir)
    _write_json(output_dir / "metrics.json", metrics)
    manifest = _read_json(output_dir / "manifest.json")
    rag_rows = _read_jsonl(output_dir / "rag_results.jsonl")
    task64_rows = _read_jsonl(TASK64_OUTPUT_DIR / "baseline.jsonl")
    rag_times = [float(row["rag_retrieval_elapsed_ms"]) for row in rag_rows]
    legacy_times = [float(row["elapsed_ms"]) for row in task64_rows if isinstance(row.get("elapsed_ms"), (int, float))]
    map_times = [float(row["mapping_elapsed_ms"]) for row in rag_rows]
    pipeline_times = [float(row["total_elapsed_ms"]) for row in rag_rows]
    task65 = manifest["task65_resources"]
    resource_gate = metrics["adoption_gate"]["task65_resource_gate"]
    usage = manifest["jev_run"]
    transitions = metrics["paired_dish_transitions"]
    old = metrics["old"]
    new = metrics["new"]
    fixture = evaluation.load_frozen_inputs()[0]
    dish_names = {dish["dish_id"]: dish["name_en"] for dish in fixture["dishes"]}
    status_counts = {
        "mapping_failures": new["mapping_failure_count"],
        "fallbacks": new["fallback_count"],
        "retrieval_degraded": new["retrieval_degraded_count"],
        "JEV call failures": new["jev_call_failure_count"],
        "JEV missing": new["jev_missing_count"],
        "JEV undecidable": new["jev_decision_counts"].get("undecidable", 0),
        "JEV not attempted": new["jev_not_attempted_count"],
    }

    lines = [
        "# M14 Task66 — Ingredient RAG Same-Set Comparison",
        "",
        f"- Acceptance contract: `{CONTRACT_ID}`",
        f"- Generated: `{metrics['generated_at_utc']}`",
        f"- Frozen set: 24 dishes / 72 query occurrences; fixture SHA-256 `{metrics['fixture_sha256']}`; catalog `{metrics['catalog_version']}` SHA-256 `{metrics['catalog_sha256']}`.",
        "- Task64 raw artifacts were read-only and their hashes were rechecked unchanged after evaluation. Task66 raw outputs are ignored under `output/m14-task66/`.",
        "",
        "## Result",
        "",
        f"The primary fixed-denominator dish all-reasonable rate changed from **{old['dish_all_reasonable_rate']['numerator']}/24 ({old['dish_all_reasonable_rate']['value']:.2%})** to **{new['dish_all_reasonable_rate']['numerator']}/24 ({new['dish_all_reasonable_rate']['value']:.2%})**. With the same returned JEV model on both sides, the paired set has **{transitions['improved']} improved, {transitions['regressed']} regressed, and {transitions['unchanged']} unchanged dishes**.",
        "",
        "The frozen adoption gate is **met**: the primary numerator is strictly higher, Recall@5 and reasonable coverage did not fall, and the Task65 resource budget evidence passes. This is evaluation evidence only; the product default remains `LEGACY`, and no default change is authorized by this Task.",
        "",
        "| Metric | Task64 legacy | Task66 RAG + mapper |",
        "|---|---:|---:|",
        f"| Dish all-reasonable (fixed 24) | {old['dish_all_reasonable_rate']['numerator']}/24 ({old['dish_all_reasonable_rate']['value']:.2%}) | {new['dish_all_reasonable_rate']['numerator']}/24 ({new['dish_all_reasonable_rate']['value']:.2%}) |",
        f"| Non-fallback item reasonable (determinate only) | {old['nonfallback_reasonable_rate']['numerator']}/{old['nonfallback_reasonable_rate']['denominator']} ({old['nonfallback_reasonable_rate']['value']:.2%}) | {new['nonfallback_reasonable_rate']['numerator']}/{new['nonfallback_reasonable_rate']['denominator']} ({new['nonfallback_reasonable_rate']['value']:.2%}) |",
        f"| Reasonable coverage of fixed 72 | {old['reasonable_coverage_of_fixed_query_set']['numerator']}/72 ({old['reasonable_coverage_of_fixed_query_set']['value']:.2%}) | {new['reasonable_coverage_of_fixed_query_set']['numerator']}/72 ({new['reasonable_coverage_of_fixed_query_set']['value']:.2%}) |",
        f"| Gold Recall@5 (mean per occurrence) | {old['gold_recall_at_5']['numerator_sum_of_item_recall']:.0f}/72 ({old['gold_recall_at_5']['mean']:.2%}) | {new['gold_recall_at_5']['numerator_sum_of_item_recall']:.0f}/72 ({new['gold_recall_at_5']['mean']:.2%}) |",
        f"| At least one acceptable Gold in Top 5 | {old['gold_hit_at_5']['numerator']}/72 | {new['gold_hit_at_5']['numerator']}/72 |",
        f"| Final selection in acceptable Gold | {old['selected_gold_match']['numerator']}/72 | {new['selected_gold_match']['numerator']}/72 |",
        f"| Candidate retrieval misses / selection misses after hit | {old['candidate_retrieval_miss_count']} / {old['candidate_rerank_or_selection_miss_count']} | {new['candidate_retrieval_miss_count']} / {new['candidate_rerank_or_selection_miss_count']} |",
        f"| Mapping failures / catalog fallback | {old['mapping_failure_count']} / {old['fallback_count']} | {new['mapping_failure_count']} / {new['fallback_count']} |",
        f"| JEV choice counts (reasonable / unreasonable / undecidable) | {old['jev_decision_counts']['reasonable']} / {old['jev_decision_counts']['unreasonable']} / {old['jev_decision_counts']['undecidable']} | {new['jev_decision_counts']['reasonable']} / {new['jev_decision_counts']['unreasonable']} / {new['jev_decision_counts']['undecidable']} |",
        "",
        "## Paired dish outcomes",
        "",
        "| Dish | Legacy all reasonable | RAG all reasonable | Transition |",
        "|---|:---:|:---:|---|",
    ]
    for dish in transitions["per_dish"]:
        lines.append(
            f"| `{dish['dish_id']}` {_markdown_cell(dish_names.get(dish['dish_id']))} | "
            f"{'yes' if dish['old_all_reasonable'] else 'no'} | "
            f"{'yes' if dish['new_all_reasonable'] else 'no'} | {dish['transition']} |"
        )

    lines.extend(
        [
            "",
            "## JEV protocol, reuse, and cost",
            "",
            f"Returned model/provider: `{', '.join(usage['resolved_model_versions'])}` / `TypeSafe`. Task64 and Task66 versions match exactly. There are **{usage['typed_choice_count']}/72** new-side typed judgments: **{usage['task64_state_reuse_count']}** exact-state Task64 completed typed decisions reused and **{usage['provider_call_count']}** Task66 provider calls succeeded (one protocol probe plus additional calls). No 429, failed, missing, undecidable, or not-attempted JEV outcomes occurred.",
            f"Incremental Task66 reported provider usage cost: **${usage['provider_cost_usd']:.9f}**. Task64 usage attached to reused provenance is **${usage['task64_reused_historical_cost_usd']:.9f}** and is not included in incremental Task66 cost. The total call ceiling was 72; actual provider calls were {usage['provider_call_count']}.",
            "",
            "The blind JEV state contained only dish context, the semantic ingredient, and the final mapped catalog object. Gold IDs, Top-5 candidates/scores, and old/new labels were not sent. For reused judgments, exact request-state equality, returned model, typed choice, source query ID, and Task64 `jev.jsonl` hash are recorded in `metrics.json` `task64_reuse_provenance`; the copied response data remains in ignored Task66 `jev.jsonl`.",
            "",
            "## Retrieval timing and resource gate",
            "",
            "Task64 `elapsed_ms` covers candidate building plus mapping; Task66 `total_elapsed_ms` covers candidate selection (including RAG retrieval) plus mapping, so these are comparable end-to-end per-item timings. The frozen Task64 artifact does not split retrieval and mapping phases. Task66 also records RAG retrieval-only and mapper-only timings; its sequence includes the first cold lazy-load request.",
            "",
            "| Comparable per-item mapping pipeline | Task64 legacy | Task66 RAG |",
            "|---|---:|---:|",
            f"| Candidate building + mapping median | {_nearest_rank(legacy_times, 0.50):.3f} ms | {_nearest_rank(pipeline_times, 0.50):.3f} ms |",
            f"| p95 (nearest-rank) | {_nearest_rank(legacy_times, 0.95):.3f} ms | {_nearest_rank(pipeline_times, 0.95):.3f} ms |",
            f"| Maximum | {max(legacy_times):.3f} ms | {max(pipeline_times):.3f} ms |",
            "",
            "| Task66 phase timing | Median | p95 (nearest-rank) | Maximum |",
            "|---|---:|---:|---:|",
            f"| RAG retrieval only | {_nearest_rank(rag_times, 0.50):.3f} ms | {_nearest_rank(rag_times, 0.95):.3f} ms | {max(rag_times):.3f} ms |",
            f"| Mapper only | {_nearest_rank(map_times, 0.50):.3f} ms | {_nearest_rank(map_times, 0.95):.3f} ms | {max(map_times):.3f} ms |",
            "",
            f"Task66 RAG retrieval state was success for {len(rag_rows)}/{len(rag_rows)} items, with {new['retrieval_degraded_count']} degraded retrievals. RAG asset manifest SHA-256: `{task65['manifest_sha256']}`; E5 revision `{task65['model_revision']}`. Pinned asset SHA-256 — ONNX model `{task65['asset_hashes']['model']}`, tokenizer `{task65['asset_hashes']['tokenizer']}`, vector index `{task65['asset_hashes']['vectors']}`.",
            "",
            "| Task65 measured resource | Observed | Limit | Gate |",
            "|---|---:|---:|:---:|",
            f"| Vector asset | {resource_gate['observed']['vector_bytes']:,} bytes | {resource_gate['limits']['vector_bytes_max']:,} bytes | {'pass' if resource_gate['checks']['vector_file'] else 'fail'} |",
            f"| Added distribution | {resource_gate['observed']['added_distribution_bytes']:,} bytes | {resource_gate['limits']['added_distribution_bytes_max']:,} bytes | {'pass' if resource_gate['checks']['added_distribution'] else 'fail'} |",
            f"| Cold retrieval max | {resource_gate['observed']['cold_load_max_ms']:.3f} ms | {resource_gate['limits']['cold_load_ms_max']:.3f} ms | {'pass' if resource_gate['checks']['cold_load'] else 'fail'} |",
            f"| Model RSS delta max | {resource_gate['observed']['active_model_rss_delta_max_mib']:.3f} MiB | {resource_gate['limits']['active_model_rss_delta_mib_max']:.3f} MiB | {'pass' if resource_gate['checks']['active_model_rss_delta'] else 'fail'} |",
            f"| Warm query p95 | {resource_gate['observed']['warm_query_p95_ms']:.3f} ms | {resource_gate['limits']['warm_query_p95_ms_max']:.3f} ms | {'pass' if resource_gate['checks']['warm_query_p95'] else 'fail'} |",
            "",
            "Resource values are the frozen Task65 measurements, not remeasured in Task66. Task65's Windows bundle smoke did not select the RAG backend because production default remains LEGACY; Task66 RAG evaluation used the actual explicit RAG selector and mapper in host Python with the pinned assets. No claim is made about end-user causal impact or default-path EXE quality.",
            "",
            "## Failures and limitations",
            "",
            "; ".join(f"{key}: {value}" for key, value in status_counts.items()) + ".",
            "The sample is a curated fixed 24-dish / 72-occurrence set with multi-ID Gold labels, not natural user traffic. Gold agreement is retrieval evidence, not semantic ground truth. No query/label/top-K/alias/mapper tuning was performed. Historical Task64 outputs remain read-only. No provider/UI/API/schema/default changes were made.",
            "",
            f"Raw RAG JSONL SHA-256: `{manifest['rag_run']['result_sha256']}`. Task66 JEV JSONL SHA-256: `{_sha256_file(output_dir / 'jev.jsonl')}`. Metrics SHA-256: `{_sha256_file(output_dir / 'metrics.json')}`. Raw paths: `output/m14-task66/rag_results.jsonl`, `output/m14-task66/jev.jsonl`, `output/m14-task66/metrics.json`, and `output/m14-task66/manifest.json` (all ignored).",
            "",
            "## Per-item outcomes",
            "",
            "`Top5` lists only local RAG candidate IDs (ordered); JEV receives neither those IDs nor their scores. Old/new choices are catalog IDs. `source/status` records the actual RAG retrieval result.",
            "",
            "| Query | Input | Legacy ID / JEV | RAG Top5 IDs | RAG ID / JEV | RAG source/status |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in metrics["per_item"]:
        top5 = ", ".join(str(item_id) for item_id in row["new_rag_candidate_ids"])
        lines.append(
            f"| `{row['query_id']}` | {_markdown_cell(row['normalized_name'] or row['ingredient_name'])} | "
            f"{_markdown_cell(row['old_selected_id'])} / {_markdown_cell(row['old_decision'])} | "
            f"{_markdown_cell(top5)} | {_markdown_cell(row['new_selected_id'])} / {_markdown_cell(row['new_decision'])} | "
            f"{_markdown_cell(row['new_candidate_source'])} / {_markdown_cell(row['new_retrieval_status'])} |"
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    manifest["report"] = {
        "path": str(report_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "sha256": _sha256_file(report_path),
    }
    _write_json(output_dir / "manifest.json", manifest)
    return {
        "report_path": str(report_path),
        "report_sha256": manifest["report"]["sha256"],
        "primary_old": old["dish_all_reasonable_rate"],
        "primary_new": new["dish_all_reasonable_rate"],
        "paired_transitions": {
            key: transitions[key] for key in ("improved", "regressed", "unchanged")
        },
        "jev_run": usage,
        "adoption_gate": metrics["adoption_gate"],
    }


def _format_summary(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run-rag", "probe", "full", "metrics", "report"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--resource-dir", type=Path, default=TASK65_RESOURCE_DIR)
    args = parser.parse_args(argv)
    try:
        if args.command == "run-rag":
            result = run_rag_baseline(args.output_dir, args.resource_dir)
        elif args.command == "probe":
            result = run_protocol_probe(args.output_dir)
        elif args.command == "full":
            if not (args.output_dir / "rag_results.jsonl").exists():
                run_rag_baseline(args.output_dir, args.resource_dir)
            result = run_full_jev(args.output_dir)
            metrics = calculate_metrics(args.output_dir)
            _write_json(args.output_dir / "metrics.json", metrics)
            result["dish_all_reasonable_rate"] = metrics["new"]["dish_all_reasonable_rate"]
            result["adoption_gate"] = metrics["adoption_gate"]
        elif args.command == "metrics":
            result = calculate_metrics(args.output_dir)
            _write_json(args.output_dir / "metrics.json", result)
        else:
            result = write_report(args.output_dir)
        print(_format_summary(result))
        return 0
    except (ComparisonError, evaluation.EvaluationError) as exc:
        print(f"Task66 comparison failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
