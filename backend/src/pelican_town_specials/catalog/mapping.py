"""Safe conversion from semantic ingredient candidates to domain ingredients."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

from pelican_town_specials.domain.dish import GameIngredient, SemanticIngredient
from pelican_town_specials.domain.errors import AppError

from .models import CatalogCandidate, CatalogItem
from .repository import VanillaCatalog


def map_ingredient(
    semantic: SemanticIngredient,
    candidates: Sequence[CatalogCandidate],
    catalog: VanillaCatalog,
) -> GameIngredient:
    """Map one semantic ingredient using only validated catalog candidates."""

    del semantic
    if not candidates:
        raise _mapping_error(
            "PTS_VALIDATION_INGREDIENT_CANDIDATES_EMPTY",
            "ingredient candidate list is empty",
        )

    resolved: list[tuple[CatalogCandidate, CatalogItem]] = []
    for candidate in candidates:
        if not isinstance(candidate, CatalogCandidate) or not isfinite(candidate.score):
            raise _mapping_error(
                "PTS_VALIDATION_INGREDIENT_CANDIDATE_INVALID",
                "ingredient candidate is invalid",
            )
        try:
            item = catalog.require(candidate.item_id)
        except AppError as exc:
            if exc.code == "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN":
                raise _mapping_error(
                    "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN",
                    "ingredient candidate is not present in the vanilla catalog",
                ) from exc
            raise
        resolved.append((candidate, item))

    usable = [pair for pair in resolved if pair[1].usable_as_ingredient]
    if not usable:
        raise _mapping_error(
            "PTS_VALIDATION_INGREDIENT_NOT_USABLE",
            "no candidate is usable as an ingredient",
        )

    candidate, item = min(
        usable,
        key=lambda pair: (-pair[0].score, _item_id_sort_key(pair[0].item_id)),
    )
    del candidate
    return GameIngredient(
        itemId=item.item_id,
        displayName=item.display_name_en,
        quantity=1,
        mappingReason="selected validated vanilla candidate",
        catalogVersion=catalog.version,
    )


def _item_id_sort_key(item_id: str) -> tuple[int, object]:
    if item_id.lstrip("-").isdigit():
        return (0, int(item_id))
    return (1, item_id)


def _mapping_error(code: str, message: str) -> AppError:
    return AppError(
        code=code,
        message=f"{code}: {message}",
        http_status=422,
        details={},
        retryable=False,
    )
