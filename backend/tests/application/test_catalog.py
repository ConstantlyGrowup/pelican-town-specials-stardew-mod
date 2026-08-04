"""Task 10 catalog search use-case tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pelican_town_specials.application.catalog import CatalogService
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.errors import AppError

_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


def _service() -> CatalogService:
    return CatalogService(VanillaCatalog.from_json(_CATALOG_PATH))


def test_search_ingredients_returns_public_projection() -> None:
    result = _service().search_ingredients("tomat", 10)

    assert result.catalog_version == "stardew-1.6.15-v1"
    assert result.items
    item = result.items[0]
    assert item.item_id
    assert item.display_name_en
    assert item.display_name_zh
    serialized = item.model_dump(by_alias=True)
    assert set(serialized) == {"itemId", "displayNameEn", "displayNameZh"}


def test_search_ingredients_browses_all_when_query_empty() -> None:
    service = _service()
    first = service.search_ingredients("   ", 10, offset=0)
    second = service.search_ingredients("   ", 10, offset=10)

    assert first.total >= 100
    assert len(first.items) == 10
    assert all(item.item_id for item in first.items)
    assert first.items[0].item_id != second.items[0].item_id
    assert second.total == first.total


def test_search_ingredients_rejects_invalid_limit() -> None:
    with pytest.raises(AppError) as excinfo:
        _service().search_ingredients("tomat", 0)
    assert excinfo.value.code == "PTS_INPUT_CATALOG_LIMIT_INVALID"

    with pytest.raises(AppError) as excinfo:
        _service().search_ingredients("tomat", 101)
    assert excinfo.value.code == "PTS_INPUT_CATALOG_LIMIT_INVALID"


def test_search_ingredients_rejects_invalid_offset() -> None:
    with pytest.raises(AppError) as excinfo:
        _service().search_ingredients("tomat", 10, offset=-1)
    assert excinfo.value.code == "PTS_INPUT_CATALOG_OFFSET_INVALID"
