"""Manifest, content, i18n and README templates for Content Patcher packs.

All templates are built from plain data structures and serialized by the
compiler with a fixed canonical JSON writer; nothing is string-built JSON.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pelican_town_specials.domain.archive import ArchivedDish

from .ids import build_mod_id, derive_ids, sanitize_token
from .recipes import build_recipe_value

OBJECT_TYPE = "Cooking"
OBJECT_CATEGORY = -7
OBJECT_TEXTURE = "Mods/{{ModId}}/Objects"
CONTENT_PATCHER_FORMAT = "2.9.0"
MINIMUM_GAME_VERSION = "1.6.15"

# Buff CustomAttributes in stable declaration order (Stardew 1.6 attribute
# names mapped to their BuffAttributes fields).
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
    EditData Data/CookingRecipes, then EditData Data/Objects.Buffs only
    when at least one dish carries a buff (ruling R16-3).
    """
    ordered = sorted(dishes, key=_content_order_key)
    object_entries: dict[str, Any] = {}
    recipe_entries: dict[str, Any] = {}
    buff_entries: dict[str, Any] = {}

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
        buff_entry = _buff_entry(dish, ids.item_id)
        if buff_entry is not None:
            buff_entries[ids.item_id] = buff_entry

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
    if buff_entries:
        changes.append(
            {"Action": "EditData", "Target": "Data/Objects.Buffs", "Entries": buff_entries}
        )
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
    return {
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


def _buff_entry(dish: ArchivedDish, item_id: str) -> dict[str, Any] | None:
    buff = dish.gameplay.buff
    if buff is None:
        return None
    custom_attributes = ", ".join(
        f"{game_name} {getattr(buff.attributes, field_name)}"
        for field_name, game_name in BUFF_ATTRIBUTE_NAMES
        if getattr(buff.attributes, field_name) != 0
    )
    return {
        "Id": f"{item_id}_{sanitize_token(buff.id)}",
        "Duration": buff.duration_minutes * 60_000,
        "IsDebuff": buff.is_debuff,
        "CustomAttributes": custom_attributes,
    }
