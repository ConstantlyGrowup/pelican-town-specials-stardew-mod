"""Stardew 1.6 ``Data/CookingRecipes`` value codec.

The recipe value format is ``ingredients/unused fields/product/unlock/display``
where ingredients are ``<itemId> <quantity>`` pairs. Pairs are sorted by
itemId so the emitted value is stable for the same snapshot.
"""

from __future__ import annotations

from pelican_town_specials.domain.dish import GameIngredient

UNUSED_FIELDS = "0 0"
DEFAULT_UNLOCK = "default"


def build_recipe_value(
    *,
    ingredients: list[GameIngredient],
    item_id: str,
    display_token: str,
) -> str:
    """Build a deterministic 1.6 CookingRecipes value for one dish."""
    pairs = " ".join(
        f"{ingredient.item_id} {ingredient.quantity}"
        for ingredient in sorted(ingredients, key=lambda ingredient: ingredient.item_id)
    )
    return f"{pairs}/{UNUSED_FIELDS}/{item_id}/{DEFAULT_UNLOCK}/{display_token}"
