from __future__ import annotations

import base64
import http.server
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
SUPPORTED_REASONING_EFFORTS = frozenset({"low", "medium", "high"})
# 参考用户给出的调用样例：images.generate 带 response_format="url" 与 quality="high"。
# 默认发送 response_format="url"（大图用 URL 比内嵌 base64 更稳）；auto 表示“不发送”。
IMAGE_OUTPUT_FORMATS = frozenset({"png", "jpeg", "webp"})
IMAGE_LEGACY_RESPONSE_FORMATS = frozenset({"url", "b64_json"})
IMAGE_FORMAT_AUTO = "auto"
SUPPORTED_IMAGE_RESPONSE_FORMATS = (
    {IMAGE_FORMAT_AUTO} | IMAGE_OUTPUT_FORMATS | IMAGE_LEGACY_RESPONSE_FORMATS
)
# 中转站实测：gpt-image-2-max 接受 3840x2160（4K 16:9）。其余尺寸由
# 分辨率档位（长边像素）× 比例 换算得到；默认比例 1:1。
IMAGE_SIZE_TIERS = {"1K": 1280, "2K": 2560, "4K": 3840}
IMAGE_ASPECT_RATIOS = {
    "1:1": (1, 1),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:3": (4, 3),
    "3:4": (3, 4),
}
DEFAULT_SIZE_TIER = "2K"
DEFAULT_ASPECT_RATIO = "1:1"


def compute_image_size(tier: str, aspect_ratio: str) -> str:
    """把分辨率档位和比例换算成中转站接受的 WxH 像素尺寸。"""

    long_edge = IMAGE_SIZE_TIERS[tier]
    ratio_w, ratio_h = IMAGE_ASPECT_RATIOS[aspect_ratio]
    if ratio_w >= ratio_h:
        width = long_edge
        height = round(long_edge * ratio_h / ratio_w)
    else:
        height = long_edge
        width = round(long_edge * ratio_w / ratio_h)
    return f"{width}x{height}"


IMAGE_DATA_URL_PATTERN = re.compile(
    r"data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+",
    re.IGNORECASE,
)
MAX_SAFE_DRAIN_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class AppConfig:
    base_url: str
    api_key: str | None
    text_model: str
    text_reasoning_effort: str
    image_model: str
    image_size: str
    image_size_tier: str
    image_aspect_ratio: str
    image_response_format: str
    image_quality: str | None
    chat_timeout_seconds: float
    image_timeout_seconds: float
    max_upload_bytes: int


class ProviderConfigurationError(ValueError):
    """Raised when a provider call is attempted without an API key."""


