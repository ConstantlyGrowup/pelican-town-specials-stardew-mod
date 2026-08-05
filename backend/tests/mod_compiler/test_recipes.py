"""Stardew 1.6 Data/CookingRecipes value codec tests (plan Task 16 Step 1)."""

from __future__ import annotations

from pelican_town_specials.domain.dish import GameIngredient
from pelican_town_specials.mod_compiler.recipes import build_recipe_value


def _ingredient(item_id: str, quantity: int = 1) -> GameIngredient:
    return GameIngredient(
        itemId=item_id,
        displayName="model supplied text must not be trusted",
        quantity=quantity,
        mappingReason="fixture",
        catalogVersion="stardew-1.6.15-v1",
    )


def test_default_recipe_value() -> None:
    value = build_recipe_value(
        ingredients=[_ingredient("24")],
        item_id="{{ModId}}_ParsnipSoup",
        display_token="{{i18n:recipe.ParsnipSoup.name}}",
    )
    assert (
        value
        == "24 1/0 0/{{ModId}}_ParsnipSoup/default/{{i18n:recipe.ParsnipSoup.name}}"
    )


def test_ingredient_pairs_are_sorted_by_item_id() -> None:
    value = build_recipe_value(
        ingredients=[_ingredient("256", quantity=2), _ingredient("24", quantity=1)],
        item_id="{{ModId}}_TomatoStew",
        display_token="{{i18n:recipe.TomatoStew.name}}",
    )
    assert (
        value
        == "24 1 256 2/0 0/{{ModId}}_TomatoStew/default/{{i18n:recipe.TomatoStew.name}}"
    )


def test_recipe_value_uses_namespaced_product_and_default_unlock() -> None:
    value = build_recipe_value(
        ingredients=[_ingredient("24", quantity=3)],
        item_id="{{ModId}}_ParsnipSoup",
        display_token="{{i18n:recipe.ParsnipSoup.name}}",
    )
    assert "/default/" in value
    assert value.startswith("24 3/0 0/{{ModId}}_ParsnipSoup/")


def test_recipe_value_preserves_display_token_verbatim() -> None:
    token = "{{i18n:recipe.ParsnipSoup.name}}"
    value = build_recipe_value(
        ingredients=[_ingredient("24")],
        item_id="{{ModId}}_ParsnipSoup",
        display_token=token,
    )
    assert value.endswith(f"/{token}")
