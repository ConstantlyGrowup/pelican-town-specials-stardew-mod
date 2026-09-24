"""Offline protocol harness for Task 67's per-dish ingredient verifier.

The default mode uses a deterministic fake Gateway and never touches a
Provider. Real mode accepts only the remaining-125 scope: one OpenAI-compatible
HTTP request per case, without retries or structured-output repair calls. The
completed 15-case pilot IDs remain readable for historical scoring and are
rejected for new real invocations.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "backend" / "src")]

from pelican_town_specials.application.settings import (
    ProviderSettings,
    ProviderSettingsService,
)
from pelican_town_specials.catalog.mapping import map_ingredient
from pelican_town_specials.catalog.models import CatalogCandidate
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.config import AppConfig
from pelican_town_specials.domain.common import Language, StrictModel
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.persistence.secret_store import (
    WindowsEnvironmentSecretStore,
)
from pelican_town_specials.providers.openai_compatible import (
    OpenAICompatibleGateway,
    _extract_chat_text,
)
from pelican_town_specials.providers.structured_output import (
    StructuredOutputError,
    parse_json_object,
)

CONTRACT_ID = "m14-task67-full-text-verifier-evaluation-v4"
MAX_REAL_CALLS = 1
MAX_REMAINING_CALLS = 1
FROZEN_NEGATIVE_FIXTURE_SHA256 = (
    "F50F02C6C847B7EFBF039128030784E8F08CBF582362A70661917A739B4303D8"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "m14-task67-llm-v3"
DEFAULT_POSITIVE_RESULTS = (
    REPO_ROOT / "output" / "m14-task67-full-v2" / "positive_results.jsonl"
)
DEFAULT_NEGATIVE_RESULTS = (
    REPO_ROOT / "output" / "m14-task67-full-v2" / "negative_results.jsonl"
)
DEFAULT_V2_MANIFEST = (
    REPO_ROOT / "output" / "m14-task67-full-v2" / "positive_manifest.json"
)
DEFAULT_NEGATIVE_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "m14_ingredient_no_match_queries.json"
)
DEFAULT_CATALOG = (
    REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)

# These IDs identify the completed pilot. They remain part of the input universe
# for historic scoring, but can never be sent to the Provider again.
AUTHORIZED_REAL_PILOT_IDS = frozenset(
    {
        "d07",
        "d18",
        "h66-ambiguous_name-06",
        "h66-ambiguous_name-19",
        "h66-bilingual_or_synonym-06",
        "h66-bilingual_or_synonym-19",
        "h66-direct_name-06",
        "h66-direct_name-19",
        "h66-raw_vs_prepared-06",
        "h66-raw_vs_prepared-19",
        "n13",
        "n14",
        "n15",
        "n19",
        "n20",
    }
)
REMAINING_REAL_SCOPE = "remaining-125"

REQUEST_FIELDS = (
    "dish name (positive cases only)",
    "real-world ingredient name",
    "Top5 item ID and English/Chinese catalog names",
    "explicit null no-match option",
)
FORBIDDEN_PROMPT_FIELDS = (
    "Gold labels",
    "legacy or RAG final mappings",
    "candidate scores or rank scores",
    "dataset/stratum labels and case IDs",
    "type or category",
    "image data",
    "user context",
    "API key or Provider settings",
)


class Task67RunError(RuntimeError):
    """Raised for invalid frozen inputs, call selection, or output scope."""


class Task67ProtocolError(ValueError):
    """A model response is malformed or chooses an unsafe candidate."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class GatewayCallError(RuntimeError):
    """A Gateway call failed without retaining its potentially sensitive body."""

    def __init__(
        self,
        code: str,
        *,
        network_request_count: int,
        http_status: int | None = None,
        elapsed_ms: float | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.network_request_count = network_request_count
        self.http_status = http_status
        self.elapsed_ms = elapsed_ms


@dataclass(frozen=True)
class VerifierCandidate:
    item_id: str
    name_en: str
    name_zh: str


@dataclass(frozen=True)
class EvaluationIngredient:
    query_id: str
    query: str
    candidates: tuple[VerifierCandidate, ...]
    acceptable_item_ids: tuple[str, ...]
    baseline_v2: BaselineV2Status | None = None


@dataclass(frozen=True)
class BaselineV2Status:
    retrieval_status: str | None
    retrieval_reason_code: str | None
    mapping_status: str | None
    mapping_reason: str | None
    selected_item_id: str | None
    is_fallback: bool | None


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    kind: Literal["positive", "negative"]
    dataset: str
    dish_id: str | None
    dish_name_en: str | None
    dish_name_zh: str | None
    ingredients: tuple[EvaluationIngredient, ...]


def _baseline_v2_status(row: dict[str, Any]) -> BaselineV2Status:
    retrieval_status = row.get("retrieval_status")
    retrieval_reason_code = row.get("retrieval_reason_code")
    mapping_status = row.get("mapping_status")
    mapping_reason = row.get("mapping_reason")
    selected_item_id = row.get("selected_id")
    is_fallback = row.get("is_fallback")
    return BaselineV2Status(
        retrieval_status=retrieval_status if isinstance(retrieval_status, str) else None,
        retrieval_reason_code=(
            retrieval_reason_code
            if isinstance(retrieval_reason_code, str)
            else None
        ),
        mapping_status=mapping_status if isinstance(mapping_status, str) else None,
        mapping_reason=mapping_reason if isinstance(mapping_reason, str) else None,
        selected_item_id=selected_item_id if isinstance(selected_item_id, str) else None,
        is_fallback=is_fallback if isinstance(is_fallback, bool) else None,
    )


def _baseline_v2_record(ingredient: EvaluationIngredient) -> dict[str, Any] | None:
    baseline = ingredient.baseline_v2
    if baseline is None:
        return None
    return {
        "retrieval_status": baseline.retrieval_status,
        "retrieval_reason_code": baseline.retrieval_reason_code,
        "mapping_status": baseline.mapping_status,
        "mapping_reason": baseline.mapping_reason,
        "selected_item_id": baseline.selected_item_id,
        "is_fallback": baseline.is_fallback,
    }


class IngredientDecision(StrictModel):
    ingredient_index: int = Field(ge=0)
    selected_item_id: str | None = Field(min_length=1)


class IngredientVerifierResponse(StrictModel):
    decisions: list[IngredientDecision]


@dataclass(frozen=True)
class GatewayReply:
    response_text: str
    raw_response_sha256: str
    elapsed_ms: float
    network_request_count: int
    http_status: int | None = None


class VerifierGateway(Protocol):
    async def complete(
        self,
        *,
        prompt_payload: dict[str, Any],
        prompt_text: str,
    ) -> GatewayReply: ...


@dataclass(frozen=True)
class EvaluationRun:
    requests: list[dict[str, Any]]
    responses: list[dict[str, Any]]
    ingredient_results: list[dict[str, Any]]
    summary: dict[str, Any]
    manifest: dict[str, Any]


RealScope = Literal["pilot", "remaining-125"]


class FakeVerifierGateway:
    """Deterministic protocol fake; it never imports or opens a Provider."""

    def __init__(self) -> None:
        self.logical_call_count = 0

    async def complete(
        self,
        *,
        prompt_payload: dict[str, Any],
        prompt_text: str,
    ) -> GatewayReply:
        del prompt_text
        self.logical_call_count += 1
        used: set[str] = set()
        decisions = []
        for ingredient in prompt_payload["ingredients"]:
            choice = next(
                (
                    candidate["item_id"]
                    for candidate in ingredient["candidates"]
                    if candidate["item_id"] not in used
                ),
                None,
            )
            if choice is not None:
                used.add(choice)
            decisions.append(
                {
                    "ingredientIndex": ingredient["ingredient_index"],
                    "selectedItemId": choice,
                }
            )
        response_text = json.dumps(
            {"decisions": decisions}, ensure_ascii=False, separators=(",", ":")
        )
        return GatewayReply(
            response_text=response_text,
            raw_response_sha256=_sha256_bytes(response_text.encode("utf-8")),
            elapsed_ms=0.0,
            network_request_count=0,
        )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise Task67RunError(f"missing frozen artifact: {path.name}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Task67RunError(f"invalid frozen JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise Task67RunError(f"invalid frozen JSON object: {path.name}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise Task67RunError(f"missing frozen artifact: {path.name}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Task67RunError(
                f"invalid JSONL artifact row: {path.name}:{line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise Task67RunError(f"invalid JSONL row: {path.name}:{line_number}")
        rows.append(value)
    return rows


def _candidate_list(candidates: object) -> tuple[VerifierCandidate, ...]:
    if not isinstance(candidates, list) or len(candidates) > 5:
        raise Task67RunError("frozen Top5 candidate list is invalid")
    result: list[VerifierCandidate] = []
    seen_ids: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            raise Task67RunError("frozen candidate is invalid")
        item_id = item.get("item_id")
        name_en = item.get("name_en")
        name_zh = item.get("name_zh")
        if not all(isinstance(value, str) and value for value in (item_id, name_en, name_zh)):
            raise Task67RunError("frozen candidate is missing an approved display field")
        if item_id in seen_ids:
            raise Task67RunError("frozen Top5 contains duplicate candidate IDs")
        seen_ids.add(item_id)
        result.append(VerifierCandidate(item_id, name_en, name_zh))
    return tuple(result)


def cases_from_frozen_rows(
    positive_rows: list[dict[str, Any]],
    negative_fixture: dict[str, Any],
    negative_rows: list[dict[str, Any]],
) -> list[EvaluationCase]:
    """Build scoring cases while keeping labels out of prompt construction."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in positive_rows:
        dish_id = row.get("dish_id")
        if not isinstance(dish_id, str) or not dish_id:
            raise Task67RunError("positive row is missing dish_id")
        grouped.setdefault(dish_id, []).append(row)

    cases: list[EvaluationCase] = []
    seen_query_ids: set[str] = set()
    for dish_id in sorted(grouped):
        rows = grouped[dish_id]
        first = rows[0]
        dish_name_en = first.get("dish_name_en")
        dish_name_zh = first.get("dish_name_zh")
        dataset = first.get("dataset")
        if not all(isinstance(value, str) and value for value in (dish_name_en, dish_name_zh, dataset)):
            raise Task67RunError("positive dish is missing an approved display field")
        ingredients: list[EvaluationIngredient] = []
        for row in rows:
            query_id = row.get("query_id")
            query = row.get("query")
            acceptable_ids = row.get("gold_item_ids")
            if not isinstance(query_id, str) or not query_id or query_id in seen_query_ids:
                raise Task67RunError("positive query IDs must be present and unique")
            if not isinstance(query, str) or not query:
                raise Task67RunError("positive row is missing the real-world ingredient")
            if not isinstance(acceptable_ids, list) or not all(
                isinstance(item_id, str) and item_id for item_id in acceptable_ids
            ):
                raise Task67RunError("positive Gold item IDs are invalid")
            if row.get("dish_name_en") != dish_name_en or row.get("dish_name_zh") != dish_name_zh:
                raise Task67RunError("positive dish names differ between ingredient rows")
            if row.get("dataset") != dataset:
                raise Task67RunError("positive dataset differs within a dish")
            seen_query_ids.add(query_id)
            ingredients.append(
                EvaluationIngredient(
                    query_id=query_id,
                    query=query,
                    candidates=_candidate_list(row.get("mapper_candidates")),
                    acceptable_item_ids=tuple(acceptable_ids),
                    baseline_v2=_baseline_v2_status(row),
                )
            )
        cases.append(
            EvaluationCase(
                case_id=dish_id,
                kind="positive",
                dataset=dataset,
                dish_id=dish_id,
                dish_name_en=dish_name_en,
                dish_name_zh=dish_name_zh,
                ingredients=tuple(ingredients),
            )
        )

    fixture_cases = negative_fixture.get("cases")
    if not isinstance(fixture_cases, list):
        raise Task67RunError("negative fixture cases are missing")
    result_by_id: dict[str, dict[str, Any]] = {}
    for row in negative_rows:
        case_id = row.get("query_id")
        if not isinstance(case_id, str) or not case_id or case_id in result_by_id:
            raise Task67RunError("negative result IDs must be present and unique")
        result_by_id[case_id] = row

    fixture_ids: set[str] = set()
    for fixture_case in fixture_cases:
        if not isinstance(fixture_case, dict):
            raise Task67RunError("negative fixture case is invalid")
        case_id = fixture_case.get("id")
        query = fixture_case.get("query")
        if not isinstance(case_id, str) or not case_id or case_id in fixture_ids:
            raise Task67RunError("negative fixture IDs must be present and unique")
        if not isinstance(query, str) or not query:
            raise Task67RunError("negative fixture query is invalid")
        fixture_ids.add(case_id)
        row = result_by_id.get(case_id)
        if row is None or row.get("query") != query:
            raise Task67RunError("negative candidate evidence differs from frozen query")
        cases.append(
            EvaluationCase(
                case_id=case_id,
                kind="negative",
                dataset="negative",
                dish_id=None,
                dish_name_en=None,
                dish_name_zh=None,
                ingredients=(
                    EvaluationIngredient(
                        query_id=case_id,
                        query=query,
                        candidates=_candidate_list(
                            row.get("retrieval_evidence", {}).get(
                                "ranked_candidates_before_semantic_verification"
                            )
                            if isinstance(row.get("retrieval_evidence"), dict)
                            else None
                        ),
                        acceptable_item_ids=(),
                        baseline_v2=_baseline_v2_status(row),
                    ),
                ),
            )
        )
    if fixture_ids != set(result_by_id):
        raise Task67RunError("negative result IDs differ from frozen fixture")
    return cases


def load_frozen_cases() -> tuple[list[EvaluationCase], dict[str, int], dict[str, str]]:
    positive_rows = _read_jsonl(DEFAULT_POSITIVE_RESULTS)
    negative_rows = _read_jsonl(DEFAULT_NEGATIVE_RESULTS)
    negative_fixture = _read_json(DEFAULT_NEGATIVE_FIXTURE)
    prior_manifest = _read_json(DEFAULT_V2_MANIFEST)
    input_hashes = {
        "positive_results.jsonl": _sha256_file(DEFAULT_POSITIVE_RESULTS),
        "negative_results.jsonl": _sha256_file(DEFAULT_NEGATIVE_RESULTS),
        "negative_fixture.json": _sha256_file(DEFAULT_NEGATIVE_FIXTURE),
        "catalog.json": _sha256_file(DEFAULT_CATALOG),
        "positive_manifest.json": _sha256_file(DEFAULT_V2_MANIFEST),
    }
    expected_hashes = {
        "positive_results.jsonl": prior_manifest.get("positive_result_sha256"),
        "negative_results.jsonl": prior_manifest.get("negative_result_sha256"),
        "negative_fixture.json": FROZEN_NEGATIVE_FIXTURE_SHA256,
        "catalog.json": prior_manifest.get("catalog_sha256"),
    }
    for name, expected in expected_hashes.items():
        if input_hashes[name] != expected:
            raise Task67RunError(f"frozen input hash mismatch: {name}")

    cases = cases_from_frozen_rows(positive_rows, negative_fixture, negative_rows)
    positive_cases = [case for case in cases if case.kind == "positive"]
    negative_cases = [case for case in cases if case.kind == "negative"]
    positive_item_count = sum(len(case.ingredients) for case in positive_cases)
    dataset_counts = {
        dataset: sum(1 for row in positive_rows if row.get("dataset") == dataset)
        for dataset in ("task64", "task66_1")
    }
    if (
        len(positive_rows) != 360
        or len(positive_cases) != 120
        or len(negative_cases) != 20
        or positive_item_count != 360
        or dataset_counts != {"task64": 72, "task66_1": 288}
        or any(len(case.ingredients) != 3 for case in positive_cases)
    ):
        raise Task67RunError("frozen Task67 universe must be 120 dishes / 360 items / 20 negatives")
    if len(cases) != len({case.case_id for case in cases}):
        raise Task67RunError("frozen evaluation case IDs are not unique")
    source_counts = {
        "positive_dish_count": len(positive_cases),
        "positive_item_count": positive_item_count,
        "negative_case_count": len(negative_cases),
    }
    return cases, source_counts, input_hashes


def build_prompt_payload(case: EvaluationCase) -> dict[str, Any]:
    dish_name = None
    if case.kind == "positive":
        dish_name = {
            "english": case.dish_name_en,
            "chinese": case.dish_name_zh,
        }
    return {
        "dish_name": dish_name,
        "ingredients": [
            {
                "ingredient_index": index,
                "real_world_ingredient": ingredient.query,
                "candidates": [
                    {
                        "item_id": candidate.item_id,
                        "name_en": candidate.name_en,
                        "name_zh": candidate.name_zh,
                    }
                    for candidate in ingredient.candidates
                ],
                "no_match_option": None,
            }
            for index, ingredient in enumerate(case.ingredients)
        ],
    }


PROMPT_INSTRUCTIONS = (
    "For each real-world ingredient, choose one listed vanilla game ingredient only when it is a clear, "
    "reasonable match. If no candidate is a clear match, choose null. Decide each ingredient independently. "
    "Return one complete decision for every ingredient index, with no explanation."
)
JSON_SCHEMA_INSTRUCTION = (
    "Return exactly one JSON object matching the required response schema. "
    "Use a candidate item ID or null for each ingredient index."
)


def render_prompt(prompt_payload: dict[str, Any]) -> str:
    return (
        f"{PROMPT_INSTRUCTIONS}\n\nApproved evaluation input:\n"
        f"{json.dumps(prompt_payload, ensure_ascii=False, separators=(',', ':'))}"
    )


def candidate_fingerprint(prompt_payload: dict[str, Any]) -> str:
    candidates = [
        ingredient["candidates"] for ingredient in prompt_payload["ingredients"]
    ]
    canonical = json.dumps(candidates, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(canonical.encode("utf-8"))


def validate_response(case: EvaluationCase, response_text: str) -> tuple[str | None, ...]:
    try:
        value = parse_json_object(response_text)
        response = IngredientVerifierResponse.model_validate(value)
    except (StructuredOutputError, ValidationError):
        raise Task67ProtocolError("invalid_structured_response") from None

    decisions = response.decisions
    expected_indexes = set(range(len(case.ingredients)))
    indexes = [decision.ingredient_index for decision in decisions]
    if len(indexes) != len(case.ingredients):
        raise Task67ProtocolError("decision_count_mismatch")
    if len(set(indexes)) != len(indexes):
        raise Task67ProtocolError("duplicate_ingredient_index")
    if set(indexes) != expected_indexes:
        raise Task67ProtocolError("missing_or_unexpected_ingredient_index")

    by_index = {decision.ingredient_index: decision.selected_item_id for decision in decisions}
    selected_ids = [item_id for item_id in by_index.values() if item_id is not None]
    if len(set(selected_ids)) != len(selected_ids):
        raise Task67ProtocolError("duplicate_selected_id")
    for index, selected_id in by_index.items():
        if selected_id is None:
            continue
        allowed = {candidate.item_id for candidate in case.ingredients[index].candidates}
        if selected_id not in allowed:
            raise Task67ProtocolError("selected_id_not_in_candidates")
    return tuple(by_index[index] for index in range(len(case.ingredients)))


def select_cases(
    cases: list[EvaluationCase],
    *,
    mode: Literal["fake", "real"],
    include_ids: list[str] | None,
    max_real_calls: int | None,
    confirmed_real: bool,
    real_scope: RealScope = "pilot",
) -> list[EvaluationCase]:
    by_id = {case.case_id: case for case in cases}
    if len(by_id) != len(cases):
        raise Task67RunError("evaluation case IDs must be unique")
    if mode == "fake":
        if max_real_calls is not None or confirmed_real or real_scope != "pilot":
            raise Task67RunError("real-call controls are only valid in real mode")
        requested = list(by_id) if include_ids is None else include_ids
    elif mode == "real":
        if not confirmed_real:
            raise Task67RunError("real mode requires --confirm-real")
        if include_ids is None or not include_ids:
            raise Task67RunError("real mode requires an explicit --include-id allowlist")
        if real_scope == "pilot":
            raise Task67RunError(
                "the real pilot IDs were already consumed; only remaining-125 is available"
            )
        elif real_scope == REMAINING_REAL_SCOPE:
            if max_real_calls != MAX_REMAINING_CALLS or len(include_ids) != 1:
                raise Task67RunError(
                    "remaining-125 mode requires exactly one --include-id and --max-real-calls 1"
                )
            remaining_ids = remaining_authorized_ids(cases)
            if not set(include_ids).issubset(remaining_ids):
                raise Task67RunError(
                    "remaining-125 mode ID is outside the frozen remaining allowlist"
                )
        else:
            raise Task67RunError("unsupported real scope")
        requested = include_ids
    else:
        raise Task67RunError("unsupported run mode")

    if len(requested) != len(set(requested)):
        raise Task67RunError("--include-id values must be unique")
    missing = set(requested) - set(by_id)
    if missing:
        raise Task67RunError("selected evaluation IDs are not present in frozen inputs")
    return [by_id[case_id] for case_id in requested]


def remaining_authorized_ids(cases: list[EvaluationCase]) -> frozenset[str]:
    """Derive the frozen 125-ID scope by removing the completed pilot IDs.

    The CLI loads these cases only after verifying the frozen artifact hashes
    and 120/360/20 denominators. Requiring the exact universe here prevents a
    partial or expanded case list from silently changing the live allowlist.
    """
    case_ids = {case.case_id for case in cases}
    if len(case_ids) != len(cases):
        raise Task67RunError("evaluation case IDs must be unique")
    if len(case_ids) != 140 or not AUTHORIZED_REAL_PILOT_IDS.issubset(case_ids):
        raise Task67RunError("remaining-125 mode requires the frozen 140-case universe")
    remaining = case_ids - AUTHORIZED_REAL_PILOT_IDS
    if len(remaining) != 125 or remaining.intersection(AUTHORIZED_REAL_PILOT_IDS):
        raise Task67RunError("remaining-125 allowlist is inconsistent with the frozen pilot")
    return frozenset(remaining)


def _failure_rows(case: EvaluationCase, *, status: str, error_code: str) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case.case_id,
            "kind": case.kind,
            "dataset": case.dataset,
            "dish_id": case.dish_id,
            "query_id": ingredient.query_id,
            "ingredient_index": index,
            "query": ingredient.query,
            "candidate_ids": [candidate.item_id for candidate in ingredient.candidates],
            "baseline_v2": _baseline_v2_record(ingredient),
            "decision_status": status,
            "error_code": error_code,
            "selected_item_id": None,
            "final_item_id": None,
            "is_fallback": False,
            "acceptable_item_ids": list(ingredient.acceptable_item_ids),
            "gold_hit": False,
            "negative_fallback_correct": False,
            "elapsed_ms": None,
        }
        for index, ingredient in enumerate(case.ingredients)
    ]


def score_case(
    case: EvaluationCase,
    selected_ids: tuple[str | None, ...],
    catalog: VanillaCatalog,
    *,
    elapsed_ms: float | None = None,
) -> list[dict[str, Any]]:
    if len(selected_ids) != len(case.ingredients):
        raise Task67ProtocolError("decision_count_mismatch")

    reserved_selected_item_ids: set[str] = set()
    for ingredient, selected_id in zip(case.ingredients, selected_ids, strict=True):
        if selected_id is None:
            continue
        candidate_ids = {candidate.item_id for candidate in ingredient.candidates}
        if selected_id not in candidate_ids:
            raise Task67ProtocolError("selected_id_not_in_candidates")
        if selected_id in reserved_selected_item_ids:
            raise Task67ProtocolError("duplicate_selected_id")
        reserved_selected_item_ids.add(selected_id)

    used_item_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, (ingredient, selected_id) in enumerate(zip(case.ingredients, selected_ids, strict=True)):
        semantic = _SemanticIngredient(ingredient.query)
        fallback_exclusions = frozenset(used_item_ids | reserved_selected_item_ids)
        if selected_id is None:
            mapped = map_ingredient(
                semantic,
                [],
                catalog,
                used_item_ids=fallback_exclusions,
                language=Language.ZH_CN,
            )
            is_fallback = True
        else:
            mapped = map_ingredient(
                semantic,
                [CatalogCandidate(selected_id, 1.0)],
                catalog,
                used_item_ids=fallback_exclusions,
                language=Language.ZH_CN,
            )
            is_fallback = mapped.mapping_reason.startswith("catalog fallback")
        if mapped.item_id in used_item_ids:
            raise Task67ProtocolError("duplicate_final_item_id")
        if is_fallback and mapped.item_id in reserved_selected_item_ids:
            raise Task67ProtocolError("duplicate_final_item_id")
        used_item_ids.add(mapped.item_id)
        gold_hit = (
            case.kind == "positive"
            and not is_fallback
            and mapped.item_id in ingredient.acceptable_item_ids
        )
        rows.append(
            {
                "case_id": case.case_id,
                "kind": case.kind,
                "dataset": case.dataset,
                "dish_id": case.dish_id,
                "query_id": ingredient.query_id,
                "ingredient_index": index,
                "query": ingredient.query,
                "candidate_ids": [candidate.item_id for candidate in ingredient.candidates],
                "baseline_v2": _baseline_v2_record(ingredient),
                "decision_status": "valid",
                "error_code": None,
                "selected_item_id": selected_id,
                "final_item_id": mapped.item_id,
                "is_fallback": is_fallback,
                "acceptable_item_ids": list(ingredient.acceptable_item_ids),
                "gold_hit": gold_hit,
                "negative_fallback_correct": case.kind == "negative" and is_fallback,
                "elapsed_ms": elapsed_ms,
            }
        )
    return rows


@dataclass(frozen=True)
class _SemanticIngredient:
    name: str

    @property
    def normalized_name(self) -> str:
        return self.name


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def summarize_results(
    cases: list[EvaluationCase],
    item_results: list[dict[str, Any]],
    *,
    mode: str,
    logical_call_count: int,
    network_request_count: int,
    latencies_ms: list[float],
    source_counts: dict[str, int],
) -> dict[str, Any]:
    positive_items = [row for row in item_results if row["kind"] == "positive"]
    negative_items = [row for row in item_results if row["kind"] == "negative"]
    positive_cases = [case for case in cases if case.kind == "positive"]
    negative_cases = [case for case in cases if case.kind == "negative"]
    results_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in positive_items:
        results_by_case.setdefault(row["case_id"], []).append(row)
    all_gold_dishes = sum(
        bool(results_by_case.get(case.case_id))
        and all(row["gold_hit"] for row in results_by_case[case.case_id])
        for case in positive_cases
    )
    gold_item_hits = sum(bool(row["gold_hit"]) for row in positive_items)
    correct_negative_fallbacks = sum(
        bool(row["negative_fallback_correct"]) for row in negative_items
    )
    fallback_count = sum(bool(row["is_fallback"]) for row in item_results)
    failed_count = sum(row["decision_status"] != "valid" for row in item_results)
    return {
        "acceptance_contract_id": CONTRACT_ID,
        "mode": mode,
        "source_fixed_denominators": source_counts,
        "evaluated_denominators": {
            "positive_dish_count": len(positive_cases),
            "positive_item_count": len(positive_items),
            "negative_case_count": len(negative_cases),
        },
        "positive_item_gold": {
            "numerator": gold_item_hits,
            "denominator": len(positive_items),
            "value": gold_item_hits / len(positive_items) if positive_items else None,
        },
        "positive_dish_all_gold": {
            "numerator": all_gold_dishes,
            "denominator": len(positive_cases),
            "value": all_gold_dishes / len(positive_cases) if positive_cases else None,
        },
        "negative_fallback_correct": {
            "numerator": correct_negative_fallbacks,
            "denominator": len(negative_cases),
            "value": (
                correct_negative_fallbacks / len(negative_cases)
                if negative_cases
                else None
            ),
        },
        "catalog_fallback_count": fallback_count,
        "invalid_or_failed_item_count": failed_count,
        "logical_call_count": logical_call_count,
        "network_request_count": network_request_count,
        "latency_ms": {
            "mean": round(statistics.fmean(latencies_ms), 3) if latencies_ms else None,
            "p50": _percentile(latencies_ms, 0.50),
            "p95": _percentile(latencies_ms, 0.95),
            "per_call": latencies_ms,
        },
    }


async def evaluate_cases(
    cases: list[EvaluationCase],
    gateway: VerifierGateway,
    catalog: VanillaCatalog,
    *,
    mode: Literal["fake", "real"] = "fake",
    real_scope: RealScope = "pilot",
    call_limit: int | None = None,
    source_counts: dict[str, int] | None = None,
    input_hashes: dict[str, str] | None = None,
    model_id: str | None = None,
) -> EvaluationRun:
    if len(cases) != len({case.case_id for case in cases}):
        raise Task67RunError("evaluation case IDs must be unique")
    if mode == "real":
        if real_scope == "pilot":
            raise Task67RunError(
                "the real pilot IDs were already consumed; only remaining-125 is available"
            )
        if real_scope != REMAINING_REAL_SCOPE:
            raise Task67RunError("unsupported real scope")
        scope_limit = MAX_REMAINING_CALLS
        if call_limit is None or not 1 <= call_limit <= scope_limit:
            raise Task67RunError(f"real mode call limit must be 1..{scope_limit}")
        if real_scope == REMAINING_REAL_SCOPE and len(cases) != 1:
            raise Task67RunError("remaining-125 mode requires exactly one case per invocation")
        if len(cases) > call_limit:
            raise Task67RunError("selected cases exceed the physical HTTP request limit")
    elif call_limit is not None:
        raise Task67RunError("call_limit is only valid for real mode")
    elif real_scope != "pilot":
        raise Task67RunError("real_scope is only valid for real mode")

    payloads = [(case, build_prompt_payload(case)) for case in cases]
    requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    item_results: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    logical_call_count = 0
    network_request_count = 0
    run_started = time.perf_counter()

    for case, payload in payloads:
        prompt_text = render_prompt(payload)
        requests.append(
            {
                "case_id": case.case_id,
                "prompt_payload": payload,
                "prompt_text": prompt_text,
                "prompt_sha256": _sha256_bytes(prompt_text.encode("utf-8")),
                "candidate_sha256": candidate_fingerprint(payload),
            }
        )
        logical_call_count += 1
        try:
            reply = await gateway.complete(
                prompt_payload=payload,
                prompt_text=prompt_text,
            )
            network_request_count += reply.network_request_count
            latencies_ms.append(reply.elapsed_ms)
            selected_ids = validate_response(case, reply.response_text)
            case_results = score_case(case, selected_ids, catalog, elapsed_ms=reply.elapsed_ms)
            response_record = {
                "case_id": case.case_id,
                "status": "valid",
                "parsed_response": {
                    "decisions": [
                        {"ingredient_index": index, "selected_item_id": item_id}
                        for index, item_id in enumerate(selected_ids)
                    ]
                },
                "raw_response_sha256": reply.raw_response_sha256,
                "elapsed_ms": reply.elapsed_ms,
                "network_request_count": reply.network_request_count,
                "http_status": reply.http_status,
                "error_code": None,
            }
        except GatewayCallError as exc:
            network_request_count += exc.network_request_count
            if exc.elapsed_ms is not None:
                latencies_ms.append(exc.elapsed_ms)
            responses.append(
                {
                    "case_id": case.case_id,
                    "status": "provider_error",
                    "parsed_response": None,
                    "raw_response_sha256": None,
                    "elapsed_ms": exc.elapsed_ms,
                    "network_request_count": exc.network_request_count,
                    "http_status": exc.http_status,
                    "error_code": exc.code,
                }
            )
            item_results.extend(
                _failure_rows(case, status="provider_error", error_code=exc.code)
            )
            continue
        except Task67ProtocolError as exc:
            # Keep only the validation code/hash; never persist malformed body text.
            hash_value = reply.raw_response_sha256
            elapsed_value = reply.elapsed_ms
            request_count = reply.network_request_count
            http_status = reply.http_status
            responses.append(
                {
                    "case_id": case.case_id,
                    "status": "invalid_response",
                    "parsed_response": None,
                    "raw_response_sha256": hash_value,
                    "elapsed_ms": elapsed_value,
                    "network_request_count": request_count,
                    "http_status": http_status,
                    "error_code": exc.code,
                }
            )
            item_results.extend(
                _failure_rows(case, status="invalid_response", error_code=exc.code)
            )
            continue
        else:
            responses.append(response_record)
            item_results.extend(case_results)

    summary = summarize_results(
        cases,
        item_results,
        mode=mode,
        logical_call_count=logical_call_count,
        network_request_count=network_request_count,
        latencies_ms=latencies_ms,
        source_counts=source_counts
        or {
            "positive_dish_count": sum(case.kind == "positive" for case in cases),
            "positive_item_count": sum(
                len(case.ingredients) for case in cases if case.kind == "positive"
            ),
            "negative_case_count": sum(case.kind == "negative" for case in cases),
        },
    )
    summary["total_elapsed_ms"] = round((time.perf_counter() - run_started) * 1000, 3)
    summary["model_id"] = model_id if mode == "real" else None
    manifest = {
        "acceptance_contract_id": CONTRACT_ID,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": mode,
        "real_scope": real_scope if mode == "real" else None,
        "model_id": model_id if mode == "real" else None,
        "input_sha256": input_hashes or {},
        "source_fixed_denominators": summary["source_fixed_denominators"],
        "evaluated_denominators": summary["evaluated_denominators"],
        "logical_call_count": logical_call_count,
        "network_request_count": network_request_count,
        "prompt_allowed_fields": list(REQUEST_FIELDS),
        "prompt_forbidden_fields": list(FORBIDDEN_PROMPT_FIELDS),
        "api_key_recorded": False,
        "jev_calls": 0,
        "artifact_sha256": {},
    }
    return EvaluationRun(requests, responses, item_results, summary, manifest)


def _json_bytes(value: object, *, indent: int | None = None) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=indent) + "\n").encode(
        "utf-8"
    )


def reserve_remaining_case_output(
    output_dir: Path,
    case: EvaluationCase,
    *,
    input_hashes: dict[str, str],
) -> None:
    """Exclusively reserve a one-case output before its only real request."""
    output_dir.mkdir(parents=True, exist_ok=False)
    reservation = {
        "acceptance_contract_id": CONTRACT_ID,
        "mode": "real",
        "real_scope": REMAINING_REAL_SCOPE,
        "case_id": case.case_id,
        "reserved_at_utc": datetime.now(UTC).isoformat(),
        "expected_physical_requests": 1,
        "state": "reserved_before_request",
        "input_sha256": input_hashes,
        "api_key_recorded": False,
    }
    with (output_dir / "reservation.json").open("xb") as handle:
        handle.write(_json_bytes(reservation, indent=2))


def write_run(output_dir: Path, run: EvaluationRun, *, reserved: bool = False) -> None:
    if reserved:
        if not output_dir.is_dir():
            raise Task67RunError("reserved output directory must already exist")
        existing_names = {path.name for path in output_dir.iterdir()}
        if existing_names not in (set(), {"reservation.json"}):
            raise Task67RunError("reserved output directory contains prior output")
    else:
        output_dir.mkdir(parents=True, exist_ok=False)

    artifact_values = {
        "requests.jsonl": run.requests,
        "responses.jsonl": run.responses,
        "ingredient_results.jsonl": run.ingredient_results,
    }
    for name, rows in artifact_values.items():
        path = output_dir / name
        with path.open("xb") as handle:
            for row in rows:
                handle.write(_json_bytes(row))

    summary_path = output_dir / "summary.json"
    with summary_path.open("xb") as handle:
        handle.write(_json_bytes(run.summary, indent=2))
    run.manifest["artifact_sha256"] = {
        name: _sha256_file(output_dir / name)
        for name in (*artifact_values, "summary.json")
    }
    with (output_dir / "manifest.json").open("xb") as handle:
        handle.write(_json_bytes(run.manifest, indent=2))


class _SettingsWorkspaceView:
    def __init__(self, app_state_dir: Path) -> None:
        self.app_state_dir = app_state_dir


class ExistingProviderVerifierGateway:
    """One-shot adapter over the application's existing personal Provider."""

    def __init__(
        self,
        gateway: OpenAICompatibleGateway,
        settings: ProviderSettings,
        *,
        max_requests: int,
    ) -> None:
        if max_requests != MAX_REAL_CALLS:
            raise Task67RunError("Provider adapter cap must be exactly one request")
        gateway_retry_policy = getattr(gateway, "_retry", None)
        if settings.max_automatic_retries != 0 or (
            gateway_retry_policy is not None
            and getattr(gateway_retry_policy, "max_retries", None) != 0
        ):
            raise Task67RunError("Provider automatic retries must be disabled")
        self._gateway = gateway
        self._settings = settings
        self._max_requests = max_requests
        self.network_request_count = 0

    @classmethod
    def from_personal_settings(
        cls,
        *,
        workspace_root: Path | None,
        max_requests: int,
    ) -> ExistingProviderVerifierGateway:
        root = (workspace_root or AppConfig().workspace_path).expanduser().resolve()
        settings_path = root / "app-state" / "settings.json"
        if not settings_path.is_file():
            raise Task67RunError("personal Provider settings file is missing")
        secret_store = WindowsEnvironmentSecretStore()
        service = ProviderSettingsService(
            _SettingsWorkspaceView(root / "app-state"),  # type: ignore[arg-type]
            secret_store,
        )
        view = service.get_provider_settings()
        if not view.api_key_configured or secret_store.get_api_key() is None:
            raise Task67RunError("personal PTS_OPENAI_API_KEY is not configured")
        settings = ProviderSettings.model_validate(
            view.model_dump(exclude={"api_key_configured", "api_key_source"})
        )
        if not settings.text_model.strip():
            raise Task67RunError("personal text model is not configured")
        # The gateway's transport retry policy is disabled to preserve one HTTP
        # request per selected case. Structured-output repair is not invoked.
        settings = settings.model_copy(update={"max_automatic_retries": 0})
        gateway = OpenAICompatibleGateway(settings=settings, secret_store=secret_store)
        return cls(gateway, settings, max_requests=max_requests)

    async def complete(
        self,
        *,
        prompt_payload: dict[str, Any],
        prompt_text: str,
    ) -> GatewayReply:
        del prompt_payload
        if self.network_request_count >= self._max_requests:
            raise GatewayCallError("physical_request_limit_reached", network_request_count=0)
        body = self._gateway._chat_body(
            model=self._settings.text_model,
            prompt=prompt_text,
            json_instruction=JSON_SCHEMA_INSTRUCTION,
            image_data_urls=None,
            use_json_schema=True,
            target_type=IngredientVerifierResponse,
        )
        request_id = uuid4()
        started = time.perf_counter()
        self.network_request_count += 1
        try:
            response = await self._gateway._request(
                method="POST",
                url=self._gateway._url("chat/completions"),
                request_id=request_id,
                timeout=self._settings.chat_timeout_seconds,
                json=body,
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            if response.status_code >= 400:
                raise GatewayCallError(
                    "provider_http_error",
                    network_request_count=1,
                    http_status=response.status_code,
                    elapsed_ms=elapsed_ms,
                )
            response_text = _extract_chat_text(response)
            return GatewayReply(
                response_text=response_text,
                raw_response_sha256=_sha256_bytes(response_text.encode("utf-8")),
                elapsed_ms=elapsed_ms,
                network_request_count=1,
                http_status=response.status_code,
            )
        except GatewayCallError:
            raise
        except (AppError, StructuredOutputError):
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            raise GatewayCallError(
                "provider_request_failed",
                network_request_count=1,
                elapsed_ms=elapsed_ms,
            ) from None

    async def aclose(self) -> None:
        await self._gateway._http_client.aclose()


def _dry_run_plan(
    cases: list[EvaluationCase],
    selected: list[EvaluationCase],
    *,
    mode: str,
    real_scope: RealScope,
    max_real_calls: int | None,
    input_hashes: dict[str, str],
    source_counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "acceptance_contract_id": CONTRACT_ID,
        "mode": mode,
        "real_scope": real_scope if mode == "real" else None,
        "network_requests_performed": 0,
        "would_request_count": len(selected) if mode == "real" else 0,
        "real_physical_request_cap": max_real_calls if mode == "real" else 0,
        "selected_ids": [case.case_id for case in selected],
        "available_case_count": len(cases),
        "source_fixed_denominators": source_counts,
        "input_sha256": input_hashes,
        "prompt_allowed_fields": list(REQUEST_FIELDS),
        "prompt_forbidden_fields": list(FORBIDDEN_PROMPT_FIELDS),
        "api_key_recorded": False,
        "jev_calls": 0,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fake", "real"), default="fake")
    parser.add_argument(
        "--real-scope", choices=("pilot", REMAINING_REAL_SCOPE), default="pilot"
    )
    parser.add_argument("--include-id", action="append", dest="include_ids")
    parser.add_argument("--max-real-calls", type=int)
    parser.add_argument("--confirm-real", action="store_true")
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


async def _run_cli(args: argparse.Namespace) -> int:
    cases, source_counts, input_hashes = load_frozen_cases()
    selected = select_cases(
        cases,
        mode=args.mode,
        include_ids=args.include_ids,
        max_real_calls=args.max_real_calls,
        confirmed_real=args.confirm_real,
        real_scope=args.real_scope,
    )
    if args.dry_run:
        plan = _dry_run_plan(
            cases,
            selected,
            mode=args.mode,
            real_scope=args.real_scope,
            max_real_calls=args.max_real_calls,
            input_hashes=input_hashes,
            source_counts=source_counts,
        )
        sys.stdout.write(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
        return 0

    gateway: VerifierGateway
    model_id: str | None = None
    if args.mode == "fake":
        gateway = FakeVerifierGateway()
    else:
        if args.max_real_calls is None:
            raise Task67RunError("--max-real-calls is required in real mode")
        real_gateway = ExistingProviderVerifierGateway.from_personal_settings(
            workspace_root=args.workspace_root,
            max_requests=args.max_real_calls,
        )
        gateway = real_gateway
        model_id = real_gateway._settings.text_model

    # Reserve the per-case output before the first request. The marker survives
    # an interrupted request so the parent can reconcile its cross-run ledger.
    if args.mode == "real" and args.real_scope == REMAINING_REAL_SCOPE:
        reserve_remaining_case_output(
            args.output_dir,
            selected[0],
            input_hashes=input_hashes,
        )
    else:
        # Existing runs are never overwritten and cannot accidentally receive
        # new results.
        args.output_dir.mkdir(parents=True, exist_ok=False)
    try:
        run = await evaluate_cases(
            selected,
            gateway,
            VanillaCatalog.from_json(DEFAULT_CATALOG),
            mode=args.mode,
            real_scope=args.real_scope,
            call_limit=args.max_real_calls if args.mode == "real" else None,
            source_counts=source_counts,
            input_hashes=input_hashes,
            model_id=model_id,
        )
        write_run(args.output_dir, run, reserved=True)
    finally:
        close = getattr(gateway, "aclose", None)
        if close is not None:
            await close()
    sys.stdout.write(json.dumps(run.summary, ensure_ascii=False, indent=2) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return asyncio.run(_run_cli(args))
    except (Task67RunError, OSError) as exc:
        sys.stderr.write(f"Task67 evaluation stopped: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
