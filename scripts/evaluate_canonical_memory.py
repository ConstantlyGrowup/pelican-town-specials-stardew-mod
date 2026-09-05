"""Small, local-only evaluation tools for the Canonical memory experiment.

The commands in this module are deliberately conservative.  Validation and
dry-run paths never load a model, call a Provider, or write to the product
workspace.  A real run requires both ``--live`` and a positive logical-call
budget, and writes only result files under the explicitly selected evaluation
directory.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypeVar, cast
from uuid import UUID, uuid4

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_SRC = _REPO_ROOT / "backend" / "src"
if str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

_RELEVANT_SOURCE_FILES = (
    _REPO_ROOT / "scripts" / "evaluate_canonical_memory.py",
    _REPO_ROOT / "scripts" / "evaluation_embedding.py",
    _BACKEND_SRC / "pelican_town_specials" / "application" / "canonical_memory.py",
    _BACKEND_SRC / "pelican_town_specials" / "domain" / "canonical.py",
    _BACKEND_SRC / "pelican_town_specials" / "domain" / "dish.py",
    _BACKEND_SRC / "pelican_town_specials" / "providers" / "contracts.py",
    _BACKEND_SRC / "pelican_town_specials" / "providers" / "openai_compatible.py",
    _BACKEND_SRC
    / "pelican_town_specials"
    / "providers"
    / "prompts"
    / "canonical_match_v1.py",
)

from pelican_town_specials.application.canonical_memory import (
    CandidateRetriever,
    CanonicalRetriever,
    RankedCanonicalCandidate,
    RecallService,
    build_dish_signature,
    build_recall_document,
)
from pelican_town_specials.application.settings import (
    ProviderSettingsService,
)
from pelican_town_specials.domain.assets import MediaType
from pelican_town_specials.domain.canonical import (
    CANONICAL_CANDIDATE_LIMIT,
    CANONICAL_MATCH_THRESHOLD,
    CANONICAL_REGISTRY_SCHEMA_VERSION,
    CANONICAL_REUSE_CONTRACT_VERSION,
    CanonicalDish,
    CanonicalDishRegistration,
    CanonicalIconInput,
    CanonicalIconKind,
    CanonicalRecallCandidate,
    RecallDecision,
)
from pelican_town_specials.domain.common import (
    Language,
    StrictModel,
    ensure_utc,
    ensure_uuid4,
)
from pelican_town_specials.domain.dish import (
    DishAnalysis,
    GameIngredient,
    GameplaySpec,
    PresentationSpec,
    RecoverySpec,
    SemanticIngredient,
)
from pelican_town_specials.persistence.canonical_registry import (
    SQLiteCanonicalRegistry,
)
from pelican_town_specials.persistence.secret_store import (
    WindowsEnvironmentSecretStore,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths
from pelican_town_specials.providers.contracts import (
    CanonicalMatchRequest,
    CanonicalMatchResponse,
    ModelGateway,
)
from PIL import Image
from pydantic import Field, ValidationError, field_validator, model_validator

try:
    from evaluation_embedding import (
        MODEL_DEVICE,
        MODEL_MAX_SEQ_LENGTH,
        MODEL_NAME,
        MODEL_REVISION,
        CpuEmbeddingRetriever,
        cpu_thread_count,
        load_cpu_model,
        measure_retrieval,
        resolve_model_revision,
        runtime_versions,
        serialize_embedding_text,
    )
except ModuleNotFoundError:
    from scripts.evaluation_embedding import (
        MODEL_DEVICE,
        MODEL_MAX_SEQ_LENGTH,
        MODEL_NAME,
        MODEL_REVISION,
        CpuEmbeddingRetriever,
        cpu_thread_count,
        load_cpu_model,
        measure_retrieval,
        resolve_model_revision,
        runtime_versions,
        serialize_embedding_text,
    )

EvaluationKind = Literal["positive", "negative"]
_ModelT = TypeVar("_ModelT", bound=StrictModel)


class EvaluationInputError(ValueError):
    """An evaluation input violates its frozen, strict schema."""


class SeedConflictError(EvaluationInputError):
    """A requested id would overwrite a different Registry record."""


class EvaluationQuery(StrictModel):
    query_id: UUID = Field(alias="queryId")
    analysis: DishAnalysis
    language: Language
    context_text: str | None = Field(default=None, alias="contextText", max_length=500)

    @field_validator("query_id", mode="before")
    @classmethod
    def _validate_query_id(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        if isinstance(value, str):
            return ensure_uuid4(UUID(value))
        return value


class EvaluationLabel(StrictModel):
    query_id: UUID = Field(alias="queryId")
    kind: EvaluationKind
    expected_canonical_id: UUID | None = Field(
        default=None,
        alias="expectedCanonicalId",
    )

    @field_validator("query_id", "expected_canonical_id", mode="before")
    @classmethod
    def _validate_ids(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        if isinstance(value, str):
            return ensure_uuid4(UUID(value))
        return value

    @model_validator(mode="after")
    def _validate_expected_id(self) -> EvaluationLabel:
        if self.kind == "positive" and self.expected_canonical_id is None:
            raise ValueError("positive labels require expectedCanonicalId")
        if self.kind == "negative" and self.expected_canonical_id is not None:
            raise ValueError("negative labels must not have expectedCanonicalId")
        return self


class EvaluationResult(StrictModel):
    query_id: UUID = Field(alias="queryId")
    kind: EvaluationKind
    expected_canonical_id: UUID | None = Field(
        default=None,
        alias="expectedCanonicalId",
    )
    candidate_ids: list[UUID] = Field(alias="candidateIds", max_length=5)
    selected_id: UUID | None = Field(default=None, alias="selectedId")
    decision: str = Field(min_length=1, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)
    error_category: str | None = Field(
        default=None,
        alias="errorCategory",
        max_length=80,
    )

    @field_validator(
        "query_id",
        "expected_canonical_id",
        "selected_id",
        mode="before",
    )
    @classmethod
    def _validate_optional_ids(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        if isinstance(value, str):
            return ensure_uuid4(UUID(value))
        return value

    @field_validator("candidate_ids", mode="before")
    @classmethod
    def _validate_candidate_ids(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        return [
            ensure_uuid4(item)
            if isinstance(item, UUID)
            else ensure_uuid4(UUID(str(item)))
            for item in value
        ]


class ManifestEntry(StrictModel):
    canonical_id: UUID = Field(alias="canonicalId")
    source_archive_id: UUID = Field(alias="sourceArchiveId")
    icon_source_path: str = Field(alias="iconSourcePath", min_length=1, max_length=240)
    icon_16_path: str = Field(alias="icon16Path", min_length=1, max_length=240)
    icon_source_sha256: str = Field(
        alias="iconSourceSha256", min_length=64, max_length=64
    )
    icon_16_sha256: str = Field(alias="icon16Sha256", min_length=64, max_length=64)
    icon_source_byte_size: int = Field(alias="iconSourceByteSize", gt=0)
    icon_16_byte_size: int = Field(alias="icon16ByteSize", gt=0)

    @field_validator("canonical_id", "source_archive_id", mode="before")
    @classmethod
    def _validate_manifest_ids(cls, value: object) -> object:
        if isinstance(value, UUID):
            return ensure_uuid4(value)
        if isinstance(value, str):
            return ensure_uuid4(UUID(value))
        return value

    @field_validator("icon_source_sha256", "icon_16_sha256")
    @classmethod
    def _validate_hashes(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("manifest icon hashes must be lowercase SHA-256")
        return value

    @field_validator("icon_source_path", "icon_16_path")
    @classmethod
    def _validate_relative_paths(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or "\\" in value or ".." in path.parts:
            raise ValueError("manifest icon paths must be safe relative paths")
        return value


class SeedManifest(StrictModel):
    schema_version: int = Field(default=1, alias="schemaVersion")
    language: Language
    catalog_version: str = Field(alias="catalogVersion", min_length=1, max_length=80)
    entries: list[ManifestEntry] = Field(min_length=0)
    created_at: datetime = Field(alias="createdAt")

    @field_validator("created_at", mode="before")
    @classmethod
    def _validate_created_at(cls, value: object) -> object:
        if isinstance(value, datetime):
            return ensure_utc(value)
        if isinstance(value, str):
            return ensure_utc(datetime.fromisoformat(value))
        return value

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != CANONICAL_REGISTRY_SCHEMA_VERSION:
            raise ValueError("seed manifest schemaVersion must be 1")
        return value

    @model_validator(mode="after")
    def _validate_unique_entries(self) -> SeedManifest:
        canonical_ids = [entry.canonical_id for entry in self.entries]
        source_ids = [entry.source_archive_id for entry in self.entries]
        if len(set(canonical_ids)) != len(canonical_ids):
            raise ValueError("seed manifest canonical IDs must be unique")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("seed manifest source archive IDs must be unique")
        return self


@dataclass(frozen=True)
class EvaluationBundle:
    canonicals: tuple[CanonicalDish | CanonicalDishRegistration, ...]
    queries: tuple[EvaluationQuery, ...]
    labels: tuple[EvaluationLabel, ...]
    manifest: SeedManifest | None = None


@dataclass(frozen=True)
class FixtureRegistration:
    registration: CanonicalDishRegistration
    icon_source: CanonicalIconInput
    icon_16: CanonicalIconInput


@dataclass(frozen=True)
class EvaluationMetrics:
    positive_hit_success: int
    positive_total: int
    candidate_inclusion: int
    negative_false_hit: int
    negative_total: int
    error_count: int
    provider_error_count: int

    def as_dict(self) -> dict[str, int | float]:
        return {
            "positiveHitSuccess": self.positive_hit_success,
            "positiveTotal": self.positive_total,
            "hitSuccessRate": _safe_ratio(
                self.positive_hit_success,
                self.positive_total,
            ),
            "candidateInclusion": self.candidate_inclusion,
            "candidateInclusionRate": _safe_ratio(
                self.candidate_inclusion,
                self.positive_total,
            ),
            "negativeFalseHit": self.negative_false_hit,
            "negativeTotal": self.negative_total,
            "negativeFalseHitRate": _safe_ratio(
                self.negative_false_hit,
                self.negative_total,
            ),
            "errorCount": self.error_count,
            "providerErrorCount": self.provider_error_count,
        }


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _read_jsonl(path: Path, model_type: type[_ModelT]) -> list[_ModelT]:
    if not path.is_file():
        raise EvaluationInputError(f"missing evaluation file: {path}")
    records: list[_ModelT] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            records.append(model_type.model_validate_json(line))
        except (ValidationError, TypeError, ValueError) as exc:
            raise EvaluationInputError(
                f"invalid {path.name} record at line {line_number}"
            ) from exc
    return records


def _read_canonical_jsonl(
    path: Path,
) -> list[CanonicalDish | CanonicalDishRegistration]:
    if not path.is_file():
        raise EvaluationInputError(f"missing evaluation file: {path}")
    records: list[CanonicalDish | CanonicalDishRegistration] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise TypeError("canonical record must be an object")
            payload = _normalise_canonical_payload(payload)
            try:
                records.append(CanonicalDish.model_validate(payload))
            except ValidationError:
                records.append(CanonicalDishRegistration.model_validate(payload))
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise EvaluationInputError(
                f"invalid canonicals.jsonl record at line {line_number}"
            ) from exc
    return records


def _normalise_canonical_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Rehydrate JSON scalar values before strict domain validation.

    The production Registry reads UUIDs, enums and timestamps from SQLite into
    typed values before constructing ``CanonicalDish``.  JSONL is a transport
    format, so this small adapter performs the same rehydration and removes the
    recovery fields that the domain intentionally derives from ``edibility``.
    """

    mutable = dict(payload)
    for field_name in ("canonicalId", "sourceArchiveId"):
        value = mutable.get(field_name)
        if isinstance(value, str):
            mutable[field_name] = UUID(value)
    language = mutable.get("language")
    if isinstance(language, str):
        mutable["language"] = Language(language)
    for field_name in ("registeredAt", "lastUsedAt"):
        timestamp = mutable.get(field_name)
        if isinstance(timestamp, str):
            mutable[field_name] = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )
    for field_name in ("iconSource", "icon16"):
        icon = mutable.get(field_name)
        if isinstance(icon, Mapping):
            icon_payload = dict(icon)
            media_type = icon_payload.get("mediaType")
            if isinstance(media_type, str):
                icon_payload["mediaType"] = MediaType(media_type)
            mutable[field_name] = icon_payload
    gameplay = mutable.get("gameplay")
    if isinstance(gameplay, Mapping):
        gameplay_payload = dict(gameplay)
        recovery = gameplay_payload.get("recovery")
        if isinstance(recovery, Mapping):
            recovery_payload = dict(recovery)
            for field_name in ("calculationVersion", "energyRestore", "healthRestore"):
                recovery_payload.pop(field_name, None)
            gameplay_payload["recovery"] = recovery_payload
        mutable["gameplay"] = gameplay_payload
    return mutable


