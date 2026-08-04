"""Task refinement: curated dish category/tag option tests."""

from __future__ import annotations

import pytest

from pelican_town_specials.application.meta import MetaService
from pelican_town_specials.domain.errors import AppError


def test_list_categories_returns_curated_options() -> None:
    page = MetaService().list_categories(query="", limit=20, offset=0)

    assert page.total >= 5
    assert page.items
    assert any(item.value == "主菜" for item in page.items)


def test_list_categories_filters_by_query() -> None:
    page = MetaService().list_categories(query="汤", limit=20, offset=0)

    assert page.items
    assert all("汤" in item.value for item in page.items)


def test_list_tags_returns_curated_options() -> None:
    page = MetaService().list_tags(query="", limit=20, offset=0)

    assert page.total >= 5
    assert all(item.value for item in page.items)


def test_meta_rejects_invalid_params() -> None:
    with pytest.raises(AppError) as limit_error:
        MetaService().list_categories(query="", limit=0, offset=0)
    assert limit_error.value.code == "PTS_INPUT_META_LIMIT_INVALID"

    with pytest.raises(AppError) as offset_error:
        MetaService().list_tags(query="", limit=10, offset=-1)
    assert offset_error.value.code == "PTS_INPUT_META_OFFSET_INVALID"
