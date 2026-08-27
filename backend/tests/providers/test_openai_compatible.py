"""OpenAI-compatible gateway fake-provider tests."""

from __future__ import annotations

import base64
import json
from uuid import uuid4

import httpx
import pytest
import respx

from pelican_town_specials.application.settings import ProviderSettings
from pelican_town_specials.domain.canonical import RecallDocument, RecallIngredient
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.dish import DishAnalysis
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.providers import (
    AskGusDesignRequest,
    DishAnalysisRequest,
    ImageGenerationRequest,
    ImageMediaType,
    ImageOperation,
    OpenAICompatibleGateway,
    ProviderImageInput,
)
from pelican_town_specials.providers.contracts import (
    CanonicalMatchCandidate,
    CanonicalMatchRequest,
)
from pelican_town_specials.providers.prompts.canonical_match_v1 import (
    canonical_match_prompt_for,
)

from .conftest import FakeSecretStore

_ANALYSIS_JSON = {
    "recognizedDish": "Spring Noodles",
    "summary": "A warm noodle bowl.",
    "semanticIngredients": [
        {"name": "Noodles", "normalizedName": "noodles", "visibleConfidence": 0.9}
    ],
    "confidence": 0.9,
}


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_json_schema_required_includes_all_properties() -> None:
    from pelican_town_specials.domain.dish import DishAnalysis
    from pelican_town_specials.providers.openai_compatible import _model_schema

    schema = _model_schema("dishanalysis", DishAnalysis)
    ingredient = schema["schema"]["$defs"]["SemanticIngredient"]

    assert "quantityHint" in ingredient["required"]


def test_generated_dish_schema_excludes_derived_recovery_fields() -> None:
    from pelican_town_specials.providers.contracts import GeneratedDishCore
    from pelican_town_specials.providers.openai_compatible import _model_schema

    schema = _model_schema("generateddishcore", GeneratedDishCore)
    recovery = schema["schema"]["$defs"]["RecoverySpec"]

    assert set(recovery["properties"]) == {"edibility"}
    assert recovery["required"] == ["edibility"]
    assert "energyRestore" not in recovery["properties"]
    assert "healthRestore" not in recovery["properties"]
    assert "calculationVersion" not in recovery["properties"]


def test_generated_dish_core_accepts_recovery_with_only_edibility() -> None:
    from pelican_town_specials.providers.contracts import GeneratedDishCore
    from pelican_town_specials.providers.structured_output import (
        validate_structured,
    )

    payload = json.dumps(
        {
            "presentation": {
                "displayName": "春日面碗",
                "internalName": "SpringNoodleBowl",
                "categoryLabel": "主菜",
                "description": "一碗带着春天气息的热汤面。",
                "tags": ["spring", "noodles"],
            },
            "ingredients": [
                {"name": "Egg", "normalizedName": "egg"},
                {"name": "Spring Onion", "normalizedName": "spring onion"},
            ],
            "recovery": {"edibility": 80},
            "sellPrice": 220,
            "isDrink": False,
            "visualBrief": "Warm ceramic bowl on a rustic tavern table.",
        }
    )

    core = validate_structured(GeneratedDishCore, payload)

    assert core.recovery.edibility == 80
    assert core.recovery.energy_restore == 200
    assert core.recovery.calculation_version == "stardew-1.6"


def test_generated_dish_core_rejects_echoed_derived_recovery_fields() -> None:
    from pelican_town_specials.providers.contracts import GeneratedDishCore
    from pelican_town_specials.providers.structured_output import (
        StructuredOutputValidationFailed,
        validate_structured,
    )

    payload = json.dumps(
        {
            "presentation": {
                "displayName": "春日面碗",
                "internalName": "SpringNoodleBowl",
                "categoryLabel": "主菜",
                "description": "一碗带着春天气息的热汤面。",
                "tags": ["spring", "noodles"],
            },
            "ingredients": [
                {"name": "Egg", "normalizedName": "egg"},
                {"name": "Spring Onion", "normalizedName": "spring onion"},
            ],
            "recovery": {
                "edibility": 80,
                "energyRestore": 200,
                "healthRestore": 90,
                "calculationVersion": "stardew-1.6",
            },
            "sellPrice": 220,
            "isDrink": False,
            "visualBrief": "Warm ceramic bowl on a rustic tavern table.",
        }
    )

    with pytest.raises(StructuredOutputValidationFailed):
        validate_structured(GeneratedDishCore, payload)


