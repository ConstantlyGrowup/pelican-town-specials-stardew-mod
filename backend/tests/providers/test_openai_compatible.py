"""OpenAI-compatible gateway fake-provider tests."""

from __future__ import annotations

import base64
import json
from uuid import uuid4

import httpx
import pytest
import respx

from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.providers import (
    DishAnalysisRequest,
    ImageGenerationRequest,
    ImageMediaType,
    ImageOperation,
    OpenAICompatibleGateway,
    ProviderImageInput,
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


def _analysis_request() -> DishAnalysisRequest:
    return DishAnalysisRequest(
        image=ProviderImageInput(data=b"png-bytes", media_type=ImageMediaType.PNG),
        context_text=None,
        language=Language.ZH_CN,
        requestId=uuid4(),
    )


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
    repair_prompt = json.loads(route.calls[1].request.content.decode())["messages"][0][
        "content"
    ][0]["text"]
    assert "confidence:less_than_equal" in repair_prompt


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
    assert body.count('name="image"') == 2
    assert body.find('"image-0"') < body.find('"image-1"')


@respx.mock
async def test_analyze_sends_multimodal_image_url(gateway: OpenAICompatibleGateway) -> None:
    route = respx.post("https://yibuapi.com/v1/chat/completions").mock(
        return_value=_chat_response(json.dumps(_ANALYSIS_JSON))
    )

    await gateway.analyze_dish(_analysis_request())

    body = json.loads(route.calls[0].request.content.decode())
    content = body["messages"][0]["content"]
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
