"""Deterministic 16x16 RGBA spritesheet composition.

Dishes are ordered by ``(internalName, dishId)``; icons are laid out with
16 cells per row. The same archive content always produces the same pixels.
"""

from __future__ import annotations

import io

from PIL import Image

from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.persistence.asset_store import (
    AssetNotFoundError,
    FileAssetStore,
)

ICON_SIZE = 16
ICONS_PER_ROW = 16

type SpriteIndices = dict[str, int]


def build_spritesheet(
    dishes: list[ArchivedDish],
    asset_store: FileAssetStore,
) -> tuple[bytes, SpriteIndices]:
    """Compose the pack spritesheet and return PNG bytes plus sprite indices."""
    ordered = sorted(dishes, key=_dish_order_key)
    columns = ICONS_PER_ROW
    rows = (len(ordered) + columns - 1) // columns
    canvas = Image.new(
        "RGBA",
        (columns * ICON_SIZE, max(rows, 1) * ICON_SIZE),
        (0, 0, 0, 0),
    )
    indices: dict[str, int] = {}
    for index, dish in enumerate(ordered):
        icon = _load_icon_16(dish, asset_store)
        row = index // columns
        column = index % columns
        canvas.paste(icon, (column * ICON_SIZE, row * ICON_SIZE))
        indices[dish.presentation.internal_name] = index

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue(), indices


def _dish_order_key(dish: ArchivedDish) -> tuple[str, str]:
    return (dish.presentation.internal_name, str(dish.dish_id))


def _load_icon_16(dish: ArchivedDish, asset_store: FileAssetStore) -> Image.Image:
    icon_asset_id = dish.visuals.icon_16_asset_id
    if icon_asset_id is None:
        raise ValueError(f"dish {dish.dish_id} has no icon16 asset")
    try:
        stored = asset_store.stat(icon_asset_id)
    except AssetNotFoundError as exc:
        raise ValueError(f"icon16 asset {icon_asset_id} is not registered") from exc
    try:
        with asset_store.open(stored) as handle:
            image = Image.open(handle)
            image.load()
    except (OSError, ValueError) as exc:
        raise ValueError(f"icon16 asset {icon_asset_id} is unreadable") from exc
    if image.mode != "RGBA":
        raise ValueError(f"icon16 asset {icon_asset_id} must be RGBA")
    if image.size != (ICON_SIZE, ICON_SIZE):
        raise ValueError(f"icon16 asset {icon_asset_id} must be {ICON_SIZE}x{ICON_SIZE}")
    return image
