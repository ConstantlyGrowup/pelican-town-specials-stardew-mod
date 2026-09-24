from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
import respx

from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.providers.contracts import (
    IngredientVerifierCandidate,
    IngredientVerifierIngredient,
    IngredientVerifierRequest,
    IngredientVerifierResponse,
    IngredientVerifierSelection,
    validate_ingredient_verifier_response,
)
from pelican_town_specials.providers.openai_compatible import (
    OpenAICompatibleGateway,
    _model_schema,
)


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _request() -> IngredientVerifierRequest:
    return IngredientVerifierRequest(
        dishName="春日面碗",
        requestId=uuid4(),
        ingredients=[
            IngredientVerifierIngredient(
                index=0,
                name="egg",
                candidates=[
                    IngredientVerifierCandidate(
                        itemId="176", displayNameEn="Egg", displayNameZh="鸡蛋"
                    )
                ],
            ),
            IngredientVerifierIngredient(
                index=1,
                name="spring onion",
                candidates=[
                    IngredientVerifierCandidate(
                        itemId="399",
                        displayNameEn="Spring Onion",
                        displayNameZh="大葱",
                    )
                ],
            ),
        ],
    )


def _response(*, first: str | None = "176") -> IngredientVerifierResponse:
    return IngredientVerifierResponse(
        items=[
            IngredientVerifierSelection(index=0, selectedItemId=first),
            IngredientVerifierSelection(index=1, selectedItemId="399"),
        ]
    )


def test_verifier_response_schema_is_minimal_and_strict() -> None:
    schema = _model_schema("ingredientverifierresponse", IngredientVerifierResponse)
    assert set(schema["schema"]["properties"]) == {"items"}
    item = schema["schema"]["$defs"]["IngredientVerifierSelection"]
    assert set(item["properties"]) == {"index", "selectedItemId"}
    assert item["required"] == ["index", "selectedItemId"]


def test_verifier_response_rejects_non_candidate_duplicate_and_missing_choices() -> None:
    request = _request()
    expanded_second = request.ingredients[1].model_copy(
        update={
            "candidates": [
                request.ingredients[0].candidates[0],
                *request.ingredients[1].candidates,
            ]
        }
    )
    duplicate_ready_request = request.model_copy(
        update={"ingredients": [request.ingredients[0], expanded_second]}
    )

    with pytest.raises(ValueError):
        validate_ingredient_verifier_response(
            request,
            IngredientVerifierResponse(
                items=[
                    IngredientVerifierSelection(index=0, selectedItemId="not-a-candidate"),
                    IngredientVerifierSelection(index=1, selectedItemId="399"),
                ]
            ),
        )
    with pytest.raises(ValueError):
        validate_ingredient_verifier_response(
            duplicate_ready_request,
            IngredientVerifierResponse(
                items=[
                    IngredientVerifierSelection(index=0, selectedItemId="176"),
                    IngredientVerifierSelection(index=1, selectedItemId="176"),
                ]
            ),
        )
    with pytest.raises(ValueError):
        validate_ingredient_verifier_response(
            request,
            IngredientVerifierResponse(
                items=[IngredientVerifierSelection(index=0, selectedItemId="176")]
            ),
        )


@respx.mock
async def test_verifier_sends_only_minimal_bilingual_candidates_once(
    gateway: OpenAICompatibleGateway,
) -> None:
    request = _request()
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(
            json.dumps(
                {
                    "items": [
                        {"index": 0, "selectedItemId": "176"},
                        {"index": 1, "selectedItemId": "399"},
                    ]
                },
                ensure_ascii=False,
            )
        )
    )

    result = await gateway.verify_ingredient_candidates(request)

    assert result == _response()
    assert route.call_count == 1
    outbound = json.loads(route.calls[0].request.content.decode())
    assert outbound["model"] == "text-model"
    assert "image_url" not in str(outbound["messages"])
    prompt = outbound["messages"][0]["content"][0]["text"]
    assert "春日面碗" in prompt
    assert "spring onion" in prompt
    assert "Spring Onion" in prompt
    assert "399" in prompt
    assert "quantity" not in prompt.lower()
    assert "score" not in prompt.lower()
    assert "category" not in prompt.lower()


@pytest.mark.parametrize("status", [429, 500])
@respx.mock
async def test_verifier_does_not_retry_provider_failures(
    gateway: OpenAICompatibleGateway, status: int
) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=httpx.Response(status)
    )

    with pytest.raises(AppError):
        await gateway.verify_ingredient_candidates(_request())

    assert route.call_count == 1


@respx.mock
async def test_verifier_does_not_repair_invalid_json(
    gateway: OpenAICompatibleGateway,
) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response("not-json")
    )

    with pytest.raises(AppError):
        await gateway.verify_ingredient_candidates(_request())

    assert route.call_count == 1
