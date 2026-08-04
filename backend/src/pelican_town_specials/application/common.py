"""Shared public application-layer DTOs used by Task 9 use cases."""

from __future__ import annotations

from pydantic import Field

from pelican_town_specials.domain.common import StrictModel


class Page[T](StrictModel):
    items: list[T]
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    total: int = Field(ge=0)
