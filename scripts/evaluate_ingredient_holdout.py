"""Validate and freeze the M14 Task 66.1 pre-run ingredient holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

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

from scripts import compare_ingredient_rag as previous_comparison
from scripts import evaluate_ingredients as jev_protocol

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "m14_ingredient_holdout_queries.json"
TASK64_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "m14_ingredient_queries.json"
CATALOG_PATH = (
    REPO_ROOT / "resources" / "catalogs" / "stardew-1.6.15" / "vanilla-ingredients.json"
)
TASK65_ASSET_ROOT = REPO_ROOT / "output" / "m14-task65" / "ingredient-rag-spm"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "m14-task66-1"
LEGACY_RESULT_NAME = "legacy_results.jsonl"
RAG_RESULT_NAME = "rag_results.jsonl"
JEV_RESULT_NAME = "jev.jsonl"
RUN_MANIFEST_NAME = "manifest.json"
METRICS_NAME = "metrics.json"
REPORT_PATH = REPO_ROOT / "docs" / "development" / "M14_TASK66_1_EXPANDED_HOLDOUT.md"

CONTRACT_ID = "m14-task66-1-expanded-ingredient-holdout-v1"
FROZEN_FIXTURE_SHA256 = "1E9B49077589E8A9B9699DD4FC140359DF1A9A6389D75C7911ACE4A14D92A25C"
FROZEN_FIXTURE_GIT_BLOB_SHA = "7856d22f32a51de937cf6cf5f7cedf7a23aeff85"
EXPECTED_TASK64_FIXTURE_SHA256 = "7B49E7B88393CCC627DD4AEC7545AC45FDAF4786081D2E9BCC973B202796EEB7"
EXPECTED_CATALOG_SHA256 = "4D07E9B3EE45670543C1BDCFFA69F84CC2FB2829C4DB4CF2BEFD273B36374E2B"
EXPECTED_CATALOG_VERSION = "stardew-1.6.15-v1"
MAX_JEV_PROVIDER_CALLS = 576
JEV_BASELINE_MODEL = "typesafe/jev-1.13-20260917"
BOOTSTRAP_SEED = 661_001
BOOTSTRAP_REPLICATES = 10_000
FALLBACK_PREFIX = "catalog fallback"
EXPECTED_DISH_COUNT = 96
EXPECTED_INGREDIENTS_PER_DISH = 3
EXPECTED_QUERY_COUNT = EXPECTED_DISH_COUNT * EXPECTED_INGREDIENTS_PER_DISH
EXPECTED_DISHES_PER_STRATUM = 24
MIN_DISTINCT_NORMALIZED_QUERIES = 80
MIN_QUERIES_ABSENT_FROM_TASK64 = 40
MIN_QUERIES_PER_LANGUAGE = 90
STRATA = (
    "direct_name",
    "bilingual_or_synonym",
    "ambiguous_name",
    "raw_vs_prepared",
)
LANGUAGES = ("en", "zh")
EXCLUDED_MEAT = re.compile(r"\b(?:beef|lamb|chicken|pork)\b|牛肉|羊肉|鸡肉|猪肉", re.IGNORECASE)
HAN_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
LATIN_CHARACTER = re.compile(r"[A-Za-z]")

TASK65_ASSETS = {
    "manifest": (
        "ingredient-index.manifest.json",
        "93E9AED32AA68DEC48D1C6E102C4F82FABDB916B84CD852E807F85BF3284DE85",
    ),
    "vectors": (
        "ingredient-vectors.f32",
        "D640532CBD3316EED3A6831939A7289858D492E025D3223ECCFA7D93D8D4EC58",
    ),
    "model_int8": (
        "model-int8.onnx",
        "739C8F25BBE6D8A6001CD2F048701DA9879140CC67D4E9327716111E869DD717",
    ),
    "sentencepiece_tokenizer": (
        "sentencepiece.bpe.model",
        "CFC8146ABE2A0488E9E2A0C56DE7952F7C11AB059ECA145A0A727AFCE0DB2865",
    ),
}


class HoldoutFixtureError(RuntimeError):
    """Raised when a pre-run fixture does not meet the frozen sample contract."""


def normalize_query(value: str) -> str:
    """Normalize text for exact Query uniqueness and old-set overlap checks."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HoldoutFixtureError(f"could not read JSON input: {path.name}") from exc
    if not isinstance(value, dict):
        raise HoldoutFixtureError(f"JSON input must be an object: {path.name}")
    return value


def load_raw_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    """Read the new fixture, historical fixture, and frozen catalog without mapping."""
    fixture = _read_json(FIXTURE_PATH)
    old_fixture = _read_json(TASK64_FIXTURE_PATH)
    catalog = _read_json(CATALOG_PATH)
    items = catalog.get("items")
    if not isinstance(items, list):
        raise HoldoutFixtureError("catalog items must be a list")
    catalog_items: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("itemId"), (str, int)):
            raise HoldoutFixtureError("catalog item is missing its item ID")
        catalog_items[str(item["itemId"])] = item
    return fixture, old_fixture, catalog_items


