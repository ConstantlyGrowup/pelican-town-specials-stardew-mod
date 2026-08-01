from __future__ import annotations

import base64
import http.client
import importlib.util
import json
import sys
import threading
import unittest
from http.client import HTTPMessage
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


SAMPLE_DIR = Path(__file__).parent


def load_server_module():
    module_name = "yibu_api_probe_server"
    spec = importlib.util.spec_from_file_location(module_name, SAMPLE_DIR / "server.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load samples/yibu-api-probe/server.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


server = load_server_module()


class FakeHTTPResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")
        self.headers = HTTPMessage()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeProviderClient:
    def create_prompt(self, image_data_url: str, user_instruction: str, reasoning_effort: str) -> dict:
        return {
            "prompt": "fake image prompt",
            "model": "gpt-5.6-luna",
            "usage": {"total_tokens": 4},
            "elapsedMs": 1,
        }

    def generate_image(
        self, prompt: str, model: str | None = None, size: str | None = None
    ) -> dict:
        return {
            "imageUrl": "https://example.test/result.png",
            "model": model or "gpt-image-2-max",
            "usage": {"total_tokens": 5},
            "elapsedMs": 2,
        }

    def edit_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        model: str | None = None,
        size: str | None = None,
    ) -> dict:
        return {
            "imageUrl": "https://example.test/edited.png",
            "model": model or "gpt-image-2-max",
            "usage": {"total_tokens": 6},
            "elapsedMs": 3,
        }


class ErrorProviderClient(FakeProviderClient):
    def generate_image(
        self, prompt: str, model: str | None = None, size: str | None = None
    ) -> dict:
        raise server.ProviderError(429, "provider rate limit")


class TestResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.text = body.decode("utf-8")
        try:
            self.json = json.loads(self.text)
        except json.JSONDecodeError:
            self.json = None


class RunningApp:
    def __init__(self, config, provider=None) -> None:
        self.http_server = server.create_server(config, provider=provider or FakeProviderClient())
        self.thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.http_server.server_address[1]

    def request(self, method: str, path: str, payload: dict | None = None) -> TestResponse:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = TestResponse(response.status, response.read())
        connection.close()
        return result

    def get(self, path: str) -> TestResponse:
        return self.request("GET", path)

    def post(self, path: str, payload: dict) -> TestResponse:
        return self.request("POST", path, payload)

    def close(self) -> None:
        self.http_server.shutdown()
        self.http_server.server_close()
        self.thread.join(timeout=3)


class ConfigAndInputTests(unittest.TestCase):
    def test_default_config_uses_max_high_quality_url_and_2k(self) -> None:
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})

        self.assertEqual(config.base_url, "https://yibuapi.com/v1")
        self.assertEqual(config.text_model, "gpt-5.6-luna")
        self.assertEqual(config.text_reasoning_effort, "high")
        self.assertEqual(config.image_model, "gpt-image-2-max")
        self.assertEqual(config.image_size, "2560x2560")
        self.assertEqual(config.image_size_tier, "2K")
        self.assertEqual(config.image_aspect_ratio, "1:1")
        self.assertEqual(config.image_response_format, "url")
        self.assertEqual(config.image_quality, "high")

    def test_quality_and_format_can_be_overridden(self) -> None:
        config = server.load_config(
            {
                "PTS_OPENAI_API_KEY": "sk-test",
                "PTS_IMAGE_QUALITY": "medium",
                "PTS_IMAGE_RESPONSE_FORMAT": "b64_json",
            }
        )

        self.assertEqual(config.image_model, "gpt-image-2-max")
        self.assertEqual(config.image_quality, "medium")
        self.assertEqual(config.image_response_format, "b64_json")

    def test_missing_key_keeps_health_available(self) -> None:
        config = server.load_config({})

        self.assertIsNone(config.api_key)

    def test_parse_data_url_accepts_supported_image(self) -> None:
        encoded = base64.b64encode(b"png-bytes").decode("ascii")

        mime_type, image_bytes = server.parse_data_url(
            f"data:image/png;base64,{encoded}",
            max_bytes=64,
        )

        self.assertEqual(mime_type, "image/png")
        self.assertEqual(image_bytes, b"png-bytes")

    def test_parse_data_url_rejects_unsupported_mime_and_size(self) -> None:
        encoded = base64.b64encode(b"png-bytes").decode("ascii")

        with self.assertRaises(ValueError):
            server.parse_data_url(f"data:image/gif;base64,{encoded}", max_bytes=64)
        with self.assertRaises(ValueError):
            server.parse_data_url(f"data:image/png;base64,{encoded}", max_bytes=2)

    def test_redact_text_removes_secret_and_bearer_token(self) -> None:
        text = "Authorization: Bearer sk-secret-value and sk-another-secret"

        redacted = server.redact_text(text, ["sk-secret-value"])

        self.assertNotIn("sk-secret-value", redacted)
        self.assertNotIn("sk-another-secret", redacted)
        self.assertIn("[REDACTED]", redacted)


