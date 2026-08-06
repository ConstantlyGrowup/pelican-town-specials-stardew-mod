"""Manifest, content, i18n and README templates for Content Patcher packs.

All templates are built from plain data structures and serialized by the
compiler with a fixed canonical JSON writer; nothing is string-built JSON.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.dish import BuffSpec

from .ids import build_mod_id, derive_ids
from .recipes import build_recipe_value

OBJECT_TYPE = "Cooking"
OBJECT_CATEGORY = -7
OBJECT_TEXTURE = "Mods/{{ModId}}/Objects"
CONTENT_PATCHER_FORMAT = "2.9.0"
MINIMUM_GAME_VERSION = "1.6.15"

# Domain BuffAttributes fields mapped to Stardew 1.6 attribute names.
BUFF_ATTRIBUTE_NAMES: tuple[tuple[str, str], ...] = (
    ("farming_level", "FarmingLevel"),
    ("fishing_level", "FishingLevel"),
    ("mining_level", "MiningLevel"),
    ("foraging_level", "ForagingLevel"),
    ("combat_level", "CombatLevel"),
    ("luck_level", "LuckLevel"),
    ("attack", "Attack"),
    ("defense", "Defense"),
    ("immunity", "Immunity"),
    ("magnetic_radius", "MagneticRadius"),
    ("max_stamina", "MaxStamina"),
    ("speed", "Speed"),
)

# All CustomAttributes keys the vanilla game writes, in the exact order and
# float shape observed in Data/Objects (stardew-1.6.15 Objects.json). The
# game accepts omitted keys, but mirroring the vanilla document keeps the
# compiled pack byte-comparable with official data.
VANILLA_BUFF_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "CombatLevel",
    "FarmingLevel",
    "FishingLevel",
    "MiningLevel",
    "LuckLevel",
    "ForagingLevel",
    "MaxStamina",
    "MagneticRadius",
    "Speed",
    "Defense",
    "Attack",
    "AttackMultiplier",
    "Immunity",
    "KnockbackMultiplier",
    "WeaponSpeedMultiplier",
    "CriticalChanceMultiplier",
    "CriticalPowerMultiplier",
    "WeaponPrecisionMultiplier",
)

README_TEXT = """Pelican Town Specials - Content Pack
===================================

This folder is a Content Patcher content pack for Stardew Valley 1.6.

Installation:
1. Install SMAPI and Content Patcher 2.9.0 or newer.
2. Copy or extract this folder into your Stardew Valley Mods directory.
3. Start the game through SMAPI.

