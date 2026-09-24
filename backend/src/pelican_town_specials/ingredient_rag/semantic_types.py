"""Small bilingual ingredient ontology used only to prove catalog gaps."""

from __future__ import annotations

import re
import unicodedata

from pelican_town_specials.catalog.models import CatalogItem

_WORD = re.compile(r"[^\W_]+", re.UNICODE)

# These are semantic families, not query deny-lists: a family is rejected only
# when the frozen game catalog contains no ingredient in that same family.
_FAMILY_ALIASES: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "land_animal_meat",
        frozenset(
            {
                "beef",
                "pork",
                "lamb",
                "mutton",
                "chicken",
                "duck",
                "turkey",
                "goat",
                "venison",
                "bacon",
                "ham",
                "poultry",
                "meat",
            }
        ),
    ),
    (
        "prepared_soy",
        frozenset({"tofu", "doufu", "bean curd", "豆腐", "豆腐脑"}),
    ),
)

_CHINESE_LAND_ANIMAL_MEAT_ENDING = "肉"
_FISH_TYPE = "Fish"
_FISH_CATEGORY = "-4"
_ANIMAL_MEAT_WORDS = frozenset(
    {
        "beef",
        "pork",
        "lamb",
        "mutton",
        "chicken",
        "duck",
        "turkey",
        "goat",
        "venison",
        "bacon",
        "ham",
        "poultry",
        "meat",
    }
)
_NONMEAT_ANIMAL_PRODUCTS = frozenset(
    {"egg", "eggs", "milk", "cheese", "mayonnaise", "mayo", "oil", "sauce"}
)
_AQUATIC_TERMS = frozenset({"fish", "seafood"})


def normalize_semantic_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def classify_ingredient_family(value: str) -> str | None:
    """Recognize a small set of high-confidence ingredient families.

    The family inventory is intentionally conservative. Unrecognized text
    proceeds through ordinary retrieval; known families can trigger abstention
    only when the local catalog contains no ingredient classified likewise.
    """

    normalized = normalize_semantic_text(value)
    words = set(_WORD.findall(normalized))
    if "鱼" in normalized or words.intersection(_AQUATIC_TERMS):
        return None
    for family, aliases in _FAMILY_ALIASES:
        if normalized in aliases:
            return family
        if family == "land_animal_meat" and "meat" in words:
            return family
        if (
            family == "land_animal_meat"
            and words.intersection(_ANIMAL_MEAT_WORDS)
            and not words.intersection(_NONMEAT_ANIMAL_PRODUCTS)
        ):
            return family
        if family == "prepared_soy" and words.intersection(aliases):
            return family
    if (
        normalized.endswith(_CHINESE_LAND_ANIMAL_MEAT_ENDING)
        and "鱼" not in normalized
    ):
        return "land_animal_meat"
    return None


def classify_catalog_family(item: CatalogItem) -> str | None:
    """Classify catalog rows from their bilingual labels and game type."""

    if item.type.casefold() == _FISH_TYPE.casefold() or item.category == _FISH_CATEGORY:
        return "fish"
    labels = (item.display_name_en, item.display_name_zh, *item.aliases)
    families = {family for label in labels if (family := classify_ingredient_family(label))}
    return next(iter(families)) if len(families) == 1 else None


def catalog_family_item_ids(catalog_items: tuple[CatalogItem, ...], family: str) -> tuple[str, ...]:
    """Return stable catalog IDs classified into ``family``."""

    return tuple(
        item.item_id
        for item in catalog_items
        if classify_catalog_family(item) == family
    )