class ProviderClientTests(unittest.TestCase):
    def test_prompt_request_is_multimodal_and_uses_reasoning(self) -> None:
        response = FakeHTTPResponse(
            {
                "choices": [{"message": {"content": "fake image prompt"}}],
                "usage": {"total_tokens": 12},
            }
        )
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})

        with patch.object(server.urllib.request, "urlopen", return_value=response) as fake_urlopen:
            result = server.ProviderClient(config).create_prompt(
                "data:image/png;base64,aGVsbG8=",
                "把背景改成黄昏",
                "high",
            )

        request = fake_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://yibuapi.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "gpt-5.6-luna")
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["messages"][1]["content"][1]["type"], "image_url")
        self.assertEqual(result["prompt"], "fake image prompt")
        self.assertEqual(result["usage"]["total_tokens"], 12)

    def test_generation_sends_url_and_high_quality_by_default(self) -> None:
        response = FakeHTTPResponse(
            {"created": 1, "data": [{"url": "https://example.test/result.png"}]}
        )
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})

        with patch.object(server.urllib.request, "urlopen", return_value=response) as fake_urlopen:
            result = server.ProviderClient(config).generate_image("cinematic sunset")

        request = fake_urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/images/generations"))
        body = json.loads(request.data)
        # 默认：2K · 1:1 → 2560x2560；response_format=url + quality=high
        self.assertEqual(
            body,
            {
                "model": "gpt-image-2-max",
                "prompt": "cinematic sunset",
                "size": "2560x2560",
                "n": 1,
                "response_format": "url",
                "quality": "high",
            },
        )
        self.assertNotIn("output_format", body)
        self.assertEqual(result["imageUrl"], "https://example.test/result.png")

    def test_compute_image_size_uses_tier_and_ratio(self) -> None:
        # 16:9 行应与历史 1K/2K/4K 值一致，1:1 应为方形。
        self.assertEqual(server.compute_image_size("1K", "16:9"), "1280x720")
        self.assertEqual(server.compute_image_size("2K", "16:9"), "2560x1440")
        self.assertEqual(server.compute_image_size("4K", "16:9"), "3840x2160")
        self.assertEqual(server.compute_image_size("2K", "1:1"), "2560x2560")
        self.assertEqual(server.compute_image_size("1K", "1:1"), "1280x1280")
        self.assertEqual(server.compute_image_size("4K", "1:1"), "3840x3840")
        # 竖向比例应交换长边。
        self.assertEqual(server.compute_image_size("2K", "9:16"), "1440x2560")
        self.assertEqual(server.compute_image_size("2K", "3:4"), "1920x2560")

    def test_gpt_image_output_format_accepts_jpeg_and_webp(self) -> None:
        for output_format in ("jpeg", "webp"):
            with self.subTest(output_format=output_format):
                response = FakeHTTPResponse(
                    {"data": [{"b64_json": base64.b64encode(b"generated").decode("ascii")}]}
                )
                config = server.load_config(
                    {
                        "PTS_OPENAI_API_KEY": "sk-test",
                        "PTS_IMAGE_RESPONSE_FORMAT": output_format,
                    }
                )

                with patch.object(server.urllib.request, "urlopen", return_value=response) as fake_urlopen:
                    server.ProviderClient(config).generate_image("test")

                body = json.loads(fake_urlopen.call_args.args[0].data)
                self.assertEqual(body["output_format"], output_format)
                self.assertNotIn("response_format", body)

    def test_legacy_response_format_is_used_for_dall_e_style_models(self) -> None:
        for response_format in ("url", "b64_json"):
            with self.subTest(response_format=response_format):
                response = FakeHTTPResponse(
                    {"data": [{"url": "https://example.test/dalle.png"}]}
                )
                config = server.load_config(
                    {
                        "PTS_OPENAI_API_KEY": "sk-test",
                        "PTS_IMAGE_RESPONSE_FORMAT": response_format,
                    }
                )

                with patch.object(server.urllib.request, "urlopen", return_value=response) as fake_urlopen:
                    server.ProviderClient(config).generate_image("test")

                body = json.loads(fake_urlopen.call_args.args[0].data)
                self.assertEqual(body["response_format"], response_format)
                self.assertNotIn("output_format", body)

    def test_quality_is_sent_for_base_model_too(self) -> None:
        response = FakeHTTPResponse(
            {
                "created": 1,
                "data": [{"b64_json": base64.b64encode(b"generated").decode("ascii")}],
            }
        )
        config = server.load_config(
            {
                "PTS_OPENAI_API_KEY": "sk-test",
                "PTS_IMAGE_QUALITY": "high",
                "PTS_IMAGE_RESPONSE_FORMAT": "png",
            }
        )

        with patch.object(server.urllib.request, "urlopen", return_value=response) as fake_urlopen:
            result = server.ProviderClient(config).generate_image("pixel art", model="gpt-image-2")

        body = json.loads(fake_urlopen.call_args.args[0].data)
        self.assertEqual(body["model"], "gpt-image-2")
        self.assertEqual(body["quality"], "high")
        self.assertEqual(body["output_format"], "png")
        self.assertNotIn("response_format", body)
        self.assertEqual(result["imageDataUrl"], "data:image/png;base64,Z2VuZXJhdGVk")

    def test_generation_uses_override_model(self) -> None:
        response = FakeHTTPResponse(
            {"data": [{"url": "https://example.test/result.png"}]}
        )
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})

        with patch.object(server.urllib.request, "urlopen", return_value=response) as fake_urlopen:
            result = server.ProviderClient(config).generate_image("test", model="gpt-image-2")

        body = json.loads(fake_urlopen.call_args.args[0].data)
        self.assertEqual(body["model"], "gpt-image-2")
        self.assertEqual(result["model"], "gpt-image-2")

    def test_quality_is_sent_for_both_models(self) -> None:
        config = server.load_config(
            {
                "PTS_OPENAI_API_KEY": "sk-test",
                "PTS_IMAGE_QUALITY": "high",
            }
        )
        client = server.ProviderClient(config)
        response = FakeHTTPResponse(
            {"data": [{"url": "https://example.test/result.png"}]}
        )
        for model in ("gpt-image-2", "gpt-image-2-max"):
            with self.subTest(model=model):
                with patch.object(
                    server.urllib.request, "urlopen", return_value=response
                ) as fake_urlopen:
                    client.generate_image("test", model=model)
                body = json.loads(fake_urlopen.call_args.args[0].data)
                self.assertEqual(body["quality"], "high")

    def test_provider_error_is_sanitized(self) -> None:
        error = HTTPError(
            "https://yibuapi.com/v1/images/generations",
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )
        error.read = lambda: b'{"error":{"message":"Bearer sk-secret-value"}}'  # type: ignore[method-assign]
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-secret-value"})

        with patch.object(server.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(server.ProviderError) as context:
                server.ProviderClient(config).generate_image("test")

        self.assertEqual(context.exception.status_code, 401)
        self.assertNotIn("sk-secret-value", context.exception.detail)
        self.assertNotIn("Bearer sk-secret-value", context.exception.detail)

    def test_provider_requires_key_only_when_calling(self) -> None:
        config = server.load_config({})

        with self.assertRaises(server.ProviderConfigurationError):
            server.ProviderClient(config).generate_image("test")

    def test_prompt_response_supports_segmented_content(self) -> None:
        response = FakeHTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "first part"},
                                {"type": "text", "text": "second part"},
                            ]
                        }
                    }
                ]
            }
        )
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})

        with patch.object(server.urllib.request, "urlopen", return_value=response):
            result = server.ProviderClient(config).create_prompt(
                "data:image/png;base64,aGVsbG8=",
                "keep the subject",
                "high",
            )

        self.assertEqual(result["prompt"], "first part\nsecond part")

    def test_malformed_chat_choice_is_provider_error(self) -> None:
        response = FakeHTTPResponse({"choices": [None]})
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})

        with patch.object(server.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(server.ProviderError) as context:
                server.ProviderClient(config).create_prompt(
                    "data:image/png;base64,aGVsbG8=",
                    "keep the subject",
                    "high",
                )

        self.assertEqual(context.exception.status_code, 200)
        self.assertIn("invalid chat choice", context.exception.detail)

    def test_provider_error_does_not_echo_prompt_or_image_data(self) -> None:
        error = HTTPError(
            "https://yibuapi.com/v1/images/generations",
            400,
            "Bad Request",
            hdrs=None,
            fp=None,
        )
        error.read = lambda: (
            b'{"error":{"message":"echo add a sunset '
            b'data:image/png;base64,aGVsbG8="}}'
        )  # type: ignore[method-assign]
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})

        with patch.object(server.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(server.ProviderError) as context:
                server.ProviderClient(config).generate_image("add a sunset")

        self.assertNotIn("add a sunset", context.exception.detail)
        self.assertNotIn("data:image/png;base64,aGVsbG8=", context.exception.detail)
        self.assertIn("[IMAGE_DATA_REDACTED]", context.exception.detail)

    def test_http_error_status_is_preserved_for_rate_limit_and_server_error(self) -> None:
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})
        for status_code in (429, 500):
            with self.subTest(status_code=status_code):
                error = HTTPError(
                    "https://yibuapi.com/v1/images/generations",
                    status_code,
                    "Provider Error",
                    hdrs=None,
                    fp=None,
                )
                error.read = lambda: b'{"error":{"message":"retry later"}}'  # type: ignore[method-assign]
                with patch.object(server.urllib.request, "urlopen", side_effect=error):
                    with self.assertRaises(server.ProviderError) as context:
                        server.ProviderClient(config).generate_image("test")
                self.assertEqual(context.exception.status_code, status_code)

    def test_custom_base_url_does_not_duplicate_v1(self) -> None:
        response = FakeHTTPResponse({"data": [{"url": "https://example.test/result.png"}]})
        config = server.load_config(
            {
                "PTS_OPENAI_API_KEY": "sk-test",
                "PTS_OPENAI_BASE_URL": "https://example.test/v1/",
            }
        )

        with patch.object(server.urllib.request, "urlopen", return_value=response) as fake_urlopen:
            server.ProviderClient(config).generate_image("test")

        self.assertEqual(
            fake_urlopen.call_args.args[0].full_url,
            "https://example.test/v1/images/generations",
        )

    def test_edit_request_is_multipart_and_contains_source_image(self) -> None:
        response = FakeHTTPResponse(
            {"data": [{"url": "https://example.test/edited.png"}]}
        )
        config = server.load_config({"PTS_OPENAI_API_KEY": "sk-test"})

        with patch.object(server.urllib.request, "urlopen", return_value=response) as fake_urlopen:
            result = server.ProviderClient(config).edit_image(
                b"source-bytes",
                "image/png",
                "add a sunset",
            )

        request = fake_urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/images/edits"))
        content_type = request.headers.get("Content-Type") or request.headers.get("Content-type")
        self.assertIsNotNone(content_type)
        self.assertIn("multipart/form-data; boundary=", content_type)
        self.assertIn(b'name="image"; filename="source.png"', request.data)
        self.assertIn(b"source-bytes", request.data)
        self.assertIn(b'name="prompt"', request.data)
        # 默认 response_format=url + quality=high：multipart 里应出现这两个字段
        self.assertIn(b'name="response_format"', request.data)
        self.assertIn(b'name="quality"', request.data)
        self.assertIn(b"high", request.data)
        self.assertNotIn(b"output_format", request.data)
        self.assertEqual(result["imageUrl"], "https://example.test/edited.png")


class HttpRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = RunningApp(server.load_config({"PTS_OPENAI_API_KEY": "sk-test"}))

    def tearDown(self) -> None:
        self.app.close()

    def test_health_never_returns_api_key(self) -> None:
        response = self.app.get("/api/health")

        self.assertEqual(response.status, 200)
        self.assertTrue(response.json["apiKeyConfigured"])
        self.assertEqual(response.json["maxUploadBytes"], 10485760)
        self.assertNotIn("sk-test", response.text)

    def test_prompt_route_returns_generated_prompt(self) -> None:
        response = self.app.post(
            "/api/prompt",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "userInstruction": "把背景改成黄昏",
                "reasoningEffort": "high",
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["prompt"], "fake image prompt")

    def test_image_route_selects_generation_mode(self) -> None:
        response = self.app.post(
            "/api/image",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "prompt": "fake image prompt",
                "mode": "generate",
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["imageUrl"], "https://example.test/result.png")

    def test_image_route_selects_edit_mode(self) -> None:
        response = self.app.post(
            "/api/image",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "prompt": "fake image prompt",
                "mode": "edit",
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["imageUrl"], "https://example.test/edited.png")

    def test_image_route_forwards_selected_model(self) -> None:
        response = self.app.post(
            "/api/image",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "prompt": "fake image prompt",
                "mode": "generate",
                "model": "gpt-image-2",
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["model"], "gpt-image-2")

    def test_image_route_accepts_valid_tier_and_ratio(self) -> None:
        response = self.app.post(
            "/api/image",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "prompt": "fake image prompt",
                "mode": "generate",
                "sizeTier": "4K",
                "aspectRatio": "9:16",
            },
        )

        self.assertEqual(response.status, 200)

    def test_image_route_rejects_invalid_tier(self) -> None:
        response = self.app.post(
            "/api/image",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "prompt": "fake image prompt",
                "mode": "generate",
                "sizeTier": "8K",
            },
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(response.json["error"]["code"], "INVALID_REQUEST")

    def test_image_route_rejects_invalid_ratio(self) -> None:
        response = self.app.post(
            "/api/image",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "prompt": "fake image prompt",
                "mode": "generate",
                "aspectRatio": "21:9",
            },
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(response.json["error"]["code"], "INVALID_REQUEST")

    def test_image_route_rejects_invalid_model(self) -> None:
        response = self.app.post(
            "/api/image",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "prompt": "fake image prompt",
                "mode": "generate",
                "model": "",
            },
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(response.json["error"]["code"], "INVALID_REQUEST")

    def test_invalid_request_returns_structured_error(self) -> None:
        response = self.app.post("/api/image", {"mode": "unknown"})

        self.assertEqual(response.status, 400)
        self.assertEqual(response.json["error"]["code"], "INVALID_REQUEST")

    def test_provider_error_is_structured_at_route_boundary(self) -> None:
        self.app.close()
        self.app = RunningApp(
            server.load_config({"PTS_OPENAI_API_KEY": "sk-test"}),
            provider=ErrorProviderClient(),
        )

        response = self.app.post(
            "/api/image",
            {
                "imageDataUrl": "data:image/png;base64,aGVsbG8=",
                "prompt": "fake image prompt",
                "mode": "generate",
            },
        )

        self.assertEqual(response.status, 502)
        self.assertEqual(response.json["error"]["code"], "PROVIDER_ERROR")
        self.assertEqual(response.json["error"]["upstreamStatus"], 429)

    def test_oversized_http_body_is_rejected_before_provider_call(self) -> None:
        self.app.close()
        self.app = RunningApp(
            server.load_config({"PTS_OPENAI_API_KEY": "sk-test", "PTS_MAX_UPLOAD_BYTES": "1"})
        )
        oversized_value = "x" * 1_100_000

        response = self.app.post(
            "/api/image",
            {"imageDataUrl": oversized_value, "prompt": "test", "mode": "generate"},
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(response.json["error"]["code"], "INVALID_REQUEST")

    def test_unknown_path_returns_not_found(self) -> None:
        response = self.app.get("/not-found")

        self.assertEqual(response.status, 404)

    def test_index_is_served(self) -> None:
        response = self.app.get("/")

        self.assertEqual(response.status, 200)
        self.assertIn("一步 API", response.text)

    def test_health_is_available_without_key(self) -> None:
        self.app.close()
        self.app = RunningApp(server.load_config({}))

        response = self.app.get("/api/health")

        self.assertEqual(response.status, 200)
        self.assertFalse(response.json["apiKeyConfigured"])


class StaticPageTests(unittest.TestCase):
    def test_index_contains_workflow_and_no_key_input(self) -> None:
        html = (SAMPLE_DIR / "index.html").read_text(encoding="utf-8")

        for text in (
            "生成编辑指令",
            "图生图编辑（推荐，已实测可用）",
            "从文本生成（无原图参与）",
            "输出尺寸（分辨率）",
            "输出比例",
            "1:1",
            "gpt-image-2",
            "revisedPrompt",
            "maxUploadBytes",
            "/api/prompt",
            "/api/image",
        ):
            self.assertIn(text, html)
        self.assertNotIn('name="apiKey"', html)
        self.assertNotIn("PTS_OPENAI_API_KEY", html)


class RuntimeDocumentationTests(unittest.TestCase):
    def test_runtime_files_document_safe_configuration(self) -> None:
        example = (SAMPLE_DIR / ".env.example").read_text(encoding="utf-8")
        runner = (SAMPLE_DIR / "run.ps1").read_text(encoding="utf-8")
        readme = (SAMPLE_DIR / "README.md").read_text(encoding="utf-8")

        self.assertIn("PTS_OPENAI_API_KEY", example)
        self.assertIn("Read-Host", runner)
        self.assertIn("AsSecureString", runner)
        self.assertIn("gpt-image-2-max", readme)
        self.assertIn("gpt-image-2", readme)
        self.assertIn("quality", readme)
        self.assertIn("1K", readme)
        self.assertIn("1:1", readme)
        self.assertIn("不要", readme)


if __name__ == "__main__":
    unittest.main()
