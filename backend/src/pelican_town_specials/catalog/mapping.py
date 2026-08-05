"""Safe conversion from semantic ingredient candidates to domain ingredients."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from typing import Protocol

from pelican_town_specials.domain.dish import GameIngredient
from pelican_town_specials.domain.errors import AppError

from .models import CatalogCandidate, CatalogItem
from .repository import VanillaCatalog

_FALLBACK_INGREDIENT_ID = "176"


class _SemanticIngredientLike(Protocol):
    name: str
    normalized_name: str
    quantity_hint: str | None = None


def map_ingredient(
    semantic: _SemanticIngredientLike,
    candidates: Sequence[CatalogCandidate],
    catalog: VanillaCatalog,
    *,
    used_item_ids: frozenset[str] = frozenset(),
) -> GameIngredient:
    """Map one semantic ingredient using only validated catalog candidates.

    ``used_item_ids`` lists item IDs already assigned earlier in the same dish;
    the catalog-fallback path uses it to avoid selecting an item that would
    duplicate an existing mapped ingredient.
    """

    del semantic
    if not candidates:
        return _fallback_ingredient(
            catalog,
            "catalog fallback: no candidate matched the ingredient",
            used_item_ids,
        )

    resolved: list[tuple[CatalogCandidate, CatalogItem]] = []
    for candidate in candidates:
        if not isinstance(candidate, CatalogCandidate) or not isfinite(candidate.score):
            raise _mapping_error(
                "PTS_VALIDATION_INGREDIENT_CANDIDATE_INVALID",
                "ingredient candidate is invalid",
            )
        try:
            item = catalog.require(candidate.item_id)
        except AppError as exc:
            if exc.code == "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN":
                raise _mapping_error(
                    "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN",
                    "ingredient candidate is not present in the vanilla catalog",
                ) from exc
            raise
        resolved.append((candidate, item))

    usable = [pair for pair in resolved if pair[1].usable_as_ingredient]
    if not usable:
        return _fallback_ingredient(
            catalog,
            "catalog fallback: no candidate is usable as an ingredient",
            used_item_ids,
        )

    candidate, item = min(
        usable,
        key=lambda pair: (-pair[0].score, _item_id_sort_key(pair[0].item_id)),
    )
    del candidate
    return GameIngredient(
        itemId=item.item_id,
        displayName=item.display_name_en,
        quantity=1,
        mappingReason="selected validated vanilla candidate",
        catalogVersion=catalog.version,
    )


def _fallback_ingredient(
    catalog: VanillaCatalog,
    reason: str,
    used_item_ids: frozenset[str],
) -> GameIngredient:
    item = _fallback_catalog_item(catalog, used_item_ids)
    return GameIngredient(
        itemId=item.item_id,
        displayName=item.display_name_en,
        quantity=1,
        mappingReason=reason,
        catalogVersion=catalog.version,
    )


def _fallback_catalog_item(
    catalog: VanillaCatalog,
    used_item_ids: frozenset[str],
) -> CatalogItem:
    """Return a deterministic unused usable catalog item for the fallback path.

    Prefers the stable Egg ingredient (itemId "176") when it is usable and not
    already used; otherwise returns the first usable-as-ingredient item that is
    not already used. If every usable item is used (extreme edge case), falls
    back to the Egg item, then to the first usable item.
    """
    try:
        egg = catalog.require(_FALLBACK_INGREDIENT_ID)
    except AppError:
        egg = None
    if (
        egg is not None
        and egg.usable_as_ingredient
        and egg.item_id not in used_item_ids
    ):
        return egg
    for item in catalog.ingredients:
        if item.item_id not in used_item_ids:
            return item
    if egg is not None and egg.usable_as_ingredient:
        return egg
    ingredients = catalog.ingredients
    if not ingredients:
        raise _mapping_error(
            "PTS_VALIDATION_INGREDIENT_NOT_USABLE",
            "catalog has no usable ingredient for fallback",
        )
    return ingredients[0]


def _item_id_sort_key(item_id: str) -> tuple[int, object]:
    if item_id.lstrip("-").isdigit():
        return (0, int(item_id))
    return (1, item_id)


def _mapping_error(code: str, message: str) -> AppError:
    return AppError(
        code=code,
        message=f"{code}: {message}",
        http_status=422,
        details={},
        retryable=False,
    )
