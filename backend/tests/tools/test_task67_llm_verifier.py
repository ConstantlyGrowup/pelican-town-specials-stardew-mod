from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Self

import pytest
from scripts import evaluate_task67_llm_verifier as verifier

from pelican_town_specials.catalog.repository import VanillaCatalog

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = (
    REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


def _candidate(item_id: str, name_en: str = "Potato", name_zh: str = "土豆") -> dict[str, str]:
    return {"item_id": item_id, "name_en": name_en, "name_zh": name_zh}


def _positive_row(
    *,
    query_id: str,
    dish_id: str,
    query: str,
    gold: list[str],
    candidates: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "dataset": "task64",
        "dish_id": dish_id,
        "dish_name_en": "Potato Soup",
        "dish_name_zh": "土豆汤",
        "query_id": query_id,
        "query": query,
        "gold_item_ids": gold,
        "retrieval_status": "success",
        "retrieval_reason_code": None,
        "mapping_status": "mapped",
        "mapping_reason": "selected validated vanilla candidate",
        "selected_id": candidates[0]["item_id"],
        "is_fallback": False,
        "historical_legacy": {"selected_id": "999"},
        "mapper_candidates": [
            {
                **candidate,
                "category": "sensitive-local-field",
                "type": "sensitive-local-field",
                "rank_score": 0.99,
            }
            for candidate in candidates
        ],
        "retrieval_evidence": {
            "semantic_top5": [
                {
                    **_candidate("semantic-only", "Wrong source", "错误来源"),
                    "category": "sensitive-local-field",
                    "type": "sensitive-local-field",
                    "cosine_similarity": 0.99,
                }
            ]
        },
    }


def _negative_fixture() -> dict[str, Any]:
    return {
        "fixture_id": "fixture-v1",
        "expected_result": "fallback",
        "cases": [{"id": "n13", "query": "unmapped ingredient", "group": "private-label"}],
    }


def _negative_row() -> dict[str, Any]:
    return {
        "query_id": "n13",
        "query": "unmapped ingredient",
        "expected_fallback": True,
        "selected_id": "176",
        "retrieval_status": "no_match",
        "retrieval_reason_code": "rag_no_semantic_match",
        "mapping_status": "mapped",
        "mapping_reason": "catalog fallback: no candidate matched the ingredient",
        "is_fallback": True,
        "retrieval_evidence": {
            "ranked_candidates_before_semantic_verification": [
                {
                    "item_id": "192",
                    "name_en": "Potato",
                    "name_zh": "土豆",
                    "category": "sensitive-local-field",
                    "type": "sensitive-local-field",
                    "rank_score": 0.99,
                }
            ],
            "semantic_top5": [
                {
                    "item_id": "semantic-only",
                    "name_en": "Wrong source",
                    "name_zh": "错误来源",
                    "category": "sensitive-local-field",
                    "type": "sensitive-local-field",
                    "cosine_similarity": 0.99,
                }
            ]
        },
    }


def _case(case_id: str = "d07") -> verifier.EvaluationCase:
    return verifier.EvaluationCase(
        case_id=case_id,
        kind="positive",
        dataset="task64",
        dish_id=case_id,
        dish_name_en="Potato Soup",
        dish_name_zh="土豆汤",
        ingredients=(
            verifier.EvaluationIngredient(
                query_id=f"{case_id}-i01",
                query="potato",
                candidates=(verifier.VerifierCandidate("192", "Potato", "土豆"),),
                acceptable_item_ids=("192",),
            ),
        ),
    )


def test_prompt_only_contains_approved_payload_and_omits_labels_and_scores() -> None:
    positive_rows = [
        _positive_row(
            query_id="d07-i01",
            dish_id="d07",
            query="potato",
            gold=["192"],
            candidates=[_candidate("192")],
        )
    ]
    cases = verifier.cases_from_frozen_rows(
        positive_rows,
        _negative_fixture(),
        [_negative_row()],
    )

    payload = verifier.build_prompt_payload(cases[0])
    prompt = verifier.render_prompt(payload)
    encoded = json.dumps(payload, ensure_ascii=False)

    assert set(payload) == {"dish_name", "ingredients"}
    assert set(payload["dish_name"]) == {"english", "chinese"}
    ingredient = payload["ingredients"][0]
    assert set(ingredient) == {
        "ingredient_index",
        "real_world_ingredient",
        "candidates",
        "no_match_option",
    }
    assert set(ingredient["candidates"][0]) == {"item_id", "name_en", "name_zh"}
    assert ingredient["candidates"][0]["item_id"] == "192"
    assert "semantic-only" not in encoded
    assert ingredient["no_match_option"] is None
    assert "sensitive-local-field" not in prompt
    assert "0.99" not in prompt
    assert "historical_legacy" not in prompt
    assert "acceptable_item_ids" not in prompt
    assert "private-label" not in prompt
    assert "gold" not in encoded.casefold()
    assert "retrieval_status" not in prompt
    assert "selected_id" not in prompt
    scored = verifier.score_case(
        cases[0], ("192",), VanillaCatalog.from_json(CATALOG_PATH)
    )
    assert scored[0]["baseline_v2"] == {
        "retrieval_status": "success",
        "retrieval_reason_code": None,
        "mapping_status": "mapped",
        "mapping_reason": "selected validated vanilla candidate",
        "selected_item_id": "192",
        "is_fallback": False,
    }

    negative = cases[1]
    negative_payload = verifier.build_prompt_payload(negative)
    assert negative_payload["dish_name"] is None
    assert negative_payload["ingredients"][0]["real_world_ingredient"] == "unmapped ingredient"
    assert negative_payload["ingredients"][0]["candidates"][0]["item_id"] == "192"
    assert "semantic-only" not in json.dumps(negative_payload)
    negative_scored = verifier.score_case(
        negative, (None,), VanillaCatalog.from_json(CATALOG_PATH)
    )
    assert negative_scored[0]["baseline_v2"]["retrieval_status"] == "no_match"
    assert negative_scored[0]["baseline_v2"]["is_fallback"] is True


def test_frozen_rows_make_one_positive_request_per_dish_and_one_per_negative() -> None:
    positives = [
        _positive_row(
            query_id="d01-i01",
            dish_id="d01",
            query="potato",
            gold=["192"],
            candidates=[_candidate("192")],
        ),
        _positive_row(
            query_id="d01-i02",
            dish_id="d01",
            query="egg",
            gold=["176"],
            candidates=[_candidate("176", "Egg", "蛋")],
        ),
    ]
    negatives = [{"query_id": "n13", "query": "unmapped ingredient", "retrieval_evidence": _negative_row()["retrieval_evidence"]}]

    cases = verifier.cases_from_frozen_rows(positives, _negative_fixture(), negatives)

    assert [case.case_id for case in cases] == ["d01", "n13"]
    assert len(cases[0].ingredients) == 2
    assert len(cases[1].ingredients) == 1


@pytest.mark.parametrize(
    "response_text, error_code",
    [
        ('{"decisions":[]}', "decision_count_mismatch"),
        (
            json.dumps(
                {
                    "decisions": [
                        {"ingredientIndex": 0, "selectedItemId": "192"},
                        {"ingredientIndex": 0, "selectedItemId": "176"},
                    ]
                }
            ),
            "duplicate_ingredient_index",
        ),
        (
            json.dumps(
                {
                    "decisions": [
                        {"ingredientIndex": 0, "selectedItemId": "999"},
                        {"ingredientIndex": 1, "selectedItemId": None},
                    ]
                }
            ),
            "selected_id_not_in_candidates",
        ),
        (
            json.dumps(
                {
                    "decisions": [
                        {"ingredientIndex": 0, "selectedItemId": "192"},
                        {"ingredientIndex": 1, "selectedItemId": "192"},
                    ]
                }
            ),
            "duplicate_selected_id",
        ),
        (
            '{"decisions":[{"ingredientIndex":0,"selectedItemId":"192"}],"reason":"x"}',
            "invalid_structured_response",
        ),
        ("```json\n{}\n```", "invalid_structured_response"),
    ],
)
def test_response_validation_rejects_incomplete_or_unsafe_selections(
    response_text: str, error_code: str
) -> None:
    case = verifier.EvaluationCase(
        case_id="d07",
        kind="positive",
        dataset="task64",
        dish_id="d07",
        dish_name_en="Potato Soup",
        dish_name_zh="土豆汤",
        ingredients=(
            verifier.EvaluationIngredient(
                query_id="d07-i01",
                query="potato",
                candidates=(verifier.VerifierCandidate("192", "Potato", "土豆"),),
                acceptable_item_ids=("192",),
            ),
            verifier.EvaluationIngredient(
                query_id="d07-i02",
                query="egg",
                candidates=(verifier.VerifierCandidate("176", "Egg", "蛋"),),
                acceptable_item_ids=("176",),
            ),
        ),
    )

    with pytest.raises(verifier.Task67ProtocolError) as exc_info:
        verifier.validate_response(case, response_text)

    assert exc_info.value.code == error_code


def test_null_is_mapped_through_existing_catalog_fallback_for_scoring() -> None:
    catalog = VanillaCatalog.from_json(CATALOG_PATH)
    case = verifier.EvaluationCase(
        case_id="n13",
        kind="negative",
        dataset="negative",
        dish_id=None,
        dish_name_en=None,
        dish_name_zh=None,
        ingredients=(
            verifier.EvaluationIngredient(
                query_id="n13",
                query="unmapped ingredient",
                candidates=(verifier.VerifierCandidate("192", "Potato", "土豆"),),
                acceptable_item_ids=(),
            ),
        ),
    )

    results = verifier.score_case(case, (None,), catalog)

    assert results[0]["is_fallback"] is True
    assert results[0]["selected_item_id"] is None
    assert results[0]["final_item_id"] == "176"
    assert results[0]["negative_fallback_correct"] is True


def test_fallback_reserves_later_selected_id_without_counting_it_as_a_strong_match() -> None:
    catalog = VanillaCatalog.from_json(CATALOG_PATH)
    case = verifier.EvaluationCase(
        case_id="d07",
        kind="positive",
        dataset="task64",
        dish_id="d07",
        dish_name_en="Potato and egg soup",
        dish_name_zh="土豆鸡蛋汤",
        ingredients=(
            verifier.EvaluationIngredient(
                query_id="d07-i01",
                query="unmapped ingredient",
                candidates=(verifier.VerifierCandidate("192", "Potato", "土豆"),),
                acceptable_item_ids=("176",),
            ),
            verifier.EvaluationIngredient(
                query_id="d07-i02",
                query="egg",
                candidates=(verifier.VerifierCandidate("176", "Egg", "蛋"),),
                acceptable_item_ids=("176",),
            ),
        ),
    )

    class FixedDecisionGateway:
        async def complete(
            self,
            *,
            prompt_payload: dict[str, Any],
            prompt_text: str,
        ) -> verifier.GatewayReply:
            del prompt_payload, prompt_text
            response_text = json.dumps(
                {
                    "decisions": [
                        {"ingredientIndex": 0, "selectedItemId": None},
                        {"ingredientIndex": 1, "selectedItemId": "176"},
                    ]
                }
            )
            return verifier.GatewayReply(
                response_text=response_text,
                raw_response_sha256="0" * 64,
                elapsed_ms=1.0,
                network_request_count=0,
            )

    run = asyncio.run(
        verifier.evaluate_cases([case], FixedDecisionGateway(), catalog)
    )
    first, second = run.ingredient_results

    assert first["is_fallback"] is True
    assert first["final_item_id"] != "176"
    assert first["gold_hit"] is False
    assert second["selected_item_id"] == "176"
    assert second["final_item_id"] == "176"
    assert second["is_fallback"] is False
    assert second["gold_hit"] is True
    assert run.summary["positive_item_gold"] == {
        "numerator": 1,
        "denominator": 2,
        "value": 0.5,
    }
    assert run.summary["positive_dish_all_gold"] == {
        "numerator": 0,
        "denominator": 1,
        "value": 0.0,
    }
    assert run.summary["catalog_fallback_count"] == 1
    assert run.summary["invalid_or_failed_item_count"] == 0


def test_multiple_null_fallbacks_are_unique_and_reserve_later_selected_ids() -> None:
    catalog = VanillaCatalog.from_json(CATALOG_PATH)
    case = verifier.EvaluationCase(
        case_id="d18",
        kind="positive",
        dataset="task64",
        dish_id="d18",
        dish_name_en="Mixed dish",
        dish_name_zh="混合菜",
        ingredients=(
            verifier.EvaluationIngredient(
                query_id="d18-i01",
                query="unmapped ingredient one",
                candidates=(),
                acceptable_item_ids=(),
            ),
            verifier.EvaluationIngredient(
                query_id="d18-i02",
                query="unmapped ingredient two",
                candidates=(),
                acceptable_item_ids=(),
            ),
            verifier.EvaluationIngredient(
                query_id="d18-i03",
                query="egg",
                candidates=(verifier.VerifierCandidate("176", "Egg", "蛋"),),
                acceptable_item_ids=("176",),
            ),
        ),
    )

    results = verifier.score_case(case, (None, None, "176"), catalog)
    final_ids = [row["final_item_id"] for row in results]

    assert len(final_ids) == len(set(final_ids))
    assert final_ids[0] != "176"
    assert final_ids[1] != "176"
    assert results[0]["is_fallback"] is True
    assert results[1]["is_fallback"] is True
    assert results[2]["is_fallback"] is False
    assert results[2]["gold_hit"] is True


def test_real_mode_rejects_already_consumed_pilot_scope_but_fake_can_read_it() -> None:
    cases = [_case("d07"), _case("n13")]
    assert verifier.AUTHORIZED_REAL_PILOT_IDS == {
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
    assert len(verifier.AUTHORIZED_REAL_PILOT_IDS) == 15

    with pytest.raises(verifier.Task67RunError, match="already consumed"):
        verifier.select_cases(
            cases,
            mode="real",
            include_ids=["d07"],
            max_real_calls=1,
            confirmed_real=True,
        )

    fake_selected = verifier.select_cases(
        cases,
        mode="fake",
        include_ids=["d07"],
        max_real_calls=None,
        confirmed_real=False,
    )
    assert [case.case_id for case in fake_selected] == ["d07"]


def _full_frozen_case_universe() -> list[verifier.EvaluationCase]:
    pilot_cases = [
        _case(case_id) for case_id in sorted(verifier.AUTHORIZED_REAL_PILOT_IDS)
    ]
    remaining_cases = [_case(f"remaining-{index:03d}") for index in range(125)]
    return pilot_cases + remaining_cases


@pytest.mark.parametrize("dry_run", [False, True])
def test_cli_blocks_consumed_pilot_before_provider_or_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    dry_run: bool,
) -> None:
    cases = _full_frozen_case_universe()
    monkeypatch.setattr(
        verifier,
        "load_frozen_cases",
        lambda: (
            cases,
            {
                "positive_dish_count": 120,
                "positive_item_count": 360,
                "negative_case_count": 20,
            },
            {"fixture.json": "A" * 64},
        ),
    )
    provider_config_calls: list[bool] = []
    output_mkdir_calls: list[Path] = []

    class ForbiddenProviderFactory:
        @classmethod
        def from_personal_settings(cls, **_: Any) -> None:
            provider_config_calls.append(True)
            raise AssertionError("consumed pilot must fail before Provider setup")

    monkeypatch.setattr(
        verifier, "ExistingProviderVerifierGateway", ForbiddenProviderFactory
    )
    output_dir = Path(f"task67-v4-pilot-blocked-output-{id(monkeypatch)}")
    original_mkdir = Path.mkdir

    def track_output_mkdir(
        path: Path, *args: Any, **kwargs: Any
    ) -> None:
        if path == output_dir:
            output_mkdir_calls.append(path)
            raise AssertionError("consumed pilot must fail before output reservation")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", track_output_mkdir)
    argv = [
        "--mode",
        "real",
        "--real-scope",
        "pilot",
        "--include-id",
        "d07",
        "--max-real-calls",
        "1",
        "--confirm-real",
        "--output-dir",
        str(output_dir),
    ]
    if dry_run:
        argv.append("--dry-run")

    assert verifier.main(argv) == 2
    assert "already consumed" in capsys.readouterr().err
    assert provider_config_calls == []
    assert output_mkdir_calls == []


def test_remaining_125_scope_is_disjoint_and_requires_one_case_and_one_call() -> None:
    cases = _full_frozen_case_universe()
    remaining_ids = verifier.remaining_authorized_ids(cases)

    assert len(remaining_ids) == 125
    assert not remaining_ids.intersection(verifier.AUTHORIZED_REAL_PILOT_IDS)
    assert remaining_ids.union(verifier.AUTHORIZED_REAL_PILOT_IDS) == {
        case.case_id for case in cases
    }
    selected = verifier.select_cases(
        cases,
        mode="real",
        real_scope="remaining-125",
        include_ids=["remaining-000"],
        max_real_calls=1,
        confirmed_real=True,
    )
    assert [case.case_id for case in selected] == ["remaining-000"]

    for include_ids, max_real_calls in (
        (["d07"], 1),
        (["remaining-000", "remaining-001"], 1),
        (["remaining-000"], 2),
        (["unknown"], 1),
        (["remaining-000", "remaining-000"], 1),
    ):
        with pytest.raises(verifier.Task67RunError):
            verifier.select_cases(
                cases,
                mode="real",
                real_scope="remaining-125",
                include_ids=include_ids,
                max_real_calls=max_real_calls,
                confirmed_real=True,
            )

    with pytest.raises(verifier.Task67RunError, match="140-case universe"):
        verifier.remaining_authorized_ids(cases[:-1])


def test_remaining_scope_enforces_one_case_before_gateway_invocation() -> None:
    class CountingGateway:
        calls = 0

        async def complete(self, **_: Any) -> verifier.GatewayReply:
            self.calls += 1
            raise AssertionError("remaining scope must reject before the gateway call")

    gateway = CountingGateway()
    catalog = VanillaCatalog.from_json(CATALOG_PATH)

    with pytest.raises(verifier.Task67RunError, match="one case"):
        asyncio.run(
            verifier.evaluate_cases(
                [_case("remaining-a"), _case("remaining-b")],
                gateway,
                catalog,
                mode="real",
                real_scope="remaining-125",
                call_limit=1,
            )
        )

    assert gateway.calls == 0


def test_remaining_output_reservation_is_exclusive_and_contains_no_prompt_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = Path("task67-v4-one-case-output")
    case = _case("remaining-000")
    hashes = {"frozen.jsonl": "A" * 64}
    catalog = VanillaCatalog.from_json(CATALOG_PATH)
    files: dict[str, bytes] = {}
    directory_reserved = False

    class FakeBinaryFile:
        def __init__(self, name: str) -> None:
            self.name = name
            self.value = bytearray()

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            files[self.name] = bytes(self.value)

        def write(self, value: bytes) -> int:
            self.value.extend(value)
            return len(value)

    def fake_mkdir(path: Path, *_: object, **__: object) -> None:
        nonlocal directory_reserved
        assert path == output_dir
        if directory_reserved:
            raise FileExistsError(path)
        directory_reserved = True

    def fake_is_dir(path: Path) -> bool:
        return path == output_dir and directory_reserved

    def fake_iterdir(path: Path) -> Any:
        assert path == output_dir
        return iter(Path(name) for name in files)

    def fake_open(path: Path, mode: str = "r", *_: object, **__: object) -> FakeBinaryFile:
        assert path.parent == output_dir
        assert mode == "xb"
        if path.name in files:
            raise FileExistsError(path)
        return FakeBinaryFile(path.name)

    def fake_read_bytes(path: Path) -> bytes:
        return files[path.name]

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)
    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    verifier.reserve_remaining_case_output(output_dir, case, input_hashes=hashes)
    reservation_text = files["reservation.json"].decode("utf-8")
    reservation = json.loads(reservation_text)

    assert reservation["acceptance_contract_id"] == (
        "m14-task67-full-text-verifier-evaluation-v4"
    )
    assert reservation["real_scope"] == "remaining-125"
    assert reservation["case_id"] == "remaining-000"
    assert reservation["expected_physical_requests"] == 1
    assert reservation["state"] == "reserved_before_request"
    assert reservation["api_key_recorded"] is False
    assert "prompt" not in reservation_text.casefold()
    assert "potato" not in reservation_text.casefold()
    assert "candidate" not in reservation_text.casefold()
    assert "Bearer" not in reservation_text

    run = asyncio.run(
        verifier.evaluate_cases(
            [case],
            verifier.FakeVerifierGateway(),
            catalog,
        )
    )
    verifier.write_run(output_dir, run, reserved=True)
    assert "manifest.json" in files
    assert "reservation.json" in files

    with pytest.raises(FileExistsError):
        verifier.reserve_remaining_case_output(output_dir, case, input_hashes=hashes)
    with pytest.raises(verifier.Task67RunError, match="prior output"):
        verifier.write_run(output_dir, run, reserved=True)