def _analysis_request() -> DishAnalysisRequest:
    return DishAnalysisRequest(
        image=ProviderImageInput(data=b"png-bytes", media_type=ImageMediaType.PNG),
        context_text=None,
        language=Language.ZH_CN,
        requestId=uuid4(),
    )


def _canonical_match_request() -> CanonicalMatchRequest:
    candidate_id = uuid4()
    return CanonicalMatchRequest(
        analysis=DishAnalysis.model_validate(_ANALYSIS_JSON),
        contextText="make this a spicy spring noodle bowl",
        language=Language.EN_US,
        candidates=[
            CanonicalMatchCandidate(
                canonicalId=candidate_id,
                displayName="Spring Noodles",
                recallDocument=RecallDocument(
                    recognizedDish="Spring Noodles",
                    normalizedName="spring noodles",
                    summary="A warm noodle bowl.",
                    cuisine="Farmhouse",
                    semanticIngredients=[
                        RecallIngredient(
                            name="Noodles",
                            normalizedName="noodles",
                            visibleConfidence=0.9,
                        )
                    ],
                    cookingMethods=["boiled"],
                    flavorProfile=[],
                ),
            )
        ],
        requestId=uuid4(),
    )


def test_canonical_match_schema_is_exactly_two_fields() -> None:
    from pelican_town_specials.providers.contracts import CanonicalMatchResponse
    from pelican_town_specials.providers.openai_compatible import _model_schema

    schema = _model_schema("canonicalmatchresponse", CanonicalMatchResponse)
    assert set(schema["schema"]["properties"]) == {"candidateId", "confidence"}
    assert schema["schema"]["required"] == ["candidateId", "confidence"]


@pytest.mark.parametrize("language", [Language.ZH_CN, Language.EN_US])
def test_canonical_match_prompt_is_bilingual_context_conflict_and_json_only(
    language: Language,
) -> None:
    prompt, instruction = canonical_match_prompt_for(language)

    assert "contextText" in prompt
    assert "confiden" in prompt or "置信度" in prompt
    assert "candidateId" in instruction
    assert "confidence" in instruction
    assert "reasoning" in prompt or "推理" in prompt


@respx.mock
async def test_canonical_match_uses_text_model_and_sends_no_image_or_reasoning(
    gateway: OpenAICompatibleGateway,
) -> None:
    request = _canonical_match_request()
    candidate_id = request.candidates[0].canonical_id
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(
            json.dumps({"candidateId": str(candidate_id), "confidence": 0.95})
        )
    )

    result = await gateway.match_canonical(request)

    assert result.candidate_id == candidate_id
    assert result.confidence == 0.95
    body = json.loads(route.calls[0].request.content.decode())
    assert body["model"] == "text-model"
    assert "temperature" not in body
    assert "reasoning_effort" not in body
    content = body["messages"][0]["content"]
    assert len(content) == 1
    prompt_text = content[0]["text"]
    assert request.context_text in prompt_text
    assert str(candidate_id) in prompt_text
    assert "image_url" not in body
    response_format = body["response_format"]
    assert set(response_format["json_schema"]["schema"]["properties"]) == {
        "candidateId",
        "confidence",
    }


@respx.mock
async def test_canonical_match_json_only_uses_existing_structured_fallback(
    gateway: OpenAICompatibleGateway,
) -> None:
    request = _canonical_match_request()
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(json.dumps({"candidateId": None, "confidence": 0.1}))
    )

    result = await gateway.match_canonical(request, json_only=True)

    assert result.candidate_id is None
    body = json.loads(route.calls[0].request.content.decode())
    assert "temperature" not in body
    assert "response_format" not in body


@respx.mock
async def test_chat_path_not_duplicated_bearer_and_request_id(gateway: OpenAICompatibleGateway) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(json.dumps(_ANALYSIS_JSON))
    )

    result = await gateway.analyze_dish(_analysis_request())

    assert route.called
    request = route.calls[0].request
    assert str(request.url) == "https://yibuapi.com/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test-key"
    assert request.headers["x-request-id"]
    assert result.recognized_dish == "Spring Noodles"


