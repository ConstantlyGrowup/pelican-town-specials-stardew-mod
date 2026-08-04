"""Curated dish category and tag options for the Blueprint editor."""

from __future__ import annotations

from pydantic import Field

from pelican_town_specials.domain.common import StrictModel
from pelican_town_specials.domain.errors import AppError

from .common import Page

DISH_CATEGORIES = (
    "主菜",
    "汤类",
    "小吃",
    "甜品",
    "饮品",
    "早餐",
    "沙拉",
    "主食",
    "配菜",
    "节日大餐",
)

DISH_TAGS = (
    "家常",
    "清淡",
    "香辣",
    "酸甜",
    "咸鲜",
    "浓郁",
    "清爽",
    "暖胃",
    "节日",
    "春夏",
    "秋冬",
    "面食",
    "米饭",
    "素食",
    "鱼肉",
    "禽蛋",
    "奶香",
)


class MetaOption(StrictModel):
    value: str = Field(min_length=1, max_length=40)

    @classmethod
    def from_str(cls, value: str) -> MetaOption:
        return cls(value=value)


class MetaService:
    def list_categories(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
    ) -> Page[MetaOption]:
        return self._page(DISH_CATEGORIES, query, limit, offset)

    def list_tags(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
    ) -> Page[MetaOption]:
        return self._page(DISH_TAGS, query, limit, offset)

    @staticmethod
    def _page(
        options: tuple[str, ...],
        query: str,
        limit: int,
        offset: int,
    ) -> Page[MetaOption]:
        if not 1 <= limit <= 100:
            raise MetaService._limit_invalid_error()
        if offset < 0:
            raise MetaService._offset_invalid_error()
        normalized = query.strip().lower()
        filtered = [option for option in options if normalized in option.lower()]
        if not normalized:
            filtered = list(options)
        items = [
            MetaOption.from_str(option) for option in filtered[offset : offset + limit]
        ]
        return Page(items=items, nextCursor=None, total=len(filtered))

    @staticmethod
    def _limit_invalid_error() -> AppError:
        return AppError(
            code="PTS_INPUT_META_LIMIT_INVALID",
            message="meta limit 必须在 1 到 100 之间。",
            http_status=422,
            details={},
            retryable=False,
        )

    @staticmethod
    def _offset_invalid_error() -> AppError:
        return AppError(
            code="PTS_INPUT_META_OFFSET_INVALID",
            message="meta offset 必须是非负整数。",
            http_status=422,
            details={},
            retryable=False,
        )
