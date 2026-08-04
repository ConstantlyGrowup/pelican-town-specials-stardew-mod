from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from .common import (
    GenerationStage,
    SafeScalar,
    StrictModel,
    ensure_safe_details,
    ensure_utc,
    ensure_uuid4,
)


class ErrorSummary(StrictModel):
    code: str
    message: str
    retryable: bool
    request_id: UUID
    occurred_at: datetime
    stage: GenerationStage | None = None

    @field_validator("request_id", mode="before")
    @classmethod
    def _validate_request_id(cls, value: UUID) -> UUID:
        return ensure_uuid4(value)

    @field_validator("occurred_at", mode="before")
    @classmethod
    def _validate_occurred_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


AppDetail = SafeScalar | list[str]


def recommended_action(code: str) -> str:
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


class ErrorPayload(StrictModel):
    """Strict, redacted error payload shared by HTTP and NDJSON protocols."""

    code: str
    message: str
    retryable: bool
    request_id: UUID = Field(alias="requestId")
    details: dict[str, AppDetail] = Field(default_factory=dict)
    recommended_action: str = Field(alias="recommendedAction")

    @field_validator("request_id", mode="before")
    @classmethod
    def _validate_request_id(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        try:
            return ensure_uuid4(UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("requestId must be a valid UUID v4") from exc

    @classmethod
    def from_app_error(cls, error: AppError, request_id: UUID) -> ErrorPayload:
        return cls(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            requestId=request_id,
            details=dict(error.details),
            recommendedAction=recommended_action(error.code),
        )


class ErrorEnvelope(StrictModel):
    error: ErrorPayload


def _ensure_app_error_details(
    details: Mapping[str, Any] | None,
) -> dict[str, AppDetail]:
    if details is None:
        return {}

    safe_details: dict[str, AppDetail] = {}
    for key, value in details.items():
        if not isinstance(key, str):
            raise TypeError("detail keys must be strings")
        if isinstance(value, list):
            safe_action_names: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise TypeError("detail lists must contain strings")
                safe_action_names.append(item)
            safe_details[key] = safe_action_names
            continue
        safe_details.update(ensure_safe_details({key: value}))
    return safe_details


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        http_status: int,
        details: Mapping[str, Any] | None,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details: dict[str, AppDetail] = _ensure_app_error_details(details)
        self.retryable = retryable
