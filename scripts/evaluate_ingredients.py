"""Reproduce the M14 ingredient-mapping baseline and evaluate it with Jev."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from pelican_town_specials.catalog.mapping import map_ingredient
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.generation.orchestrator import _build_candidates

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "m14_ingredient_queries.json"
CATALOG_PATH = (
    REPO_ROOT / "resources" / "catalogs" / "stardew-1.6.15" / "vanilla-ingredients.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "m14-task64"
EXPECTED_CATALOG_SHA256 = "4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B"
EXPECTED_FIXTURE_SHA256 = "7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7"
EXPECTED_CATALOG_VERSION = "stardew-1.6.15-v1"
API_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
QUESTION_ID = "ingredient_mapping"
DECISIONS = ("reasonable", "unreasonable", "undecidable")
PROBE_QUERY_IDS = ("d01-i01", "d02-i01", "d03-i01")
FALLBACK_PREFIX = "catalog fallback"

CRITERIA = {
    "reasonable": (
        "The mapped Stardew Valley item is a plausible counterpart to the stated real-world "
        "ingredient in this dish: it is the same ingredient or a sensible ingredient-level "
        "substitute/category equivalent, and it is not an unrelated item or finished dish."
    ),
    "unreasonable": (
        "The mapped Stardew Valley item is a different ingredient, unrelated to the stated "
        "ingredient in this dish, or is a finished dish/drink instead of the ingredient."
    ),
    "undecidable": (
        "The dish and ingredient context do not provide enough information to decide, or "
        "multiple materially different interpretations remain plausible."
    ),
}
INSTRUCTIONS = (
    "Judge whether mapped_game_ingredient reasonably corresponds to semantic_ingredient "
    "in dish_context. Choose exactly one criterion. Judge culinary meaning, not item ID "
    "validity, and do not provide an explanation."
)


class EvaluationError(RuntimeError):
    """Raised when the frozen evaluation inputs or the typed Jev contract is invalid."""


class JEVProtocolError(EvaluationError):
    """Unexpected typed response, retaining the provider payload for review."""

    def __init__(self, message: str, raw_response: Any) -> None:
        super().__init__(message)
        self.raw_response = raw_response


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest().upper()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"could not read JSON input: {path.name}") from exc
    if not isinstance(value, dict):
        raise EvaluationError(f"JSON input must be an object: {path.name}")
    return value


def load_frozen_inputs() -> tuple[dict[str, Any], VanillaCatalog, str, str]:
    """Load and verify the pinned query fixture and Stardew catalog."""
    fixture_bytes = FIXTURE_PATH.read_bytes()
    catalog_bytes = CATALOG_PATH.read_bytes()
    fixture_sha = _sha256_bytes(fixture_bytes)
    catalog_sha = _sha256_bytes(catalog_bytes)
    if fixture_sha != EXPECTED_FIXTURE_SHA256:
        raise EvaluationError("query fixture SHA-256 differs from its frozen value")
    if catalog_sha != EXPECTED_CATALOG_SHA256:
        raise EvaluationError("pinned Stardew catalog SHA-256 differs from Task 62")

    fixture = _read_json(FIXTURE_PATH)
    if fixture.get("catalog_version") != EXPECTED_CATALOG_VERSION:
        raise EvaluationError("query fixture catalog version does not match the pinned catalog")
    catalog = VanillaCatalog.from_json(CATALOG_PATH)
    if catalog.version != EXPECTED_CATALOG_VERSION:
        raise EvaluationError("loaded catalog version differs from the frozen version")

    dishes = fixture.get("dishes")
    if not isinstance(dishes, list) or len(dishes) < 20:
        raise EvaluationError("frozen fixture must contain at least 20 dishes")
    query_ids: set[str] = set()
    query_count = 0
    banned = re.compile(r"\b(?:beef|lamb|chicken)\b|牛肉|羊肉|鸡肉", re.IGNORECASE)
    for dish in dishes:
        if not isinstance(dish, dict):
            raise EvaluationError("dish entry must be an object")
        for name_key in ("name_en", "name_zh"):
            name = dish.get(name_key)
            if not isinstance(name, str) or not name.strip():
                raise EvaluationError(f"dish is missing {name_key}")
            if banned.search(name):
                raise EvaluationError("fixture contains a dish with an excluded meat")
        ingredients = dish.get("ingredients")
        if not isinstance(ingredients, list):
            raise EvaluationError("dish ingredients must be a list")
        for ingredient in ingredients:
            query_count += 1
            query_id = ingredient.get("query_id")
            if not isinstance(query_id, str) or not query_id or query_id in query_ids:
                raise EvaluationError("query IDs must be unique non-empty strings")
            query_ids.add(query_id)
            for name_key in ("name", "normalized_name"):
                name = ingredient.get(name_key)
                if not isinstance(name, str) or not name.strip():
                    raise EvaluationError(f"query {query_id} is missing {name_key}")
                if banned.search(name):
                    raise EvaluationError("fixture contains an excluded meat query")
            gold_ids = ingredient.get("acceptable_item_ids")
            if not isinstance(gold_ids, list) or not gold_ids:
                raise EvaluationError(f"query {query_id} needs one or more accepted catalog IDs")
            if len(set(gold_ids)) != len(gold_ids):
                raise EvaluationError(f"query {query_id} has duplicate accepted catalog IDs")
            for item_id in gold_ids:
                item = catalog.require(item_id)
                if not item.usable_as_ingredient:
                    raise EvaluationError(f"query {query_id} Gold ID is not usable as an ingredient")
    if query_count < 60:
        raise EvaluationError("frozen fixture must contain at least 60 ingredient queries")
    return fixture, catalog, fixture_sha, catalog_sha


def iter_fixture_queries(fixture: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (dish, ingredient)
        for dish in fixture["dishes"]
        for ingredient in dish["ingredients"]
    ]


def run_baseline(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Run the exact current deterministic candidate builder and mapper offline."""
    fixture, catalog, fixture_sha, catalog_sha = load_frozen_inputs()
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    started_at = datetime.now(UTC).isoformat()
    for dish, ingredient in iter_fixture_queries(fixture):
        started = time.perf_counter()
        candidate_rows: list[dict[str, Any]] = []
        try:
            semantic = type(
                "SemanticIngredient",
                (),
                {"name": ingredient["name"], "normalized_name": ingredient["normalized_name"]},
            )()
            candidates = _build_candidates(semantic, catalog)
            for candidate in candidates:
                item = catalog.require(candidate.item_id)
                candidate_rows.append(
                    {
                        "item_id": candidate.item_id,
                        "score": candidate.score,
                        "name_en": item.display_name_en,
                        "name_zh": item.display_name_zh,
                    }
                )
            mapped = map_ingredient(
                semantic,
                candidates,
                catalog,
                language=Language.EN_US,
            )
            record = {
                "query_id": ingredient["query_id"],
                "dish_id": dish["dish_id"],
                "query_name": ingredient["name"],
                "normalized_name": ingredient["normalized_name"],
                "acceptable_item_ids": ingredient["acceptable_item_ids"],
                "candidate_ids": [row["item_id"] for row in candidate_rows],
                "candidates": candidate_rows,
                "selected_id": mapped.item_id,
                "selected_name_en": catalog.require(mapped.item_id).display_name_en,
                "selected_name_zh": catalog.require(mapped.item_id).display_name_zh,
                "mapping_reason": mapped.mapping_reason,
                "is_fallback": mapped.mapping_reason.startswith(FALLBACK_PREFIX),
                "status": "mapped",
            }
        except (AppError, TypeError, ValueError) as exc:
            record = {
                "query_id": ingredient["query_id"],
                "dish_id": dish["dish_id"],
                "query_name": ingredient["name"],
                "normalized_name": ingredient["normalized_name"],
                "acceptable_item_ids": ingredient["acceptable_item_ids"],
                "candidate_ids": [row["item_id"] for row in candidate_rows],
                "candidates": candidate_rows,
                "selected_id": None,
                "selected_name_en": None,
                "selected_name_zh": None,
                "mapping_reason": None,
                "is_fallback": False,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_code": getattr(exc, "code", None),
            }
        record["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        records.append(record)

    _write_jsonl(output_dir / "baseline.jsonl", records)
    summary = {
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "fixture_sha256": fixture_sha,
        "catalog_sha256": catalog_sha,
        "catalog_version": catalog.version,
        "dish_count": len(fixture["dishes"]),
        "query_count": len(records),
        "distinct_normalized_query_count": len({row["normalized_name"] for row in records}),
        "mapped_count": sum(row["status"] == "mapped" for row in records),
        "fallback_count": sum(row["status"] == "mapped" and row["is_fallback"] for row in records),
        "failure_count": sum(row["status"] == "failed" for row in records),
        "baseline_artifact": "baseline.jsonl",
    }
    _write_json(output_dir / "baseline_manifest.json", summary)
    return summary


def build_jev_state(
    dish: dict[str, Any], ingredient: dict[str, Any], baseline_row: dict[str, Any], catalog: VanillaCatalog
) -> dict[str, Any]:
    """Build a minimal Jev state without exposing Gold IDs or solution labels."""
    if baseline_row.get("status") != "mapped" or baseline_row.get("is_fallback"):
        raise EvaluationError("Jev state requires a non-fallback mapped catalog item")
    selected_id = baseline_row.get("selected_id")
    if not isinstance(selected_id, str):
        raise EvaluationError("baseline selected item ID is missing")
    item = catalog.require(selected_id)
    return {
        "dish_context": {"name_en": dish["name_en"], "name_zh": dish["name_zh"]},
        "semantic_ingredient": {
            "name": ingredient["name"],
            "normalized_name": ingredient["normalized_name"],
        },
        "mapped_game_ingredient": {
            "item_id": item.item_id,
            "name_en": item.display_name_en,
            "name_zh": item.display_name_zh,
        },
    }


def build_decisions_request(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": MODEL,
        "state": state,
        "questions": {
            QUESTION_ID: {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": CRITERIA,
            }
        },
    }


def parse_decisions_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EvaluationError("Jev response must be a JSON object")
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise EvaluationError("Jev response is missing typed answers")
    answer = answers.get(QUESTION_ID)
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise EvaluationError("Jev answer does not match the Choice protocol")
    choice = answer.get("choice")
    if choice not in DECISIONS:
        raise EvaluationError("Jev Choice returned an unknown option")
    confidence = answer.get("confidence")
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise EvaluationError("Jev Choice confidence is missing or invalid")
    model = payload.get("model")
    if not isinstance(model, str) or not (model == MODEL or model.startswith(f"{MODEL}-")):
        raise EvaluationError("Jev response model does not match the requested TypeSafe model")
    provider = payload.get("provider")
    if provider is not None and provider != "TypeSafe":
        raise EvaluationError("Jev response provider is not TypeSafe")

    probabilities = answer.get("probabilities")
    if probabilities is not None:
        if not isinstance(probabilities, dict) or set(probabilities) != set(DECISIONS):
            raise EvaluationError("Jev Choice probabilities do not match the fixed options")
        normalized: dict[str, float] = {}
        for key, value in probabilities.items():
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise EvaluationError("Jev Choice probability is invalid")
            normalized[key] = float(value)
        if not math.isclose(sum(normalized.values()), 1.0, abs_tol=0.05):
            raise EvaluationError("Jev Choice probabilities do not sum to one")
        probabilities = normalized

    usage = payload.get("usage")
    if usage is not None and not isinstance(usage, dict):
        raise EvaluationError("Jev usage must be an object when present")
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if cost is not None and (
        not isinstance(cost, (int, float))
        or isinstance(cost, bool)
        or not math.isfinite(cost)
        or cost < 0
    ):
        raise EvaluationError("Jev usage cost is invalid")
    return {
        "decision": choice,
        "confidence": float(confidence),
        "probabilities": probabilities,
        "model": model,
        "provider": provider,
        "usage": usage,
    }


def call_jev(
    state: dict[str, Any],
    api_key: str,
    *,
    opener: Any = urlopen,
    timeout: float = 45.0,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    request_body = build_decisions_request(state)
    request = Request(
        API_URL,
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with opener(request, timeout=timeout) as response:
            response_text = response.read().decode("utf-8")
            status = getattr(response, "status", 200)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise EvaluationError(f"OpenRouter Decisions API returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise EvaluationError(f"OpenRouter Decisions API request failed: {exc.reason}") from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    if status < 200 or status >= 300:
        raise EvaluationError(f"OpenRouter Decisions API returned HTTP {status}")
    try:
        raw_response = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise EvaluationError("OpenRouter Decisions API returned non-JSON content") from exc
    try:
        parsed = parse_decisions_response(raw_response)
    except EvaluationError as exc:
        raise JEVProtocolError(str(exc), raw_response) from exc
    return parsed, raw_response, elapsed_ms


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]], *, append: bool = False) -> None:
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationError(f"invalid JSONL artifact at line {line_number}") from exc
        if not isinstance(row, dict):
            raise EvaluationError(f"JSONL artifact row {line_number} must be an object")
        rows.append(row)
    return rows


def _baseline_index(output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture, catalog, fixture_sha, catalog_sha = load_frozen_inputs()
    manifest = _read_json(output_dir / "baseline_manifest.json")
    if manifest.get("fixture_sha256") != fixture_sha or manifest.get("catalog_sha256") != catalog_sha:
        raise EvaluationError("baseline artifact hashes do not match frozen inputs")
    rows = _read_jsonl(output_dir / "baseline.jsonl")
    if len(rows) != manifest.get("query_count"):
        raise EvaluationError("baseline artifact row count does not match its manifest")
    return {row["query_id"]: row for row in rows}, {"fixture": fixture, "catalog": catalog}


def _run_query_ids(
    query_ids: list[str],
    output_dir: Path,
    *,
    stage: str,
) -> dict[str, Any]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise EvaluationError("OPENROUTER_API_KEY is not present in this process")
    baseline_by_id, inputs = _baseline_index(output_dir)
    fixture = inputs["fixture"]
    catalog = inputs["catalog"]
    fixture_sha = _sha256_bytes(FIXTURE_PATH.read_bytes())
    catalog_sha = _sha256_bytes(CATALOG_PATH.read_bytes())
    ingredient_by_id = {
        ingredient["query_id"]: (dish, ingredient)
        for dish, ingredient in iter_fixture_queries(fixture)
    }
    artifact_path = output_dir / "jev.jsonl"
    existing = _read_jsonl(artifact_path)
    latest = {row.get("query_id"): row for row in existing if isinstance(row.get("query_id"), str)}
    completed_before = {
        query_id
        for query_id, row in latest.items()
        if row.get("status") == "completed"
        and row.get("fixture_sha256") == fixture_sha
        and row.get("catalog_sha256") == catalog_sha
    }
    requested = 0
    reused = 0
    for query_id in query_ids:
        baseline_row = baseline_by_id.get(query_id)
        pair = ingredient_by_id.get(query_id)
        if baseline_row is None or pair is None:
            raise EvaluationError(f"probe references unknown query ID: {query_id}")
        if baseline_row.get("status") == "failed":
            raise EvaluationError(f"baseline failed for query ID: {query_id}")
        if baseline_row.get("is_fallback"):
            raise EvaluationError(f"Jev query must have a non-fallback mapping: {query_id}")
        if query_id in completed_before:
            reused += 1
            continue
        dish, ingredient = pair
        state = build_jev_state(dish, ingredient, baseline_row, catalog)
        started_at = datetime.now(UTC).isoformat()
        try:
            parsed, raw_response, elapsed_ms = call_jev(state, api_key)
        except Exception as exc:
            failure = {
                "query_id": query_id,
                "status": "failed",
                "stage": stage,
                "failure_type": type(exc).__name__,
                "failure_message": str(exc)[:600],
                "started_at_utc": started_at,
                "fixture_sha256": fixture_sha,
                "catalog_sha256": catalog_sha,
                "request_state": state,
                "raw_response": getattr(exc, "raw_response", None),
            }
            _write_jsonl(artifact_path, [failure], append=True)
            raise EvaluationError(
                f"Jev {stage} stopped at {query_id}; failure was recorded in ignored output"
            ) from exc
        row = {
            "query_id": query_id,
            "status": "completed",
            "stage": stage,
            "started_at_utc": started_at,
            "elapsed_ms": elapsed_ms,
            "fixture_sha256": fixture_sha,
            "catalog_sha256": catalog_sha,
            "request_state": state,
            **parsed,
            "raw_response": raw_response,
        }
        _write_jsonl(artifact_path, [row], append=True)
        requested += 1
    return {"stage": stage, "requested": requested, "reused": reused, "artifact": str(artifact_path)}


def run_probe(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    return _run_query_ids(list(PROBE_QUERY_IDS), output_dir, stage="protocol_probe")


def run_full(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    baseline_by_id, _ = _baseline_index(output_dir)
    query_ids = [
        query_id
        for query_id, row in baseline_by_id.items()
        if row.get("status") == "mapped" and not row.get("is_fallback")
    ]
    result = _run_query_ids(query_ids, output_dir, stage="full")
    result["query_count"] = len(query_ids)
    return result


def build_metrics(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    baseline_by_id, inputs = _baseline_index(output_dir)
    fixture = inputs["fixture"]
    jev_rows = _read_jsonl(output_dir / "jev.jsonl")
    latest = {row.get("query_id"): row for row in jev_rows if isinstance(row.get("query_id"), str)}
    successful_attempts = [row for row in jev_rows if row.get("status") == "completed"]
    failed_attempts = [row for row in jev_rows if row.get("status") == "failed"]
    elapsed_values = sorted(
        row["elapsed_ms"]
        for row in successful_attempts
        if isinstance(row.get("elapsed_ms"), (int, float))
    )

    def percentile(values: list[float], quantile: float) -> float | None:
        if not values:
            return None
        rank = max(1, math.ceil(quantile * len(values)))
        return round(float(values[rank - 1]), 3)

    usage_rows = [row.get("usage") for row in successful_attempts if isinstance(row.get("usage"), dict)]
    costs = [usage["cost"] for usage in usage_rows if isinstance(usage.get("cost"), (int, float))]
    input_tokens = [
        usage.get("input_tokens", usage.get("inputTokens", 0)) for usage in usage_rows
    ]
    output_tokens = [
        usage.get("output_tokens", usage.get("outputTokens", 0)) for usage in usage_rows
    ]
    model_versions = sorted(
        {row["model"] for row in successful_attempts if isinstance(row.get("model"), str)}
    )
    providers = sorted(
        {row["provider"] for row in successful_attempts if isinstance(row.get("provider"), str)}
    )
    results: list[dict[str, Any]] = []
    all_queries = [
        ingredient
        for dish in fixture["dishes"]
        for ingredient in dish["ingredients"]
    ]
    determinate = {"reasonable", "unreasonable"}
    for dish in fixture["dishes"]:
        for ingredient in dish["ingredients"]:
            baseline = baseline_by_id[ingredient["query_id"]]
            jev = latest.get(ingredient["query_id"], {})
            decision = jev.get("decision") if jev.get("status") == "completed" else None
            record = {
                "query_id": ingredient["query_id"],
                "dish_id": dish["dish_id"],
                "status": baseline.get("status"),
                "is_fallback": baseline.get("is_fallback", False),
                "selected_id": baseline.get("selected_id"),
                "candidate_ids": baseline.get("candidate_ids", []),
                "acceptable_item_ids": ingredient["acceptable_item_ids"],
                "selected_id_in_gold": baseline.get("selected_id")
                in set(ingredient["acceptable_item_ids"]),
                "jev_status": jev.get("status", "not_run"),
                "decision": decision,
                "confidence": jev.get("confidence"),
            }
            results.append(record)

    determinate_rows = [
        row
        for row in results
        if row["status"] == "mapped" and not row["is_fallback"] and row["decision"] in determinate
    ]
    reasonable_rows = [row for row in determinate_rows if row["decision"] == "reasonable"]
    fallback_count = sum(row["status"] == "mapped" and row["is_fallback"] for row in results)
    baseline_failures = sum(row["status"] == "failed" for row in results)
    undecidable_count = sum(row["decision"] == "undecidable" for row in results)
    api_failures = sum(row["jev_status"] == "failed" for row in results)
    all_reasonable_dishes = sum(
        len(rows) == 3
        and all(
            row["status"] == "mapped"
            and not row["is_fallback"]
            and row["decision"] == "reasonable"
            for row in rows
        )
        for dish in fixture["dishes"]
        for rows in [[row for row in results if row["dish_id"] == dish["dish_id"]]]
    )
    evaluable_dishes = sum(
        len(rows) == 3
        and all(
            row["status"] == "mapped"
            and not row["is_fallback"]
            and row["decision"] in determinate
            for row in rows
        )
        for dish in fixture["dishes"]
        for rows in [[row for row in results if row["dish_id"] == dish["dish_id"]]]
    )
    gold_recall_values: list[float] = []
    gold_hit_count = 0
    selected_gold_count = 0
    retrieval_miss_count = 0
    rerank_miss_count = 0
    decision_gold_cross: dict[str, dict[str, int]] = {
        decision: {"selected_id_in_gold": 0, "selected_id_not_in_gold": 0}
        for decision in DECISIONS
    }
    disagreements: list[dict[str, Any]] = []
    for row in results:
        gold_ids = set(row["acceptable_item_ids"])
        candidate_ids = set(row["candidate_ids"])
        overlap = candidate_ids & gold_ids
        gold_recall_values.append(len(overlap) / len(gold_ids))
        gold_hit_count += bool(overlap)
        selected_gold_count += row["selected_id_in_gold"]
        retrieval_miss_count += not bool(overlap)
        rerank_miss_count += bool(overlap) and row["selected_id"] not in gold_ids
        if row["decision"] in determinate:
            gold_bucket = "selected_id_in_gold" if row["selected_id_in_gold"] else "selected_id_not_in_gold"
            decision_gold_cross[row["decision"]][gold_bucket] += 1
            if (row["decision"] == "reasonable") != row["selected_id_in_gold"]:
                disagreements.append(
                    {
                        "query_id": row["query_id"],
                        "dish_id": row["dish_id"],
                        "jev_choice": row["decision"],
                        "confidence": row["confidence"],
                        "selected_id_in_gold": row["selected_id_in_gold"],
                    }
                )

    total = len(results)
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "fixture_sha256": _sha256_bytes(FIXTURE_PATH.read_bytes()),
        "catalog_sha256": _sha256_bytes(CATALOG_PATH.read_bytes()),
        "catalog_version": EXPECTED_CATALOG_VERSION,
        "dish_count": len(fixture["dishes"]),
        "query_occurrence_count": total,
        "distinct_normalized_query_count": len({item["normalized_name"] for item in all_queries}),
        "baseline": {
            "fallback_count_excluded_from_accuracy": fallback_count,
            "mapping_failure_count": baseline_failures,
            "gold_recall_at_5_mean": sum(gold_recall_values) / total if total else None,
            "gold_hit_at_5": {"numerator": gold_hit_count, "denominator": total},
            "selected_gold_match": {"numerator": selected_gold_count, "denominator": total},
            "candidate_retrieval_miss_count": retrieval_miss_count,
            "candidate_rerank_or_selection_miss_count": rerank_miss_count,
            "jev_choice_by_gold_selected_id_cross_tab": decision_gold_cross,
            "jev_gold_disagreements": disagreements,
            "jev_gold_disagreement_count": len(disagreements),
        },
        "jev": {
            "model_requested": MODEL,
            "model_versions_observed": model_versions,
            "providers_observed": providers,
            "successful_provider_call_count": len(successful_attempts),
            "failed_attempt_record_count": len(failed_attempts),
            "unique_query_failure_count": sum(row.get("status") == "failed" for row in latest.values()),
            "usage_cost_usd_total": sum(costs) if costs else None,
            "input_tokens_total": sum(input_tokens) if input_tokens else None,
            "output_tokens_total": sum(output_tokens) if output_tokens else None,
            "latency_ms_p50_nearest_rank": percentile(elapsed_values, 0.50),
            "latency_ms_p95_nearest_rank": percentile(elapsed_values, 0.95),
            "completed_count": sum(row["jev_status"] == "completed" for row in results),
            "reasonable_count": sum(row["decision"] == "reasonable" for row in results),
            "unreasonable_count": sum(row["decision"] == "unreasonable" for row in results),
            "undecidable_count": undecidable_count,
            "call_failure_count": api_failures,
            "nonfallback_reasonable_rate": {
                "numerator": len(reasonable_rows),
                "denominator": len(determinate_rows),
                "value": len(reasonable_rows) / len(determinate_rows) if determinate_rows else None,
                "denominator_definition": "completed, non-fallback mappings with a determinate Jev Choice",
            },
            "reasonable_coverage_of_fixed_query_set": {
                "numerator": sum(row["decision"] == "reasonable" for row in results),
                "denominator": total,
                "value": sum(row["decision"] == "reasonable" for row in results) / total if total else None,
            },
            "dish_all_reasonable_rate": {
                "numerator": all_reasonable_dishes,
                "denominator": len(fixture["dishes"]),
                "value": all_reasonable_dishes / len(fixture["dishes"]) if fixture["dishes"] else None,
                "rule": "a dish counts only when all three rows are non-fallback and Jev says reasonable",
            },
            "dish_all_reasonable_evaluable_rate": {
                "numerator": all_reasonable_dishes,
                "denominator": evaluable_dishes,
                "value": all_reasonable_dishes / evaluable_dishes if evaluable_dishes else None,
                "rule": "denominator dishes have three non-fallback determinate Jev decisions",
            },
        },
    }
    _write_json(output_dir / "metrics.json", report)
    _write_jsonl(output_dir / "query_results.jsonl", results)
    return report


def _format_summary(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("baseline", "probe", "full", "metrics"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        if args.command == "baseline":
            result = run_baseline(args.output_dir)
        elif args.command == "probe":
            result = run_probe(args.output_dir)
        elif args.command == "full":
            result = run_full(args.output_dir)
        else:
            result = build_metrics(args.output_dir)
        print(_format_summary(result))
        return 0
    except EvaluationError as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
