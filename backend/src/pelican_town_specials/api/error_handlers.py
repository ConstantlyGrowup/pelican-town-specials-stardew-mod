from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pelican_town_specials.domain.errors import AppError

logger = logging.getLogger(__name__)

_INPUT_VALIDATION_CODE = "PTS_INPUT_VALIDATION_FAILED"
_SYSTEM_UNEXPECTED_CODE = "PTS_SYSTEM_UNEXPECTED"


def _recommended_action(code: str) -> str:
    if code == "PTS_WORKSPACE_SECRET_STORE_UNAVAILABLE":
        return "CHECK_LOCAL_CONFIGURATION"
    if code.startswith("PTS_SYSTEM_"):
        return "RETRY_OR_CONTACT_SUPPORT"
    if code.startswith(("PTS_INPUT_", "PTS_VALIDATION_")):
        return "REVIEW_INPUT"
    if code.startswith(("PTS_PROVIDER_", "PTS_GEN_")):
        return "RETRY_STAGE"
    if code.startswith("PTS_WORKSPACE_"):
        return "CHECK_LOCAL_CONFIGURATION"
    if code.startswith("PTS_STATE_"):
        return "REFRESH_ENTITY"
    if code.startswith("PTS_AUTH_"):
        return "REOPEN_APPLICATION"
    if code.startswith("PTS_EXPORT_"):
        return "REVIEW_INPUT"
    return "RETRY_OR_CONTACT_SUPPORT"


def _request_id() -> str:
    return str(uuid4())


def _envelope(
    *,
    code: str,
    message: str,
    retryable: bool,
    request_id: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "requestId": request_id,
            "details": details,
            "recommendedAction": _recommended_action(code),
        }
    }


def _field_path(location: Iterable[object]) -> str:
    return ".".join(str(part) for part in location) or "request"


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    del request
    app_error = cast(AppError, exc)
    request_id = _request_id()
    return JSONResponse(
        status_code=app_error.http_status,
        content=_envelope(
            code=app_error.code,
            message=app_error.message,
            retryable=app_error.retryable,
            request_id=request_id,
            details=dict(app_error.details),
        ),
    )


async def handle_request_validation_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request
    validation_error = cast(RequestValidationError, exc)
    fields = sorted(
        {
            _field_path(error.get("loc", ()))
            for error in validation_error.errors()
        }
    )
    details: dict[str, Any] = {"fields": fields} if fields else {}
    return JSONResponse(
        status_code=422,
        content=_envelope(
            code=_INPUT_VALIDATION_CODE,
            message="请求参数无效。",
            retryable=False,
            request_id=_request_id(),
            details=details,
        ),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    del request
    request_id = _request_id()
    logger.error(
        "Unexpected exception requestId=%s exceptionType=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content=_envelope(
            code=_SYSTEM_UNEXPECTED_CODE,
            message="系统暂时无法完成请求，请稍后重试或联系支持。",
            retryable=True,
            request_id=request_id,
            details={},
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
