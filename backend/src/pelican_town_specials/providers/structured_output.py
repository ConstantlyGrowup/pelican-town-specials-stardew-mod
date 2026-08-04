"""Strict structured chat output: pure JSON, json_schema preference, one repair."""

from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError


class StructuredOutputError(Exception):
    """Response is not a single pure JSON object."""


class StructuredOutputValidationFailed(Exception):
    """Response parsed but failed strict model validation."""

    def __init__(self, issues: list[dict[str, object]]) -> None:
        super().__init__("structured output failed validation")
        self.issues = issues


def parse_json_object(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        raise StructuredOutputError("response must be a pure JSON object")
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError("response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise StructuredOutputError("response JSON must be an object")
    return value


def validate_structured[T: BaseModel](model_type: type[T], text: str) -> T:
    """Validate a pure JSON document against a target pydantic model.

    On failure, raises StructuredOutputValidationFailed with repair issues that
    contain only field locations and error types -- never input values.
    """
    payload = parse_json_object(text)
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        issues: list[dict[str, object]] = []
        for error in exc.errors():
            loc = list(error.get("loc", ()))
            issues.append(
                {
                    "loc": [str(part) for part in loc],
                    "type": error.get("type", ""),
                }
            )
        raise StructuredOutputValidationFailed(issues=issues) from exc