@respx.mock
async def test_json_schema_capability_error_degrades_to_json_only(
    gateway: OpenAICompatibleGateway,
) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(
                400,
                json={"error": {"message": "response_format json_schema unsupported"}},
            ),
            _chat_response(json.dumps(_ANALYSIS_JSON)),
        ]
    )

    result = await gateway.analyze_dish(_analysis_request())

    assert route.call_count == 2
    assert result.recognized_dish == "Spring Noodles"
    first_body = json.loads(route.calls[0].request.content.decode())
    second_body = json.loads(route.calls[1].request.content.decode())
    assert "temperature" not in first_body
    assert "temperature" not in second_body
    assert "response_format" in first_body
    assert "response_format" not in second_body


@respx.mock
async def test_structured_output_repairs_once(gateway: OpenAICompatibleGateway) -> None:
    invalid = json.dumps({**_ANALYSIS_JSON, "confidence": 2.5})
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        side_effect=[
            _chat_response(invalid),
            _chat_response(json.dumps(_ANALYSIS_JSON)),
        ]
    )

    result = await gateway.analyze_dish(_analysis_request())

    assert route.call_count == 2
    assert result.confidence == 0.9
    assert all(
        "temperature" not in json.loads(call.request.content.decode())
        for call in route.calls
    )
    repair_prompt = json.loads(route.calls[1].request.content.decode())["messages"][0][
        "content"
    ][0]["text"]
    assert "confidence:less_than_equal" in repair_prompt


@respx.mock
async def test_structured_output_repairs_twice_before_success(
    gateway: OpenAICompatibleGateway,
) -> None:
    invalid = json.dumps({**_ANALYSIS_JSON, "confidence": 2.5})
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        side_effect=[
            _chat_response(invalid),
            _chat_response(invalid),
            _chat_response(json.dumps(_ANALYSIS_JSON)),
        ]
    )

    result = await gateway.analyze_dish(_analysis_request())

    assert route.call_count == 3
    assert result.confidence == 0.9
    assert all(
        "temperature" not in json.loads(call.request.content.decode())
        for call in route.calls
    )
    repair_prompt = json.loads(route.calls[2].request.content.decode())["messages"][0][
        "content"
    ][0]["text"]
    assert "confidence:less_than_equal" in repair_prompt


@respx.mock
async def test_structured_output_raises_after_three_attempts(
    gateway: OpenAICompatibleGateway,
) -> None:
    invalid = json.dumps({**_ANALYSIS_JSON, "confidence": 2.5})
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(invalid)
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_INVALID_STRUCTURED_OUTPUT"
    assert route.call_count == 3


@respx.mock
async def test_structured_output_repairs_json_errors_twice(
    gateway: OpenAICompatibleGateway,
) -> None:
    malformed = _chat_response("this is not a JSON object")
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        side_effect=[
            malformed,
            malformed,
            _chat_response(json.dumps(_ANALYSIS_JSON)),
        ]
    )

    result = await gateway.analyze_dish(_analysis_request())

    assert route.call_count == 3
    assert result.recognized_dish == "Spring Noodles"


@respx.mock
async def test_structured_output_raises_after_three_json_errors(
    gateway: OpenAICompatibleGateway,
) -> None:
    malformed = _chat_response("this is not a JSON object")
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=malformed
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_INVALID_STRUCTURED_OUTPUT"
    assert route.call_count == 3


@respx.mock
async def test_structured_output_repairs_envelope_errors_twice(
    gateway: OpenAICompatibleGateway,
) -> None:
    no_choices = httpx.Response(200, json={"choices": []})
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        side_effect=[
            no_choices,
            no_choices,
            _chat_response(json.dumps(_ANALYSIS_JSON)),
        ]
    )

    result = await gateway.analyze_dish(_analysis_request())

    assert route.call_count == 3
    assert result.recognized_dish == "Spring Noodles"


@respx.mock
async def test_structured_output_raises_after_three_envelope_errors(
    gateway: OpenAICompatibleGateway,
) -> None:
    no_choices = httpx.Response(200, json={"choices": []})
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=no_choices
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_INVALID_STRUCTURED_OUTPUT"
    assert route.call_count == 3


