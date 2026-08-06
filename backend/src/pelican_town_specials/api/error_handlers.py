from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pelican_town_specials.domain.errors import (
    AppError,
    ErrorEnvelope,
    ErrorPayload,
    recommended_action,
)
from pelican_town_specials.observability.logging import log_event

logger = logging.getLogger(__name__)

_INPUT_VALIDATION_CODE = "PTS_INPUT_VALIDATION_FAILED"
_SYSTEM_UNEXPECTED_CODE = "PTS_SYSTEM_UNEXPECTED"


def _request_id() -> UUID:
    return uuid4()


def _envelope(
    *,
    code: str,
    message: str,
    retryable: bool,
    request_id: UUID,
    details: dict[str, Any],
) -> dict[str, Any]:
    payload = ErrorPayload(
        code=code,
        message=message,
        retryable=retryable,
        requestId=request_id,
        details=details,
        recommendedAction=recommended_action(code),
    )
    return ErrorEnvelope(error=payload).model_dump(by_alias=True, mode="json")


def _field_path(location: Iterable[object]) -> str:
    return ".".join(str(part) for part in location) or "request"


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    del request
    app_error = cast(AppError, exc)
    request_id = _request_id()
    log_event(
        logging.ERROR,
        request_id=str(request_id),
        error_code=app_error.code,
    )
    envelope = ErrorEnvelope(
        error=ErrorPayload.from_app_error(app_error, request_id=request_id)
    )
    return JSONResponse(
        status_code=app_error.http_status,
        content=envelope.model_dump(by_alias=True, mode="json"),
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
    log_event(
        logging.ERROR,
        request_id=str(request_id),
        error_code=_SYSTEM_UNEXPECTED_CODE,
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