The pack adds the cooking recipes and dishes created with Pelican Town
Specials. Removing the folder from your Mods directory uninstalls it.
"""


def build_manifest(
    *,
    author_name: str,
    pack_slug: str,
    version: str,
    description: str,
) -> dict[str, Any]:
    """Build the manifest.json document (design 14.4)."""
    return {
        "Name": f"Pelican Town Specials - {pack_slug}",
        "Author": author_name,
        "Version": version,
        "Description": description,
        "UniqueID": build_mod_id(author_name=author_name, pack_slug=pack_slug),
        "MinimumGameVersion": MINIMUM_GAME_VERSION,
        "UpdateKeys": [],
        "ContentPackFor": {
            "UniqueID": "Pathoschild.ContentPatcher",
            "MinimumVersion": "2.9.0",
        },
    }


def build_content(
    *,
    author_name: str,
    pack_slug: str,
    dishes: list[ArchivedDish],
    sprite_indices: Mapping[str, int],
) -> dict[str, Any]:
    """Build the content.json document (design 14.5 with the Task 16 rulings).

    Change order is fixed: Load spritesheet, EditData Data/Objects,
    EditData Data/CookingRecipes. Buffs are embedded in each Data/Objects
    entry's ``Buffs`` array in the vanilla 1.6 shape (R13 fix: the game
    ignores the previously emitted ``Data/Objects.Buffs`` patch because no
    such asset exists).
    """
    ordered = sorted(dishes, key=_content_order_key)
    object_entries: dict[str, Any] = {}
    recipe_entries: dict[str, Any] = {}

    for dish in ordered:
        internal_name = dish.presentation.internal_name
        ids = derive_ids(
            author_name=author_name,
            pack_slug=pack_slug,
            internal_name=internal_name,
        )
        object_entries[ids.item_id] = _object_entry(dish, ids.item_id, sprite_indices[internal_name])
        recipe_entries[ids.item_id] = build_recipe_value(
            ingredients=list(dish.gameplay.ingredients),
            item_id=ids.item_id,
            display_token=f"{{{{i18n:recipe.{internal_name}.name}}}}",
        )

    changes: list[dict[str, Any]] = [
        {
            "Action": "Load",
            "Target": "Mods/{{ModId}}/Objects",
            "FromFile": "assets/objects.png",
        },
        {"Action": "EditData", "Target": "Data/Objects", "Entries": object_entries},
        {
            "Action": "EditData",
            "Target": "Data/CookingRecipes",
            "Entries": recipe_entries,
        },
    ]
    return {"Format": CONTENT_PATCHER_FORMAT, "Changes": changes}


def build_i18n(dishes: list[ArchivedDish]) -> dict[str, Any]:
    """Build the i18n documents; keys always use internal names.

    Both default.json and zh.json carry the same content (ruling R16-4);
    the compiler writes this document to both files.
    """
    i18n: dict[str, Any] = {}
    for dish in sorted(dishes, key=_content_order_key):
        internal_name = dish.presentation.internal_name
        i18n[f"item.{internal_name}.name"] = dish.presentation.display_name
        i18n[f"item.{internal_name}.description"] = dish.presentation.description
        i18n[f"recipe.{internal_name}.name"] = dish.presentation.display_name
    return i18n


def _content_order_key(dish: ArchivedDish) -> tuple[str, str]:
    return (dish.presentation.internal_name, str(dish.dish_id))


def _object_entry(dish: ArchivedDish, item_id: str, sprite_index: int) -> dict[str, Any]:
    internal_name = dish.presentation.internal_name
    entry: dict[str, Any] = {
        "Name": internal_name,
        "DisplayName": f"{{{{i18n:item.{internal_name}.name}}}}",
        "Description": f"{{{{i18n:item.{internal_name}.description}}}}",
        "Type": OBJECT_TYPE,
        "Category": OBJECT_CATEGORY,
        "Price": dish.gameplay.sell_price,
        "Texture": OBJECT_TEXTURE,
        "SpriteIndex": sprite_index,
        "Edibility": dish.gameplay.recovery.edibility,
        "IsDrink": dish.gameplay.is_drink,
    }
    if dish.gameplay.buff is not None:
        entry["Buffs"] = [
            _inline_buff(dish.gameplay.buff, is_drink=dish.gameplay.is_drink)
        ]
    return entry


def _inline_buff(buff: BuffSpec, *, is_drink: bool) -> dict[str, Any]:
    """Build one vanilla-shaped Buffs entry embedded in a Data/Objects item.

    Mirrors the Stardew 1.6.15 Data/Objects format: ``Id`` is the Food/Drink
    category string, ``Duration`` is in game minutes (identical to the domain
    ``duration_minutes``), and ``CustomAttributes`` is a full-key float object.
    """
    attributes = {key: 0.0 for key in VANILLA_BUFF_ATTRIBUTE_KEYS}
    for field_name, game_name in BUFF_ATTRIBUTE_NAMES:
        value = getattr(buff.attributes, field_name)
        if value != 0:
            attributes[game_name] = float(value)
    return {
        "Id": "Drink" if is_drink else "Food",
        "BuffId": None,
        "IconTexture": None,
        "IconSpriteIndex": 0,
        "Duration": buff.duration_minutes,
        "IsDebuff": buff.is_debuff,
        "GlowColor": None,
        "CustomAttributes": attributes,
        "CustomFields": None,
    }
