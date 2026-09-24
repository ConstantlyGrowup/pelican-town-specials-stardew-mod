"""Deterministic lexical + local E5 retrieval with guarded lazy loading."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Protocol

import numpy as np

from pelican_town_specials.catalog.models import CatalogCandidate, CatalogItem
from pelican_town_specials.catalog.repository import VanillaCatalog

from . import constants
from .encoder import OnnxE5Encoder
from .errors import IngredientRagNoMatch, IngredientRagUnavailable
from .index import StaticIngredientIndex, load_static_index
from .resources import catalog_resource_path, ingredient_rag_resource_dir
from .semantic_types import classify_catalog_family, classify_ingredient_family


class _TextEncoder(Protocol):
    def encode(self, text: str) -> np.ndarray: ...


@dataclass(frozen=True, slots=True)
class IngredientRetrievalEvidence:
    """Auditable retrieval signals kept separate from the mapper rank score."""

    candidates: tuple[CatalogCandidate, ...]
    semantic_hits: tuple[tuple[str, float], ...]
    lexical_item_ids: tuple[str, ...]
    exact_item_ids: tuple[str, ...]


class IngredientRagRetriever:
    """Lazily load and safely disable local RAG after the first failure."""

    __slots__ = (
        "_catalog",
        "_catalog_path",
        "_disabled_reason",
        "_encoder",
        "_index",
        "_lock",
        "_resource_dir",
    )

    def __init__(
        self,
        catalog: VanillaCatalog,
        *,
        catalog_path: Path | None = None,
        resource_dir: Path | None = None,
        encoder: _TextEncoder | None = None,
        index: StaticIngredientIndex | None = None,
    ) -> None:
        self._catalog = catalog
        self._catalog_path = catalog_path or catalog_resource_path()
        self._resource_dir = resource_dir or ingredient_rag_resource_dir()
        self._disabled_reason: str | None = None
        self._encoder = encoder
        self._index = index
        self._lock = RLock()

    @property
    def disabled_reason(self) -> str | None:
        return self._disabled_reason

    def retrieve(
        self,
        query: str,
        *,
        used_item_ids: frozenset[str] = frozenset(),
    ) -> list[CatalogCandidate]:
        return list(
            self.retrieve_with_evidence(query, used_item_ids=used_item_ids).candidates
        )

    def retrieve_with_evidence(
        self,
        query: str,
        *,
        used_item_ids: frozenset[str] = frozenset(),
    ) -> IngredientRetrievalEvidence:
        """Return the production ranking plus raw lexical/cosine evidence."""
        with self._lock:
            if self._disabled_reason is not None:
                raise IngredientRagUnavailable(self._disabled_reason)
            try:
                self._ensure_loaded()
            except IngredientRagUnavailable as exc:
                self._disabled_reason = exc.reason_code
                raise
            except Exception as exc:
                self._disabled_reason = "rag_model_unavailable"
                raise IngredientRagUnavailable(self._disabled_reason) from exc

            assert self._index is not None
            assert self._encoder is not None
            try:
                evidence = rank_candidate_evidence(
                    query,
                    self._catalog,
                    self._index,
                    self._encoder.encode,
                    used_item_ids=used_item_ids,
                )
                self._verify_catalog_semantic_support(query, evidence)
                return evidence
            except IngredientRagNoMatch:
                raise
            except IngredientRagUnavailable as exc:
                self._disabled_reason = exc.reason_code
                raise
            except Exception as exc:
                self._disabled_reason = "rag_query_failed"
                raise IngredientRagUnavailable(self._disabled_reason) from exc

    def _verify_catalog_semantic_support(
        self,
        query: str,
        evidence: IngredientRetrievalEvidence,
    ) -> None:
        """Reject only when an explicit local ontology proves the family absent."""
        semantic_family = classify_ingredient_family(query)
        if semantic_family is None:
            return
        supported_ids = tuple(
            item.item_id
            for item in self._catalog.ingredients
            if classify_catalog_family(item) == semantic_family
        )
        if supported_ids:
            return
        raise IngredientRagNoMatch(
            semantic_family=semantic_family,
            evidence=evidence,
        )

    def _ensure_loaded(self) -> None:
        if self._index is not None and self._encoder is not None:
            return
        resource_dir = self._resource_dir
        try:
            self._index = load_static_index(
                catalog=self._catalog,
                catalog_path=self._catalog_path,
                manifest_path=resource_dir / constants.MANIFEST_FILE_NAME,
                vector_path=resource_dir / constants.VECTOR_FILE_NAME,
                model_path=resource_dir / constants.MODEL_FILE_NAME,
                tokenizer_path=resource_dir / constants.TOKENIZER_FILE_NAME,
            )
        except Exception as exc:
            raise IngredientRagUnavailable("rag_index_invalid") from exc
        if self._encoder is None:
            self._encoder = OnnxE5Encoder(
                model_path=resource_dir / constants.MODEL_FILE_NAME,
                tokenizer_path=resource_dir / constants.TOKENIZER_FILE_NAME,
            )


def rank_candidates(
    query: str,
    catalog: VanillaCatalog,
    index: StaticIngredientIndex,
    encode_query: Callable[[str], np.ndarray],
    *,
    used_item_ids: frozenset[str] = frozenset(),
) -> list[CatalogCandidate]:
    """Fuse the catalog's lexical order and exact E5 cosine Top 5."""
    return list(
        rank_candidate_evidence(
            query,
            catalog,
            index,
            encode_query,
            used_item_ids=used_item_ids,
        ).candidates
    )


