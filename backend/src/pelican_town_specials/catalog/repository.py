"""Strict, read-only repository for a generated vanilla catalog."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from pelican_town_specials.domain.errors import AppError

from .models import CatalogItem


class CatalogFormatError(ValueError):
    """Raised when a generated catalog violates its stable file contract."""


_CATALOG_VERSION = "stardew-1.6.15-v1"
_EXPECTED_TOP_LEVEL_FIELDS = frozenset({"catalogVersion", "items"})
_EXPECTED_ITEM_FIELDS = frozenset(
    {
        "itemId",
        "displayNameEn",
        "displayNameZh",
        "aliases",
        "category",
        "type",
        "usableAsIngredient",
        "isCategory",
        "edibility",
        "sellPrice",
    }
)
_ITEM_ID_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*|-5|[A-Za-z][A-Za-z0-9_]*)$")
_CATEGORY_PATTERN = re.compile(r"^-?[0-9]+$")
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_MAX_SEARCH_LIMIT = 100


class VanillaCatalog:
    """An immutable in-memory view of one generated vanilla catalog."""

    __slots__ = ("_items", "_sealed", "_version")
    _items: Mapping[str, CatalogItem]
    _sealed: bool
    _version: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("VanillaCatalog instances must be loaded with from_json")

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("VanillaCatalog is read-only")
        object.__setattr__(self, name, value)

    @classmethod
    def from_json(cls, path: Path) -> VanillaCatalog:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("catalog JSON could not be read") from exc

        if not isinstance(document, dict):
            raise CatalogFormatError("catalog top level must be an object")
        if set(document) != _EXPECTED_TOP_LEVEL_FIELDS:
            raise CatalogFormatError("catalog top level fields are invalid")

        version = document.get("catalogVersion")
        if version != _CATALOG_VERSION:
            raise CatalogFormatError("catalogVersion is invalid")

        raw_items = document.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise CatalogFormatError("catalog items must be a non-empty list")

        parsed: list[CatalogItem] = []
        seen_ids: set[str] = set()
        for index, raw_item in enumerate(raw_items):
            parsed_item = _parse_item(raw_item, index)
            if parsed_item.item_id in seen_ids:
                raise CatalogFormatError("duplicate itemId in catalog")
            seen_ids.add(parsed_item.item_id)
            parsed.append(parsed_item)

        catalog = object.__new__(cls)
        object.__setattr__(catalog, "_version", version)
        object.__setattr__(
            catalog,
            "_items",
            MappingProxyType({item.item_id: item for item in parsed}),
        )
        object.__setattr__(catalog, "_sealed", True)
        return catalog

    @property
    def version(self) -> str:
        return self._version

    @property
    def items(self) -> tuple[CatalogItem, ...]:
        return tuple(
            self._items[item_id] for item_id in sorted(self._items, key=_item_sort_key)
        )

    def require(self, item_id: str) -> CatalogItem:
        if not isinstance(item_id, str):
            raise _unknown_item_error()
        item = self._items.get(item_id)
        if item is None:
            raise _unknown_item_error()
        return item

    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        usable_only: bool = False,
    ) -> list[CatalogItem]:
        if (
            not isinstance(query, str)
            or not isinstance(limit, int)
            or isinstance(limit, bool)
        ):
            return []
        if limit <= 0:
            return []

        normalized_query = _normalize(query)
        if not normalized_query:
            return []
        bounded_limit = min(limit, _MAX_SEARCH_LIMIT)
        query_tokens = set(_tokens(normalized_query))
        ranked: list[tuple[int, float, str, CatalogItem]] = []

        for item in self._items.values():
            if usable_only and not item.usable_as_ingredient:
                continue
            if normalized_query == item.item_id.casefold():
                ranked.append((0, 1.0, item.item_id, item))
                continue

            aliases = tuple(_normalize(alias) for alias in item.aliases)
            exact_alias = any(alias == normalized_query for alias in aliases)
            if exact_alias:
                ranked.append((1, 1.0, item.item_id, item))
                continue

            prefix_scores = [
                len(normalized_query) / len(alias)
                for alias in aliases
                if alias.startswith(normalized_query)
            ]
            if prefix_scores:
                ranked.append((2, max(prefix_scores), item.item_id, item))
                continue

            if query_tokens:
                overlap_scores = [
                    len(query_tokens.intersection(_tokens(alias))) / len(query_tokens)
                    for alias in aliases
                ]
                overlap = max(overlap_scores, default=0.0)
                if overlap > 0:
                    ranked.append((3, overlap, item.item_id, item))

        ranked.sort(key=lambda match: (match[0], -match[1], _item_sort_key(match[2])))
        return [match[3] for match in ranked[:bounded_limit]]

    def search_ingredients(self, query: str, limit: int = 20) -> list[CatalogItem]:
        """Ingredient-only search that reuses the catalog ranking rules."""
        return self.search(query, limit=limit, usable_only=True)


def _parse_item(raw_item: object, index: int) -> CatalogItem:
    if not isinstance(raw_item, dict):
        raise CatalogFormatError(f"catalog item {index} has invalid structure")
    if set(raw_item) != _EXPECTED_ITEM_FIELDS:
        raise CatalogFormatError(f"catalog item {index} fields are invalid")

    item_id = raw_item["itemId"]
    if not isinstance(item_id, str):
        raise CatalogFormatError(f"catalog item {index} has invalid itemId")
    if item_id.startswith("-") and item_id != "-5":
        raise CatalogFormatError(f"catalog item {index} has invalid negative itemId")
    if not _ITEM_ID_PATTERN.fullmatch(item_id):
        raise CatalogFormatError(f"catalog item {index} has invalid itemId")
    is_category = raw_item["isCategory"]
    if not isinstance(is_category, bool):
        raise CatalogFormatError(f"catalog item {index} field types are invalid")
    if item_id == "-5" and not is_category:
        raise CatalogFormatError(f"catalog item {index} -5 must be a category")
    if is_category and item_id != "-5":
        raise CatalogFormatError(f"catalog item {index} category ID is invalid")

    display_name_en = raw_item["displayNameEn"]
    display_name_zh = raw_item["displayNameZh"]
    category = raw_item["category"]
    item_type = raw_item["type"]
    aliases = raw_item["aliases"]
    if not all(
        isinstance(value, str) and bool(value.strip())
        for value in (display_name_en, display_name_zh, category, item_type)
    ):
        raise CatalogFormatError(f"catalog item {index} field types are invalid")
    if not _CATEGORY_PATTERN.fullmatch(category):
        raise CatalogFormatError(f"catalog item {index} category is invalid")
    if (
        not isinstance(aliases, list)
        or not aliases
        or not all(isinstance(alias, str) and bool(alias.strip()) for alias in aliases)
    ):
        raise CatalogFormatError(f"catalog item {index} aliases are invalid")
    if len(set(aliases)) != len(aliases):
        raise CatalogFormatError(f"catalog item {index} aliases are invalid")

    usable = raw_item["usableAsIngredient"]
    if not isinstance(usable, bool):
        raise CatalogFormatError(f"catalog item {index} field types are invalid")
    edibility = raw_item["edibility"]
    sell_price = raw_item["sellPrice"]
    if not _optional_int(edibility) or not _optional_int(sell_price):
        raise CatalogFormatError(f"catalog item {index} field types are invalid")

    return CatalogItem(
        item_id=item_id,
        display_name_en=display_name_en,
        display_name_zh=display_name_zh,
        aliases=tuple(aliases),
        category=category,
        type=item_type,
        usable_as_ingredient=usable,
        is_category=is_category,
        edibility=edibility,
        sell_price=sell_price,
    )


def _optional_int(value: object) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN_PATTERN.findall(value))


def _item_sort_key(item_id: str) -> tuple[int, object]:
    if item_id.lstrip("-").isdigit():
        return (0, int(item_id))
    return (1, item_id)


def _unknown_item_error() -> AppError:
    return AppError(
        code="PTS_VALIDATION_INGREDIENT_ID_UNKNOWN",
        message="ingredient ID is not present in the vanilla catalog",
        http_status=422,
        details={},
        retryable=False,
    )