def test_call_limit_is_checked_before_any_gateway_invocation() -> None:
    cases = [_case("remaining-000")]

    class CountingGateway:
        calls = 0

        async def complete(self, _payload: dict[str, Any]) -> verifier.GatewayReply:
            self.calls += 1
            return verifier.GatewayReply(
                response_text='{"decisions":[{"ingredientIndex":0,"selectedItemId":"192"}]}',
                raw_response_sha256="0" * 64,
                elapsed_ms=1.0,
                network_request_count=0,
            )

    gateway = CountingGateway()
    catalog = VanillaCatalog.from_json(CATALOG_PATH)

    with pytest.raises(verifier.Task67RunError, match="already consumed"):
        asyncio.run(
            verifier.evaluate_cases(
                [_case("d07")],
                gateway,
                catalog,
                mode="real",
                real_scope="pilot",
                call_limit=1,
            )
        )

    with pytest.raises(verifier.Task67RunError, match="call limit must be 1..1"):
        asyncio.run(
            verifier.evaluate_cases(
                cases,
                gateway,
                catalog,
                mode="real",
                real_scope="remaining-125",
                call_limit=0,
            )
        )

    assert gateway.calls == 0


def test_real_adapter_uses_one_fake_http_request_and_stops_at_its_cap() -> None:
    response_text = json.dumps(
        {"decisions": [{"ingredientIndex": 0, "selectedItemId": "192"}]}
    )

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": response_text}}]}

    class FakeProviderGateway:
        def __init__(self) -> None:
            self.calls = 0
            self.body: dict[str, Any] | None = None

        def _chat_body(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["image_data_urls"] is None
            assert kwargs["use_json_schema"] is True
            self.body = {"prompt": kwargs["prompt"]}
            return self.body

        def _url(self, path: str) -> str:
            return f"https://offline.invalid/{path}"

        async def _request(self, **_: Any) -> FakeResponse:
            self.calls += 1
            return FakeResponse()

    fake_gateway = FakeProviderGateway()
    with pytest.raises(verifier.Task67RunError, match="exactly one request"):
        verifier.ExistingProviderVerifierGateway(
            fake_gateway,
            verifier.ProviderSettings(
                text_model="offline-test", max_automatic_retries=0
            ),
            max_requests=2,
        )
    with pytest.raises(verifier.Task67RunError, match="retries must be disabled"):
        verifier.ExistingProviderVerifierGateway(
            fake_gateway,
            verifier.ProviderSettings(text_model="offline-test"),
            max_requests=1,
        )
    adapter = verifier.ExistingProviderVerifierGateway(
        fake_gateway,
        verifier.ProviderSettings(text_model="offline-test", max_automatic_retries=0),
        max_requests=1,
    )
    payload = verifier.build_prompt_payload(_case())
    prompt = verifier.render_prompt(payload)

    reply = asyncio.run(adapter.complete(prompt_payload=payload, prompt_text=prompt))

    assert reply.network_request_count == 1
    assert fake_gateway.calls == 1
    assert fake_gateway.body == {"prompt": prompt}
    with pytest.raises(verifier.GatewayCallError, match="physical_request_limit_reached"):
        asyncio.run(adapter.complete(prompt_payload=payload, prompt_text=prompt))
    assert fake_gateway.calls == 1


def test_evaluation_uses_one_fake_call_per_case_and_writes_exclusively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = VanillaCatalog.from_json(CATALOG_PATH)
    cases = [_case("d07")]
    cases[0] = verifier.EvaluationCase(
        **{
            **cases[0].__dict__,
            "ingredients": (
                verifier.EvaluationIngredient(
                    query_id="d07-i01",
                    query="potato",
                    candidates=(verifier.VerifierCandidate("192", "Potato", "土豆"),),
                    acceptable_item_ids=("192",),
                ),
            ),
        }
    )

    run = asyncio.run(verifier.evaluate_cases(cases, verifier.FakeVerifierGateway(), catalog))
    assert run.summary["logical_call_count"] == 1
    assert run.summary["network_request_count"] == 0
    assert run.summary["positive_item_gold"]["denominator"] == 1
    assert run.summary["positive_dish_all_gold"]["denominator"] == 1
    assert run.requests[0]["candidate_sha256"] == verifier.candidate_fingerprint(
        run.requests[0]["prompt_payload"]
    )
    assert len(run.requests[0]["candidate_sha256"]) == 64

    output_dir = Path("task67-v3-fake-output")
    artifacts: dict[str, bytes] = {}

    class FakeBinaryFile:
        def __init__(self, name: str) -> None:
            self.name = name
            self.value = bytearray()

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            artifacts[self.name] = bytes(self.value)

        def write(self, value: bytes) -> int:
            self.value.extend(value)
            return len(value)

    def fake_is_dir(path: Path) -> bool:
        return path == output_dir

    def fake_iterdir(path: Path) -> Any:
        assert path == output_dir
        return iter(Path(name) for name in artifacts)

    def fake_open(path: Path, mode: str = "r", *_: object, **__: object) -> FakeBinaryFile:
        assert mode == "xb"
        if path.name in artifacts:
            raise FileExistsError(path)
        return FakeBinaryFile(path.name)

    def fake_read_bytes(path: Path) -> bytes:
        return artifacts[path.name]

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    verifier.write_run(output_dir, run, reserved=True)

    assert "manifest.json" in artifacts
    with pytest.raises(verifier.Task67RunError, match="prior output"):
        verifier.write_run(output_dir, run, reserved=True)
