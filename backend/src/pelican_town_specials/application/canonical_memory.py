"""Fail-open Canonical registration for immutable Ask Gus archives."""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from collections.abc import Mapping
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.assets import AssetKind
from pelican_town_specials.domain.canonical import (
    CanonicalDishRegistration,
    CanonicalIconInput,
    CanonicalRepository,
    RecallDocument,
    RecallIngredient,
)
from pelican_town_specials.domain.common import DraftMode, Language, ensure_uuid4
from pelican_town_specials.domain.dish import DishAnalysis, GenerationSource
from pelican_town_specials.observability.logging import log_event
from pelican_town_specials.persistence.asset_store import (
    AssetNotFoundError,
    FileAssetStore,
)
from pelican_town_specials.persistence.canonical_registry import (
    CanonicalRegistryUnavailableError,
)
from pelican_town_specials.persistence.repositories import (
    ArchiveRepository,
    DraftRepository,
)

RegistrationOutcome = Literal[
    "registered",
    "usage_recorded",
    "already_registered",
    "skipped",
]


class _SkipRegistration(Exception):
    """A malformed or inapplicable archive that must not block startup."""


def normalize_recall_text(value: str) -> str:
    """Build a deterministic, local-only semantic text normalization."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    cleaned: list[str] = []
    for character in normalized:
        if character.isspace() or unicodedata.category(character).startswith("P"):
            cleaned.append(" ")
        else:
            cleaned.append(character)
    return " ".join("".join(cleaned).split())


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_recall_text(value)
    return normalized or None


def build_recall_document(analysis: DishAnalysis) -> RecallDocument:
    """Copy only analysis fields that are part of the Canonical recall contract."""

    ingredients = [
        RecallIngredient(
            name=ingredient.name,
            normalizedName=normalize_recall_text(ingredient.normalized_name),
            visibleConfidence=ingredient.visible_confidence,
            quantityHint=ingredient.quantity_hint or None,
        )
        for ingredient in analysis.semantic_ingredients
    ]
    return RecallDocument(
        recognizedDish=analysis.recognized_dish,
        normalizedName=normalize_recall_text(analysis.recognized_dish),
        summary=analysis.summary,
        cuisine=analysis.cuisine or None,
        semanticIngredients=ingredients,
        cookingMethods=list(analysis.cooking_methods),
        flavorProfile=list(analysis.flavor_profile),
    )


def _normalize_signature_value(value: object) -> object:
    if isinstance(value, str):
        return normalize_recall_text(value)
    if isinstance(value, list):
        return [_normalize_signature_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _normalize_signature_value(item)
            for key, item in value.items()
        }
    return value


def build_dish_signature(
    language: Language,
    recall_document: RecallDocument,
) -> str:
    """Hash normalized semantic content for diagnostics/grouping only."""

    payload = {
        "language": language.value,
        "recallDocument": _normalize_signature_value(
            recall_document.model_dump(by_alias=True, mode="json")
        ),
    }
    compact = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


class CanonicalRegistrationService:
    """Register archive snapshots without making Archive depend on the Registry."""

    def __init__(
        self,
        *,
        registry: CanonicalRepository,
        archive_repository: ArchiveRepository,
        draft_repository: DraftRepository,
        asset_store: FileAssetStore,
    ) -> None:
        self._registry = registry
        self._archives = archive_repository
        self._drafts = draft_repository
        self._assets = asset_store

    def register_archive(self, archive: ArchivedDish) -> None:
        """Best-effort follow-up after Archive success; never raises to callers."""

        try:
            self._process_archive(archive)
        except Exception as exc:  # noqa: BLE001 - Canonical is fail-open
            self._log_failure("archive_follow_up", exc)

    def reconcile_active_archives(self) -> dict[str, int]:
        """Run one bounded local pass over active archives."""

        counts = {
            "scanned": 0,
            "registered": 0,
            "usageRecorded": 0,
            "alreadyRegistered": 0,
            "skipped": 0,
            "failed": 0,
        }
        try:
            archives = self._archives.list_active()
        except Exception:  # noqa: BLE001 - startup repair is fail-open
            counts["failed"] = 1
            self._log_reconciliation(counts)
            return counts

        for archive in archives:
            counts["scanned"] += 1
            try:
                outcome = self._process_archive(archive)
            except Exception:  # noqa: BLE001 - one bad archive cannot block the pass
                counts["failed"] += 1
                continue
            if outcome == "registered":
                counts["registered"] += 1
            elif outcome == "usage_recorded":
                counts["usageRecorded"] += 1
            elif outcome == "already_registered":
                counts["alreadyRegistered"] += 1
            else:
                counts["skipped"] += 1

        self._log_reconciliation(counts)
        return counts

    def _process_archive(self, archive: ArchivedDish) -> RegistrationOutcome:
        provenance = archive.internal_provenance
        if self._value_text(self._field(provenance, "mode", "mode")) != DraftMode.ASK_GUS.value:
            return "skipped"

        # Both fresh and reused archives are keyed by their immutable archive
        # id. A source archive already present in the Registry is complete.
        existing = self._registry.get_by_source_archive_id(archive.dish_id)
        if existing is not None:
            return "already_registered"

        generation_source = self._value_text(
            self._field(provenance, "generation_source", "generationSource")
        )
        if generation_source == "CANONICAL_REUSED":
            canonical_id = self._read_canonical_id(provenance)
            if canonical_id is None:
                return "skipped"
            self._registry.record_usage(
                canonical_id,
                source_archive_id=archive.dish_id,
            )
            return "usage_recorded"
        if generation_source != GenerationSource.FRESH_GENERATION.value:
            return "skipped"

        try:
            registration, icon_source, icon_16 = self._build_registration(archive)
        except _SkipRegistration:
            return "skipped"
        try:
            self._registry.register(
                registration,
                icon_source=icon_source,
                icon_16=icon_16,
            )
        except (ValueError, TypeError) as exc:
            # Invalid source snapshots are a per-item miss, not a startup
            # failure. Registry availability failures use their typed error.
            if isinstance(exc, CanonicalRegistryUnavailableError):
                raise
            return "skipped"
        return "registered"

    def _build_registration(
        self,
        archive: ArchivedDish,
    ) -> tuple[CanonicalDishRegistration, CanonicalIconInput, CanonicalIconInput]:
        try:
            draft = self._drafts.get(archive.source_draft_id)
        except (AssetNotFoundError, FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise _SkipRegistration from exc
        if draft.mode is not DraftMode.ASK_GUS or draft.analysis is None:
            raise _SkipRegistration

        try:
            icon_source = self._read_icon(
                archive.visuals.icon_source_asset_id,
                expected_kind=AssetKind.ICON_SOURCE,
            )
            icon_16 = self._read_icon(
                archive.visuals.icon_16_asset_id,
                expected_kind=AssetKind.ICON_16,
            )
            recall_document = build_recall_document(draft.analysis)
            language = draft.source.language
            catalog_versions = {
                ingredient.catalog_version for ingredient in archive.gameplay.ingredients
            }
            if len(catalog_versions) != 1:
                raise ValueError("gameplay catalog metadata is inconsistent")
            catalog_version = next(iter(catalog_versions))
            registration = CanonicalDishRegistration(
                canonicalId=uuid4(),
                sourceArchiveId=archive.dish_id,
                dishSignature=build_dish_signature(language, recall_document),
                language=language,
                recallDocument=recall_document,
                presentation=archive.presentation,
                gameplay=archive.gameplay,
                visualBrief=archive.visuals.visual_brief,
                catalogVersion=catalog_version,
            )
        except (AssetNotFoundError, FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise _SkipRegistration from exc
        return registration, icon_source, icon_16

    def _read_icon(
        self,
        asset_id: UUID | None,
        *,
        expected_kind: AssetKind,
    ) -> CanonicalIconInput:
        if asset_id is None:
            raise _SkipRegistration
        try:
            reference = self._assets.stat(asset_id)
            if reference.kind is not expected_kind:
                raise _SkipRegistration
            if reference.width is None or reference.height is None:
                raise _SkipRegistration
            with self._assets.open(reference) as handle:
                data = handle.read()
            if len(data) != reference.byte_size:
                raise _SkipRegistration
            if hashlib.sha256(data).hexdigest() != reference.sha256:
                raise _SkipRegistration
            return CanonicalIconInput(
                data=data,
                mediaType=reference.media_type,
                sha256=reference.sha256,
                byteSize=reference.byte_size,
                width=reference.width,
                height=reference.height,
            )
        except _SkipRegistration:
            raise
        except (AssetNotFoundError, FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise _SkipRegistration from exc

    @staticmethod
    def _field(value: object, name: str, alias: str) -> object:
        if isinstance(value, Mapping):
            return value.get(alias, value.get(name))
        return getattr(value, name, getattr(value, alias, None))

    @staticmethod
    def _value_text(value: object) -> str | None:
        if isinstance(value, Enum):
            return str(value.value)
        if isinstance(value, str):
            return value
        return None

    @staticmethod
    def _read_canonical_id(provenance: object) -> UUID | None:
        raw = CanonicalRegistrationService._field(
            provenance,
            "canonical_dish_id",
            "canonicalDishId",
        )
        if raw is None:
            return None
        try:
            return ensure_uuid4(raw if isinstance(raw, UUID) else UUID(str(raw)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _failure_reason(exc: Exception) -> str:
        if isinstance(exc, CanonicalRegistryUnavailableError):
            return "REGISTRY_UNAVAILABLE"
        if isinstance(exc, (AssetNotFoundError, FileNotFoundError, OSError)):
            return "SOURCE_UNAVAILABLE"
        if isinstance(exc, (TypeError, ValueError)):
            return "SOURCE_INVALID"
        return "UNEXPECTED_FAILURE"

    def _log_failure(self, operation: str, exc: Exception) -> None:
        log_event(
            logging.WARNING,
            error_code="PTS_CANONICAL_REGISTRATION_FAILED",
            usage={
                "operation": operation,
                "reason": self._failure_reason(exc),
            },
        )

    @staticmethod
    def _log_reconciliation(counts: Mapping[str, int]) -> None:
        log_event(
            logging.INFO,
            error_code="PTS_CANONICAL_RECONCILIATION_SUMMARY",
            usage={
                "operation": "startup_reconciliation",
                **dict(counts),
            },
        )
