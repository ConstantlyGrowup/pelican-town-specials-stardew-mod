from __future__ import annotations

import json
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, SecretStr

from pelican_town_specials.api.error_handlers import register_error_handlers
from pelican_town_specials.domain.errors import (
    AppError,
    trial_service_unavailable_error,
)


def _client(app: FastAPI) -> TestClient:
    register_error_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


def _assert_uuid4(value: str) -> None:
    request_id = UUID(value)
    assert request_id.version == 4


def test_app_error_preserves_safe_fields_and_maps_secret_store_action() -> None:
    app = FastAPI()

    @app.get("/app-error")
    def app_error_route() -> None:
        raise AppError(
            code="PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE",
            message="无法保存本机配置，请检查当前用户权限。",
            http_status=503,
            details={"operation": "set", "fields": ["apiKey"]},
            retryable=True,
        )

    response = _client(app).get("/app-error")

    assert response.status_code == 503
    error = response.json()["error"]
    assert set(error) == {
        "code",
        "message",
        "retryable",
        "requestId",
        "details",
        "recommendedAction",
    }
    assert error["code"] == "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE"
    assert error["message"] == "无法保存本机配置，请检查当前用户权限。"
    assert error["retryable"] is True
    assert error["details"] == {"operation": "set", "fields": ["apiKey"]}
    assert error["recommendedAction"] == "CHECK_LOCAL_CONFIGURATION"
    _assert_uuid4(error["requestId"])


class _ValidationPayload(BaseModel):
    api_key: SecretStr = Field(alias="apiKey")
    count: int
    name: str = Field(min_length=3)


def test_request_validation_returns_only_safe_field_paths() -> None:
    app = FastAPI()

    @app.post("/validation")
    def validation_route(_payload: _ValidationPayload) -> None:
        return None

    sentinel = "sk-validation-api-key-sentinel"
    payload = {"apiKey": sentinel, "count": "not-an-int"}
    response = _client(app).post("/validation", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PTS_INPUT_VALIDATION_FAILED"
    assert error["message"] == "请求参数无效。"
    assert error["retryable"] is False
    assert set(error["details"]) == {"fields"}
    assert set(error["details"]["fields"]) == {"body.count", "body.name"}
    assert error["recommendedAction"] == "REVIEW_INPUT"
    _assert_uuid4(error["requestId"])

    response_text = response.text
    assert sentinel not in response_text
    assert "not-an-int" not in response_text
    assert '"input"' not in response_text
    assert '"ctx"' not in response_text
    assert '"msg"' not in response_text
    assert json.dumps(payload) not in response_text


def test_unexpected_exception_returns_safe_500_and_logs_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    sentinel = "runtime-api-key-sentinel"

    @app.get("/unexpected")
    def unexpected_route() -> None:
        raise RuntimeError(f"unexpected failure containing {sentinel}")

    with caplog.at_level("ERROR"):
        response = _client(app).get("/unexpected")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "PTS_SYSTEM_UNEXPECTED"
    assert error["message"] == "系统暂时无法完成请求，请稍后重试或联系支持。"
    assert error["retryable"] is True
    assert error["details"] == {}
    assert error["recommendedAction"] == "RETRY_OR_CONTACT_SUPPORT"
    _assert_uuid4(error["requestId"])

    assert sentinel not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
    assert error["requestId"] in caplog.text
    assert "RuntimeError" in caplog.text


def test_app_error_system_code_maps_to_retry_or_support_action() -> None:
    app = FastAPI()

    @app.get("/system-error")
    def system_error_route() -> None:
        raise AppError(
            code="PTS_SYSTEM_UNEXPECTED",
            message="内部错误",
            http_status=500,
            details={},
            retryable=True,
        )

    response = _client(app).get("/system-error")

    assert response.status_code == 500
    assert response.json()["error"]["recommendedAction"] == (
        "RETRY_OR_CONTACT_SUPPORT"
    )


def test_trial_service_unavailable_has_stable_redacted_retryable_envelope() -> None:
    app = FastAPI()

    @app.get("/trial-service-unavailable")
    def trial_error_route() -> None:
        raise trial_service_unavailable_error()

    response = _client(app).get("/trial-service-unavailable")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "PTS_TRIAL_SERVICE_UNAVAILABLE"
    assert error["retryable"] is True
    assert error["details"] == {}
    assert error["recommendedAction"] == "CHECK_LOCAL_CONFIGURATION"
    assert "本次未消耗试用次数" in error["message"]
    assert "provider" not in response.text.lower()
    assert "api_key" not in response.text.lower()