class ProviderError(RuntimeError):
    """A sanitized upstream provider or transport failure."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def load_config(environ: Mapping[str, str] | None = None) -> AppConfig:
    """Load settings from an environment mapping without requiring a Key."""

    values = os.environ if environ is None else environ
    api_key = values.get("PTS_OPENAI_API_KEY", "").strip() or None
    base_url = values.get("PTS_OPENAI_BASE_URL", "https://yibuapi.com/v1").strip().rstrip("/")
    text_reasoning_effort = values.get("PTS_TEXT_REASONING_EFFORT", "high").strip().lower()
    image_response_format = values.get("PTS_IMAGE_RESPONSE_FORMAT", "url").strip()
    chat_timeout_seconds = float(values.get("PTS_CHAT_TIMEOUT_SECONDS", "120"))
    image_timeout_seconds = float(values.get("PTS_IMAGE_TIMEOUT_SECONDS", "600"))
    max_upload_bytes = int(values.get("PTS_MAX_UPLOAD_BYTES", "10485760"))
    image_size_tier = values.get("PTS_IMAGE_SIZE_TIER", DEFAULT_SIZE_TIER).strip()
    image_aspect_ratio = values.get("PTS_IMAGE_ASPECT_RATIO", DEFAULT_ASPECT_RATIO).strip()

    if not base_url:
        raise ValueError("PTS_OPENAI_BASE_URL must not be empty")
    if text_reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
        raise ValueError("PTS_TEXT_REASONING_EFFORT must be low, medium, or high")
    if image_response_format not in SUPPORTED_IMAGE_RESPONSE_FORMATS:
        raise ValueError(
            "PTS_IMAGE_RESPONSE_FORMAT must be auto, url, b64_json, png, jpeg, or webp"
        )
    if image_size_tier not in IMAGE_SIZE_TIERS:
        raise ValueError("PTS_IMAGE_SIZE_TIER must be 1K, 2K, or 4K")
    if image_aspect_ratio not in IMAGE_ASPECT_RATIOS:
        raise ValueError(
            "PTS_IMAGE_ASPECT_RATIO must be 1:1, 16:9, 9:16, 4:3, or 3:4"
        )
    # 由档位 × 比例换算出默认像素尺寸，与前端默认（2K · 1:1）保持一致。
    image_size = compute_image_size(image_size_tier, image_aspect_ratio)
    if chat_timeout_seconds <= 0 or image_timeout_seconds <= 0:
        raise ValueError("provider timeouts must be positive")
    if max_upload_bytes <= 0:
        raise ValueError("PTS_MAX_UPLOAD_BYTES must be positive")

    return AppConfig(
        base_url=base_url,
        api_key=api_key,
        text_model=values.get("PTS_TEXT_MODEL", "gpt-5.6-luna").strip(),
        text_reasoning_effort=text_reasoning_effort,
        image_model=values.get("PTS_IMAGE_MODEL", "gpt-image-2-max").strip(),
        image_size=image_size,
        image_size_tier=image_size_tier,
        image_aspect_ratio=image_aspect_ratio,
        image_response_format=image_response_format,
        image_quality=values.get("PTS_IMAGE_QUALITY", "high").strip() or None,
        chat_timeout_seconds=chat_timeout_seconds,
        image_timeout_seconds=image_timeout_seconds,
        max_upload_bytes=max_upload_bytes,
    )


def parse_data_url(value: str, max_bytes: int) -> tuple[str, bytes]:
    """Decode a supported base64 image data URL and enforce its byte limit."""

    if not isinstance(value, str) or not value.startswith("data:"):
        raise ValueError("imageDataUrl must be a base64 data URL")

    header, separator, encoded = value.partition(",")
    if separator != "," or ";base64" not in header:
        raise ValueError("imageDataUrl must use base64 encoding")

    mime_type = header[5:].split(";", 1)[0].lower()
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ValueError("imageDataUrl must be PNG, JPEG, or WEBP")
    if not encoded:
        raise ValueError("imageDataUrl must contain image bytes")

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("imageDataUrl contains invalid base64") from exc

    if not image_bytes:
        raise ValueError("imageDataUrl must contain image bytes")
    if len(image_bytes) > max_bytes:
        raise ValueError(f"image exceeds the {max_bytes} byte limit")
    return mime_type, image_bytes


def redact_text(value: str, secrets: Iterable[str]) -> str:
    """Remove configured secrets, bearer tokens, and common OpenAI key fragments."""

    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")

    redacted = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+|bearer\s+)[^\s,;\"']+",
        r"\1[REDACTED]",
        redacted,
    )
    return re.sub(r"(?i)sk-[A-Za-z0-9_-]{4,}", "[REDACTED]", redacted)


def sanitize_provider_detail(value: str, secrets: Iterable[str]) -> str:
    """Keep only a bounded provider message and remove request-sensitive content."""

    candidate = "provider returned an HTTP error"
    try:
        payload = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None

    if isinstance(payload, Mapping):
        error = payload.get("error")
        if isinstance(error, Mapping) and isinstance(error.get("message"), str):
            candidate = error["message"]
        elif isinstance(payload.get("message"), str):
            candidate = payload["message"]

    sanitized = redact_text(candidate, secrets)
    sanitized = IMAGE_DATA_URL_PATTERN.sub("[IMAGE_DATA_REDACTED]", sanitized)
    sanitized = re.sub(r"[A-Za-z0-9+/]{80,}={0,2}", "[DATA_REDACTED]", sanitized)
    if len(sanitized) > 1000:
        sanitized = f"{sanitized[:1000]}…"
    return sanitized


PROMPT_SYSTEM_INSTRUCTION = """
You are an image-edit prompt writer. Inspect the supplied source image and the user's
one-sentence request. Produce one self-contained prompt that an image generation model
can use directly. Preserve the subject, identity, composition, and details that the
user did not ask to change. Make requested changes precise and add useful visual details
such as style, lighting, camera, material, and composition when they are implied by the
image. Output only the prompt, with no explanation, JSON, Markdown, or code fence.
""".strip()


def _endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _image_filename(mime_type: str) -> str:
    extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime_type]
    return f"source.{extension}"


def _multipart_body(
    fields: Mapping[str, str],
    file_field: str,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
) -> tuple[bytes, str]:
    boundary = f"----YibuApiProbe{os.urandom(12).hex()}"
    boundary_bytes = boundary.encode("ascii")
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                b"--" + boundary_bytes + b"\r\n",
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(
                    "utf-8"
                ),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            b"--" + boundary_bytes + b"\r\n",
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("ascii"),
            file_bytes,
            b"\r\n",
            b"--" + boundary_bytes + b"--\r\n",
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class ProviderClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def create_prompt(
        self,
        image_data_url: str,
        user_instruction: str,
        reasoning_effort: str,
    ) -> dict[str, Any]:
        self._require_api_key()
        started_at = time.perf_counter()
        payload = {
            "model": self.config.text_model,
            "messages": [
                {"role": "system", "content": PROMPT_SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"User's requested edit:\n{user_instruction}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url, "detail": "high"},
                        },
                    ],
                },
            ],
            "reasoning_effort": reasoning_effort,
        }
        body = self._request_json(
            "chat/completions",
            payload,
            timeout=self.config.chat_timeout_seconds,
            sensitive_values=(user_instruction,),
        )
        prompt = self._extract_prompt(body)
        return {
            "prompt": prompt,
            "model": body.get("model", self.config.text_model),
            "usage": body.get("usage"),
            "elapsedMs": round((time.perf_counter() - started_at) * 1000),
        }

    def generate_image(
        self,
        prompt: str,
        model: str | None = None,
        size: str | None = None,
    ) -> dict[str, Any]:
        self._require_api_key()
        started_at = time.perf_counter()
        model = model or self.config.image_model
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size or self.config.image_size,
            "n": 1,
        }
        self._add_image_format_parameter(payload)
        if self.config.image_quality:
            payload["quality"] = self.config.image_quality
        body = self._request_json(
            "images/generations",
            payload,
            timeout=self.config.image_timeout_seconds,
            sensitive_values=(prompt,),
        )
        result = self._normalize_image_response(body, self.config.image_response_format)
        result.update(
            {
                "model": body.get("model", model),
                "usage": body.get("usage"),
                "elapsedMs": round((time.perf_counter() - started_at) * 1000),
            }
        )
        return result

    def edit_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        model: str | None = None,
        size: str | None = None,
    ) -> dict[str, Any]:
        self._require_api_key()
        started_at = time.perf_counter()
        model = model or self.config.image_model
        fields: dict[str, str] = {
            "model": model,
            "prompt": prompt,
            "n": "1",
            "size": size or self.config.image_size,
        }
        self._add_image_format_parameter(fields)
        if self.config.image_quality:
            fields["quality"] = self.config.image_quality
        body, content_type = _multipart_body(
            fields,
            file_field="image",
            filename=_image_filename(mime_type),
            mime_type=mime_type,
            file_bytes=image_bytes,
        )
        response = self._request_bytes(
            "images/edits",
            body,
            content_type=content_type,
            timeout=self.config.image_timeout_seconds,
            sensitive_values=(prompt,),
        )
        result = self._normalize_image_response(response, self.config.image_response_format)
        result.update(
            {
                "model": response.get("model", model),
                "usage": response.get("usage"),
                "elapsedMs": round((time.perf_counter() - started_at) * 1000),
            }
        )
        return result

    def _add_image_format_parameter(self, target: dict[str, Any]) -> None:
        """Choose the format parameter to send, matching proven provider behavior.

        成功案例（gpt-image-2-edit-multi*.py）不发送任何 format 参数，中转站对
        gpt-image-2-max 默认返回 b64_json，因此默认 auto 就是“不发送”。只有显式
        配置时才补充：png/jpeg/webp → output_format（GPT 风格）；url/b64_json →
        response_format（dall-e-2/3 风格）。两者互斥，不会同时出现。
        """
        configured = self.config.image_response_format
        if configured in IMAGE_OUTPUT_FORMATS:
            target["output_format"] = configured
        elif configured in IMAGE_LEGACY_RESPONSE_FORMATS:
            target["response_format"] = configured

    def _require_api_key(self) -> str:
        if not self.config.api_key:
            raise ProviderConfigurationError(
                "PTS_OPENAI_API_KEY is not configured; restart the sample with a Key"
            )
        return self.config.api_key

    def _request_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        timeout: float,
        sensitive_values: Iterable[str] = (),
    ) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._request_json_bytes(
            path,
            raw,
            "application/json",
            timeout,
            sensitive_values=sensitive_values,
        )

    def _request_json_bytes(
        self,
        path: str,
        body: bytes,
        content_type: str,
        timeout: float,
        sensitive_values: Iterable[str] = (),
    ) -> dict[str, Any]:
        response_body = self._request_raw(
            path,
            body,
            content_type,
            timeout,
            sensitive_values=sensitive_values,
        )
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(200, "provider returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ProviderError(200, "provider returned a non-object JSON response")
        return decoded

    def _request_bytes(
        self,
        path: str,
        body: bytes,
        content_type: str,
        timeout: float,
        sensitive_values: Iterable[str] = (),
    ) -> dict[str, Any]:
        return self._request_json_bytes(
            path,
            body,
            content_type,
            timeout,
            sensitive_values=sensitive_values,
        )

    def _request_raw(
        self,
        path: str,
        body: bytes,
        content_type: str,
        timeout: float,
        sensitive_values: Iterable[str] = (),
    ) -> bytes:
        api_key = self._require_api_key()
        request = urllib.request.Request(
            _endpoint_url(self.config.base_url, path),
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": content_type,
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status_code = getattr(response, "status", None)
                if status_code is None:
                    status_code = response.getcode()
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            detail = sanitize_provider_detail(
                response_body.decode("utf-8", errors="replace"),
                [api_key, *sensitive_values],
            )
            raise ProviderError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            detail = redact_text(str(exc.reason), [api_key])
            raise ProviderError(0, detail) from exc
        except OSError as exc:
            detail = redact_text(str(exc), [api_key])
            raise ProviderError(0, detail) from exc

        if not 200 <= status_code < 300:
            detail = sanitize_provider_detail(
                response_body.decode("utf-8", errors="replace"),
                [api_key, *sensitive_values],
            )
            raise ProviderError(status_code, detail)
        return response_body

    @staticmethod
    def _extract_prompt(body: Mapping[str, Any]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(200, "provider returned no chat choices")
        choice = choices[0]
        if not isinstance(choice, Mapping):
            raise ProviderError(200, "provider returned an invalid chat choice")
        message = choice.get("message")
        if not isinstance(message, Mapping):
            raise ProviderError(200, "provider returned no chat message")
        content = message.get("content")
        if isinstance(content, str):
            prompt = content.strip()
        elif isinstance(content, list):
            prompt = "\n".join(
                str(part.get("text", "")).strip()
                for part in content
                if isinstance(part, Mapping) and part.get("text")
            ).strip()
        else:
            prompt = ""
        if not prompt:
            raise ProviderError(200, "provider returned an empty image prompt")
        return prompt

    @staticmethod
    def _normalize_image_response(
        body: Mapping[str, Any],
        default_output_format: str = "png",
    ) -> dict[str, Any]:
        data = body.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], Mapping):
            raise ProviderError(200, "provider returned no image data")
        item = data[0]
        result: dict[str, Any] = {}
        if isinstance(item.get("url"), str) and item["url"]:
            result["imageUrl"] = item["url"]
        if isinstance(item.get("b64_json"), str) and item["b64_json"]:
            mime_type = {
                "png": "image/png",
                "jpeg": "image/jpeg",
                "webp": "image/webp",
            }.get(default_output_format, "image/png")
            result["imageDataUrl"] = f"data:{mime_type};base64,{item['b64_json']}"
        if not result:
            raise ProviderError(200, "provider returned neither an image URL nor b64_json")
        if isinstance(item.get("revised_prompt"), str):
            result["revisedPrompt"] = item["revised_prompt"]
        return result


class ProbeRequestHandler(http.server.BaseHTTPRequestHandler):
    """Serve the sample UI and same-origin JSON API without request-body logging."""

    server_version = "YibuApiProbe/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return None

    @property
    def app_config(self) -> AppConfig:
        return self.server.app_config  # type: ignore[attr-defined,no-any-return]

    @property
    def provider(self) -> ProviderClient:
        return self.server.provider  # type: ignore[attr-defined,no-any-return]

    @property
    def sample_dir(self) -> Path:
        return self.server.sample_dir  # type: ignore[attr-defined,no-any-return]

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "apiKeyConfigured": bool(self.app_config.api_key),
                    "baseUrl": self.app_config.base_url,
                    "textModel": self.app_config.text_model,
                    "textReasoningEffort": self.app_config.text_reasoning_effort,
                    "imageModel": self.app_config.image_model,
                    "imageSize": self.app_config.image_size,
                    "imageSizeTier": self.app_config.image_size_tier,
                    "imageAspectRatio": self.app_config.image_aspect_ratio,
                    "imageResponseFormat": self.app_config.image_response_format,
                    "imageQuality": self.app_config.image_quality,
                    "maxUploadBytes": self.app_config.max_upload_bytes,
                },
            )
            return

        if path == "/":
            index_path = self.sample_dir / "index.html"
            if index_path.is_file():
                self._send_bytes(200, index_path.read_bytes(), "text/html; charset=utf-8")
                return

        self._send_error_payload(404, "NOT_FOUND", "resource not found")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in {"/api/prompt", "/api/image"}:
            self._send_error_payload(404, "NOT_FOUND", "resource not found")
            return

        try:
            payload = self._read_json_body()
            if path == "/api/prompt":
                self._handle_prompt(payload)
            else:
                self._handle_image(payload)
        except InvalidRequestError as exc:
            self._send_error_payload(400, "INVALID_REQUEST", str(exc))
        except ProviderConfigurationError as exc:
            self._send_error_payload(503, "PROVIDER_KEY_MISSING", str(exc))
        except ProviderError as exc:
            self._send_error_payload(
                502,
                "PROVIDER_ERROR",
                redact_text(exc.detail, [self.app_config.api_key or ""]),
                upstream_status=exc.status_code,
            )
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._send_error_payload(500, "INTERNAL_ERROR", redact_text(str(exc), [self.app_config.api_key or ""]))

    def _handle_prompt(self, payload: dict[str, Any]) -> None:
        image_data_url = self._required_string(payload, "imageDataUrl")
        user_instruction = self._required_string(payload, "userInstruction")
        if len(user_instruction) > 2000:
            raise InvalidRequestError("userInstruction is too long")
        parse_data_url(image_data_url, self.app_config.max_upload_bytes)

        reasoning_effort = payload.get("reasoningEffort", self.app_config.text_reasoning_effort)
        if reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
            raise InvalidRequestError("reasoningEffort must be low, medium, or high")
        self._send_json(
            200,
            self.provider.create_prompt(image_data_url, user_instruction, reasoning_effort),
        )

    def _handle_image(self, payload: dict[str, Any]) -> None:
        image_data_url = self._required_string(payload, "imageDataUrl")
        prompt = self._required_string(payload, "prompt")
        mode = payload.get("mode", "generate")
        if mode not in {"generate", "edit"}:
            raise InvalidRequestError("mode must be generate or edit")
        if len(prompt) > 32000:
            raise InvalidRequestError("prompt is too long")
        model = payload.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise InvalidRequestError("model must be a non-empty string when provided")
        # 分辨率档位 × 比例 → 最终像素尺寸；两者都不提供时回落到服务端默认。
        size_tier = payload.get("sizeTier")
        aspect_ratio = payload.get("aspectRatio")
        if size_tier is not None and (not isinstance(size_tier, str) or not size_tier.strip()):
            raise InvalidRequestError("sizeTier must be a non-empty string when provided")
        if aspect_ratio is not None and (not isinstance(aspect_ratio, str) or not aspect_ratio.strip()):
            raise InvalidRequestError("aspectRatio must be a non-empty string when provided")
        if size_tier is not None or aspect_ratio is not None:
            size_tier = size_tier or self.app_config.image_size_tier
            aspect_ratio = aspect_ratio or self.app_config.image_aspect_ratio
            if size_tier not in IMAGE_SIZE_TIERS:
                raise InvalidRequestError(
                    f"sizeTier must be one of {', '.join(sorted(IMAGE_SIZE_TIERS))}"
                )
            if aspect_ratio not in IMAGE_ASPECT_RATIOS:
                raise InvalidRequestError(
                    f"aspectRatio must be one of {', '.join(sorted(IMAGE_ASPECT_RATIOS))}"
                )
            size = compute_image_size(size_tier, aspect_ratio)
        else:
            size = None
        mime_type, image_bytes = parse_data_url(image_data_url, self.app_config.max_upload_bytes)
        if mode == "edit":
            result = self.provider.edit_image(
                image_bytes, mime_type, prompt, model=model, size=size
            )
        else:
            result = self.provider.generate_image(prompt, model=model, size=size)
        self._send_json(200, result)

    def _read_json_body(self) -> dict[str, Any]:
        content_length_header = self.headers.get("Content-Length")
        try:
            content_length = int(content_length_header or "0")
        except ValueError as exc:
            raise InvalidRequestError("Content-Length must be an integer") from exc
        max_request_bytes = self.app_config.max_upload_bytes * 2 + 1_000_000
        if content_length <= 0 or content_length > max_request_bytes:
            if content_length > max_request_bytes and content_length <= MAX_SAFE_DRAIN_BYTES:
                self._drain_request_body(content_length)
            else:
                self.close_connection = True
            raise InvalidRequestError("request body is missing or too large")
        body = self.rfile.read(content_length)
        if self.headers.get_content_type() != "application/json":
            raise InvalidRequestError("Content-Type must be application/json")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidRequestError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise InvalidRequestError("request body must be a JSON object")
        return payload

    def _drain_request_body(self, content_length: int) -> None:
        remaining = content_length
        while remaining > 0:
            chunk = self.rfile.read(min(64 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    @staticmethod
    def _required_string(payload: Mapping[str, Any], field_name: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise InvalidRequestError(f"{field_name} is required")
        return value.strip()

    def _send_error_payload(
        self,
        status_code: int,
        code: str,
        message: str,
        upstream_status: int | None = None,
    ) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if upstream_status is not None:
            error["upstreamStatus"] = upstream_status
        self._send_json(status_code, {"error": error})

    def _send_json(self, status_code: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status_code, body, "application/json; charset=utf-8")

    def _send_bytes(self, status_code: int, body: bytes, content_type: str) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class InvalidRequestError(ValueError):
    """Raised for malformed requests at the local HTTP boundary."""


def create_server(
    config: AppConfig,
    provider: ProviderClient | Any | None = None,
    port: int = 0,
    sample_dir: Path | None = None,
) -> http.server.ThreadingHTTPServer:
    """Create a loopback-only server, optionally injecting a fake provider for tests."""

    http_server = http.server.ThreadingHTTPServer(("127.0.0.1", port), ProbeRequestHandler)
    http_server.app_config = config  # type: ignore[attr-defined]
    http_server.provider = provider or ProviderClient(config)  # type: ignore[attr-defined]
    http_server.sample_dir = sample_dir or Path(__file__).parent  # type: ignore[attr-defined]
    return http_server


def main() -> None:
    config = load_config()
    port = int(os.environ.get("PORT", "8765"))
    http_server = create_server(config, port=port)
    print(f"Yibu API probe listening at http://127.0.0.1:{port}")
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http_server.server_close()


if __name__ == "__main__":
    main()
