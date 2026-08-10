"""Safe conversion from semantic ingredient candidates to domain ingredients."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from typing import Protocol

from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.dish import GameIngredient
from pelican_town_specials.domain.errors import AppError

from .models import CatalogCandidate, CatalogItem
from .repository import VanillaCatalog


def _display_name(item: CatalogItem, language: Language) -> str:
    """Pick the catalog display name for the target language.

    ``item_id`` stays the authoritative vanilla identity; the display name is
    only the user-visible label for the target language.
    """
    if language is Language.EN_US:
        return item.display_name_en
    return item.display_name_zh

_FALLBACK_INGREDIENT_ID = "176"
_FALLBACK_REASON_PREFIX = "catalog fallback"

# Vanilla category for fish (Data/Objects Category -4). Used by the
# main-protein consistency guard (R15).
_FISH_CATEGORY = "-4"

# Substrings that imply a fish/seafood main ingredient, in both supported
# languages. Ordered from specific to generic so the targeted catalog search
# tries the most precise term first. English terms are matched
# case-insensitively so en-US draft text (e.g. "Pan-seared Salmon") reaches
# the same main-protein consistency guard as zh-CN drafts (R15).
_SEAFOOD_KEYWORDS: tuple[str, ...] = (
    "金枪鱼",
    "沙丁鱼",
    "鲑鱼",
    "鳕鱼",
    "鲷鱼",
    "鲈鱼",
    "鳟鱼",
    "鲤鱼",
    "鲶鱼",
    "鳗鱼",
    "鲱鱼",
    "鳀鱼",
    "鲟鱼",
    "龙虾",
    "鱿鱼",
    "章鱼",
    "蛤蜊",
    "牡蛎",
    "扇贝",
    "螃蟹",
    "虾",
    "蟹",
    "鱼",
    "salmon",
    "tuna",
    "sardine",
    "anchovy",
    "herring",
    "mackerel",
    "trout",
    "carp",
    "catfish",
    "eel",
    "snapper",
    "perch",
    "bass",
    "pike",
    "sunfish",
    "flounder",
    "halibut",
    "tilapia",
    "sturgeon",
    "albacore",
    "squid",
    "octopus",
    "lobster",
    "crab",
    "shrimp",
    "prawn",
    "scallop",
    "clam",
    "oyster",
    "fish",
    "seafood",
)


class _SemanticIngredientLike(Protocol):
    name: str
    normalized_name: str
    quantity_hint: str | None = None


def ensure_main_protein(
    dish_text: str,
    ingredients: Sequence[GameIngredient],
    catalog: VanillaCatalog,
    *,
    language: Language = Language.ZH_CN,
) -> list[GameIngredient]:
    """Guarantee a seafood main ingredient when the dish text mentions one.

    The LLM occasionally designs a fish dish whose ingredient list contains
    no fish at all (R15). When any seafood keyword appears in ``dish_text``
    but no mapped ingredient belongs to the vanilla fish category, insert the
    best matching catalog fish: appended in front when there is room,
    otherwise replacing the first fallback-mapped ingredient. If neither is
    possible the list is returned unchanged.
    """
    lower_text = dish_text.casefold()
    mentioned = [
        keyword for keyword in _SEAFOOD_KEYWORDS if keyword.casefold() in lower_text
    ]
    if not mentioned:
        return list(ingredients)

    used_item_ids: set[str] = set()
    for ingredient in ingredients:
        used_item_ids.add(ingredient.item_id)
        try:
            item = catalog.require(ingredient.item_id)
        except AppError:
            continue
        if item.category == _FISH_CATEGORY:
            return list(ingredients)

    fish_item: CatalogItem | None = None
    mentioned_keyword = ""
    for keyword in mentioned:
        for item in catalog.search_ingredients(keyword, limit=5):
            if item.category == _FISH_CATEGORY and item.item_id not in used_item_ids:
                fish_item = item
                mentioned_keyword = keyword
                break
        if fish_item is not None:
            break
    if fish_item is None:
        return list(ingredients)

    inserted = GameIngredient(
        itemId=fish_item.item_id,
        displayName=_display_name(fish_item, language),
        quantity=1,
        mappingReason=(
            "main-protein consistency: dish mentions "
            f"{mentioned_keyword} but no fish was mapped"
        ),
        catalogVersion=catalog.version,
    )
    result = list(ingredients)
    if len(result) < 8:
        return [inserted, *result]
    for index, ingredient in enumerate(result):
        if ingredient.mapping_reason.startswith(_FALLBACK_REASON_PREFIX):
            result[index] = inserted
            return result
    return result


def map_ingredient(
    semantic: _SemanticIngredientLike,
    candidates: Sequence[CatalogCandidate],
    catalog: VanillaCatalog,
    *,
    used_item_ids: frozenset[str] = frozenset(),
    language: Language = Language.ZH_CN,
) -> GameIngredient:
    """Map one semantic ingredient using only validated catalog candidates.

    ``used_item_ids`` lists item IDs already assigned earlier in the same dish;
    the catalog-fallback path uses it to avoid selecting an item that would
    duplicate an existing mapped ingredient. ``language`` selects the
    user-visible display name; ``item_id`` is authoritative regardless.
    """

    del semantic
    if not candidates:
        return _fallback_ingredient(
            catalog,
            "catalog fallback: no candidate matched the ingredient",
            used_item_ids,
            language=language,
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
            language=language,
        )

    candidate, item = min(
        usable,
        key=lambda pair: (-pair[0].score, _item_id_sort_key(pair[0].item_id)),
    )
    del candidate
    return GameIngredient(
        itemId=item.item_id,
        displayName=_display_name(item, language),
        quantity=1,
        mappingReason="selected validated vanilla candidate",
        catalogVersion=catalog.version,
    )


def _fallback_ingredient(
    catalog: VanillaCatalog,
    reason: str,
    used_item_ids: frozenset[str],
    *,
    language: Language = Language.ZH_CN,
) -> GameIngredient:
    item = _fallback_catalog_item(catalog, used_item_ids)
    return GameIngredient(
        itemId=item.item_id,
        displayName=_display_name(item, language),
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
