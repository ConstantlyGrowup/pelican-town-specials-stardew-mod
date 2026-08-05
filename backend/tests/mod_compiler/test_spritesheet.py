"""Spritesheet composition tests (design 14.6, plan Task 16 Step 5)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from pelican_town_specials.mod_compiler.spritesheet import build_spritesheet
from pelican_town_specials.persistence.asset_store import FileAssetStore

from .conftest import (
    archive_dish,
    archive_from_doc,
    content_hash_of,
    load_archive_doc,
    put_icon,
)


def test_spritesheet_is_deterministic_sorted_and_rgba(
    asset_store: FileAssetStore,
) -> None:
    dishes = [
        archive_dish("ask-gus-dish", asset_store),
        archive_dish("blueprint-dish", asset_store),
    ]

    first, first_indices = build_spritesheet(dishes, asset_store)
    second, second_indices = build_spritesheet(dishes, asset_store)

    assert first == second
    assert first_indices == second_indices
    # Sorted by (internalName, dishId): ParsnipSoup before TomatoStew.
    assert first_indices == {"ParsnipSoup": 0, "TomatoStew": 1}

    image = Image.open(io.BytesIO(first))
    assert image.mode == "RGBA"
    assert image.size == (256, 16)


def test_spritesheet_orders_by_internal_name_regardless_of_input_order(
    asset_store: FileAssetStore,
) -> None:
    dishes = [
        archive_dish("ask-gus-dish", asset_store),
        archive_dish("blueprint-dish", asset_store),
    ]
    # Reverse the input order: the sort key must win.
    _, indices = build_spritesheet(list(reversed(dishes)), asset_store)

    assert indices == {"ParsnipSoup": 0, "TomatoStew": 1}


def test_spritesheet_rejects_non_16x16_icon(asset_store: FileAssetStore) -> None:
    doc = load_archive_doc("ask-gus-dish")
    doc["visuals"]["icon16AssetId"] = str(put_icon(asset_store, size=32))
    doc["contentHash"] = content_hash_of(doc)
    dish = archive_from_doc(doc)

    with pytest.raises(ValueError):
        build_spritesheet([dish], asset_store)


def test_spritesheet_rejects_missing_icon(asset_store: FileAssetStore) -> None:
    doc = load_archive_doc("ask-gus-dish")
    doc["visuals"]["icon16AssetId"] = None
    doc["contentHash"] = content_hash_of(doc)
    dish = archive_from_doc(doc)

    with pytest.raises(ValueError):
        build_spritesheet([dish], asset_store)


def test_spritesheet_rejects_unregistered_icon(asset_store: FileAssetStore) -> None:
    doc = load_archive_doc("blueprint-dish")
    doc["visuals"]["icon16AssetId"] = "deadbeef-dead-4ead-8ead-deadbeefdead"
    doc["contentHash"] = content_hash_of(doc)
    missing = archive_from_doc(doc)

    with pytest.raises(ValueError):
        build_spritesheet([missing], asset_store)
