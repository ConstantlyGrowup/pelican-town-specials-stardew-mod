"""Validated static float32 catalog index and deterministic exact scan."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pelican_town_specials.catalog.repository import VanillaCatalog

from . import constants


class IndexCompatibilityError(ValueError):
    """Static resources do not match the frozen catalog/model contract."""

    reason_code = "rag_index_invalid"

    def __init__(self, message: str = "rag_index_invalid") -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class IndexArtifacts:
    manifest_path: Path
    vector_path: Path
    manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StaticIngredientIndex:
    item_ids: tuple[str, ...]
    vectors: np.ndarray

    def __post_init__(self) -> None:
        matrix = np.asarray(self.vectors)
        if (
            len(self.item_ids) != constants.CATALOG_ELIGIBLE_ROWS
            or matrix.shape
            != (constants.CATALOG_ELIGIBLE_ROWS, constants.EMBEDDING_DIMENSION)
            or matrix.dtype.kind != "f"
            or matrix.dtype.itemsize != 4
            or len(set(self.item_ids)) != len(self.item_ids)
            or not np.isfinite(matrix).all()
        ):
            raise IndexCompatibilityError()
        norms = np.linalg.norm(matrix.astype(np.float64), axis=1)
        if not np.all(np.isclose(norms, 1.0, rtol=1e-4, atol=1e-4)):
            raise IndexCompatibilityError()
        normalized = np.asarray(matrix, dtype="<f4")
        normalized.setflags(write=False)
        object.__setattr__(self, "vectors", normalized)

    def search(
        self,
        query_vector: np.ndarray,
        *,
        top_k: int = constants.TOP_K,
        excluded_item_ids: frozenset[str] = frozenset(),
    ) -> list[tuple[str, float]]:
        """Return a stable exact cosine ranking, filling after exclusions."""
        query = np.asarray(query_vector, dtype=np.float32)
        if query.shape != (constants.EMBEDDING_DIMENSION,) or not np.isfinite(query).all():
            raise IndexCompatibilityError()
        norm = float(np.linalg.norm(query.astype(np.float64)))
        if not math.isfinite(norm) or norm <= 0:
            raise IndexCompatibilityError()
        normalized_query = query / np.float32(norm)
        similarities = self.vectors @ normalized_query
        ranked = sorted(
            (
                (item_id, float(similarities[index]))
                for index, item_id in enumerate(self.item_ids)
                if item_id not in excluded_item_ids
            ),
            key=lambda hit: (-hit[1], _item_id_sort_key(hit[0])),
        )
        return ranked[: max(0, top_k)]


def write_index_artifacts(
    *,
    catalog_path: Path,
    output_dir: Path,
    embeddings: np.ndarray,
    model_path: Path,
    tokenizer_path: Path,
) -> IndexArtifacts:
    """Write the little-endian normalized flat vectors and strict manifest."""
    catalog_bytes = _read_bytes(catalog_path)
    catalog_sha256 = _sha256_bytes(catalog_bytes)
    if catalog_sha256 != constants.CATALOG_SHA256:
        raise IndexCompatibilityError()
    catalog = VanillaCatalog.from_json(catalog_path)
    item_ids = tuple(item.item_id for item in catalog.ingredients)
    if catalog.version != constants.CATALOG_VERSION or len(item_ids) != 253:
        raise IndexCompatibilityError()

    matrix = _normalized_matrix(embeddings, item_ids)
    vector_bytes = np.asarray(matrix, dtype="<f4").tobytes(order="C")
    if len(vector_bytes) != constants.CATALOG_ELIGIBLE_ROWS * constants.EMBEDDING_DIMENSION * 4:
        raise IndexCompatibilityError()

    model_sha256 = _sha256_file(model_path)
    tokenizer_sha256 = _sha256_file(tokenizer_path)
    if tokenizer_sha256 != constants.TOKENIZER_SHA256:
        raise IndexCompatibilityError()

    output_dir.mkdir(parents=True, exist_ok=True)
    vector_path = output_dir / constants.VECTOR_FILE_NAME
    manifest_path = output_dir / constants.MANIFEST_FILE_NAME
    vector_sha256 = _sha256_bytes(vector_bytes)
    manifest: dict[str, Any] = {
        "schemaVersion": constants.MANIFEST_SCHEMA_VERSION,
        "retrievalConfigVersion": constants.RETRIEVAL_CONFIG_VERSION,
        "catalogVersion": catalog.version,
        "catalogSha256": catalog_sha256,
        "modelId": constants.MODEL_ID,
        "modelRevision": constants.MODEL_REVISION,
        "sourceModelSha256": constants.SOURCE_MODEL_SHA256,
        "modelSha256": model_sha256,
        "tokenizerSha256": tokenizer_sha256,
        "tokenizerFormat": constants.TOKENIZER_FORMAT,
        "queryPrefix": constants.QUERY_PREFIX,
        "passageTemplateVersion": constants.PASSAGE_TEMPLATE_VERSION,
        "normalizationVersion": constants.NORMALIZATION_VERSION,
        "maxSequenceLength": constants.MAX_SEQUENCE_LENGTH,
        "embeddingDimension": constants.EMBEDDING_DIMENSION,
        "dtype": constants.VECTOR_DTYPE,
        "rowCount": len(item_ids),
        "itemIds": list(item_ids),
        "vectorBytes": len(vector_bytes),
        "vectorSha256": vector_sha256,
        "topK": constants.TOP_K,
        "quantization": {
            "method": "onnxruntime.quantize_dynamic",
            "weightType": "QInt8",
            "perChannel": True,
            "opTypes": list(constants.QUANTIZED_OP_TYPES),
            "onnxruntimeVersion": constants.ONNXRUNTIME_VERSION,
            "onnxVersion": constants.ONNX_VERSION,
        },
        "sentencepieceVersion": constants.SENTENCEPIECE_VERSION,
        "numpyVersion": constants.NUMPY_VERSION,
        "builderVersion": constants.BUILDER_VERSION,
    }
    _atomic_write(vector_path, vector_bytes)
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_write(manifest_path, manifest_bytes)
    return IndexArtifacts(
        manifest_path=manifest_path,
        vector_path=vector_path,
        manifest=manifest,
    )


def load_static_index(
    *,
    catalog: VanillaCatalog,
    catalog_path: Path,
    manifest_path: Path,
    vector_path: Path,
    model_path: Path,
    tokenizer_path: Path,
) -> StaticIngredientIndex:
    """Validate every packed input against code-owned frozen expectations."""
    try:
        manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IndexCompatibilityError() from exc
    if not isinstance(manifest_raw, dict) or set(manifest_raw) != _MANIFEST_FIELDS:
        raise IndexCompatibilityError()
    manifest = manifest_raw

    catalog_bytes = _read_bytes(catalog_path)
    catalog_sha256 = _sha256_bytes(catalog_bytes)
    catalog_item_ids = tuple(item.item_id for item in catalog.ingredients)
    if (
        catalog.version != constants.CATALOG_VERSION
        or catalog_sha256 != constants.CATALOG_SHA256
        or manifest["catalogVersion"] != catalog.version
        or manifest["catalogSha256"] != catalog_sha256
        or manifest["itemIds"] != list(catalog_item_ids)
        or len(catalog_item_ids) != constants.CATALOG_ELIGIBLE_ROWS
    ):
        raise IndexCompatibilityError()

    expected_fields: dict[str, Any] = {
        "schemaVersion": constants.MANIFEST_SCHEMA_VERSION,
        "retrievalConfigVersion": constants.RETRIEVAL_CONFIG_VERSION,
        "modelId": constants.MODEL_ID,
        "modelRevision": constants.MODEL_REVISION,
        "sourceModelSha256": constants.SOURCE_MODEL_SHA256,
        "tokenizerSha256": constants.TOKENIZER_SHA256,
        "tokenizerFormat": constants.TOKENIZER_FORMAT,
        "queryPrefix": constants.QUERY_PREFIX,
        "passageTemplateVersion": constants.PASSAGE_TEMPLATE_VERSION,
        "normalizationVersion": constants.NORMALIZATION_VERSION,
        "maxSequenceLength": constants.MAX_SEQUENCE_LENGTH,
        "embeddingDimension": constants.EMBEDDING_DIMENSION,
        "dtype": constants.VECTOR_DTYPE,
        "rowCount": constants.CATALOG_ELIGIBLE_ROWS,
        "vectorBytes": constants.CATALOG_ELIGIBLE_ROWS
        * constants.EMBEDDING_DIMENSION
        * 4,
        "topK": constants.TOP_K,
        "quantization": {
            "method": "onnxruntime.quantize_dynamic",
            "weightType": "QInt8",
            "perChannel": True,
            "opTypes": list(constants.QUANTIZED_OP_TYPES),
            "onnxruntimeVersion": constants.ONNXRUNTIME_VERSION,
            "onnxVersion": constants.ONNX_VERSION,
        },
        "sentencepieceVersion": constants.SENTENCEPIECE_VERSION,
        "numpyVersion": constants.NUMPY_VERSION,
        "builderVersion": constants.BUILDER_VERSION,
    }
    if any(manifest.get(key) != value for key, value in expected_fields.items()):
        raise IndexCompatibilityError()

    model_sha256 = _sha256_file(model_path)
    tokenizer_sha256 = _sha256_file(tokenizer_path)
    vector_bytes = _read_bytes(vector_path)
    vector_sha256 = _sha256_bytes(vector_bytes)
    if (
        manifest["modelSha256"] != model_sha256
        or manifest["tokenizerSha256"] != tokenizer_sha256
        or manifest["vectorSha256"] != vector_sha256
        or (constants.QUANTIZED_MODEL_SHA256 and model_sha256 != constants.QUANTIZED_MODEL_SHA256)
        or (constants.VECTOR_INDEX_SHA256 and vector_sha256 != constants.VECTOR_INDEX_SHA256)
        or manifest["vectorBytes"] != len(vector_bytes)
    ):
        raise IndexCompatibilityError()

    expected_bytes = constants.CATALOG_ELIGIBLE_ROWS * constants.EMBEDDING_DIMENSION * 4
    if len(vector_bytes) != expected_bytes:
        raise IndexCompatibilityError()
    vectors = np.frombuffer(vector_bytes, dtype="<f4").reshape(
        constants.CATALOG_ELIGIBLE_ROWS, constants.EMBEDDING_DIMENSION
    )
    return StaticIngredientIndex(item_ids=catalog_item_ids, vectors=vectors)


def _normalized_matrix(embeddings: np.ndarray, item_ids: tuple[str, ...]) -> np.ndarray:
    matrix = np.asarray(embeddings, dtype=np.float32)
    if (
        matrix.shape != (len(item_ids), constants.EMBEDDING_DIMENSION)
        or not np.isfinite(matrix).all()
    ):
        raise IndexCompatibilityError()
    norms = np.linalg.norm(matrix.astype(np.float64), axis=1, keepdims=True)
    if not np.isfinite(norms).all() or (norms <= 0).any():
        raise IndexCompatibilityError()
    return np.asarray(matrix / norms.astype(np.float32), dtype="<f4")


def _item_id_sort_key(item_id: str) -> tuple[int, int | str, str]:
    try:
        return (0, int(item_id), item_id)
    except ValueError:
        return (1, item_id.casefold(), item_id)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise IndexCompatibilityError() from exc
    return digest.hexdigest().upper()


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise IndexCompatibilityError() from exc


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


_MANIFEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "retrievalConfigVersion",
        "catalogVersion",
        "catalogSha256",
        "modelId",
        "modelRevision",
        "sourceModelSha256",
        "modelSha256",
        "tokenizerSha256",
        "tokenizerFormat",
        "queryPrefix",
        "passageTemplateVersion",
        "normalizationVersion",
        "maxSequenceLength",
        "embeddingDimension",
        "dtype",
        "rowCount",
        "itemIds",
        "vectorBytes",
        "vectorSha256",
        "topK",
        "quantization",
        "sentencepieceVersion",
        "numpyVersion",
        "builderVersion",
    }
)
