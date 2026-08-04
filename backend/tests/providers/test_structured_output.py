"""Structured chat output parsing, validation, and repair-boundary tests."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from pelican_town_specials.providers.structured_output import (
    StructuredOutputError,
    StructuredOutputValidationFailed,
    parse_json_object,
    validate_structured,
)


class _Simple(BaseModel):
    name: str
    count: int


def test_parse_json_object_rejects_code_fence() -> None:
    with pytest.raises(StructuredOutputError):
        parse_json_object('```json\n{"name": "x"}\n```')


def test_validate_structured_success() -> None:
    result = validate_structured(_Simple, '{"name": "x", "count": 1}')
    assert result.name == "x"
    assert result.count == 1


def test_validate_structured_rejects_non_object() -> None:
    with pytest.raises(StructuredOutputError):
        validate_structured(_Simple, "[1, 2]")


def test_validate_structured_issues_contain_no_input_values() -> None:
    with pytest.raises(StructuredOutputValidationFailed) as excinfo:
        validate_structured(_Simple, '{"name": "x", "count": "secret-value"}')

    issues = excinfo.value.issues
    assert any("count" in issue["loc"] for issue in issues)
    assert "secret-value" not in str(issues)