@respx.mock
async def test_structured_output_repairs_non_object_json_twice(
    gateway: OpenAICompatibleGateway,
) -> None:
    non_object = httpx.Response(200, json=["not", "an", "object"])
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        side_effect=[
            non_object,
            non_object,
            _chat_response(json.dumps(_ANALYSIS_JSON)),
        ]
    )

    result = await gateway.analyze_dish(_analysis_request())

    assert route.call_count == 3
    assert result.recognized_dish == "Spring Noodles"


@respx.mock
async def test_401_is_not_retried(gateway: OpenAICompatibleGateway) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad key"}})
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_AUTH_FAILED"
    assert route.call_count == 1


@respx.mock
async def test_429_retries_then_rate_limits(gateway: OpenAICompatibleGateway) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "slow down"}})
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_RATE_LIMITED"
    assert route.call_count == 3  # 1 initial + 2 retries


@respx.mock
async def test_500_retries_then_unavailable(gateway: OpenAICompatibleGateway) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "boom"}})
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_UNAVAILABLE"
    assert route.call_count == 3


@respx.mock
async def test_image_edit_uses_multipart_and_decodes_b64(
    gateway: OpenAICompatibleGateway,
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    route = respx.post("https://yibuapi.com/v1/images/edits").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(png).decode()}]},
        )
    )

    result = await gateway.generate_image(
        ImageGenerationRequest(
            operation=ImageOperation.EDIT,
            prompt="make it red",
            sourceImages=[
                ProviderImageInput(data=png, media_type=ImageMediaType.PNG)
            ],
            size="256x256",
            requestId=uuid4(),
        )
    )

    assert route.called
    assert result.media_type is ImageMediaType.PNG
    assert result.data == png
    request = route.calls[0].request
    body = request.content.decode("utf-8", errors="ignore")
    assert 'name="response_format"' not in body
    assert body.count('name="image"') == 1
    assert 'name="image[]"' not in body
    assert 'name="model"' in body
    assert 'name="prompt"' in body
    assert 'name="n"' in body
    assert 'name="size"' in body


@respx.mock
async def test_generation_rejects_source_images(gateway: OpenAICompatibleGateway) -> None:
    with pytest.raises(ValueError):
        ImageGenerationRequest(
            operation=ImageOperation.GENERATION,
            prompt="x",
            sourceImages=[
                ProviderImageInput(data=b"x", media_type=ImageMediaType.PNG)
            ],
            requestId=uuid4(),
        )


@respx.mock
async def test_network_error_is_retried_then_unavailable(
    gateway: OpenAICompatibleGateway,
) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_UNAVAILABLE"
    assert route.call_count == 3


@respx.mock
async def test_501_is_retried_then_unavailable(gateway: OpenAICompatibleGateway) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=httpx.Response(501, json={})
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_UNAVAILABLE"
    assert route.call_count == 3


def test_provider_error_extracts_redacted_message(
    gateway: OpenAICompatibleGateway,
) -> None:
    response = httpx.Response(
        400,
        json={
            "error": {
                "message": "  image   too  large \n please reduce the file size  "
            }
        },
    )

    error = gateway._provider_error(response)

    assert error.code == "PTS_PROVIDER_REQUEST_FAILED"
    assert error.details["providerHttpStatus"] == 400
    assert (
        error.details["providerError"]
        == "image too large please reduce the file size"
    )


def test_provider_error_truncates_long_message(
    gateway: OpenAICompatibleGateway,
) -> None:
    response = httpx.Response(400, json={"error": {"message": "m" * 500}})

    error = gateway._provider_error(response)

    value = error.details["providerError"]
    assert isinstance(value, str)
    assert len(value) == 200
    assert value.endswith("…")
    assert value == "m" * 199 + "…"


def test_provider_error_omits_message_when_body_malformed(
    gateway: OpenAICompatibleGateway,
) -> None:
    response = httpx.Response(502, content=b"<html>bad gateway</html>")

    error = gateway._provider_error(response)

    assert "providerError" not in error.details
    assert error.details["providerHttpStatus"] == 502


def test_provider_error_omits_message_when_not_a_string(
    gateway: OpenAICompatibleGateway,
) -> None:
    response = httpx.Response(400, json={"error": {"message": 123}})

    error = gateway._provider_error(response)

    assert "providerError" not in error.details


def test_provider_error_omits_message_when_no_error_object(
    gateway: OpenAICompatibleGateway,
) -> None:
    response = httpx.Response(400, json={"message": "plain top-level text"})

    error = gateway._provider_error(response)

    assert "providerError" not in error.details