def _canonical_id(record: CanonicalDish | CanonicalDishRegistration) -> UUID:
    return record.canonical_id


def _source_archive_id(record: CanonicalDish | CanonicalDishRegistration) -> UUID:
    return record.source_archive_id


def _canonical_language(record: CanonicalDish | CanonicalDishRegistration) -> Language:
    return record.language


def _canonical_catalog_version(
    record: CanonicalDish | CanonicalDishRegistration,
) -> str:
    return record.catalog_version


def _canonical_icon_paths(record: CanonicalDish) -> tuple[str, str]:
    return record.icon_source.relative_path, record.icon_16.relative_path


def _registration_content_payload(
    record: CanonicalDish | CanonicalDishRegistration,
) -> dict[str, object]:
    """Return stable Canonical content without generated or mutable fields."""

    payload = record.model_dump(by_alias=True, mode="json")
    for field_name in (
        "canonicalId",
        "sourceArchiveId",
        "schemaVersion",
        "registeredAt",
        "lastUsedAt",
        "useCount",
        "iconSource",
        "icon16",
    ):
        payload.pop(field_name, None)
    return payload


def _icon_content_payload(icon: CanonicalIconInput | Any) -> dict[str, object]:
    payload = icon.model_dump(by_alias=True, mode="json", exclude={"data"})
    return {
        field_name: payload[field_name]
        for field_name in ("mediaType", "sha256", "byteSize", "width", "height")
        if field_name in payload
    }