def rank_candidate_evidence(
    query: str,
    catalog: VanillaCatalog,
    index: StaticIngredientIndex,
    encode_query: Callable[[str], np.ndarray],
    *,
    used_item_ids: frozenset[str] = frozenset(),
) -> IngredientRetrievalEvidence:
    """Fuse candidates while retaining original E5 and lexical evidence."""
    normalized_query = normalize_ingredient_name(query)
    if not normalized_query:
        return IngredientRetrievalEvidence((), (), (), ())
    query_vector = encode_query(f"{constants.QUERY_PREFIX}{normalized_query}")
    semantic_hits = index.search(
        query_vector,
        top_k=constants.TOP_K,
        excluded_item_ids=used_item_ids,
    )
    lexical_items = catalog.search_ingredients(normalized_query, limit=100)
    exact_ids = {
        item.item_id
        for item in catalog.ingredients
        if _is_exact_name_or_alias(item, normalized_query)
    }
    lexical_item_ids = tuple(item.item_id for item in lexical_items)
    unique_exact_id = next(iter(exact_ids)) if len(exact_ids) == 1 else None
    lexical_rank = {item.item_id: rank for rank, item in enumerate(lexical_items)}
    semantic_score = {item_id: score for item_id, score in semantic_hits}
    candidate_ids = set(lexical_rank) | set(semantic_score)
    candidate_ids.difference_update(used_item_ids)

    items: dict[str, CatalogItem] = {}
    for item_id in candidate_ids:
        try:
            item = catalog.require(item_id)
        except Exception as exc:
            raise IngredientRagUnavailable("rag_index_invalid") from exc
        if item.usable_as_ingredient and not item.is_category:
            items[item_id] = item

    def rank_key(item_id: str) -> tuple[int, int, float, str, tuple[int, int | str, str]]:
        item = items[item_id]
        if item_id == unique_exact_id:
            group, lexical_position = 0, 0
        elif item_id in lexical_rank:
            group, lexical_position = 1, lexical_rank[item_id]
        else:
            group, lexical_position = 2, 0
        similarity = semantic_score.get(item_id, float("-inf"))
        return (
            group,
            lexical_position,
            -similarity,
            item.category,
            _item_id_sort_key(item_id),
        )

    ordered_ids = sorted(items, key=rank_key)[: constants.TOP_K]
    candidates = tuple(
        CatalogCandidate(item_id=item_id, score=1.0 - rank / constants.TOP_K)
        for rank, item_id in enumerate(ordered_ids)
    )
    return IngredientRetrievalEvidence(
        candidates=candidates,
        semantic_hits=tuple(semantic_hits),
        lexical_item_ids=lexical_item_ids,
        exact_item_ids=tuple(sorted(exact_ids, key=_item_id_sort_key)),
    )


def normalize_ingredient_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalized.split())


def build_passage(item: CatalogItem) -> str:
    aliases = "、".join(
        dict.fromkeys(
            alias.strip() for alias in item.aliases if isinstance(alias, str) and alias.strip()
        )
    )
    return (
        f"{constants.PASSAGE_PREFIX}名称中文：{item.display_name_zh}；"
        f"名称英文：{item.display_name_en}；别名：{aliases}；"
        f"type：{item.type}；category：{item.category}"
    )


def _is_exact_name_or_alias(item: CatalogItem, normalized_query: str) -> bool:
    fields = (item.display_name_zh, item.display_name_en, *item.aliases)
    return any(normalize_ingredient_name(field) == normalized_query for field in fields)


def _item_id_sort_key(item_id: str) -> tuple[int, int | str, str]:
    try:
        return (0, int(item_id), item_id)
    except ValueError:
        return (1, item_id.casefold(), item_id)