@respx.mock
async def test_403_is_not_retried(gateway: OpenAICompatibleGateway) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=httpx.Response(403, json={"error": {"message": "forbidden"}})
    )

    with pytest.raises(AppError) as excinfo:
        await gateway.analyze_dish(_analysis_request())

    assert excinfo.value.code == "PTS_PROVIDER_AUTH_FAILED"
    assert route.call_count == 1


@respx.mock
async def test_generation_endpoint_uses_json(gateway: OpenAICompatibleGateway) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    route = respx.post("https://yibuapi.com/v1/images/generations").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(png).decode()}]},
        )
    )

    result = await gateway.generate_image(
        ImageGenerationRequest(
            operation=ImageOperation.GENERATION,
            prompt="a red square",
            size="256x256",
            requestId=uuid4(),
        )
    )

    assert route.called
    assert result.media_type is ImageMediaType.PNG
    body = json.loads(route.calls[0].request.content.decode())
    assert body == {
        "model": "image-model",
        "prompt": "a red square",
        "n": 1,
        "size": "256x256",
    }


@respx.mock
async def test_generation_preserves_url_response_download(
    settings: ProviderSettings,
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    generation_route = respx.post("https://yibuapi.com/v1/images/generations").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"url": "https://cdn.example.com/generated.png"}]},
        )
    )
    download_route = respx.get("https://cdn.example.com/generated.png").mock(
        return_value=httpx.Response(
            200,
            content=png,
            headers={"content-type": "image/png"},
        )
    )
    gateway = OpenAICompatibleGateway(
        settings=settings,
        secret_store=FakeSecretStore(),
        dns_resolver=lambda host: ["1.2.3.4"],
    )

    result = await gateway.generate_image(_image_generation_request())

    assert generation_route.call_count == 1
    assert download_route.call_count == 1
    body = json.loads(generation_route.calls[0].request.content.decode())
    assert "response_format" not in body
    assert result.data == png
    assert result.media_type is ImageMediaType.PNG


@respx.mock
async def test_image_edit_sends_images_in_order(gateway: OpenAICompatibleGateway) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    route = respx.post("https://yibuapi.com/v1/images/edits").mock(
        return_value=httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]})
    )

    await gateway.generate_image(
        ImageGenerationRequest(
            operation=ImageOperation.EDIT,
            prompt="combine",
            sourceImages=[
                ProviderImageInput(data=png, media_type=ImageMediaType.PNG),
                ProviderImageInput(data=png, media_type=ImageMediaType.PNG),
            ],
            requestId=uuid4(),
        )
    )

    assert route.called
    request = route.calls[0].request
    assert "multipart" in request.headers.get("content-type", "")
    body = request.content.decode("utf-8", errors="ignore")
    assert 'name="response_format"' not in body
    assert body.count('name="image[]"') == 2
    assert 'name="image"' not in body
    assert body.find('"image-0"') < body.find('"image-1"')


@respx.mock
async def test_analyze_sends_multimodal_image_url(gateway: OpenAICompatibleGateway) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(json.dumps(_ANALYSIS_JSON))
    )

    await gateway.analyze_dish(_analysis_request())

    body = json.loads(route.calls[0].request.content.decode())
    content = body["messages"][0]["content"]
    assert "temperature" not in body
    assert any(part.get("type") == "image_url" for part in content)


@respx.mock
async def test_sleep_sequence_is_recorded(settings: object) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=httpx.Response(503, json={})
    )
    gateway = OpenAICompatibleGateway(
        settings=settings,  # type: ignore[arg-type]
        secret_store=FakeSecretStore(),
        sleep=record_sleep,
    )
    with pytest.raises(AppError):
        await gateway.analyze_dish(_analysis_request())
    assert route.call_count == 3
    assert len(delays) == 2
    assert all(delay >= 0 for delay in delays)


def _ask_gus_design_request() -> AskGusDesignRequest:
    return AskGusDesignRequest(
        analysis=DishAnalysis.model_validate(_ANALYSIS_JSON),
        context_text=None,
        language=Language.ZH_CN,
        requestId=uuid4(),
    )


