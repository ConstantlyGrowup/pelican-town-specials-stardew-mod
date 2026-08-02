from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum
from math import isfinite
from typing import Any, NoReturn
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

SafeScalar = str | int | float | bool | None


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )


class DraftMode(str, Enum):
    ASK_GUS = "ASK_GUS"
    BLUEPRINT = "BLUEPRINT"


class GenerationStage(str, Enum):
    INPUT_VALIDATION = "INPUT_VALIDATION"
    DISH_ANALYSIS = "DISH_ANALYSIS"
    GAMEPLAY_DESIGN = "GAMEPLAY_DESIGN"
    INGREDIENT_MAPPING = "INGREDIENT_MAPPING"
    VISUAL_BRIEF = "VISUAL_BRIEF"
    ICON_GENERATION_AND_NORMALIZATION = "ICON_GENERATION_AND_NORMALIZATION"
    PREVIEW_ART_GENERATION_AND_COMPOSITION = "PREVIEW_ART_GENERATION_AND_COMPOSITION"
    RESULT_VALIDATION = "RESULT_VALIDATION"
    ATOMIC_PROMOTION = "ATOMIC_PROMOTION"







class ImmutableList[T](list[T]):
    def _raise_immutable(self, *_args: Any, **_kwargs: Any) -> NoReturn:
        raise TypeError("collection is immutable")

    def __deepcopy__(self, memo: dict[int, Any]) -> ImmutableList[T]:
        copied = ImmutableList(deepcopy(list(self), memo))
        memo[id(self)] = copied
        return copied

    def __setitem__(self, _index: int | slice, _value: T | Iterable[T]) -> None:  # type: ignore[override]
        self._raise_immutable()

    def __delitem__(self, _index: int | slice) -> None:  # type: ignore[override]
        self._raise_immutable()

    def append(self, _item: T) -> None:
        self._raise_immutable()

    def clear(self) -> None:
        self._raise_immutable()

    def extend(self, _items: Iterable[T]) -> None:
        self._raise_immutable()

    def insert(self, _index: int, _item: T) -> None:  # type: ignore[override]
        self._raise_immutable()

    def pop(self, _index: int = -1) -> T:  # type: ignore[override]
        self._raise_immutable()

    def remove(self, _item: T) -> None:
        self._raise_immutable()

    def reverse(self) -> None:
        self._raise_immutable()

    def sort(self, *, key: Any = None, reverse: bool = False) -> None:
        self._raise_immutable()

    def __iadd__(self, _items: Iterable[T]) -> ImmutableList[T]:  # type: ignore[override, misc]
        self._raise_immutable()

    def __imul__(self, _count: int) -> ImmutableList[T]:  # type: ignore[override, misc]
        self._raise_immutable()


class ImmutableDict[K, V](dict[K, V]):
    def __deepcopy__(self, memo: dict[int, Any]) -> ImmutableDict[K, V]:
        copied = ImmutableDict(deepcopy(dict(self), memo))
        memo[id(self)] = copied
        return copied

    def __setitem__(self, _key: K, _value: V) -> None:
        raise TypeError("collection is immutable")

    def __delitem__(self, _key: K) -> None:
        raise TypeError("collection is immutable")

    def clear(self) -> None:
        raise TypeError("collection is immutable")

    def pop(self, _key: K, _default: Any = None) -> V:
        raise TypeError("collection is immutable")

    def popitem(self) -> tuple[K, V]:
        raise TypeError("collection is immutable")

    def setdefault(self, _key: K, _default: V | None = None) -> V:
        raise TypeError("collection is immutable")

    def update(  # type: ignore[override]
        self,
        _other: Mapping[K, V] | Iterable[tuple[K, V]] = (),
        **_kwargs: V,
    ) -> None:
        raise TypeError("collection is immutable")

    def __ior__(self, _other: Mapping[K, V]) -> ImmutableDict[K, V]:  # type: ignore[override, misc]
        raise TypeError("collection is immutable")


class Language(str, Enum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_uuid4(value: UUID) -> UUID:
    if value.version != 4:
        raise ValueError("UUID must be version 4")
    return value


def ensure_safe_details(details: Mapping[str, Any] | None) -> dict[str, SafeScalar]:
    if details is None:
        return {}
    safe_details: dict[str, SafeScalar] = {}
    for key, value in details.items():
        if not isinstance(key, str):
            raise TypeError("detail keys must be strings")
        if value is None or isinstance(value, (str, int, bool)):
            safe_details[key] = value
            continue
        if isinstance(value, float):
            if not isfinite(value):
                raise TypeError("detail values must be finite")
            safe_details[key] = value
            continue
        raise TypeError("detail values must be scalar")
    return safe_details