def _canonical_content_payload(
    record: CanonicalDish | CanonicalDishRegistration,
) -> dict[str, object]:
    payload = _registration_content_payload(record)
    if isinstance(record, CanonicalDish):
        payload["iconSource"] = _icon_content_payload(record.icon_source)
        payload["icon16"] = _icon_content_payload(record.icon_16)
    return payload


def _fixture_content_payload(fixture: FixtureRegistration) -> dict[str, object]:
    payload = _registration_content_payload(fixture.registration)
    payload["iconSource"] = _icon_content_payload(fixture.icon_source)
    payload["icon16"] = _icon_content_payload(fixture.icon_16)
    return payload


def _content_fingerprint(payload: Mapping[str, object]) -> str:
    return _sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _canonical_content_fingerprint(
    record: CanonicalDish | CanonicalDishRegistration,
) -> str:
    return _content_fingerprint(_canonical_content_payload(record))


def _fixture_content_fingerprint(fixture: FixtureRegistration) -> str:
    return _content_fingerprint(_fixture_content_payload(fixture))


def load_evaluation_bundle(
    input_dir: Path,
    *,
    require_manifest: bool = False,
) -> EvaluationBundle:
    canonicals = _read_canonical_jsonl(input_dir / "canonicals.jsonl")
    queries = _read_jsonl(input_dir / "queries.jsonl", EvaluationQuery)
    labels = _read_jsonl(input_dir / "labels.jsonl", EvaluationLabel)
    manifest_path = input_dir / "seed_manifest.json"
    manifest: SeedManifest | None = None
    if manifest_path.exists():
        try:
            manifest = SeedManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise EvaluationInputError("invalid seed_manifest.json") from exc
    elif require_manifest:
        raise EvaluationInputError("seed_manifest.json is required")
    validate_evaluation_bundle(canonicals, queries, labels, manifest=manifest)
    return EvaluationBundle(
        canonicals=tuple(canonicals),
        queries=tuple(queries),
        labels=tuple(labels),
        manifest=manifest,
    )


def validate_evaluation_bundle(
    canonicals: Sequence[CanonicalDish | CanonicalDishRegistration],
    queries: Sequence[EvaluationQuery],
    labels: Sequence[EvaluationLabel],
    *,
    manifest: SeedManifest | None = None,
) -> None:
    canonical_ids = [_canonical_id(record) for record in canonicals]
    if len(set(canonical_ids)) != len(canonical_ids):
        raise EvaluationInputError("canonical IDs must be unique")
    if not canonicals:
        raise EvaluationInputError("at least one canonical record is required")
    query_ids = [query.query_id for query in queries]
    label_ids = [label.query_id for label in labels]
    if len(set(query_ids)) != len(query_ids):
        raise EvaluationInputError("query IDs must be unique")
    if len(set(label_ids)) != len(label_ids):
        raise EvaluationInputError("label query IDs must be unique")
    if set(query_ids) != set(label_ids):
        raise EvaluationInputError("every query must have exactly one frozen label")
    canonical_id_set = set(canonical_ids)
    for label in labels:
        if (
            label.kind == "positive"
            and label.expected_canonical_id not in canonical_id_set
        ):
            raise EvaluationInputError(
                f"positive label points outside canonical pool: {label.query_id}"
            )
    if manifest is not None:
        manifest_ids = {entry.canonical_id for entry in manifest.entries}
        if manifest_ids != canonical_id_set:
            raise EvaluationInputError(
                "seed manifest must identify exactly the canonical evaluation pool"
            )
        languages = {_canonical_language(record) for record in canonicals}
        catalogs = {_canonical_catalog_version(record) for record in canonicals}
        if languages != {manifest.language} or catalogs != {manifest.catalog_version}:
            raise EvaluationInputError(
                "canonical pool does not match the manifest language/catalog"
            )


def validate_manifest_files(
    manifest: SeedManifest,
    *,
    root: Path | None = None,
    registry: Any | None = None,
    canonicals: Sequence[CanonicalDish | CanonicalDishRegistration] | None = None,
) -> None:
    """Validate complete manifest paths, digests, and Registry-owned icons."""

    frozen = {record.canonical_id: record for record in canonicals or ()}
    if canonicals is not None and (
        len(frozen) != len(canonicals)
        or set(frozen) != {entry.canonical_id for entry in manifest.entries}
    ):
        raise EvaluationInputError("frozen Canonical membership differs from manifest")
    seen_canonical: set[UUID] = set()
    for entry in manifest.entries:
        if entry.canonical_id in seen_canonical:
            raise EvaluationInputError("duplicate canonical ID in manifest")
        seen_canonical.add(entry.canonical_id)
        if root is not None:
            for path_text, expected_hash, expected_size in (
                (
                    entry.icon_source_path,
                    entry.icon_source_sha256,
                    entry.icon_source_byte_size,
                ),
                (
                    entry.icon_16_path,
                    entry.icon_16_sha256,
                    entry.icon_16_byte_size,
                ),
            ):
                path = (root / path_text).resolve()
                if root.resolve() not in path.parents:
                    raise EvaluationInputError("manifest icon path escapes its root")
                if not path.is_file():
                    raise EvaluationInputError(f"manifest icon is missing: {path_text}")
                data = path.read_bytes()
                if len(data) != expected_size or _sha256(data) != expected_hash:
                    raise EvaluationInputError(
                        f"manifest icon digest mismatch: {path_text}"
                    )
        if registry is not None:
            canonical = registry.get_valid(entry.canonical_id)
            if canonical is None:
                raise EvaluationInputError(
                    f"manifest canonical is not valid in Registry: {entry.canonical_id}"
                )
            if (
                canonical.source_archive_id != entry.source_archive_id
                or canonical.language != manifest.language
                or canonical.catalog_version != manifest.catalog_version
            ):
                raise EvaluationInputError(
                    "Registry identity/language/catalog differs from manifest"
                )
            if entry.canonical_id in frozen:
                expected = frozen[entry.canonical_id]
                if (
                    expected.source_archive_id != canonical.source_archive_id
                    or _registration_content_payload(expected)
                    != _registration_content_payload(canonical)
                    or (
                        isinstance(expected, CanonicalDish)
                        and _canonical_content_fingerprint(expected)
                        != _canonical_content_fingerprint(canonical)
                    )
                ):
                    raise EvaluationInputError(
                        "Registry content differs from frozen Canonical input"
                    )
            for kind in (CanonicalIconKind.SOURCE, CanonicalIconKind.ICON_16):
                try:
                    data = registry.load_owned_icon(entry.canonical_id, kind)
                except Exception as exc:
                    raise EvaluationInputError(
                        f"manifest icon failed Registry validation: {entry.canonical_id}"
                    ) from exc
                if not data:
                    raise EvaluationInputError(
                        f"manifest Registry icon is empty: {entry.canonical_id}"
                    )
                expected_hash, expected_size = (
                    (entry.icon_source_sha256, entry.icon_source_byte_size)
                    if kind == CanonicalIconKind.SOURCE
                    else (entry.icon_16_sha256, entry.icon_16_byte_size)
                )
                if _sha256(data) != expected_hash or len(data) != expected_size:
                    raise EvaluationInputError(
                        "Registry icon differs from manifest digest"
                    )
            source_path, icon_16_path = _canonical_icon_paths(canonical)
            if (
                source_path != entry.icon_source_path
                or icon_16_path != entry.icon_16_path
            ):
                raise EvaluationInputError(
                    f"manifest icon path disagrees with Registry: {entry.canonical_id}"
                )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _png_icon(size: int, *, color: tuple[int, int, int]) -> CanonicalIconInput:
    if size < 1:
        raise ValueError("icon size must be positive")
    output = io.BytesIO()
    Image.new("RGBA", (size, size), color + (255,)).save(output, format="PNG")
    data = output.getvalue()
    return CanonicalIconInput(
        data=data,
        mediaType=MediaType.PNG,
        sha256=_sha256(data),
        byteSize=len(data),
        width=size,
        height=size,
    )