def test_ask_gus_v2_prompt_relaxes_buff_eligibility_without_forcing_it() -> None:
    from pelican_town_specials.providers.prompts.ask_gus_v2 import (
        ASK_GUS_PROMPT_V2,
    )

    assert "不要因为菜品普通就默认将 buff 设为 null" in ASK_GUS_PROMPT_V2
    assert "主食材、烹饪方式、风味、饮品特征或主题" in ASK_GUS_PROMPT_V2
    assert "通常推荐一个温和的非零属性" in ASK_GUS_PROMPT_V2
    assert "最多两个明确互补的非零属性" in ASK_GUS_PROMPT_V2
    assert "不得添加无关属性" in ASK_GUS_PROMPT_V2
    assert "不得给出夸张数值或夸张持续时间" in ASK_GUS_PROMPT_V2
    assert "非常朴素且没有可信玩法关联" in ASK_GUS_PROMPT_V2
    assert "buff 设为 null" in ASK_GUS_PROMPT_V2


def test_ask_gus_v3_prompt_constrains_prices_to_vanilla_bands() -> None:
    from pelican_town_specials.providers.prompts.ask_gus_v3 import (
        ASK_GUS_PROMPT_V3,
    )

    for expected in (
        "普通菜 80..250g",
        "精致菜 250..400g",
        "明确高档或复杂菜 400..500g",
        "大多数菜应落在 100..400g",
        "普通菜或无 Buff 菜不得超过 500g",
        "不得用抬高售价来补偿没有 Buff",
        "Oil of Garlic（蒜油）1000g",
        "Magic Rock Candy（魔法糖冰棍）5000g",
        "明确的传奇定位或特殊功能性消耗品",
        "清楚说明高价对应的玩法理由",
        "原料价值与稀有度、制作复杂度、恢复量、Buff 强度与持续时间、菜品定位",
    ):
        assert expected in ASK_GUS_PROMPT_V3

@respx.mock
async def test_design_ask_gus_routes_new_calls_through_v3_prompt(
    gateway: OpenAICompatibleGateway,
) -> None:
    payload = {
        "presentation": {
            "displayName": "春日面碗",
            "internalName": "SpringNoodleBowl",
            "categoryLabel": "主菜",
            "description": "一碗带着春天气息的热汤面。",
            "tags": ["春日", "面食"],
        },
        "ingredients": [{"name": "Egg", "normalizedName": "鸡蛋"}],
        "recovery": {"edibility": 40},
        "buff": None,
        "sellPrice": 220,
        "isDrink": False,
        "visualBrief": "春日热汤面。",
    }
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(json.dumps(payload, ensure_ascii=False))
    )

    await gateway.design_ask_gus(_ask_gus_design_request())

    outbound = json.loads(route.calls[0].request.content.decode())
    assert "temperature" not in outbound
    prompt = outbound["messages"][0]["content"][0]["text"]
    assert "不要因为菜品普通就默认将 buff 设为 null" in prompt
    assert "最多两个明确互补的非零属性" in prompt
    assert "普通菜 80..250g" in prompt
    assert "普通菜或无 Buff 菜不得超过 500g" in prompt
    assert "不得用抬高售价来补偿没有 Buff" in prompt


def _analysis_request_en() -> DishAnalysisRequest:
    return DishAnalysisRequest(
        image=ProviderImageInput(data=b"png-bytes", media_type=ImageMediaType.PNG),
        context_text=None,
        language=Language.EN_US,
        requestId=uuid4(),
    )


def _ask_gus_design_request_en() -> AskGusDesignRequest:
    return AskGusDesignRequest(
        analysis=DishAnalysis.model_validate(_ANALYSIS_JSON),
        context_text=None,
        language=Language.EN_US,
        requestId=uuid4(),
    )


@respx.mock
async def test_analyze_dish_en_us_uses_english_prompt(
    gateway: OpenAICompatibleGateway,
) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(json.dumps(_ANALYSIS_JSON, ensure_ascii=False))
    )

    await gateway.analyze_dish(_analysis_request_en())

    outbound = json.loads(route.calls[0].request.content.decode())
    prompt = outbound["messages"][0]["content"][0]["text"]
    assert "Identify this dish from the provided photo" in prompt
    assert "recognizedDish" in prompt
    assert "Return only a single JSON object, with no code blocks or extra text." in prompt
    assert "菜品识别助手" not in prompt
    assert "只返回一个 JSON 对象" not in prompt


