"""Immutable public models for the vanilla item catalog."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class CatalogItem:
    item_id: str
    display_name_en: str
    display_name_zh: str
    aliases: tuple[str, ...]
    category: str
    type: str
    usable_as_ingredient: bool
    is_category: bool
    edibility: int | None
    sell_price: int | None


@dataclass(frozen=True, slots=True)
class CatalogCandidate:
    item_id: str
    score: float

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("candidate item_id must be a non-empty string")
        if not isinstance(self.score, (int, float)) or isinstance(self.score, bool):
            raise TypeError("candidate score must be numeric")
        if not isfinite(float(self.score)):
            raise ValueError("candidate score must be finite")
        object.__setattr__(self, "score", float(self.score))