def validate_fixture(
    fixture: dict[str, Any],
    old_fixture: dict[str, Any],
    catalog_items: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate only fixture shape, sample composition, and catalog Gold IDs."""
    if fixture.get("catalog_version") != EXPECTED_CATALOG_VERSION:
        raise HoldoutFixtureError("fixture catalog version does not match the frozen catalog")
    dishes = fixture.get("dishes")
    if not isinstance(dishes, list) or len(dishes) != EXPECTED_DISH_COUNT:
        raise HoldoutFixtureError("fixture must contain exactly 96 dishes")

    old_dishes = old_fixture.get("dishes")
    if not isinstance(old_dishes, list):
        raise HoldoutFixtureError("Task64 fixture dishes must be a list")
    old_english_dishes = {
        normalize_query(dish["name_en"])
        for dish in old_dishes
        if isinstance(dish, dict) and isinstance(dish.get("name_en"), str)
    }
    old_chinese_dishes = {
        normalize_query(dish["name_zh"])
        for dish in old_dishes
        if isinstance(dish, dict) and isinstance(dish.get("name_zh"), str)
    }
    old_queries = {
        normalize_query(ingredient[name_key])
        for dish in old_dishes
        if isinstance(dish, dict) and isinstance(dish.get("ingredients"), list)
        for ingredient in dish["ingredients"]
        if isinstance(ingredient, dict)
        for name_key in ("normalized_name", "name")
        if isinstance(ingredient.get(name_key), str) and ingredient[name_key].strip()
    }

    dish_ids: set[str] = set()
    english_dish_names: set[str] = set()
    chinese_dish_names: set[str] = set()
    query_ids: set[str] = set()
    normalized_queries: set[str] = set()
    query_languages: Counter[str] = Counter()
    dishes_by_stratum: Counter[str] = Counter()
    dish_families: set[str] = set()
    cuisine_styles: set[str] = set()
    all_gold_ids_usable = True
    query_count = 0

    for dish in dishes:
        if not isinstance(dish, dict):
            raise HoldoutFixtureError("dish entry must be an object")
        dish_id = dish.get("dish_id")
        if not isinstance(dish_id, str) or not dish_id.strip() or dish_id in dish_ids:
            raise HoldoutFixtureError("dish IDs must be unique non-empty strings")
        dish_ids.add(dish_id)
        for field, seen_names, old_names, language_name in (
            ("name_en", english_dish_names, old_english_dishes, "English"),
            ("name_zh", chinese_dish_names, old_chinese_dishes, "Chinese"),
        ):
            value = dish.get(field)
            if not isinstance(value, str) or not value.strip():
                raise HoldoutFixtureError(f"dish {dish_id} is missing {field}")
            normalized_name = normalize_query(value)
            if normalized_name in seen_names:
                raise HoldoutFixtureError(f"new fixture repeats a {language_name} dish name")
            if normalized_name in old_names:
                raise HoldoutFixtureError(f"dish name overlaps Task64: {field}")
            if EXCLUDED_MEAT.search(value):
                raise HoldoutFixtureError("fixture contains an excluded meat dish")
            seen_names.add(normalized_name)

        stratum = dish.get("stratum")
        if stratum not in STRATA:
            raise HoldoutFixtureError(f"dish {dish_id} has an unknown stratum")
        dishes_by_stratum[stratum] += 1
        for field, values in (("dish_family", dish_families), ("cuisine_style", cuisine_styles)):
            value = dish.get(field)
            if not isinstance(value, str) or not value.strip():
                raise HoldoutFixtureError(f"dish {dish_id} is missing descriptive field {field}")
            values.add(normalize_query(value))

        ingredients = dish.get("ingredients")
        if not isinstance(ingredients, list) or len(ingredients) != EXPECTED_INGREDIENTS_PER_DISH:
            raise HoldoutFixtureError(f"dish {dish_id} must contain exactly three ingredients")
        for ingredient in ingredients:
            if not isinstance(ingredient, dict):
                raise HoldoutFixtureError(f"dish {dish_id} has a non-object ingredient")
            query_count += 1
            query_id = ingredient.get("query_id")
            if not isinstance(query_id, str) or not query_id.strip() or query_id in query_ids:
                raise HoldoutFixtureError("query IDs must be unique non-empty strings")
            query_ids.add(query_id)
            name = ingredient.get("name")
            normalized_name = ingredient.get("normalized_name")
            if not isinstance(name, str) or not name.strip():
                raise HoldoutFixtureError(f"query {query_id} is missing name")
            if not isinstance(normalized_name, str) or not normalized_name.strip():
                raise HoldoutFixtureError(f"query {query_id} is missing normalized_name")
            if normalize_query(name) != normalize_query(normalized_name):
                raise HoldoutFixtureError(f"query {query_id} name and normalized_name differ")
            if EXCLUDED_MEAT.search(name) or EXCLUDED_MEAT.search(normalized_name):
                raise HoldoutFixtureError("fixture contains an excluded meat query")

            language = ingredient.get("input_language")
            has_han = bool(HAN_CHARACTER.search(name))
            has_latin = bool(LATIN_CHARACTER.search(name))
            if language not in LANGUAGES or (language == "zh" and (not has_han or has_latin)) or (
                language == "en" and (not has_latin or has_han)
            ):
                raise HoldoutFixtureError(f"query {query_id} does not match input_language")
            query_languages[language] += 1
            normalized_queries.add(normalize_query(normalized_name))

            gold_ids = ingredient.get("acceptable_item_ids")
            if not isinstance(gold_ids, list) or not gold_ids:
                raise HoldoutFixtureError(f"query {query_id} needs one or more acceptable Gold IDs")
            if any(not isinstance(item_id, str) or not item_id.strip() for item_id in gold_ids):
                raise HoldoutFixtureError(f"query {query_id} has a malformed Gold ID")
            if len(gold_ids) != len(set(gold_ids)):
                raise HoldoutFixtureError(f"query {query_id} has duplicate acceptable Gold IDs")
            for item_id in gold_ids:
                item = catalog_items.get(item_id)
                if item is None or not item.get("usableAsIngredient") or item.get("isCategory"):
                    all_gold_ids_usable = False
                    raise HoldoutFixtureError(
                        f"query {query_id} Gold ID {item_id} is not a usable ingredient"
                    )
            gold_note = ingredient.get("gold_note")
            if not isinstance(gold_note, str) or not gold_note.strip():
                raise HoldoutFixtureError(f"query {query_id} is missing its Gold rationale")

    if query_count != EXPECTED_QUERY_COUNT:
        raise HoldoutFixtureError("fixture must contain exactly 288 ingredient queries")
    if set(dishes_by_stratum) != set(STRATA) or any(
        count != EXPECTED_DISHES_PER_STRATUM for count in dishes_by_stratum.values()
    ):
        raise HoldoutFixtureError("each frozen stratum must contain exactly 24 dishes")
    if len(normalized_queries) < MIN_DISTINCT_NORMALIZED_QUERIES:
        raise HoldoutFixtureError("fixture must contain at least 80 distinct normalized queries")
    absent_from_task64 = normalized_queries - old_queries
    if len(absent_from_task64) < MIN_QUERIES_ABSENT_FROM_TASK64:
        raise HoldoutFixtureError("fixture must contain at least 40 normalized queries absent from Task64")
    if any(query_languages[language] < MIN_QUERIES_PER_LANGUAGE for language in LANGUAGES):
        raise HoldoutFixtureError("fixture must contain at least 90 English and 90 Chinese inputs")

    return {
        "dish_count": len(dishes),
        "query_count": query_count,
        "dishes_by_stratum": {stratum: dishes_by_stratum[stratum] for stratum in STRATA},
        "distinct_normalized_query_count": len(normalized_queries),
        "queries_absent_from_task64": len(absent_from_task64),
        "queries_by_language": {language: query_languages[language] for language in LANGUAGES},
        "unique_dish_name_count_en": len(english_dish_names),
        "unique_dish_name_count_zh": len(chinese_dish_names),
        "dish_family_count": len(dish_families),
        "cuisine_style_count": len(cuisine_styles),
        "all_gold_ids_usable": all_gold_ids_usable,
        "gold_id_occurrence_count": query_count,
    }


def load_frozen_inputs() -> dict[str, Any]:
    """Verify the new fixture, unchanged Task64 fixture, and pinned catalog."""
    fixture_bytes = FIXTURE_PATH.read_bytes()
    old_fixture_bytes = TASK64_FIXTURE_PATH.read_bytes()
    catalog_bytes = CATALOG_PATH.read_bytes()
    fixture, old_fixture, catalog_items = load_raw_inputs()
    fixture_sha = _sha256_bytes(fixture_bytes)
    old_fixture_sha = _sha256_bytes(old_fixture_bytes)
    catalog_sha = _sha256_bytes(catalog_bytes)
    if fixture_sha != FROZEN_FIXTURE_SHA256:
        raise HoldoutFixtureError("expanded fixture differs from the parent-reviewed frozen SHA-256")
    if _git_blob_sha(FIXTURE_PATH) != FROZEN_FIXTURE_GIT_BLOB_SHA:
        raise HoldoutFixtureError("expanded fixture Git blob differs from the parent-reviewed frozen value")
    if old_fixture_sha != EXPECTED_TASK64_FIXTURE_SHA256:
        raise HoldoutFixtureError("Task64 fixture differs from its frozen SHA-256")
    if catalog_sha != EXPECTED_CATALOG_SHA256:
        raise HoldoutFixtureError("catalog differs from the frozen M14 SHA-256")
    catalog = _read_json(CATALOG_PATH)
    if catalog.get("catalogVersion") != EXPECTED_CATALOG_VERSION:
        raise HoldoutFixtureError("catalog version differs from the frozen M14 version")
    summary = validate_fixture(fixture, old_fixture, catalog_items)
    return {
        "fixture": fixture,
        "old_fixture": old_fixture,
        "catalog_items": catalog_items,
        "fixture_sha256": fixture_sha,
        "task64_fixture_sha256": old_fixture_sha,
        "catalog_sha256": catalog_sha,
        "catalog_version": EXPECTED_CATALOG_VERSION,
        "summary": summary,
    }


def iter_fixture_queries(fixture: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (dish, ingredient)
        for dish in fixture["dishes"]
        for ingredient in dish["ingredients"]
    ]


def _git_blob_sha(path: Path) -> str:
    relative_path = path.relative_to(REPO_ROOT).as_posix()
    try:
        result = subprocess.run(
            ["git", "hash-object", f"--path={relative_path}", str(path)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HoldoutFixtureError("could not compute the fixture Git blob SHA") from exc
    return result.stdout.strip()


def task65_asset_hashes() -> dict[str, str]:
    """Verify the local pinned Task65 RAG asset files without running retrieval."""
    hashes: dict[str, str] = {}
    for asset_name, (filename, expected_sha256) in TASK65_ASSETS.items():
        path = TASK65_ASSET_ROOT / filename
        if not path.is_file():
            raise HoldoutFixtureError(f"required Task65 asset is missing: {filename}")
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise HoldoutFixtureError(f"Task65 asset hash differs from the frozen value: {filename}")
        hashes[asset_name] = actual_sha256
    return hashes


def build_freeze_manifest() -> dict[str, Any]:
    """Capture pre-mapping input and Task65 asset hashes for parent review."""
    frozen = load_frozen_inputs()
    return {
        "acceptance_contract_id": CONTRACT_ID,
        "phase": "A_fixture_frozen_before_mapping",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "fixture_path": "tests/fixtures/m14_ingredient_holdout_queries.json",
        "fixture_worktree_sha256": frozen["fixture_sha256"],
        "fixture_git_blob_sha": _git_blob_sha(FIXTURE_PATH),
        "task64_fixture_sha256": frozen["task64_fixture_sha256"],
        "catalog_path": "resources/catalogs/stardew-1.6.15/vanilla-ingredients.json",
        "catalog_version": frozen["catalog_version"],
        "catalog_sha256": frozen["catalog_sha256"],
        "task65_assets": task65_asset_hashes(),
        "sample_summary": frozen["summary"],
    }


def _write_manifest(output_dir: Path, manifest: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "freeze_manifest.json"
    if path.exists():
        existing = _read_json(path)
        if (
            existing.get("acceptance_contract_id") == CONTRACT_ID
            and existing.get("fixture_worktree_sha256") == FROZEN_FIXTURE_SHA256
            and existing.get("fixture_git_blob_sha") == FROZEN_FIXTURE_GIT_BLOB_SHA
        ):
            return path
        raise HoldoutFixtureError("refusing to overwrite a different freeze manifest")
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HoldoutFixtureError(f"could not read ignored run artifact: {path.name}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HoldoutFixtureError(f"invalid JSONL in {path.name}:{line_number}") from exc
        if not isinstance(row, dict):
            raise HoldoutFixtureError(f"non-object JSONL row in {path.name}:{line_number}")
        rows.append(row)
    return rows


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl_exclusive(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _run_manifest(output_dir: Path) -> dict[str, Any]:
    frozen = load_frozen_inputs()
    freeze_path = output_dir / "freeze_manifest.json"
    if not freeze_path.is_file():
        raise HoldoutFixtureError("Stage A freeze manifest is missing; run the freeze command first")
    freeze = _read_json(freeze_path)
    if (
        freeze.get("acceptance_contract_id") != CONTRACT_ID
        or freeze.get("fixture_worktree_sha256") != FROZEN_FIXTURE_SHA256
        or freeze.get("fixture_git_blob_sha") != FROZEN_FIXTURE_GIT_BLOB_SHA
        or freeze.get("catalog_sha256") != frozen["catalog_sha256"]
    ):
        raise HoldoutFixtureError("Stage A freeze manifest does not match the reviewed inputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / RUN_MANIFEST_NAME
    if manifest_path.exists():
        manifest = _read_json(manifest_path)
        if (
            manifest.get("acceptance_contract_id") != CONTRACT_ID
            or manifest.get("fixture_sha256") != FROZEN_FIXTURE_SHA256
            or manifest.get("catalog_sha256") != frozen["catalog_sha256"]
        ):
            raise HoldoutFixtureError("ignored output manifest belongs to different frozen inputs")
        return manifest
    manifest = {
        "acceptance_contract_id": CONTRACT_ID,
        "phase": "B_local_mapping_and_blind_jev",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fixture_path": "tests/fixtures/m14_ingredient_holdout_queries.json",
        "fixture_sha256": FROZEN_FIXTURE_SHA256,
        "fixture_git_blob_sha": FROZEN_FIXTURE_GIT_BLOB_SHA,
        "catalog_sha256": frozen["catalog_sha256"],
        "catalog_version": frozen["catalog_version"],
        "freeze_manifest_sha256": _sha256_file(freeze_path),
        "sample_summary": frozen["summary"],
        "task65_assets": freeze.get("task65_assets"),
    }
    _write_json(manifest_path, manifest)
    return manifest


class _ObservedRetriever:
    """Capture actual calls and fallback state from the production RAG seam."""

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
def _select_observed_retriever(observed: _ObservedRetriever):
    original = orchestrator._get_default_ingredient_rag_retriever
    orchestrator._get_default_ingredient_rag_retriever = lambda _catalog: observed
    try:
        yield
    finally:
        orchestrator._get_default_ingredient_rag_retriever = original


def _candidate_rows(candidates: list[CatalogCandidate], catalog: Any) -> list[dict[str, Any]]:
    return [
        {
            "item_id": candidate.item_id,
            "score": float(candidate.score),
            "name_en": catalog.require(candidate.item_id).display_name_en,
            "name_zh": catalog.require(candidate.item_id).display_name_zh,
        }
        for candidate in candidates
    ]


def _historical_artifact_hashes() -> dict[str, dict[str, str]]:
    old_task66_dir = REPO_ROOT / "output" / "m14-task66"
    artifact_names = ("manifest.json", "rag_results.jsonl", "jev.jsonl", "metrics.json")
    hashes: dict[str, dict[str, str]] = {}
    for task_name, directory in (
        ("task64", previous_comparison.TASK64_OUTPUT_DIR),
        ("task66", old_task66_dir),
    ):
        hashes[task_name] = {}
        names = previous_comparison.TASK64_ARTIFACT_NAMES if task_name == "task64" else artifact_names
        for filename in names:
            path = directory / filename
            if not path.is_file():
                raise HoldoutFixtureError(f"historical {task_name} artifact is missing: {filename}")
            hashes[task_name][filename] = _sha256_file(path)
    return hashes


def _runtime_inputs() -> tuple[dict[str, Any], Any, dict[str, str]]:
    frozen = load_frozen_inputs()
    _, catalog, _task64_fixture_sha, catalog_sha = jev_protocol.load_frozen_inputs()
    if catalog_sha != frozen["catalog_sha256"]:
        raise HoldoutFixtureError("evaluation runtime loaded a different frozen catalog")
    historical = _historical_artifact_hashes()
    return frozen["fixture"], catalog, {
        f"{task}/{filename}": digest
        for task, artifacts in historical.items()
        for filename, digest in artifacts.items()
    }


def _verify_historical_unchanged(before: dict[str, str]) -> None:
    now_nested = _historical_artifact_hashes()
    now = {
        f"{task}/{filename}": digest
        for task, artifacts in now_nested.items()
        for filename, digest in artifacts.items()
    }
    if now != before:
        raise HoldoutFixtureError("historical Task64/66 artifacts changed during Task66.1 execution")


def run_mapping_side(
    side: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    resource_dir: Path = TASK65_ASSET_ROOT,
) -> dict[str, Any]:
    """Run one frozen side through the production selector and mapper in dish order."""
    if side not in {"legacy", "rag"}:
        raise HoldoutFixtureError("mapping side must be legacy or rag")
    artifact_name = LEGACY_RESULT_NAME if side == "legacy" else RAG_RESULT_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / artifact_name
    if result_path.exists():
        raise HoldoutFixtureError(f"refusing to overwrite existing raw output: {artifact_name}")
    manifest = _run_manifest(output_dir)
    fixture, catalog, historical_hashes = _runtime_inputs()
    if manifest.get("historical_artifact_hashes") not in (None, historical_hashes):
        raise HoldoutFixtureError("historical Task64/66 artifact hashes differ from the frozen run")
    manifest["historical_artifact_hashes"] = historical_hashes
    _write_json(output_dir / RUN_MANIFEST_NAME, manifest)
    resources = None
    if side == "rag":
        try:
            resources = previous_comparison.verify_task65_resources(resource_dir)
        except (OSError, previous_comparison.ComparisonError) as exc:
            raise HoldoutFixtureError("could not verify the pinned Task65 RAG resources") from exc

    retriever = IngredientRagRetriever(catalog, resource_dir=resource_dir) if side == "rag" else None
    observed = _ObservedRetriever(retriever) if retriever is not None else None
    used_item_ids_by_dish: dict[str, set[str]] = defaultdict(set)
    rows: list[dict[str, Any]] = []
    started_at = datetime.now(UTC).isoformat()
    selector_context = _select_observed_retriever(observed) if observed is not None else nullcontext()

    with selector_context:
        for dish, ingredient in iter_fixture_queries(fixture):
            query_id = ingredient["query_id"]
            used_item_ids = frozenset(used_item_ids_by_dish[dish["dish_id"]])
            semantic = type(
                "SemanticIngredient",
                (),
                {"name": ingredient["name"], "normalized_name": ingredient["normalized_name"]},
            )()
            if observed is not None:
                observed.status = "not_called"
                observed.error_code = None
                observed.elapsed_ms = None
                observed.candidates = []
            candidate_started = time.perf_counter()
            try:
                candidates = _build_candidates(
                    semantic,
                    catalog,
                    used_item_ids=used_item_ids,
                    backend=(
                        IngredientRetrievalBackend.LEGACY
                        if side == "legacy"
                        else IngredientRetrievalBackend.RAG
                    ),
                )
                candidate_error = None
            except (AppError, TypeError, ValueError) as exc:
                candidates = []
                candidate_error = exc
            candidate_elapsed = round((time.perf_counter() - candidate_started) * 1000, 3)
            map_started = time.perf_counter()
            mapped = None
            mapping_error = candidate_error
            if mapping_error is None:
                try:
                    mapped = map_ingredient(
                        semantic,
                        candidates,
                        catalog,
                        used_item_ids=used_item_ids,
                        language=Language.EN_US,
                    )
                except (AppError, TypeError, ValueError) as exc:
                    mapping_error = exc
            mapping_elapsed = round((time.perf_counter() - map_started) * 1000, 3)

            if side == "legacy":
                retrieval_status = "legacy"
                retrieval_error_code = None
                rag_candidates: list[dict[str, Any]] = []
                candidate_source = "legacy"
            else:
                assert observed is not None
                retrieval_status = observed.status
                retrieval_error_code = observed.error_code
                rag_candidates = _candidate_rows(observed.candidates, catalog)
                candidate_source = {
                    "success": "rag",
                    "empty": "legacy_empty_result_fallback",
                    "error": "legacy_error_fallback",
                    "not_called": "not_retrieved",
                }.get(observed.status, "not_retrieved")

            mapper_candidate_rows = _candidate_rows(candidates, catalog)
            if mapped is None:
                row: dict[str, Any] = {
                    "query_id": query_id,
                    "dish_id": dish["dish_id"],
                    "dish_name_en": dish["name_en"],
                    "dish_name_zh": dish["name_zh"],
                    "stratum": dish["stratum"],
                    "query_name": ingredient["name"],
                    "normalized_name": ingredient["normalized_name"],
                    "input_language": ingredient["input_language"],
                    "acceptable_item_ids": ingredient["acceptable_item_ids"],
                    "used_item_ids_before": sorted(used_item_ids),
                    "retrieval_status": retrieval_status,
                    "retrieval_error_code": retrieval_error_code,
                    "candidate_source": candidate_source,
                    "rag_candidate_ids": [candidate["item_id"] for candidate in rag_candidates],
                    "rag_candidates": rag_candidates,
                    "mapper_candidate_ids": [candidate["item_id"] for candidate in mapper_candidate_rows],
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
                item = catalog.require(mapped.item_id)
                is_fallback = mapped.mapping_reason.startswith(jev_protocol.FALLBACK_PREFIX)
                row = {
                    "query_id": query_id,
                    "dish_id": dish["dish_id"],
                    "dish_name_en": dish["name_en"],
                    "dish_name_zh": dish["name_zh"],
                    "stratum": dish["stratum"],
                    "query_name": ingredient["name"],
                    "normalized_name": ingredient["normalized_name"],
                    "input_language": ingredient["input_language"],
                    "acceptable_item_ids": ingredient["acceptable_item_ids"],
                    "used_item_ids_before": sorted(used_item_ids),
                    "retrieval_status": retrieval_status,
                    "retrieval_error_code": retrieval_error_code,
                    "candidate_source": candidate_source,
                    "rag_candidate_ids": [candidate["item_id"] for candidate in rag_candidates],
                    "rag_candidates": rag_candidates,
                    "mapper_candidate_ids": [candidate["item_id"] for candidate in mapper_candidate_rows],
                    "mapper_candidates": mapper_candidate_rows,
                    "mapping_status": "mapped",
                    "selected_id": mapped.item_id,
                    "selected_name_en": item.display_name_en,
                    "selected_name_zh": item.display_name_zh,
                    "mapping_reason": mapped.mapping_reason,
                    "is_fallback": is_fallback,
                    "error_type": None,
                    "error_code": None,
                }
                used_item_ids_by_dish[dish["dish_id"]].add(mapped.item_id)
            row["rag_retrieval_elapsed_ms"] = observed.elapsed_ms if observed is not None else None
            row["candidate_selection_elapsed_ms"] = candidate_elapsed
            row["mapping_elapsed_ms"] = mapping_elapsed
            row["total_elapsed_ms"] = round(candidate_elapsed + mapping_elapsed, 3)
            rows.append(row)

    if len(rows) != EXPECTED_QUERY_COUNT or len({row["query_id"] for row in rows}) != EXPECTED_QUERY_COUNT:
        raise HoldoutFixtureError("mapping run did not preserve all 288 unique frozen query occurrences")
    _write_jsonl_exclusive(result_path, rows)
    _verify_historical_unchanged(historical_hashes)
    task65_after = None
    if side == "rag":
        task65_after = previous_comparison.verify_task65_resources(resource_dir)
        if task65_after["asset_hashes"] != resources["asset_hashes"]:
            raise HoldoutFixtureError("Task65 resources changed during RAG evaluation")
    result = {
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "side": side,
        "query_count": len(rows),
        "mapped_count": sum(row["mapping_status"] == "mapped" for row in rows),
        "catalog_fallback_count": sum(row["is_fallback"] for row in rows),
        "mapping_failure_count": sum(row["mapping_status"] == "failed" for row in rows),
        "retrieval_status_counts": dict(Counter(row["retrieval_status"] for row in rows)),
        "candidate_source_counts": dict(Counter(row["candidate_source"] for row in rows)),
        "result_file": artifact_name,
        "result_sha256": _sha256_file(result_path),
    }
    if resources is not None:
        result["task65_asset_hashes"] = resources["asset_hashes"]
    manifest[f"{side}_run"] = result
    _write_json(output_dir / RUN_MANIFEST_NAME, manifest)
    return result


def _pair_key(side: str, query_id: str) -> str:
    return f"{side}:{query_id}"


def _canonical_state_sha256(state: dict[str, Any]) -> str:
    return _sha256_bytes(
        json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _jev_state(
    dish: dict[str, Any], ingredient: dict[str, Any], mapping: dict[str, Any], catalog: Any
) -> dict[str, Any]:
    shape = {
        "status": mapping.get("mapping_status"),
        "is_fallback": mapping.get("is_fallback"),
        "selected_id": mapping.get("selected_id"),
    }
    return jev_protocol.build_jev_state(dish, ingredient, shape, catalog)


def _blind_request_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Build the frozen typed-choice request and assert it contains no evaluation labels."""
    payload = jev_protocol.build_decisions_request(state)
    forbidden = {"gold", "acceptable_item_ids", "side", "方案", "候选", "score", "scores"}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).casefold()
    if any(term.casefold() in serialized for term in forbidden):
        raise HoldoutFixtureError("JEV request contains a forbidden label or candidate field")
    if set(payload) != {"model", "state", "questions"} or payload["state"] != state:
        raise HoldoutFixtureError("JEV request differs from the frozen blinded Choice shape")
    if set(state) != {"dish_context", "semantic_ingredient", "mapped_game_ingredient"}:
        raise HoldoutFixtureError("JEV state has an unexpected field")
    return payload