def _fixture_analysis(
    *,
    display_name: str,
    ingredients: Sequence[str],
    cuisine: str,
    methods: Sequence[str],
) -> DishAnalysis:
    return DishAnalysis(
        recognizedDish=display_name,
        summary=f"A local evaluation fixture for {display_name}.",
        cuisine=cuisine,
        cookingMethods=list(methods),
        flavorProfile=["savory"],
        semanticIngredients=[
            SemanticIngredient(
                name=ingredient,
                normalizedName=ingredient,
                visibleConfidence=0.95,
                quantityHint=None,
            )
            for ingredient in ingredients
        ],
        confidence=0.99,
        safetyNotes=[],
    )


def build_fixture_registration(
    *,
    index: int = 1,
    display_name: str = "番茄炒蛋",
    ingredients: Sequence[str] = ("番茄", "鸡蛋"),
    language: Language = Language.ZH_CN,
    catalog_version: str = "stardew-1.6.15",
    canonical_id: UUID | None = None,
    source_archive_id: UUID | None = None,
) -> FixtureRegistration:
    """Build a legal, deterministic-shape fixture without touching a workspace."""

    analysis = _fixture_analysis(
        display_name=display_name,
        ingredients=ingredients,
        cuisine="家常菜",
        methods=("炒",),
    )
    recall_document = build_recall_document(analysis)
    gameplay_ingredients = [
        GameIngredient(
            itemId=f"evaluation-{index}-{position}",
            displayName=ingredient,
            quantity=1,
            mappingReason="Evaluation fixture only.",
            catalogVersion=catalog_version,
        )
        for position, ingredient in enumerate(ingredients, 1)
    ]
    registration = CanonicalDishRegistration(
        canonicalId=canonical_id or uuid4(),
        sourceArchiveId=source_archive_id or uuid4(),
        dishSignature=build_dish_signature(language, recall_document),
        language=language,
        reuseContractVersion=CANONICAL_REUSE_CONTRACT_VERSION,
        recallDocument=recall_document,
        presentation=PresentationSpec(
            displayName=display_name,
            internalName=f"EvaluationDish{index}",
            categoryLabel="Evaluation",
            description=f"Evaluation fixture for {display_name}.",
            gusComment=None,
            tags=[],
        ),
        gameplay=GameplaySpec(
            ingredients=gameplay_ingredients,
            recovery=RecoverySpec(edibility=50),
            buff=None,
            sellPrice=100 + index,
            isDrink=False,
        ),
        visualBrief=f"A small pixel icon of {display_name}.",
        catalogVersion=catalog_version,
    )
    hue = ((index * 61) % 180, 90, 180)
    return FixtureRegistration(
        registration=registration,
        icon_source=_png_icon(32, color=hue),
        icon_16=_png_icon(16, color=hue),
    )


def register_fixture(
    registry: Any,
    fixture: FixtureRegistration,
) -> CanonicalDish:
    """Register once, rejecting conflicting IDs rather than overwriting."""

    registration = fixture.registration
    existing_by_source = registry.get_by_source_archive_id(
        registration.source_archive_id
    )
    if existing_by_source is not None:
        if (
            existing_by_source.canonical_id != registration.canonical_id
            or _canonical_content_fingerprint(existing_by_source)
            != _fixture_content_fingerprint(fixture)
        ):
            raise SeedConflictError(
                "source archive ID already belongs to a different canonical fixture"
            )
        return existing_by_source
    existing_by_id = registry.get_valid(registration.canonical_id)
    if existing_by_id is not None:
        raise SeedConflictError("canonical ID already belongs to a different fixture")
    persisted = registry.register(
        registration,
        icon_source=fixture.icon_source,
        icon_16=fixture.icon_16,
    )
    if persisted.canonical_id != registration.canonical_id:
        raise SeedConflictError("Registry returned a conflicting canonical ID")
    return persisted


def build_seed_manifest(
    records: Sequence[CanonicalDish],
    *,
    language: Language | None = None,
    catalog_version: str | None = None,
) -> SeedManifest:
    if not records:
        raise ValueError("at least one persisted canonical is required")
    selected_language = language or records[0].language
    selected_catalog = catalog_version or records[0].catalog_version
    entries = [
        ManifestEntry(
            canonicalId=record.canonical_id,
            sourceArchiveId=record.source_archive_id,
            iconSourcePath=record.icon_source.relative_path,
            icon16Path=record.icon_16.relative_path,
            iconSourceSha256=record.icon_source.sha256,
            icon16Sha256=record.icon_16.sha256,
            iconSourceByteSize=record.icon_source.byte_size,
            icon16ByteSize=record.icon_16.byte_size,
        )
        for record in records
    ]
    return SeedManifest(
        schemaVersion=1,
        language=selected_language,
        catalogVersion=selected_catalog,
        entries=entries,
        createdAt=datetime.now(UTC),
    )