@respx.mock
async def test_design_ask_gus_en_us_uses_english_prompt_and_analysis_prefix(
    gateway: OpenAICompatibleGateway,
) -> None:
    payload = {
        "presentation": {
            "displayName": "Spring Noodle Bowl",
            "internalName": "SpringNoodleBowl",
            "categoryLabel": "Main Course",
            "description": "A warm bowl of spring noodles.",
            "tags": ["spring", "noodles"],
        },
        "ingredients": [{"name": "Egg", "normalizedName": "egg"}],
        "recovery": {"edibility": 40},
        "buff": None,
        "sellPrice": 220,
        "isDrink": False,
        "visualBrief": "A warm spring noodle bowl.",
    }
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(json.dumps(payload, ensure_ascii=False))
    )

    await gateway.design_ask_gus(_ask_gus_design_request_en())

    outbound = json.loads(route.calls[0].request.content.decode())
    prompt = outbound["messages"][0]["content"][0]["text"]
    assert "You are Gus, the chef of the Pelican Town restaurant" in prompt
    assert "Dish analysis:" in prompt
    assert "ordinary dishes 80..250g" in prompt
    assert "do not compensate for having no Buff by raising the price" in prompt
    assert "Return only a single JSON object, with no code blocks or extra text." in prompt
    assert "菜品分析：" not in prompt
    assert "你是鹈鹕镇餐厅的大厨 Gus" not in prompt


def test_repair_prompt_is_localized_to_request_language() -> None:
    from pelican_town_specials.providers.openai_compatible import (
        _repair_prompt,
        _repair_prompt_plain,
    )

    en = _repair_prompt(
        "p",
        "i",
        [{"loc": ["a"], "type": "value_error"}],
        language=Language.EN_US,
    )
    assert "previous output failed validation" in en
    assert "Validation issues:" in en
    zh = _repair_prompt(
        "p",
        "i",
        [{"loc": ["a"], "type": "value_error"}],
        language=Language.ZH_CN,
    )
    assert "上次输出未通过校验" in zh
    assert "校验问题：" in zh
    en_plain = _repair_prompt_plain("p", "i", language=Language.EN_US)
    assert "not a valid pure JSON object" in en_plain
    zh_plain = _repair_prompt_plain("p", "i", language=Language.ZH_CN)
    assert "不是合法的纯 JSON 对象" in zh_plain


def _image_generation_request() -> ImageGenerationRequest:
    return ImageGenerationRequest(
        operation=ImageOperation.GENERATION,
        prompt="a red square",
        size="256x256",
        requestId=uuid4(),
    )


def _gateway_with_empty_model(field: str) -> OpenAICompatibleGateway:
    settings = ProviderSettings(
        baseUrl="https://yibuapi.com/v1",
        visionModel="" if field == "vision_model" else "vision-model",
        textModel="" if field == "text_model" else "text-model",
        imageModel="" if field == "image_model" else "image-model",
        chatTimeoutSeconds=60,
        imageTimeoutSeconds=90,
        maxAutomaticRetries=0,
    )
    return OpenAICompatibleGateway(settings=settings, secret_store=FakeSecretStore())


@pytest.mark.parametrize(
    ("empty_field", "call"),
    [
        ("vision_model", "analyze"),
        ("text_model", "design"),
        ("image_model", "image"),
    ],
)
@respx.mock
async def test_empty_required_model_fails_before_relay(
    empty_field: str, call: str
) -> None:
    chat_route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(json.dumps(_ANALYSIS_JSON))
    )
    image_route = respx.post("https://yibuapi.com/v1/images/generations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(
                            b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
                        ).decode()
                    }
                ]
            },
        )
    )
    gateway = _gateway_with_empty_model(empty_field)

    with pytest.raises(AppError) as excinfo:
        if call == "analyze":
            await gateway.analyze_dish(_analysis_request())
        elif call == "design":
            await gateway.design_ask_gus(_ask_gus_design_request())
        else:
            await gateway.generate_image(_image_generation_request())

    assert excinfo.value.code == "PTS_PROVIDER_NOT_CONFIGURED"
    assert excinfo.value.http_status == 422
    assert excinfo.value.details["emptyFields"] == [empty_field]
    assert chat_route.call_count == 0
    assert image_route.call_count == 0