def _jev_call_row(
    *,
    side: str,
    dish: dict[str, Any],
    ingredient: dict[str, Any],
    state: dict[str, Any],
    api_key: str,
    stage: str,
) -> dict[str, Any]:
    payload = _blind_request_payload(state)
    state_sha = _canonical_state_sha256(state)
    payload_sha = _sha256_bytes(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    started_at = datetime.now(UTC).isoformat()
    try:
        parsed, raw_response, elapsed_ms = jev_protocol.call_jev(state, api_key)
    except (jev_protocol.EvaluationError, OSError, TimeoutError) as exc:
        # One authorized provider attempt is recorded; it is never retried.
        raw_response = getattr(exc, "raw_response", None)
        message = str(exc)[:600]
        if api_key:
            message = message.replace(api_key, "[REDACTED]")
        return {
            "side": side,
            "query_id": ingredient["query_id"],
            "pair_key": _pair_key(side, ingredient["query_id"]),
            "dish_id": dish["dish_id"],
            "status": "failed",
            "stage": stage,
            "provider_call": True,
            "failure_type": type(exc).__name__,
            "failure_message": message,
            "started_at_utc": started_at,
            "request_state": state,
            "request_state_sha256": state_sha,
            "request_payload_sha256": payload_sha,
            "raw_response": raw_response,
        }
    return {
        "side": side,
        "query_id": ingredient["query_id"],
        "pair_key": _pair_key(side, ingredient["query_id"]),
        "dish_id": dish["dish_id"],
        "status": "completed",
        "stage": stage,
        "provider_call": True,
        "started_at_utc": started_at,
        "elapsed_ms": elapsed_ms,
        "request_state": state,
        "request_state_sha256": state_sha,
        "request_payload_sha256": payload_sha,
        **parsed,
        "raw_response": raw_response,
    }


def _not_attempted_jev_row(
    side: str,
    dish: dict[str, Any],
    ingredient: dict[str, Any],
    reason: str,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "side": side,
        "query_id": ingredient["query_id"],
        "pair_key": _pair_key(side, ingredient["query_id"]),
        "dish_id": dish["dish_id"],
        "status": "not_attempted",
        "stage": "full",
        "provider_call": False,
        "reason": reason,
    }
    if state is not None:
        row["request_state"] = state
        row["request_state_sha256"] = _canonical_state_sha256(state)
    return row


def _completed_cache(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for row in rows:
        state = row.get("request_state")
        if row.get("status") == "completed" and isinstance(state, dict):
            key = _canonical_state_sha256(state)
            previous = cache.get(key)
            if previous is not None and previous.get("decision") != row.get("decision"):
                raise HoldoutFixtureError("identical JEV state has conflicting completed choices")
            cache.setdefault(key, row)
    return cache


def _ordered_jev_pairs(
    fixture: dict[str, Any], legacy_rows: list[dict[str, Any]], rag_rows: list[dict[str, Any]]
) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    by_side = {
        "legacy": {row.get("query_id"): row for row in legacy_rows},
        "rag": {row.get("query_id"): row for row in rag_rows},
    }
    pairs: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for side in ("legacy", "rag"):
        for dish, ingredient in iter_fixture_queries(fixture):
            mapping = by_side[side].get(ingredient["query_id"])
            if mapping is None:
                raise HoldoutFixtureError(f"{side} mappings are missing {ingredient['query_id']}")
            pairs.append((side, dish, ingredient, mapping))
    return pairs


def _jev_run_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    provider_rows = [row for row in rows if row.get("provider_call") is True]
    completed_calls = [row for row in provider_rows if row.get("status") == "completed"]
    costs = [
        row["usage"]["cost"]
        for row in completed_calls
        if isinstance(row.get("usage"), dict)
        and isinstance(row["usage"].get("cost"), (int, float))
        and not isinstance(row["usage"].get("cost"), bool)
    ]
    model_versions = sorted(
        {row["model"] for row in rows if row.get("status") == "completed" and isinstance(row.get("model"), str)}
    )
    return {
        "provider_call_count": len(provider_rows),
        "provider_success_count": len(completed_calls),
        "provider_failure_count": sum(row.get("status") == "failed" for row in provider_rows),
        "same_state_reuse_count": sum(row.get("stage") == "same_state_reuse" for row in rows),
        "not_attempted_count": sum(row.get("status") == "not_attempted" for row in rows),
        "model_versions_observed": model_versions,
        "model_version_drift": len(model_versions) > 1,
        "provider_cost_usd": sum(costs) if costs else None,
        "request_limit": MAX_JEV_PROVIDER_CALLS,
        "within_user_authorized_limit": len(provider_rows) <= MAX_JEV_PROVIDER_CALLS,
    }


def run_protocol_probe(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Send exactly one blinded typed Choice probe, using the first eligible legacy state."""
    manifest = _run_manifest(output_dir)
    legacy_rows = _read_jsonl(output_dir / LEGACY_RESULT_NAME)
    rag_rows = _read_jsonl(output_dir / RAG_RESULT_NAME)
    fixture, catalog, _ = _runtime_inputs()
    pairs = _ordered_jev_pairs(fixture, legacy_rows, rag_rows)
    existing_rows = _read_jsonl(output_dir / JEV_RESULT_NAME)
    existing_probe = [row for row in existing_rows if row.get("stage") == "protocol_probe"]
    if existing_probe:
        return {
            "status": existing_probe[0].get("status"),
            "side": existing_probe[0].get("side"),
            "query_id": existing_probe[0].get("query_id"),
            "model": existing_probe[0].get("model"),
            "reused_existing_probe": True,
        }
    eligible = [
        pair
        for pair in pairs
        if pair[3].get("mapping_status") == "mapped" and not pair[3].get("is_fallback")
    ]
    if not eligible:
        manifest["jev_probe"] = {"status": "not_required", "reason": "no non-fallback mapped items"}
        _write_json(output_dir / RUN_MANIFEST_NAME, manifest)
        return manifest["jev_probe"]
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise HoldoutFixtureError("OPENROUTER_API_KEY is absent; no JEV request was sent")
    side, dish, ingredient, mapping = eligible[0]
    state = _jev_state(dish, ingredient, mapping, catalog)
    row = _jev_call_row(
        side=side,
        dish=dish,
        ingredient=ingredient,
        state=state,
        api_key=api_key,
        stage="protocol_probe",
    )
    _append_jsonl(output_dir / JEV_RESULT_NAME, row)
    result = {
        "status": row["status"],
        "side": side,
        "query_id": ingredient["query_id"],
        "model": row.get("model"),
        "provider": row.get("provider"),
        "failure_type": row.get("failure_type"),
        "one_probe_only": True,
    }
    manifest["jev_probe"] = result
    manifest["jev_provider_call_count"] = 1
    _write_json(output_dir / RUN_MANIFEST_NAME, manifest)
    return result


def run_full_jev(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Judge each side's non-fallback mapping under one probe-returned JEV version."""
    manifest = _run_manifest(output_dir)
    legacy_rows = _read_jsonl(output_dir / LEGACY_RESULT_NAME)
    rag_rows = _read_jsonl(output_dir / RAG_RESULT_NAME)
    fixture, catalog, _ = _runtime_inputs()
    pairs = _ordered_jev_pairs(fixture, legacy_rows, rag_rows)
    jev_path = output_dir / JEV_RESULT_NAME
    existing_rows = _read_jsonl(jev_path)
    probe = next((row for row in existing_rows if row.get("stage") == "protocol_probe"), None)
    if probe is None:
        probe_summary = run_protocol_probe(output_dir)
        existing_rows = _read_jsonl(jev_path)
        probe = next((row for row in existing_rows if row.get("stage") == "protocol_probe"), None)
        if probe is None and probe_summary.get("status") == "not_required":
            return probe_summary
    if probe is None or probe.get("status") != "completed":
        result = {
            "probe_status": probe.get("status") if probe else "missing",
            "expected_model": None,
            "provider_call_count": sum(row.get("provider_call") is True for row in existing_rows),
            "completed_count": 0,
            "failed_count": sum(row.get("status") == "failed" for row in existing_rows),
            "not_attempted_after_probe_failure": True,
        }
        manifest["jev_run"] = result
        _write_json(output_dir / RUN_MANIFEST_NAME, manifest)
        return result

    expected_model = probe.get("model")
    if not isinstance(expected_model, str) or not expected_model.startswith(jev_protocol.MODEL):
        raise HoldoutFixtureError("probe returned a model outside the frozen TypeSafe JEV family")
    by_pair_key: dict[str, dict[str, Any]] = {}
    state_cache = _completed_cache(existing_rows)
    drifted = any(
        row.get("status") == "completed" and row.get("model") != expected_model
        for row in existing_rows
    )
    for row in existing_rows:
        key = row.get("pair_key")
        if isinstance(key, str):
            previous = by_pair_key.get(key)
            state = row.get("request_state")
            if previous is not None and previous.get("request_state") != state:
                raise HoldoutFixtureError("a repeated JEV pair key has inconsistent request state")
            by_pair_key[key] = row

    api_key = os.environ.get("OPENROUTER_API_KEY")
    provider_calls = sum(row.get("provider_call") is True for row in existing_rows)
    if provider_calls > MAX_JEV_PROVIDER_CALLS:
        raise HoldoutFixtureError("existing JEV artifact exceeds the user-authorized provider-call ceiling")
    stopped_for_drift = drifted
    for side, dish, ingredient, mapping in pairs:
        key = _pair_key(side, ingredient["query_id"])
        prior = by_pair_key.get(key)
        if mapping.get("mapping_status") != "mapped" or mapping.get("is_fallback"):
            if prior is None:
                row = _not_attempted_jev_row(
                    side,
                    dish,
                    ingredient,
                    "mapping_failed_or_catalog_fallback",
                )
                _append_jsonl(jev_path, row)
                by_pair_key[key] = row
            continue
        state = _jev_state(dish, ingredient, mapping, catalog)
        state_sha = _canonical_state_sha256(state)
        if prior is not None:
            if prior.get("request_state_sha256") not in (None, state_sha):
                raise HoldoutFixtureError("existing JEV state differs from the frozen mapping result")
            continue
        if stopped_for_drift:
            row = _not_attempted_jev_row(
                side, dish, ingredient, "stopped_after_jev_model_version_drift", state
            )
            _append_jsonl(jev_path, row)
            by_pair_key[key] = row
            continue
        reusable = state_cache.get(state_sha)
        if reusable is not None:
            row = {
                "side": side,
                "query_id": ingredient["query_id"],
                "pair_key": key,
                "dish_id": dish["dish_id"],
                "status": "completed",
                "stage": "same_state_reuse",
                "provider_call": False,
                "request_state": state,
                "request_state_sha256": state_sha,
                "reused_from_pair_key": reusable.get("pair_key"),
                "reused_from_query_id": reusable.get("query_id"),
                "decision": reusable["decision"],
                "confidence": reusable.get("confidence"),
                "probabilities": reusable.get("probabilities"),
                "model": reusable["model"],
                "provider": reusable.get("provider"),
                "usage": reusable.get("usage"),
            }
            _append_jsonl(jev_path, row)
            by_pair_key[key] = row
            continue
        failed_prior = next(
            (
                row
                for row in existing_rows
                if row.get("request_state_sha256") == state_sha and row.get("status") == "failed"
            ),
            None,
        )
        if failed_prior is not None:
            row = _not_attempted_jev_row(
                side,
                dish,
                ingredient,
                "same_state_provider_attempt_failed; no retry",
                state,
            )
            row["reused_failure_from_pair_key"] = failed_prior.get("pair_key")
            _append_jsonl(jev_path, row)
            by_pair_key[key] = row
            continue
        if not api_key:
            row = _not_attempted_jev_row(side, dish, ingredient, "OPENROUTER_API_KEY_absent", state)
            _append_jsonl(jev_path, row)
            by_pair_key[key] = row
            continue
        if provider_calls >= MAX_JEV_PROVIDER_CALLS:
            row = _not_attempted_jev_row(side, dish, ingredient, "user_authorized_call_ceiling_reached", state)
            _append_jsonl(jev_path, row)
            by_pair_key[key] = row
            continue
        row = _jev_call_row(
            side=side,
            dish=dish,
            ingredient=ingredient,
            state=state,
            api_key=api_key,
            stage="full",
        )
        provider_calls += 1
        _append_jsonl(jev_path, row)
        by_pair_key[key] = row
        if row.get("status") == "completed":
            if row.get("model") != expected_model:
                stopped_for_drift = True
            else:
                state_cache[state_sha] = row
        # A failed provider attempt is retained and never repeated; later distinct states continue.

    all_rows = _read_jsonl(jev_path)
    result = _jev_run_summary(all_rows)
    result.update(
        {
            "probe_status": probe.get("status"),
            "expected_model": expected_model,
            "historical_task64_model": JEV_BASELINE_MODEL,
            "historical_model_comparable": expected_model == JEV_BASELINE_MODEL,
            "stopped_after_version_drift": stopped_for_drift,
            "artifact": JEV_RESULT_NAME,
            "artifact_sha256": _sha256_file(jev_path),
        }
    )
    manifest["jev_run"] = result
    manifest["jev_provider_call_count"] = provider_calls
    _write_json(output_dir / RUN_MANIFEST_NAME, manifest)
    return result


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def exact_mcnemar_two_sided_p(improved: int, regressed: int) -> float:
    """Exact two-sided binomial McNemar p-value for paired discordant dishes."""
    if improved < 0 or regressed < 0:
        raise ValueError("paired transition counts cannot be negative")
    discordant = improved + regressed
    if discordant == 0:
        return 1.0
    tail_count = min(improved, regressed)
    tail_probability = sum(math.comb(discordant, k) for k in range(tail_count + 1)) / (2**discordant)
    return min(1.0, 2.0 * tail_probability)


def paired_dish_bootstrap_ci(
    legacy_pass: dict[str, bool],
    rag_pass: dict[str, bool],
    *,
    seed: int = BOOTSTRAP_SEED,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    if set(legacy_pass) != set(rag_pass) or not legacy_pass:
        raise ValueError("paired bootstrap needs the same non-empty dish IDs on both sides")
    deltas = [int(rag_pass[dish_id]) - int(legacy_pass[dish_id]) for dish_id in legacy_pass]
    rng = random.Random(seed)
    samples = [
        sum(rng.choices(deltas, k=len(deltas))) / len(deltas)
        for _ in range(replicates)
    ]
    return {
        "level": 0.95,
        "lower": _nearest_rank(samples, 0.025),
        "upper": _nearest_rank(samples, 0.975),
        "replicates": replicates,
        "seed": seed,
        "unit": "dish; resample paired LEGACY/RAG dish outcomes together",
    }


def _side_metrics(
    fixture: dict[str, Any],
    mapping_by_id: dict[str, dict[str, Any]],
    jev_by_pair: dict[str, dict[str, Any]],
    *,
    side: str,
) -> tuple[dict[str, Any], dict[str, bool], list[dict[str, Any]]]:
    dish_pass: dict[str, bool] = {}
    per_item: list[dict[str, Any]] = []
    choices = dict.fromkeys(jev_protocol.DECISIONS, 0)
    fallback_count = mapping_failure_count = retrieval_degraded_count = 0
    legacy_after_degrade = jev_failed = jev_not_attempted = jev_missing = 0
    determinate_count = reasonable_count = gold_hit_count = selected_gold_count = 0
    retrieval_miss_count = rerank_miss_count = 0
    recall_sum = 0.0

    for dish in fixture["dishes"]:
        dish_rows: list[dict[str, Any]] = []
        for ingredient in dish["ingredients"]:
            query_id = ingredient["query_id"]
            mapping = mapping_by_id.get(query_id, {})
            status = mapping.get("mapping_status", "missing")
            is_fallback = bool(mapping.get("is_fallback"))
            selected_id = mapping.get("selected_id")
            jev = jev_by_pair.get(_pair_key(side, query_id), {})
            jev_status = jev.get("status", "missing")
            decision = jev.get("decision") if jev_status == "completed" else None
            if side == "legacy":
                top_ids = mapping.get("mapper_candidate_ids", [])
            elif mapping.get("candidate_source") == "rag":
                top_ids = mapping.get("rag_candidate_ids", [])
            else:
                # On RAG degradation, recall describes the actual lexical list
                # that was passed through the production mapper seam.
                top_ids = mapping.get("mapper_candidate_ids", [])
            top_ids = top_ids if isinstance(top_ids, list) else []
            acceptable = set(ingredient["acceptable_item_ids"])
            overlap = set(top_ids) & acceptable
            item_recall = len(overlap) / len(acceptable) if acceptable else 0.0
            selected_in_gold = isinstance(selected_id, str) and selected_id in acceptable
            degraded = side == "rag" and mapping.get("retrieval_status") in {"error", "empty"}

            fallback_count += status == "mapped" and is_fallback
            mapping_failure_count += status != "mapped"
            retrieval_degraded_count += degraded
            legacy_after_degrade += degraded and status == "mapped" and not is_fallback
            jev_failed += jev_status == "failed"
            jev_not_attempted += jev_status == "not_attempted"
            jev_missing += jev_status == "missing" and status == "mapped" and not is_fallback
            if decision in choices:
                choices[decision] += 1
            if status == "mapped" and not is_fallback and decision in {"reasonable", "unreasonable"}:
                determinate_count += 1
                reasonable_count += decision == "reasonable"
            recall_sum += item_recall
            gold_hit_count += bool(overlap)
            selected_gold_count += selected_in_gold
            retrieval_miss_count += not bool(overlap)
            rerank_miss_count += bool(overlap) and not selected_in_gold

            item = {
                "side": side,
                "query_id": query_id,
                "dish_id": dish["dish_id"],
                "stratum": dish["stratum"],
                "query": ingredient["name"],
                "input_language": ingredient["input_language"],
                "mapping_status": status,
                "is_fallback": is_fallback,
                "candidate_source": mapping.get("candidate_source"),
                "retrieval_status": mapping.get("retrieval_status"),
                "retrieval_error_code": mapping.get("retrieval_error_code"),
                "top5_item_ids": top_ids[:5],
                "selected_id": selected_id,
                "selected_name_en": mapping.get("selected_name_en"),
                "selected_name_zh": mapping.get("selected_name_zh"),
                "mapping_reason": mapping.get("mapping_reason"),
                "acceptable_item_ids": ingredient["acceptable_item_ids"],
                "selected_id_in_gold": bool(selected_in_gold),
                "gold_recall_at_5": item_recall,
                "jev_status": jev_status,
                "jev_stage": jev.get("stage"),
                "jev_decision": decision,
                "jev_model": jev.get("model"),
                "jev_confidence": jev.get("confidence"),
                "jev_reason_if_not_attempted": jev.get("reason"),
            }
            per_item.append(item)
            dish_rows.append(item)

        dish_pass[dish["dish_id"]] = len(dish_rows) == EXPECTED_INGREDIENTS_PER_DISH and all(
            row["mapping_status"] == "mapped"
            and not row["is_fallback"]
            and row["jev_status"] == "completed"
            and row["jev_decision"] == "reasonable"
            for row in dish_rows
        )

    total_queries = sum(len(dish["ingredients"]) for dish in fixture["dishes"])
    dish_count = len(fixture["dishes"])
    metrics = {
        "dish_count": dish_count,
        "query_occurrence_count": total_queries,
        "mapping_status_counts": dict(Counter(row["mapping_status"] for row in per_item)),
        "fallback_count": fallback_count,
        "mapping_failure_count": mapping_failure_count,
        "retrieval_degraded_count": retrieval_degraded_count,
        "legacy_mapped_after_degrade_count": legacy_after_degrade,
        "jev_status_counts": dict(Counter(row["jev_status"] for row in per_item)),
        "jev_choice_counts": choices,
        "jev_call_failure_count": jev_failed,
        "jev_not_attempted_count": jev_not_attempted,
        "jev_missing_count": jev_missing,
        "nonfallback_reasonable_rate": {
            "numerator": reasonable_count,
            "denominator": determinate_count,
            "value": reasonable_count / determinate_count if determinate_count else None,
        },
        "reasonable_coverage_fixed_query_set": {
            "numerator": choices["reasonable"],
            "denominator": total_queries,
            "value": choices["reasonable"] / total_queries if total_queries else None,
        },
        "dish_all_reasonable_rate": {
            "numerator": sum(dish_pass.values()),
            "denominator": dish_count,
            "value": sum(dish_pass.values()) / dish_count if dish_count else None,
            "rule": "fixed 96-dish denominator; all 3 items must be mapped, non-fallback, and have completed reasonable JEV choices",
        },
        "dish_all_reasonable_evaluable_rate": {
            "numerator": sum(dish_pass.values()),
            "denominator": sum(
                all(
                    row["mapping_status"] == "mapped"
                    and not row["is_fallback"]
                    and row["jev_status"] == "completed"
                    and row["jev_decision"] in {"reasonable", "unreasonable"}
                    for row in per_item
                    if row["dish_id"] == dish_id
                )
                for dish_id in dish_pass
            ),
        },
        "gold_recall_at_5": {
            "mean": recall_sum / total_queries if total_queries else None,
            "numerator_sum_of_item_recall": round(recall_sum, 8),
            "denominator": total_queries,
        },
        "gold_hit_at_5": {"numerator": gold_hit_count, "denominator": total_queries},
        "selected_gold_match": {"numerator": selected_gold_count, "denominator": total_queries},
        "candidate_retrieval_miss_count": retrieval_miss_count,
        "candidate_rerank_or_selection_miss_count": rerank_miss_count,
    }
    evaluable = metrics["dish_all_reasonable_evaluable_rate"]["denominator"]
    metrics["dish_all_reasonable_evaluable_rate"]["value"] = (
        sum(dish_pass.values()) / evaluable if evaluable else None
    )
    return metrics, dish_pass, per_item


def _query_composition(fixture: dict[str, Any], old_fixture: dict[str, Any]) -> dict[str, Any]:
    new_queries_by_stratum: dict[str, Counter[str]] = defaultdict(Counter)
    old_queries = {
        normalize_query(ingredient[key])
        for dish in old_fixture["dishes"]
        for ingredient in dish.get("ingredients", [])
        for key in ("name", "normalized_name")
        if isinstance(ingredient.get(key), str) and ingredient[key].strip()
    }
    for dish, ingredient in iter_fixture_queries(fixture):
        new_queries_by_stratum[dish["stratum"]][normalize_query(ingredient["normalized_name"])] += 1
    all_counts: Counter[str] = Counter()
    for counts in new_queries_by_stratum.values():
        all_counts.update(counts)
    repeated_occurrences = sum(count - 1 for count in all_counts.values() if count > 1)
    return {
        "query_occurrences": sum(all_counts.values()),
        "distinct_normalized_queries": len(all_counts),
        "queries_repeated_within_new_fixture": sum(count > 1 for count in all_counts.values()),
        "repeat_occurrences_beyond_first": repeated_occurrences,
        "distinct_queries_absent_from_task64": len(set(all_counts) - old_queries),
        "distinct_queries_present_in_task64": len(set(all_counts) & old_queries),
        "per_stratum": {
            stratum: {
                "query_occurrences": sum(counts.values()),
                "distinct_normalized_queries": len(counts),
                "absent_from_task64": len(set(counts) - old_queries),
                "repeated_query_occurrences": sum(count - 1 for count in counts.values() if count > 1),
            }
            for stratum, counts in new_queries_by_stratum.items()
        },
    }


def calculate_metrics(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Recompute fixed-denominator side and paired metrics from frozen ignored artifacts."""
    manifest = _run_manifest(output_dir)
    fixture, old_fixture, catalog_items = load_raw_inputs()
    legacy_path = output_dir / LEGACY_RESULT_NAME
    rag_path = output_dir / RAG_RESULT_NAME
    if not legacy_path.is_file() or not rag_path.is_file():
        raise HoldoutFixtureError("both LEGACY and RAG raw result files are required before scoring")
    legacy_rows = _read_jsonl(legacy_path)
    rag_rows = _read_jsonl(rag_path)
    expected_ids = {ingredient["query_id"] for _, ingredient in iter_fixture_queries(fixture)}
    mapping_by_side: dict[str, dict[str, dict[str, Any]]] = {
        "legacy": {row.get("query_id"): row for row in legacy_rows},
        "rag": {row.get("query_id"): row for row in rag_rows},
    }
    for side, rows in (("legacy", legacy_rows), ("rag", rag_rows)):
        if len(rows) != EXPECTED_QUERY_COUNT or set(mapping_by_side[side]) != expected_ids:
            raise HoldoutFixtureError(f"{side} results do not exactly match 288 frozen query IDs")
        declared = manifest.get(f"{side}_run", {})
        path = legacy_path if side == "legacy" else rag_path
        if declared.get("result_sha256") != _sha256_file(path):
            raise HoldoutFixtureError(f"{side} result artifact hash differs from its run manifest")
    if manifest.get("historical_artifact_hashes"):
        _verify_historical_unchanged(manifest["historical_artifact_hashes"])

    jev_rows = _read_jsonl(output_dir / JEV_RESULT_NAME)
    if sum(row.get("provider_call") is True for row in jev_rows) > MAX_JEV_PROVIDER_CALLS:
        raise HoldoutFixtureError("JEV provider calls exceeded the 576-request authorization")
    jev_by_pair: dict[str, dict[str, Any]] = {}
    for row in jev_rows:
        key = row.get("pair_key")
        if isinstance(key, str):
            jev_by_pair[key] = row

    legacy, legacy_pass, legacy_items = _side_metrics(
        fixture, mapping_by_side["legacy"], jev_by_pair, side="legacy"
    )
    rag, rag_pass, rag_items = _side_metrics(
        fixture, mapping_by_side["rag"], jev_by_pair, side="rag"
    )
    per_dish: list[dict[str, Any]] = []
    transitions = Counter[str]()
    for dish in fixture["dishes"]:
        old_pass = legacy_pass[dish["dish_id"]]
        new_pass = rag_pass[dish["dish_id"]]
        transition = (
            "improved"
            if not old_pass and new_pass
            else "regressed"
            if old_pass and not new_pass
            else "unchanged"
        )
        transitions[transition] += 1
        per_dish.append(
            {
                "dish_id": dish["dish_id"],
                "name_en": dish["name_en"],
                "name_zh": dish["name_zh"],
                "stratum": dish["stratum"],
                "legacy_all_reasonable": old_pass,
                "rag_all_reasonable": new_pass,
                "transition": transition,
            }
        )
    improved = transitions["improved"]
    regressed = transitions["regressed"]
    per_stratum: dict[str, Any] = {}
    for stratum in STRATA:
        stratum_dishes = [dish for dish in fixture["dishes"] if dish["stratum"] == stratum]
        legacy_n = sum(legacy_pass[dish["dish_id"]] for dish in stratum_dishes)
        rag_n = sum(rag_pass[dish["dish_id"]] for dish in stratum_dishes)
        per_stratum[stratum] = {
            "dish_count": len(stratum_dishes),
            "legacy_all_reasonable": {"numerator": legacy_n, "denominator": len(stratum_dishes)},
            "rag_all_reasonable": {"numerator": rag_n, "denominator": len(stratum_dishes)},
            "difference_percentage_points": (
                (rag_n - legacy_n) / len(stratum_dishes) * 100 if stratum_dishes else None
            ),
            "improved": sum(
                not legacy_pass[dish["dish_id"]] and rag_pass[dish["dish_id"]]
                for dish in stratum_dishes
            ),
            "regressed": sum(
                legacy_pass[dish["dish_id"]] and not rag_pass[dish["dish_id"]]
                for dish in stratum_dishes
            ),
        }

    expected_model = manifest.get("jev_run", {}).get("expected_model")
    observed_models = sorted(
        {
            row["model"]
            for row in jev_rows
            if row.get("status") == "completed" and isinstance(row.get("model"), str)
        }
    )
    model_comparable = len(observed_models) <= 1 and (
        expected_model is None or observed_models in ([], [expected_model])
    )
    metrics = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "acceptance_contract_id": CONTRACT_ID,
        "fixture_sha256": FROZEN_FIXTURE_SHA256,
        "catalog_sha256": _sha256_bytes(CATALOG_PATH.read_bytes()),
        "catalog_version": EXPECTED_CATALOG_VERSION,
        "dish_count": len(fixture["dishes"]),
        "query_occurrence_count": EXPECTED_QUERY_COUNT,
        "sample_summary": validate_fixture(fixture, old_fixture, catalog_items),
        "query_composition": _query_composition(fixture, old_fixture),
        "legacy": legacy,
        "rag": rag,
        "paired_dish_transitions": {
            "status": "comparable_same_probe_model" if model_comparable else "not_comparable_model_drift",
            "improved": improved,
            "regressed": regressed,
            "unchanged": transitions["unchanged"],
            "difference_percentage_points": (
                (rag["dish_all_reasonable_rate"]["numerator"]
                 - legacy["dish_all_reasonable_rate"]["numerator"])
                / len(fixture["dishes"])
                * 100
            ),
            "mcnemar_exact_two_sided_p": exact_mcnemar_two_sided_p(improved, regressed),
            "cluster_bootstrap_difference_ci": paired_dish_bootstrap_ci(legacy_pass, rag_pass),
            "per_dish": per_dish,
        },
        "per_stratum": per_stratum,
        "per_item": {"legacy": legacy_items, "rag": rag_items},
        "jev_run": manifest.get("jev_run", _jev_run_summary(jev_rows)),
        "model_versions_observed": observed_models,
        "single_model_version_for_new_set": model_comparable,
        "product_default": "LEGACY (unchanged; no change authorized)",
    }
    metrics_path = output_dir / METRICS_NAME
    _write_json(metrics_path, metrics)
    manifest["metrics_sha256"] = _sha256_file(metrics_path)
    _write_json(output_dir / RUN_MANIFEST_NAME, manifest)
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate-fixture", "freeze", "run-legacy", "run-rag", "probe", "full", "metrics"),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--resource-dir", type=Path, default=TASK65_ASSET_ROOT)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-fixture":
            result = load_frozen_inputs()["summary"]
        elif args.command == "freeze":
            result = build_freeze_manifest()
            _write_manifest(args.output_dir, result)
        elif args.command == "run-legacy":
            result = run_mapping_side("legacy", args.output_dir, args.resource_dir)
        elif args.command == "run-rag":
            result = run_mapping_side("rag", args.output_dir, args.resource_dir)
        elif args.command == "probe":
            result = run_protocol_probe(args.output_dir)
        elif args.command == "full":
            result = run_full_jev(args.output_dir)
        else:
            result = calculate_metrics(args.output_dir)
    except (
        HoldoutFixtureError,
        OSError,
        previous_comparison.ComparisonError,
        jev_protocol.EvaluationError,
    ) as exc:
        print(f"Holdout validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