def seed_fixtures(
    workspace_root: Path,
    output_dir: Path,
    fixtures: Sequence[FixtureRegistration],
) -> tuple[CanonicalDish, ...]:
    """Explicitly seed a development workspace and emit a complete manifest."""

    canonical_path = output_dir / "canonicals.jsonl"
    manifest_path = output_dir / "seed_manifest.json"
    persisted_inputs = None
    manifest = None
    if canonical_path.exists() or manifest_path.exists():
        try:
            persisted_inputs = _read_canonical_jsonl(canonical_path)
            manifest = SeedManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise SeedConflictError(
                "existing seed artifacts cannot be safely reused"
            ) from exc
        if (
            len(persisted_inputs) != len(fixtures)
            or any(not isinstance(record, CanonicalDish) for record in persisted_inputs)
            or [_canonical_content_fingerprint(record) for record in persisted_inputs]
            != [_fixture_content_fingerprint(fixture) for fixture in fixtures]
        ):
            raise SeedConflictError(
                "existing seed artifacts differ from requested fixtures"
            )
    if (
        not fixtures
        or len({f.registration.canonical_id for f in fixtures}) != len(fixtures)
        or len({f.registration.source_archive_id for f in fixtures}) != len(fixtures)
    ):
        raise SeedConflictError("seed requires nonempty unique fixture identities")
    workspace = WorkspacePaths.create(workspace_root)
    registry = SQLiteCanonicalRegistry(workspace)
    if persisted_inputs is not None and manifest is not None:
        validate_manifest_files(
            manifest,
            root=workspace.canonical_assets_dir,
            registry=registry,
            canonicals=persisted_inputs,
        )
        return tuple(
            cast(CanonicalDish, registry.get_valid(record.canonical_id))
            for record in persisted_inputs
        )
    # Check the whole batch before the first registration, including later collisions.
    for fixture in fixtures:
        record = registry.get_by_source_archive_id(
            fixture.registration.source_archive_id
        )
        by_id = registry.get_valid(fixture.registration.canonical_id)
        if (
            record is not None
            and (
                record.canonical_id != fixture.registration.canonical_id
                or _canonical_content_fingerprint(record)
                != _fixture_content_fingerprint(fixture)
            )
        ) or (by_id is not None and record is None):
            raise SeedConflictError(
                "fixture identity conflicts with existing Registry content"
            )
    records = tuple(register_fixture(registry, fixture) for fixture in fixtures)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        output_dir / "canonicals.jsonl",
        [record.model_dump(by_alias=True, mode="json") for record in records],
    )
    manifest = build_seed_manifest(records)
    (output_dir / "seed_manifest.json").write_text(
        json.dumps(
            manifest.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    validate_manifest_files(
        manifest,
        root=workspace.canonical_assets_dir,
        registry=registry,
    )
    return records


def _write_jsonl(path: Path, records: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def compute_metrics(results: Sequence[EvaluationResult]) -> EvaluationMetrics:
    positive = [result for result in results if result.kind == "positive"]
    negative = [result for result in results if result.kind == "negative"]
    hit_success = sum(
        result.decision == RecallDecision.MATCH_HIT.value
        and result.expected_canonical_id is not None
        and result.selected_id == result.expected_canonical_id
        for result in positive
    )
    inclusion = sum(
        result.expected_canonical_id is not None
        and result.expected_canonical_id in result.candidate_ids
        for result in positive
    )
    false_hit = sum(
        result.decision == RecallDecision.MATCH_HIT.value for result in negative
    )
    errors = sum(result.error_category is not None for result in results)
    provider_errors = sum(
        result.error_category == "provider_error" for result in results
    )
    return EvaluationMetrics(
        positive_hit_success=hit_success,
        positive_total=len(positive),
        candidate_inclusion=inclusion,
        negative_false_hit=false_hit,
        negative_total=len(negative),
        error_count=errors,
        provider_error_count=provider_errors,
    )


def validate_result_completeness(
    queries: Sequence[EvaluationQuery],
    results: Sequence[EvaluationResult],
) -> None:
    expected = {query.query_id for query in queries}
    actual = [result.query_id for result in results]
    if len(actual) != len(set(actual)):
        raise EvaluationInputError("duplicate result query IDs")
    if set(actual) != expected:
        missing = expected - set(actual)
        extra = set(actual) - expected
        raise EvaluationInputError(
            f"incomplete result set (missing={sorted(map(str, missing))}, extra={sorted(map(str, extra))})"
        )


class _RecordingRetriever:
    def __init__(self, inner: CanonicalRetriever) -> None:
        self.inner = inner
        self.last_ranked: list[RankedCanonicalCandidate] = []

    def retrieve(
        self,
        analysis: DishAnalysis,
        candidates: Iterable[CanonicalRecallCandidate],
        *,
        language: Language | None = None,
        catalog_version: str | None = None,
    ) -> list[RankedCanonicalCandidate]:
        self.last_ranked = self.inner.retrieve(
            analysis,
            candidates,
            language=language,
            catalog_version=catalog_version,
        )
        return self.last_ranked


class _RecordingMatcher:
    def __init__(self, inner: ModelGateway) -> None:
        self.inner = inner
        self.last_error_category: str | None = None
        self.requests: list[CanonicalMatchRequest] = []

    async def match_canonical(
        self,
        request: CanonicalMatchRequest,
        *,
        json_only: bool = False,
    ) -> CanonicalMatchResponse:
        self.requests.append(request)
        try:
            return await self.inner.match_canonical(request, json_only=json_only)
        except Exception:
            self.last_error_category = "provider_error"
            raise


async def execute_recall(
    *,
    registry: Any,
    matcher: ModelGateway,
    retriever: CanonicalRetriever,
    queries: Sequence[EvaluationQuery],
    labels: Sequence[EvaluationLabel],
    max_calls: int,
) -> list[EvaluationResult]:
    if max_calls < 1:
        raise ValueError("max_calls must be positive")
    if len(queries) > max_calls:
        raise ValueError(
            f"logical call budget {max_calls} is smaller than {len(queries)} queries"
        )
    label_by_query = {label.query_id: label for label in labels}
    if len(label_by_query) != len(labels):
        raise EvaluationInputError("duplicate label query IDs")
    if set(label_by_query) != {query.query_id for query in queries}:
        raise EvaluationInputError("queries and labels must have matching IDs")
    recorded_retriever = _RecordingRetriever(retriever)
    recorded_matcher = _RecordingMatcher(matcher)
    service = RecallService(
        registry=registry,
        matcher=cast(ModelGateway, recorded_matcher),
        retriever=recorded_retriever,
    )
    results: list[EvaluationResult] = []
    for query in queries:
        recorded_retriever.last_ranked = []
        recorded_matcher.last_error_category = None
        result = await service.recall(
            query.analysis,
            query.context_text,
            query.language,
            _catalog_for_registry(registry, query.language),
            query.query_id,
        )
        label = label_by_query[query.query_id]
        error_category = recorded_matcher.last_error_category
        if (
            result.trace.outcome is RecallDecision.FALLBACK_ERROR
            and error_category is None
        ):
            error_category = "recall_error"
        results.append(
            EvaluationResult(
                queryId=query.query_id,
                kind=label.kind,
                expectedCanonicalId=label.expected_canonical_id,
                candidateIds=[
                    ranked.candidate.canonical_id
                    for ranked in recorded_retriever.last_ranked
                ],
                selectedId=result.trace.canonical_dish_id,
                decision=result.trace.outcome.value,
                confidence=result.trace.confidence,
                errorCategory=error_category,
            )
        )
    validate_result_completeness(queries, results)
    return results


def measure_query_retrieval(
    *,
    retriever: CanonicalRetriever,
    queries: Sequence[EvaluationQuery],
    candidates: Sequence[CanonicalRecallCandidate],
    repetitions: int = 10,
    language: Language = Language.ZH_CN,
    catalog_version: str = "stardew-1.6.15",
) -> dict[str, dict[str, object]]:
    """Time only in-memory candidate retrieval for each query.

    The candidate snapshot is provided by the caller and is read before the
    timer.  Matcher calls and Registry reads therefore cannot enter these
    samples.  A baseline retriever should have its corpus prepared before this
    function is called so that corpus encoding stays outside the timer too.
    """

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    measured: dict[str, dict[str, object]] = {}
    for query in queries:
        timing = measure_retrieval(
            lambda query=query: retriever.retrieve(
                query.analysis,
                candidates,
                language=language,
                catalog_version=catalog_version,
            ),
            repetitions=repetitions,
        )
        measured[str(query.query_id)] = {
            "repetitions": timing.repetitions,
            "samplesMs": list(timing.samples_ms),
            "meanMs": timing.mean_ms,
            "p50Ms": timing.p50_ms,
            "p95Ms": timing.p95_ms,
        }
    return measured


def _catalog_for_registry(registry: Any, language: Language) -> str:
    manifest = getattr(registry, "manifest", None)
    if manifest is not None:
        return manifest.catalog_version
    catalog_version = getattr(registry, "catalog_version", None)
    if isinstance(catalog_version, str) and catalog_version:
        return catalog_version
    # CLI runs always use the catalog captured by the manifest.  This fallback
    # is only for tiny fake registries supplied by tests.
    del language
    return "stardew-1.6.15"


class ManifestRepository:
    """Thin, manifest-scoped delegate around the real Canonical Repository."""

    def __init__(
        self,
        registry: Any,
        manifest: SeedManifest,
        *,
        root: Path | None = None,
        canonicals: Sequence[CanonicalDish | CanonicalDishRegistration] | None = None,
    ) -> None:
        self._registry = registry
        self.manifest = manifest
        self.catalog_version = manifest.catalog_version
        self._canonical_ids = {entry.canonical_id for entry in manifest.entries}
        self._root = root
        self._canonicals = canonicals
        self._snapshot: tuple[CanonicalRecallCandidate, ...] | None = None
        self.snapshot_digest: str | None = None

    def prepare_snapshot(self) -> list[CanonicalRecallCandidate]:
        if self._snapshot is None:
            validate_manifest_files(
                self.manifest,
                root=self._root,
                registry=self._registry,
                canonicals=self._canonicals,
            )
            pool = self._registry.list_recall_candidate_pool(
                language=self.manifest.language, catalog_version=self.catalog_version
            )
            scoped = [item for item in pool if item.canonical_id in self._canonical_ids]
            if (
                len(scoped) != len(self._canonical_ids)
                or {item.canonical_id for item in scoped} != self._canonical_ids
            ):
                raise EvaluationInputError(
                    "manifest candidate pool is incomplete or incompatible"
                )
            for item in scoped:
                record = self._registry.get_valid(item.canonical_id)
                if (
                    record is None
                    or item.recall_document != record.recall_document
                    or item.display_name != record.presentation.display_name
                    or item.dish_signature != record.dish_signature
                    or item.language != self.manifest.language
                    or item.catalog_version != self.catalog_version
                ):
                    raise EvaluationInputError(
                        "candidate snapshot differs from validated Registry content"
                    )
            self._snapshot = tuple(scoped)
            self.snapshot_digest = _content_fingerprint(
                {
                    "candidates": [
                        item.model_dump(mode="json", by_alias=True) for item in scoped
                    ]
                }
            )
        return list(self._snapshot)

    def count_valid(self) -> int:
        return len(self.prepare_snapshot())

    def list_recall_candidate_pool(
        self,
        *,
        language: Language,
        catalog_version: str,
    ) -> list[CanonicalRecallCandidate]:
        if (
            language != self.manifest.language
            or catalog_version != self.catalog_version
        ):
            return []
        return self.prepare_snapshot()

    def get_valid(self, canonical_id: UUID) -> CanonicalDish | None:
        if canonical_id not in self._canonical_ids:
            return None
        return self._registry.get_valid(canonical_id)

    def load_owned_icon(self, canonical_id: UUID, kind: CanonicalIconKind) -> bytes:
        if canonical_id not in self._canonical_ids:
            raise EvaluationInputError("icon access outside evaluation manifest")
        return self._registry.load_owned_icon(canonical_id, kind)


def _build_live_gateway(
    workspace_root: Path,
) -> tuple[Any, WorkspacePaths, dict[str, object]]:
    workspace = WorkspacePaths.create(workspace_root)
    secret_store = WindowsEnvironmentSecretStore()
    settings = ProviderSettingsService(workspace, secret_store).get_provider_settings()
    from pelican_town_specials.providers.openai_compatible import (
        OpenAICompatibleGateway,
    )

    gateway = OpenAICompatibleGateway(settings=settings, secret_store=secret_store)
    matcher_config = {
        "base_url": settings.base_url,
        "text_model": settings.text_model,
        "prompt_version": "canonical-match-v1",
        "chat_timeout_seconds": settings.chat_timeout_seconds,
        "max_automatic_retries": settings.max_automatic_retries,
    }
    return gateway, workspace, matcher_config


def build_dry_run_plan(
    *,
    query_count: int = 2,
    canonical_count: int = 2,
) -> dict[str, object]:
    """Validate the wiring shape without models, labels, network, or Memory."""

    if query_count < 0 or canonical_count < 0:
        raise ValueError("dry-run counts must not be negative")
    fixture = build_fixture_registration()
    serialized = serialize_embedding_text(fixture.registration.recall_document)
    return {
        "mode": "dry-run",
        "network": False,
        "memoryWrites": False,
        "modelLoaded": False,
        "plannedLogicalMatcherCalls": query_count if canonical_count >= 2 else 0,
        "queryCount": query_count,
        "canonicalCount": canonical_count,
        "topK": CANONICAL_CANDIDATE_LIMIT,
        "matchThreshold": CANONICAL_MATCH_THRESHOLD,
        "schemaVersion": CANONICAL_REGISTRY_SCHEMA_VERSION,
        "embedding": {
            "model": MODEL_NAME,
            "revision": MODEL_REVISION,
            "device": MODEL_DEVICE,
            "maxSeqLength": MODEL_MAX_SEQ_LENGTH,
            "serializationFields": [
                "name",
                "normalizedIngredients",
                "cuisine",
                "cookingMethods",
            ],
            "sampleTextCharacters": len(serialized.text),
            "sampleTruncated": serialized.truncated,
            "timer": "in-memory retrieval only; matcher/registry reads excluded",
        },
        "exports": [
            "canonicals.jsonl",
            "queries.jsonl",
            "labels.jsonl",
            "seed_manifest.json",
            "current_results.csv",
            "baseline_results.csv",
            "retrieval_comparison.csv",
        ],
    }


def write_templates(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("canonicals.jsonl", "queries.jsonl", "labels.jsonl"):
        if not (output_dir / name).exists():
            (output_dir / name).write_text("", encoding="utf-8")
    template_manifest = SeedManifest(
        schemaVersion=1,
        language=Language.ZH_CN,
        catalogVersion="stardew-1.6.15",
        entries=[],
        createdAt=datetime.now(UTC),
    )
    if not (output_dir / "seed_manifest.json").exists():
        (output_dir / "seed_manifest.json").write_text(
            json.dumps(
                template_manifest.model_dump(by_alias=True, mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    csv_headers = {
        "e2e_results.csv": ["case_id", "completed", "human_pass", "failure_stage"],
        "current_results.csv": [
            "query_id",
            "kind",
            "expected_canonical_id",
            "candidate_ids",
            "selected_id",
            "decision",
            "confidence",
            "error_category",
        ],
        "baseline_results.csv": [
            "query_id",
            "kind",
            "expected_canonical_id",
            "candidate_ids",
            "selected_id",
            "decision",
            "confidence",
            "error_category",
        ],
        "retrieval_comparison.csv": [
            "retriever",
            "positive_hit_success",
            "positive_total",
            "candidate_inclusion",
            "negative_false_hit",
            "negative_total",
            "mean_ms",
            "p50_ms",
            "p95_ms",
            "additional_ram_mib",
            "model_disk_bytes",
            "first_load_seconds",
        ],
    }
    for name, headers in csv_headers.items():
        if (output_dir / name).exists():
            continue
        with (output_dir / name).open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(headers)


def write_results_csv(path: Path, results: Sequence[EvaluationResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "query_id",
        "kind",
        "expected_canonical_id",
        "candidate_ids",
        "selected_id",
        "decision",
        "confidence",
        "error_category",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "query_id": str(result.query_id),
                    "kind": result.kind,
                    "expected_canonical_id": (
                        str(result.expected_canonical_id)
                        if result.expected_canonical_id is not None
                        else ""
                    ),
                    "candidate_ids": json.dumps(
                        [str(value) for value in result.candidate_ids],
                        separators=(",", ":"),
                    ),
                    "selected_id": (
                        str(result.selected_id)
                        if result.selected_id is not None
                        else ""
                    ),
                    "decision": result.decision,
                    "confidence": (
                        str(result.confidence) if result.confidence is not None else ""
                    ),
                    "error_category": result.error_category or "",
                }
            )


def _git_snapshot() -> dict[str, object]:
    def run_git(*arguments: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=_REPO_ROOT,
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()

    commit = run_git("rev-parse", "HEAD")
    status = run_git("status", "--porcelain", "--untracked-files=all")
    return {
        "sourceCommit": commit or "unknown",
        "sourceDirty": bool(status),
        "sourceFilesSha256": _content_fingerprint(
            {str(path): _sha256(path.read_bytes()) for path in _RELEVANT_SOURCE_FILES}
        ),
    }


def _prompt_sha256() -> str | None:
    prompt_path = (
        _BACKEND_SRC
        / "pelican_town_specials"
        / "providers"
        / "prompts"
        / "canonical_match_v1.py"
    )
    if not prompt_path.is_file():
        return None
    return _sha256(prompt_path.read_bytes())


def _bundle_summary(bundle: EvaluationBundle) -> dict[str, object]:
    payload = {
        "canonicals": [
            record.model_dump(by_alias=True, mode="json")
            for record in bundle.canonicals
        ],
        "queries": [
            query.model_dump(by_alias=True, mode="json") for query in bundle.queries
        ],
        "labels": [
            {
                "queryId": str(label.query_id),
                "kind": label.kind,
                "expected": (
                    str(label.expected_canonical_id)
                    if label.expected_canonical_id is not None
                    else None
                ),
            }
            for label in bundle.labels
        ],
        "manifest": (
            bundle.manifest.model_dump(by_alias=True, mode="json")
            if bundle.manifest is not None
            else None
        ),
    }
    positive = sum(label.kind == "positive" for label in bundle.labels)
    negative = sum(label.kind == "negative" for label in bundle.labels)
    return {
        "canonicalCount": len(bundle.canonicals),
        "queryCount": len(bundle.queries),
        "labelCount": len(bundle.labels),
        "positiveCount": positive,
        "negativeCount": negative,
        "fingerprint": _sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ),
    }


def _write_retrieval_timings(
    path: Path, timings: Mapping[str, Mapping[str, object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(timings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_run_metadata(
    path: Path,
    *,
    mode: str,
    bundle: EvaluationBundle,
    live: bool,
    model_revision: str | None = None,
    matcher_config: Mapping[str, object] | None = None,
    timing_path: Path | None = None,
    candidate_snapshot_digest: str | None = None,
    truncation_observations: Mapping[str, object] | None = None,
) -> None:
    git = _git_snapshot()
    manifest = bundle.manifest
    config_summary: dict[str, object] | None = None
    if matcher_config:
        config_summary = {
            key: (
                value
                if key in {"chat_timeout_seconds", "max_automatic_retries"}
                else _sha256(str(value).encode("utf-8"))
            )
            for key, value in matcher_config.items()
            if key
            in {
                "base_url",
                "text_model",
                "prompt_version",
                "user_config_id",
                "chat_timeout_seconds",
                "max_automatic_retries",
            }
        }
    metadata = {
        "schemaVersion": 1,
        **git,
        "mode": mode,
        "language": manifest.language.value if manifest else None,
        "topK": CANONICAL_CANDIDATE_LIMIT,
        "matchThreshold": CANONICAL_MATCH_THRESHOLD,
        "catalogVersion": manifest.catalog_version if manifest else None,
        "data": _bundle_summary(bundle),
        "manifestFingerprint": (
            _sha256(
                json.dumps(
                    manifest.model_dump(by_alias=True, mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            )
            if manifest
            else None
        ),
        "promptSha256": _prompt_sha256(),
        "randomSeed": None,
        "liveProviderRun": live,
        "matcherConfig": config_summary,
        "candidateSnapshotSha256": candidate_snapshot_digest,
        "truncationObservations": truncation_observations,
        "embeddingModel": MODEL_NAME if mode == "embedding" else None,
        "embeddingRevision": model_revision if mode == "embedding" else None,
        "embeddingDevice": MODEL_DEVICE if mode == "embedding" else None,
        "embeddingMaxSeqLength": MODEL_MAX_SEQ_LENGTH if mode == "embedding" else None,
        "cpuThreads": cpu_thread_count(),
        "runtimeVersions": runtime_versions(),
        "labelsMergedAfterRecall": True,
        "formalResults": False,
        "retrievalTimingFile": str(timing_path) if timing_path is not None else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_args() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("dry-run", help="check local templates and planned calls")

    templates = subparsers.add_parser(
        "templates", help="write empty evaluation templates"
    )
    templates.add_argument(
        "--output-dir", type=Path, default=Path("output/evaluation-m12")
    )

    validate = subparsers.add_parser(
        "validate", help="validate JSONL and optional manifest"
    )
    validate.add_argument("--input-dir", type=Path, required=True)
    validate.add_argument("--workspace", type=Path)

    seed = subparsers.add_parser(
        "seed",
        help="explicitly seed small local fixtures into a selected development workspace",
    )
    seed.add_argument("--workspace", type=Path, required=True)
    seed.add_argument("--output-dir", type=Path, default=Path("output/evaluation-m12"))
    seed.add_argument("--count", type=int, default=2)

    run = subparsers.add_parser(
        "run",
        help="plan by default; execute only with explicit --live and --max-calls",
    )
    run.add_argument("--input-dir", type=Path)
    run.add_argument("--workspace", type=Path)
    run.add_argument("--output", type=Path)
    run.add_argument("--mode", choices=("current", "embedding"), default="current")
    run.add_argument("--model-path", type=Path)
    run.add_argument("--max-calls", type=int, default=0)
    run.add_argument("--live", action="store_true")
    run.add_argument("--repetitions", type=int, default=10)
    run.add_argument("--matcher-config-id")
    return parser


def _run_cli(args: argparse.Namespace) -> int:
    if args.command == "dry-run":
        print(json.dumps(build_dry_run_plan(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "templates":
        write_templates(args.output_dir)
        print(json.dumps({"outputDir": str(args.output_dir), "network": False}))
        return 0
    if args.command == "validate":
        bundle = load_evaluation_bundle(args.input_dir, require_manifest=False)
        registry: Any | None = None
        if args.workspace is not None:
            workspace = WorkspacePaths.create(args.workspace)
            registry = SQLiteCanonicalRegistry(workspace)
        if bundle.manifest is not None:
            root = registry._canonical_assets_dir if registry is not None else None
            validate_manifest_files(bundle.manifest, root=root, registry=registry)
        print(
            json.dumps(
                {
                    "valid": True,
                    "canonicals": len(bundle.canonicals),
                    "queries": len(bundle.queries),
                    "labels": len(bundle.labels),
                    "manifest": bundle.manifest is not None,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "seed":
        if args.count < 1:
            raise ValueError("--count must be positive")
        fixtures = tuple(
            build_fixture_registration(
                index=index,
                display_name=("番茄炒蛋" if index == 1 else f"评测家常菜{index}"),
                ingredients=("番茄", "鸡蛋") if index == 1 else ("米饭", "蔬菜"),
            )
            for index in range(1, args.count + 1)
        )
        records = seed_fixtures(args.workspace, args.output_dir, fixtures)
        print(json.dumps({"seeded": len(records), "outputDir": str(args.output_dir)}))
        return 0
    if args.command == "run":
        if args.input_dir is None:
            if args.live:
                raise ValueError("--input-dir is required for a live run")
            print(json.dumps(build_dry_run_plan(), ensure_ascii=False, indent=2))
            return 0
        bundle = load_evaluation_bundle(args.input_dir, require_manifest=True)
        if not args.live:
            print(
                json.dumps(
                    {
                        **build_dry_run_plan(
                            query_count=len(bundle.queries),
                            canonical_count=len(bundle.canonicals),
                        ),
                        "inputDir": str(args.input_dir),
                        "plannedMode": args.mode,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.workspace is None:
            raise ValueError("--workspace is required for a live run")
        if args.max_calls < 1:
            raise ValueError("live runs require a positive --max-calls budget")
        if args.mode == "embedding" and args.model_path is None:
            raise ValueError("embedding runs require an explicit offline --model-path")
        workspace = WorkspacePaths.create(args.workspace)
        manifest = cast(SeedManifest, bundle.manifest)
        registry = ManifestRepository(
            SQLiteCanonicalRegistry(workspace),
            manifest,
            root=workspace.canonical_assets_dir,
            canonicals=bundle.canonicals,
        )
        candidates = registry.list_recall_candidate_pool(
            language=manifest.language,
            catalog_version=manifest.catalog_version,
        )
        gateway, _, matcher_config = _build_live_gateway(args.workspace)
        if args.matcher_config_id:
            matcher_config["user_config_id"] = args.matcher_config_id
        if args.mode == "current":
            retriever: CanonicalRetriever = CandidateRetriever()
            model_revision = None
        else:
            model, _ = load_cpu_model(args.model_path)
            embedding_retriever = CpuEmbeddingRetriever(model)
            embedding_retriever.prepare(
                candidates,
                language=manifest.language,
                catalog_version=manifest.catalog_version,
            )
            retriever = embedding_retriever
            model_revision = resolve_model_revision(args.model_path)
        timings = measure_query_retrieval(
            retriever=retriever,
            queries=bundle.queries,
            candidates=candidates,
            repetitions=args.repetitions,
            language=manifest.language,
            catalog_version=manifest.catalog_version,
        )
        results = asyncio.run(
            execute_recall(
                registry=registry,
                matcher=gateway,
                retriever=retriever,
                queries=bundle.queries,
                labels=bundle.labels,
                max_calls=args.max_calls,
            )
        )
        output_path = args.output or (args.input_dir / f"{args.mode}_results.csv")
        write_results_csv(output_path, results)
        timing_path = output_path.with_name(f"retrieval-{args.mode}.json")
        _write_retrieval_timings(timing_path, timings)
        _write_run_metadata(
            output_path.with_name(f"run-{args.mode}.json"),
            mode=args.mode,
            bundle=bundle,
            live=True,
            model_revision=model_revision,
            matcher_config=matcher_config,
            timing_path=timing_path,
            candidate_snapshot_digest=registry.snapshot_digest,
            truncation_observations=(
                retriever.observations([query.analysis for query in bundle.queries])
                if isinstance(retriever, CpuEmbeddingRetriever)
                else None
            ),
        )
        print(json.dumps({"results": len(results), "output": str(output_path)}))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parse_args()
    try:
        return _run_cli(parser.parse_args(argv))
    except (EvaluationInputError, FileNotFoundError, ValueError) as exc:
        print(f"evaluation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
