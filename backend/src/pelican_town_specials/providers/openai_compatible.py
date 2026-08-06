"""Strict typed OpenAI-compatible provider gateway."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections.abc import Callable
from time import monotonic
from typing import Annotated, Any, TypeVar, cast, get_args, get_origin
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel

from pelican_town_specials.application.settings import (
    ProviderSettings,
    SecretStore,
)
from pelican_town_specials.domain.dish import DishAnalysis
from pelican_town_specials.domain.errors import AppError
from pelican_town_specials.providers.contracts import (
    AskGusDesignRequest,
    DishAnalysisRequest,
    GeneratedDishCore,
    GeneratedImage,
    ImageGenerationRequest,
    ImageMediaType,
    ImageOperation,
)
from pelican_town_specials.providers.prompts.analysis_v1 import (
    ANALYSIS_JSON_INSTRUCTION,
    ANALYSIS_PROMPT_V1,
)
from pelican_town_specials.providers.prompts.ask_gus_v2 import ASK_GUS_JSON_INSTRUCTION
from pelican_town_specials.providers.prompts.ask_gus_v3 import ASK_GUS_PROMPT_V3
from pelican_town_specials.providers.retry import RetryPolicy
from pelican_town_specials.providers.safe_download import (
    SafeImageDownloader,
    _resolve_default,
)
from pelican_town_specials.providers.structured_output import (
    StructuredOutputError,
    StructuredOutputValidationFailed,
    validate_structured,
)

Sleep = Callable[[float], Any]
Clock = Callable[[], float]
UuidFactory = Callable[[], UUID]
DnsResolver = Callable[[str], list[str]]
TModel = TypeVar("TModel", bound=BaseModel)

_MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REPAIRS = 2


async def _default_sleep(delay: float) -> None:
    await asyncio.sleep(delay)


class OpenAICompatibleGateway:
    def __init__(
        self,
        *,
        settings: ProviderSettings,
        secret_store: SecretStore,
        http_client: httpx.AsyncClient | None = None,
        sleep: Sleep = _default_sleep,
        clock: Clock = monotonic,
        uuid_factory: UuidFactory = uuid4,
        dns_resolver: DnsResolver | None = None,
    ) -> None:
        self._settings = settings
        self._secret_store = secret_store
        self._clock = clock
        self._uuid = uuid_factory
        self._sleep = sleep
        self._retry = RetryPolicy(max_retries=settings.max_automatic_retries)
        self._http_client = http_client or httpx.AsyncClient()
        self._downloader = SafeImageDownloader(
            http_client=self._http_client,
            resolve_dns=dns_resolver or _resolve_default,
        )

    async def analyze_dish(
        self,
        request: DishAnalysisRequest,
        *,
        json_only: bool = False,
    ) -> DishAnalysis:
        self._require_model(self._settings.vision_model, "vision_model")
        image_data_url = self._data_url(request.image.data, request.image.media_type)
        content = await self._chat_structured(
            model=self._settings.vision_model,
            request_id=request.request_id,
            timeout=self._settings.chat_timeout_seconds,
            prompt=ANALYSIS_PROMPT_V1,
            json_instruction=ANALYSIS_JSON_INSTRUCTION,
            target_type=DishAnalysis,
            image_data_url=image_data_url,
            json_only=json_only,
        )
        return content

    async def design_ask_gus(
        self,
        request: AskGusDesignRequest,
        *,
        json_only: bool = False,
    ) -> GeneratedDishCore:
        self._require_model(self._settings.text_model, "text_model")
        prompt = f"{ASK_GUS_PROMPT_V3}\n\n菜品分析：\n{request.analysis.model_dump_json(by_alias=True)}"
        content = await self._chat_structured(
            model=self._settings.text_model,
            request_id=request.request_id,
            timeout=self._settings.chat_timeout_seconds,
            prompt=prompt,
            json_instruction=ASK_GUS_JSON_INSTRUCTION,
            target_type=GeneratedDishCore,
            image_data_url=None,
            json_only=json_only,
        )
        return content

    async def generate_image(self, request: ImageGenerationRequest) -> GeneratedImage:
        model = self._settings.image_model
        self._require_model(model, "image_model")
        timeout = self._settings.image_timeout_seconds
        if request.operation is ImageOperation.EDIT:
            return await self._generate_edit(request, model=model, timeout=timeout)
        return await self._generate_generation(request, model=model, timeout=timeout)

    async def _chat_structured(
        self,
        *,
        model: str,
        request_id: UUID,
        timeout: int,
        prompt: str,
        json_instruction: str,
        target_type: type[TModel],
        image_data_url: str | None,
        json_only: bool = False,
    ) -> TModel:
        use_json_schema = not json_only
        repairs = 0
        current_prompt = prompt
        while True:
            body = self._chat_body(
                model=model,
                prompt=current_prompt,
                json_instruction=json_instruction,
                image_data_url=image_data_url,
                use_json_schema=use_json_schema,
                target_type=target_type,
            )
            response = await self._request(
                method="POST",
                url=self._url("chat/completions"),
                request_id=request_id,
                timeout=timeout,
                json=body,
            )
            if response.status_code == 400 and use_json_schema and _is_format_capability_error(
                response.text
            ):
                use_json_schema = False
                continue
            if response.status_code >= 400:
                raise self._provider_error(response)

            try:
                content = _extract_chat_text(response)
                return validate_structured(target_type, content)
            except StructuredOutputValidationFailed as exc:
                if repairs >= MAX_REPAIRS:
                    raise self._invalid_structured_output_error(exc.issues) from exc
                repairs += 1
                current_prompt = _repair_prompt(
                    prompt, json_instruction, exc.issues
                )
            except StructuredOutputError as exc:
                if repairs >= MAX_REPAIRS:
                    raise self._invalid_structured_output_error([]) from exc
                repairs += 1
                current_prompt = _repair_prompt_plain(prompt, json_instruction)

    async def _generate_edit(
        self,
        request: ImageGenerationRequest,
        *,
        model: str,
        timeout: int,
    ) -> GeneratedImage:
        files: list[tuple[str, tuple[str, bytes, str]]] = []
        for index, image in enumerate(request.source_images):
            files.append(
                ("image", (f"image-{index}", image.data, image.media_type.value))
            )
        data: dict[str, str] = {"model": model, "prompt": request.prompt, "n": "1"}
        if request.size:
            data["size"] = request.size
        if request.quality:
            data["quality"] = request.quality
        data["response_format"] = "b64_json"
        response = await self._request(
            method="POST",
            url=self._url("images/edits"),
            request_id=request.request_id,
            timeout=timeout,
            data=data,
            files=files,
        )
        return await self._parse_image_response(response, request)

    async def _generate_generation(
        self,
        request: ImageGenerationRequest,
        *,
        model: str,
        timeout: int,
    ) -> GeneratedImage:
        body: dict[str, object] = {
            "model": model,
            "prompt": request.prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        if request.size:
            body["size"] = request.size
        if request.quality:
            body["quality"] = request.quality
        response = await self._request(
            method="POST",
            url=self._url("images/generations"),
            request_id=request.request_id,
            timeout=timeout,
            json=body,
        )
        return await self._parse_image_response(response, request)

    async def _parse_image_response(
        self,
        response: httpx.Response,
        request: ImageGenerationRequest,
    ) -> GeneratedImage:
        if response.status_code >= 400:
            raise self._provider_error(response)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise self._provider_image_error("provider returned invalid JSON") from exc
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise self._provider_image_error("provider returned no image data")
        item = data[0]
        if not isinstance(item, dict):
            raise self._provider_image_error("provider image item is malformed")
        revised_prompt = item.get("revised_prompt")
        b64 = item.get("b64_json")
        if isinstance(b64, str):
            raw = _decode_b64(b64)
            media = _detect_strict_media(raw)
            return GeneratedImage(data=raw, media_type=media, revised_prompt=revised_prompt)
        image_url = item.get("url")
        if isinstance(image_url, str):
            downloaded = await self._downloader.download(image_url)
            return GeneratedImage(
                data=downloaded.data,
                media_type=downloaded.media_type,
                revised_prompt=revised_prompt,
            )
        raise self._provider_image_error("provider image has no usable content")

    def _chat_body(
        self,
        *,
        model: str,
        prompt: str,
        json_instruction: str,
        image_data_url: str | None,
        use_json_schema: bool,
        target_type: type[TModel],
    ) -> dict[str, object]:
        content: list[dict[str, object]] = [
            {"type": "text", "text": f"{prompt}\n{json_instruction}"}
        ]
        if image_data_url:
            content.append(
                {"type": "image_url", "image_url": {"url": image_data_url}}
            )
        body: dict[str, object] = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
        }
        if use_json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": _model_schema(target_type.__name__.lower(), target_type),
            }
        return body

    @staticmethod
    def _require_model(model: str, field: str) -> None:
        """Fail locally when a required model is empty instead of a cryptic relay error."""
        if not model or not model.strip():
            raise AppError(
                code="PTS_PROVIDER_NOT_CONFIGURED",
                message="Provider 模型未配置，请先在设置页填写模型 ID。",
                http_status=422,
                details={"emptyFields": [field]},
                retryable=False,
            )

    def _data_url(self, data: bytes, media_type: ImageMediaType) -> str:
        return f"data:{media_type.value};base64,{base64.b64encode(data).decode('ascii')}"

    def _url(self, path: str) -> str:
        return f"{self._settings.base_url.rstrip('/')}/{path}"

    async def _request(
        self,
        *,
        method: str,
        url: str,
        request_id: UUID,
        timeout: int,
        **kwargs: Any,
    ) -> httpx.Response:
        secret = self._secret_store.get_api_key()
        if secret is None:
            raise self._auth_error("Provider Key 未配置。")
        headers = dict(kwargs.pop("headers", {}))
        headers["X-Request-ID"] = str(request_id)
        headers["Authorization"] = f"Bearer {secret.get_secret_value()}"
        attempt = 0
        while True:
            try:
                response = await self._http_client.request(
                    method, url, headers=headers, timeout=timeout, **kwargs
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if self._retry.should_retry(attempt=attempt, retryable=True):
                    await self._sleep(self._retry.delay_for(attempt))
                    attempt += 1
                    continue
                raise self._unavailable_error(
                    "Provider 请求超时或网络不可用。"
                ) from exc

            if response.status_code in (401, 403):
                raise self._auth_error("Provider Key 无效或未授权。")
            if (
                response.status_code == 408
                or response.status_code == 429
                or 500 <= response.status_code <= 599
            ):
                if self._retry.should_retry(attempt=attempt, retryable=True):
                    await self._sleep(self._retry.delay_for(attempt))
                    attempt += 1
                    continue
                if response.status_code == 429:
                    raise self._rate_limited_error()
                raise self._unavailable_error("Provider 服务暂时不可用。")
            return response

    def _provider_error(self, response: httpx.Response) -> AppError:
        details: dict[str, object] = {"providerHttpStatus": response.status_code}
        provider_message = _extract_provider_message(response)
        if provider_message is not None:
            details["providerError"] = provider_message
        return AppError(
            code="PTS_PROVIDER_REQUEST_FAILED",
            message="Provider 返回了无法处理的响应。",
            http_status=502,
            details=details,
            retryable=True,
        )

    def _provider_image_error(self, message: str) -> AppError:
        return AppError(
            code="PTS_PROVIDER_IMAGE_INVALID",
            message=message,
            http_status=502,
            details={},
            retryable=False,
        )

    def _invalid_structured_output_error(self, issues: list[dict[str, object]]) -> AppError:
        redacted = [
            _summarize_single_issue(issue) for issue in issues
        ]
        return AppError(
            code="PTS_PROVIDER_INVALID_STRUCTURED_OUTPUT",
            message="Provider 结构化输出无法通过校验。",
            http_status=502,
            details={"issues": redacted},
            retryable=False,
        )

    def _auth_error(self, message: str) -> AppError:
        return AppError(
            code="PTS_PROVIDER_AUTH_FAILED",
            message=message,
            http_status=502,
            details={},
            retryable=False,
        )

    def _rate_limited_error(self) -> AppError:
        return AppError(
            code="PTS_PROVIDER_RATE_LIMITED",
            message="Provider 请求被限流，请稍后重试。",
            http_status=502,
            details={},
            retryable=True,
        )

    def _unavailable_error(self, message: str) -> AppError:
        return AppError(
            code="PTS_PROVIDER_UNAVAILABLE",
            message=message,
            http_status=502,
            details={},
            retryable=True,
        )


def _model_schema[TModel: BaseModel](
    name: str, model: type[TModel]
) -> dict[str, object]:
    schema = cast(Any, model).model_json_schema(by_alias=True)
    _strip_frozen_fields(schema, _frozen_fields_by_model(model))
    _strictify_schema(schema)
    return {"name": name, "strict": True, "schema": schema}


def _frozen_fields_by_model(model: type[BaseModel]) -> dict[str, set[str]]:
    """Map model class names to their read-only (derived) field aliases.

    Derived fields are computed by domain ``model_validator``s, so the provider
    schema must not require the model to produce them (``_strictify_schema``
    would otherwise mark them ``required`` and the domain ``before`` validator
    would reject the echoed values). A model-level ``ConfigDict(frozen=True)``
    does not propagate to ``FieldInfo.frozen``, so only fields explicitly
    declared ``Field(..., frozen=True)`` are collected here.
    """
    collected: dict[str, type[BaseModel]] = {}
    _collect_models(model, collected)
    return {
        name: {
            field.alias or field_name
            for field_name, field in cls.model_fields.items()
            if field.frozen
        }
        for name, cls in collected.items()
    }


def _collect_models(
    model: type[BaseModel], collected: dict[str, type[BaseModel]]
) -> None:
    if model.__name__ in collected:
        return
    collected[model.__name__] = model
    for field in model.model_fields.values():
        _collect_annotation(field.annotation, collected)


def _collect_annotation(
    annotation: object, collected: dict[str, type[BaseModel]]
) -> None:
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        if args:
            _collect_annotation(args[0], collected)
        return
    if origin is not None:
        for arg in get_args(annotation):
            _collect_annotation(arg, collected)
        return
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        _collect_models(annotation, collected)


def _strip_frozen_fields(
    node: object, frozen_by_model: dict[str, set[str]]
) -> None:
    """Recursively remove ``Field(frozen=True)`` properties from a JSON schema.

    Walks every object schema (top level and ``$defs``) and, when the node's
    ``title`` matches a collected model name, drops that model's read-only
    properties. ``required`` is pruned in the same pass; ``_strictify_schema``
    later rebuilds it from the surviving properties.
    """
    if isinstance(node, dict):
        title = node.get("title")
        if isinstance(title, str):
            frozen = frozen_by_model.get(title)
            if frozen:
                properties = node.get("properties")
                if isinstance(properties, dict):
                    for alias in frozen:
                        properties.pop(alias, None)
                required = node.get("required")
                if isinstance(required, list):
                    node["required"] = [
                        item for item in required if item not in frozen
                    ]
        for value in node.values():
            _strip_frozen_fields(value, frozen_by_model)
    elif isinstance(node, list):
        for item in node:
            _strip_frozen_fields(item, frozen_by_model)


def _strictify_schema(node: object) -> None:
    """Make every object schema's `required` include all properties.

    The provider's strict response_format requires `required` to cover every
    key in `properties` (optional fields included). This transforms the
    standard pydantic schema accordingly, in place.
    """
    if not isinstance(node, dict):
        return
    properties = node.get("properties")
    if isinstance(properties, dict):
        node["required"] = sorted(properties)
    for value in node.values():
        if isinstance(value, dict):
            _strictify_schema(value)
        elif isinstance(value, list):
            for item in value:
                _strictify_schema(item)


def _extract_provider_message(response: httpx.Response) -> str | None:
    """Extract a redacted provider error message for diagnostics.

    Reads ``error.message`` from a JSON response body, collapses whitespace,
    and truncates to 200 characters. Returns ``None`` when the body cannot be
    parsed as JSON, has no dict ``error``, or the message is not a non-empty
    string. The request body, images, and credentials are never echoed.
    """
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    message = error.get("message")
    if not isinstance(message, str):
        return None
    collapsed = " ".join(message.split())
    if not collapsed:
        return None
    if len(collapsed) > 200:
        collapsed = collapsed[:199] + "…"
    return collapsed


def _extract_chat_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise StructuredOutputError("provider returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise StructuredOutputError("provider response JSON is not an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise StructuredOutputError("provider returned no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise StructuredOutputError("provider message has no text content")
    return content


def _is_format_capability_error(body: str) -> bool:
    lowered = body.lower()
    return "response_format" in lowered or "json_schema" in lowered


def _repair_prompt(
    prompt: str,
    json_instruction: str,
    issues: list[dict[str, object]],
) -> str:
    summary = _summarize_issues(issues)
    return (
        f"{prompt}\n{json_instruction}\n\n上次输出未通过校验，请修复。"
        f"只返回修正后的 JSON 对象。校验问题：{summary}"
    )


def _repair_prompt_plain(prompt: str, json_instruction: str) -> str:
    return (
        f"{prompt}\n{json_instruction}\n\n上次输出不是合法的纯 JSON 对象，"
        "请只返回一个 JSON 对象。"
    )


def _summarize_single_issue(issue: dict[str, object]) -> str:
    loc_value = issue.get("loc", [])
    loc = (
        ".".join(str(part) for part in loc_value)
        if isinstance(loc_value, list)
        else "root"
    )
    return f"{loc}:{issue.get('type', '')}"


def _summarize_issues(issues: list[dict[str, object]]) -> str:
    return " ".join(_summarize_single_issue(issue) for issue in issues)


def _decode_b64(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64 image payload") from exc
    if not raw or len(raw) > _MAX_IMAGE_BYTES:
        raise ValueError("image payload exceeds size limit")
    return raw


def _detect_strict_media(data: bytes) -> ImageMediaType:
    media = _detect_media_type(data)
    if media is None:
        raise ValueError("image payload has unknown media type")
    return media


def _detect_media_type(data: bytes) -> ImageMediaType | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ImageMediaType.PNG
    if data.startswith(b"\xff\xd8\xff"):
        return ImageMediaType.JPEG
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ImageMediaType.WEBP
    return None


def _redact_summary(response: httpx.Response) -> dict[str, object]:
    return {
        "status": response.status_code,
        "requestId": hashlib.sha256(
            (response.headers.get("request-id", "") or "").encode()
        ).hexdigest()[:16],
    }
