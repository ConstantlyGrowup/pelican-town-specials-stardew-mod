"""Development-only CPU embedding baseline for Milestone 12.

This module is intentionally independent from the production import graph.  The
Sentence Transformers dependency is imported only when a caller explicitly
loads a local model for an evaluation smoke or run.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol, cast
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_SRC = _REPO_ROOT / "backend" / "src"
if str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

from pelican_town_specials.application.canonical_memory import (
    RankedCanonicalCandidate,
    normalize_recall_text,
)
from pelican_town_specials.domain.canonical import (
    CanonicalRecallCandidate,
    RecallDocument,
)
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.dish import DishAnalysis

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_DEVICE = "cpu"
MODEL_MAX_SEQ_LENGTH = 128
DEFAULT_TOP_K = 5
DEFAULT_REPETITIONS = 10
DEFAULT_MAX_TEXT_CHARACTERS = 2048


class EmbeddingModel(Protocol):
    max_seq_length: int

    def encode(self, sentences: str | list[str], **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class SerializedEmbeddingText:
    text: str
    original_length: int
    truncated: bool
    max_characters: int


@dataclass(frozen=True)
class RetrievalTiming:
    repetitions: int
    samples_ms: tuple[float, ...]
    mean_ms: float
    p50_ms: float
    p95_ms: float


@dataclass(frozen=True)
class EmbeddingResourceSnapshot:
    common_runtime_rss_mib: float
    loaded_model_rss_mib: float
    cache_ready_rss_mib: float
    warmed_rss_mib: float
    additional_rss_mib: float
    model_disk_bytes: int
    first_load_seconds: float
    model_name: str
    model_revision: str
    device: str
    max_seq_length: int
    embedding_dimension: int | None
    token_truncation_count: int
    cpu_threads: int | None
    runtime_versions: dict[str, str]
    corpus_observations: dict[str, object] = field(default_factory=dict)
    query_observations: dict[str, object] = field(default_factory=dict)
    cache_additional_rss_mib: float = 0.0


def _embedding_fields(
    value: RecallDocument | DishAnalysis,
) -> tuple[str, list[str], str, list[str]]:
    if isinstance(value, RecallDocument):
        name = value.normalized_name
        ingredients = [
            ingredient.normalized_name or ingredient.name
            for ingredient in value.semantic_ingredients
        ]
        cuisine = value.cuisine
        methods = list(value.cooking_methods)
    else:
        name = value.recognized_dish
        ingredients = [
            ingredient.normalized_name or ingredient.name
            for ingredient in value.semantic_ingredients
        ]
        cuisine = value.cuisine
        methods = list(value.cooking_methods)
    return name, ingredients, cuisine or "", methods


def serialize_embedding_text(
    value: RecallDocument | DishAnalysis,
    *,
    max_characters: int = DEFAULT_MAX_TEXT_CHARACTERS,
) -> SerializedEmbeddingText:
    """Serialize the four frozen semantic fields in a stable order.

    IDs, labels, summaries, flavor profile, gameplay, and provider metadata are
    deliberately absent.  Character truncation is recorded in the returned
    value; token truncation remains the model's fixed 128-token boundary and is
    reported in run metadata.
    """

    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    name, ingredients, cuisine, methods = _embedding_fields(value)
    fields = (
        f"name={normalize_recall_text(name)}",
        "ingredients=" + ",".join(normalize_recall_text(item) for item in ingredients),
        f"cuisine={normalize_recall_text(cuisine)}",
        "cookingMethods=" + ",".join(normalize_recall_text(item) for item in methods),
    )
    text = ";".join(fields)
    original_length = len(text)
    truncated = original_length > max_characters
    if truncated:
        text = text[:max_characters]
    return SerializedEmbeddingText(
        text=text,
        original_length=original_length,
        truncated=truncated,
        max_characters=max_characters,
    )


def serialize_recall_document(
    value: RecallDocument | DishAnalysis,
    *,
    max_characters: int = DEFAULT_MAX_TEXT_CHARACTERS,
) -> str:
    """Return the stable embedding input string without evaluation metadata."""

    return serialize_embedding_text(value, max_characters=max_characters).text


def _normalise_vector(vector: Iterable[float]) -> tuple[float, ...]:
    values = tuple(float(item) for item in vector)
    norm = sum(item * item for item in values) ** 0.5
    if not values or norm == 0.0:
        raise ValueError("embedding vector must be non-empty and non-zero")
    return tuple(item / norm for item in values)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have matching dimensions")
    return sum(a * b for a, b in zip(left, right, strict=True))


def linear_percentile(samples: Sequence[float], percentile: float) -> float:
    """Return a deterministic percentile using linear interpolation."""

    if not samples:
        raise ValueError("at least one timing sample is required")
    if not 0 <= percentile <= 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(float(value) for value in samples)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarise_timings(samples_ms: Sequence[float]) -> RetrievalTiming:
    if not samples_ms:
        raise ValueError("at least one timing sample is required")
    values = tuple(float(value) for value in samples_ms)
    return RetrievalTiming(
        repetitions=len(values),
        samples_ms=values,
        mean_ms=sum(values) / len(values),
        p50_ms=linear_percentile(values, 50),
        p95_ms=linear_percentile(values, 95),
    )


def measure_retrieval(
    operation: Any,
    *,
    repetitions: int = DEFAULT_REPETITIONS,
    warmup: int = 1,
) -> RetrievalTiming:
    """Measure only an in-memory retrieval operation after warmup."""

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    if warmup < 0:
        raise ValueError("warmup must not be negative")
    for _ in range(warmup):
        operation()
    samples: list[float] = []
    for _ in range(repetitions):
        started = perf_counter()
        operation()
        samples.append((perf_counter() - started) * 1000)
    return summarise_timings(samples)


_MODEL_FILE_ALLOWLIST = {
    "modules.json",
    "config.json",
    "config_sentence_transformers.json",
    "sentence_bert_config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
    "unigram.json",
    "1_Pooling/config.json",
}


def _used_file_bytes(root: Path) -> int:
    if not root.exists():
        raise FileNotFoundError(root)
    seen: set[tuple[int, int]] = set()
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.relative_to(root).as_posix() not in _MODEL_FILE_ALLOWLIST:
            continue
        stat = path.stat()
        identity = (int(stat.st_dev), int(stat.st_ino))
        if identity in seen:
            continue
        seen.add(identity)
        total += stat.st_size
    return total


def _rss_mib() -> float:
    psutil = importlib.import_module("psutil")
    process = psutil.Process(os.getpid())
    return float(process.memory_info().rss) / (1024 * 1024)


def _runtime_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for module_name in (
        "torch",
        "sentence_transformers",
        "transformers",
        "huggingface_hub",
        "numpy",
        "psutil",
    ):
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", None)
            if isinstance(version, str):
                versions[module_name] = version
        except (ImportError, AttributeError, OSError, RuntimeError):
            continue
    return versions


def runtime_versions() -> dict[str, str]:
    """Return versions of the optional evaluation runtime components."""

    return _runtime_versions()


def _cpu_thread_count() -> int | None:
    try:
        torch = importlib.import_module("torch")
        return int(torch.get_num_threads())
    except (ImportError, AttributeError, OSError, RuntimeError):
        return None


def cpu_thread_count() -> int | None:
    """Return the active torch CPU thread count for run metadata."""

    return _cpu_thread_count()


def resolve_model_revision(
    model_path: Path | None,
    requested_revision: str = MODEL_REVISION,
) -> str:
    """Resolve the immutable revision represented by a prepared model path."""

    if model_path is not None:
        path_revision = model_path.expanduser().resolve().name
        if len(path_revision) == 40 and all(
            character in "0123456789abcdef" for character in path_revision
        ):
            return path_revision
    return requested_revision


def load_cpu_model(
    model_path: Path | None = None,
    *,
    allow_download: bool = False,
    model_name: str = MODEL_NAME,
    revision: str = MODEL_REVISION,
) -> tuple[EmbeddingModel, float]:
    """Load one CPU model, requiring an explicit local path by default."""

    if model_path is not None:
        resolved = model_path.expanduser().resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(
                f"embedding model directory does not exist: {resolved}"
            )
        source: str = str(resolved)
    elif allow_download:
        source = model_name
    else:
        raise ValueError(
            "offline embedding use requires --model-path; pass --allow-download explicitly"
        )

    started = perf_counter()
    sentence_transformers = importlib.import_module("sentence_transformers")
    sentence_transformer_type = sentence_transformers.SentenceTransformer
    kwargs: dict[str, Any] = {
        "device": MODEL_DEVICE,
        "trust_remote_code": False,
        "revision": revision,
    }
    if model_path is not None and not allow_download:
        # This is understood by the Hugging Face-backed modules used by the
        # pinned model.  It prevents a missing optional file from triggering a
        # network lookup in ordinary offline evaluation.
        kwargs["local_files_only"] = True
    model = cast(
        EmbeddingModel,
        sentence_transformer_type(source, **kwargs),
    )
    elapsed = perf_counter() - started
    # The model card's 128-token boundary is part of this baseline.  Avoid
    # silently accepting a larger runtime boundary from another local model.
    if hasattr(model, "max_seq_length"):
        model.max_seq_length = MODEL_MAX_SEQ_LENGTH
    return model, elapsed


def _token_count(model: EmbeddingModel, text: str) -> int | None:
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None or not callable(tokenizer):
        return None
    try:
        encoded = tokenizer(text, truncation=False, add_special_tokens=True)
        input_ids = encoded.get("input_ids") if isinstance(encoded, Mapping) else None
        if hasattr(input_ids, "shape"):
            shape = tuple(int(value) for value in input_ids.shape)
            return shape[-1] if shape else None
        if isinstance(input_ids, list) and input_ids and isinstance(input_ids[0], list):
            input_ids = input_ids[0]
        return len(input_ids) if isinstance(input_ids, list) else None
    except (TypeError, ValueError, RuntimeError):
        return None


def _is_token_truncated(model: EmbeddingModel, text: str) -> bool:
    count = _token_count(model, text)
    if count is None:
        return False
    return count > MODEL_MAX_SEQ_LENGTH


def encode_normalized(
    model: EmbeddingModel, texts: Sequence[str]
) -> list[tuple[float, ...]]:
    if not texts:
        return []
    encoded = model.encode(
        list(texts),
        device=MODEL_DEVICE,
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
    )
    rows = encoded.tolist() if hasattr(encoded, "tolist") else encoded
    if len(texts) == 1 and rows and isinstance(rows[0], (int, float)):
        rows = [rows]
    return [_normalise_vector(row) for row in rows]


def embedding_dimension(model: EmbeddingModel) -> int | None:
    """Read the embedding width across supported Sentence Transformers APIs."""

    getter = getattr(model, "get_embedding_dimension", None)
    if not callable(getter):
        getter = getattr(model, "get_sentence_embedding_dimension", None)
    if not callable(getter):
        return None
    raw_dimension = getter()
    return int(raw_dimension) if raw_dimension is not None else None


class CpuEmbeddingRetriever:
    """In-memory, normalized cosine Top-K retriever for evaluation only."""

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        top_k: int = DEFAULT_TOP_K,
        max_text_characters: int = DEFAULT_MAX_TEXT_CHARACTERS,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self._model = model
        self._top_k = top_k
        self._max_text_characters = max_text_characters
        self._corpus_ids: tuple[UUID, ...] = ()
        self._corpus: tuple[
            tuple[CanonicalRecallCandidate, tuple[float, ...]], ...
        ] = ()
        self.truncation_events: list[SerializedEmbeddingText] = []
        self.token_truncation_count = 0

    def prepare(
        self,
        candidates: Iterable[CanonicalRecallCandidate],
        *,
        language: Language | None = None,
        catalog_version: str | None = None,
    ) -> None:
        compatible = [
            candidate
            for candidate in candidates
            if (language is None or candidate.language is language)
            and (
                catalog_version is None or candidate.catalog_version == catalog_version
            )
        ]
        texts: list[str] = []
        self.truncation_events = []
        for candidate in compatible:
            serialized = serialize_embedding_text(
                candidate.recall_document,
                max_characters=self._max_text_characters,
            )
            texts.append(serialized.text)
            if serialized.truncated:
                self.truncation_events.append(serialized)
        vectors = encode_normalized(self._model, texts)
        self._corpus = tuple(zip(compatible, vectors, strict=True))
        self._corpus_ids = tuple(candidate.canonical_id for candidate in compatible)
        self.token_truncation_count = sum(
            _is_token_truncated(self._model, text) for text in texts
        )

    def retrieve(
        self,
        analysis: DishAnalysis,
        candidates: Iterable[CanonicalRecallCandidate],
        *,
        language: Language | None = None,
        catalog_version: str | None = None,
    ) -> list[RankedCanonicalCandidate]:
        pool = list(candidates)
        compatible = [
            candidate
            for candidate in pool
            if (language is None or candidate.language is language)
            and (
                catalog_version is None or candidate.catalog_version == catalog_version
            )
        ]
        compatible_ids = tuple(candidate.canonical_id for candidate in compatible)
        if compatible_ids != self._corpus_ids:
            self.prepare(
                compatible,
                language=None,
                catalog_version=None,
            )
        if not self._corpus:
            return []
        serialized = serialize_embedding_text(
            analysis,
            max_characters=self._max_text_characters,
        )
        if serialized.truncated:
            self.truncation_events.append(serialized)
        if _is_token_truncated(self._model, serialized.text):
            self.token_truncation_count += 1
        query_vector = encode_normalized(self._model, [serialized.text])[0]
        ranked: list[RankedCanonicalCandidate] = []
        for candidate, vector in self._corpus:
            score = cosine_similarity(query_vector, vector)
            ranked.append(
                RankedCanonicalCandidate(
                    candidate=candidate,
                    ingredient_score=score,
                    name_score=score,
                    context_score=score,
                    score=score,
                )
            )
        ranked.sort(
            key=lambda item: (
                -item.score,
                item.candidate.registered_at,
                str(item.candidate.canonical_id),
            )
        )
        return ranked[: self._top_k]

    @property
    def model(self) -> EmbeddingModel:
        return self._model

    @property
    def top_k(self) -> int:
        return self._top_k

    def observations(self, analyses: Sequence[DishAnalysis]) -> dict[str, object]:
        """Describe each frozen input once, independent of timing repetitions."""
        return {
            "corpus": truncation_observations(
                self._model,
                [
                    serialize_embedding_text(
                        item.recall_document, max_characters=self._max_text_characters
                    )
                    for item, _ in self._corpus
                ],
            ),
            "queries": truncation_observations(
                self._model,
                [
                    serialize_embedding_text(
                        item, max_characters=self._max_text_characters
                    )
                    for item in analyses
                ],
            ),
        }


def truncation_observations(
    model: EmbeddingModel, texts: Sequence[SerializedEmbeddingText]
) -> dict[str, object]:
    tokens = [_token_count(model, item.text) for item in texts]
    return {
        "count": len(texts),
        "characterTruncatedCount": sum(item.truncated for item in texts),
        "tokenTruncatedCount": sum(
            count is not None and count > MODEL_MAX_SEQ_LENGTH for count in tokens
        ),
        "tokenCountUnavailable": sum(count is None for count in tokens),
        "originalCharacterLengths": [item.original_length for item in texts],
        "encodedCharacterLengths": [len(item.text) for item in texts],
        "tokenCountsBeforeModelTruncation": tokens,
    }


def load_smoke_texts(path: Path) -> tuple[list[str], list[str]]:
    """Read serialized four-field corpus/query inputs for a fresh-process smoke."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"corpus", "queries"}:
        raise ValueError("smoke input must contain corpus and queries")
    for value in payload.values():
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(text, str) or not text for text in value)
        ):
            raise ValueError("smoke corpus and queries must be nonempty string lists")
    return payload["corpus"], payload["queries"]


def _bounded_text(text: str) -> SerializedEmbeddingText:
    return SerializedEmbeddingText(
        text[:DEFAULT_MAX_TEXT_CHARACTERS],
        len(text),
        len(text) > DEFAULT_MAX_TEXT_CHARACTERS,
        DEFAULT_MAX_TEXT_CHARACTERS,
    )


def measure_model_smoke(
    model_path: Path,
    *,
    revision: str = MODEL_REVISION,
    texts: Sequence[str] = (
        "name=番茄炒蛋;ingredients=番茄,鸡蛋;cuisine=家常菜;cookingMethods=炒",
    ),
    corpus: Sequence[str] | None = None,
    queries: Sequence[str] | None = None,
) -> EmbeddingResourceSnapshot:
    """Load and encode a tiny local sample, returning non-formal resources."""

    effective_revision = resolve_model_revision(model_path, revision)
    common_rss = _rss_mib()
    model, first_load_seconds = load_cpu_model(
        model_path,
        revision=effective_revision,
    )
    loaded_rss = _rss_mib()
    corpus_inputs = [
        _bounded_text(text) for text in (corpus if corpus is not None else texts)
    ]
    query_inputs = [
        _bounded_text(text) for text in (queries if queries is not None else texts)
    ]
    corpus_vectors = encode_normalized(model, [item.text for item in corpus_inputs])
    cache_ready_rss = _rss_mib()
    for item in query_inputs:
        vector = encode_normalized(model, [item.text])[0]
        sorted(cosine_similarity(vector, cached) for cached in corpus_vectors)
    warmed_rss = _rss_mib()
    corpus_observations = truncation_observations(model, corpus_inputs)
    query_observations = truncation_observations(model, query_inputs)
    dimension = embedding_dimension(model)
    return EmbeddingResourceSnapshot(
        common_runtime_rss_mib=common_rss,
        loaded_model_rss_mib=loaded_rss,
        cache_ready_rss_mib=cache_ready_rss,
        warmed_rss_mib=warmed_rss,
        additional_rss_mib=max(0.0, warmed_rss - common_rss),
        cache_additional_rss_mib=max(0.0, cache_ready_rss - common_rss),
        corpus_observations=corpus_observations,
        query_observations=query_observations,
        model_disk_bytes=_used_file_bytes(model_path),
        first_load_seconds=first_load_seconds,
        model_name=MODEL_NAME,
        model_revision=effective_revision,
        device=MODEL_DEVICE,
        max_seq_length=MODEL_MAX_SEQ_LENGTH,
        embedding_dimension=dimension,
        token_truncation_count=sum(
            _is_token_truncated(model, item.text)
            for item in corpus_inputs + query_inputs
        ),
        cpu_threads=_cpu_thread_count(),
        runtime_versions=_runtime_versions(),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    smoke = subparsers.add_parser(
        "smoke",
        help="load one local CPU model and encode a tiny non-formal sample",
    )
    smoke.add_argument("--model-path", type=Path)
    smoke.add_argument("--revision", default=MODEL_REVISION)
    smoke.add_argument(
        "--inputs", type=Path, help="JSON with serialized corpus and queries arrays"
    )
    smoke.add_argument(
        "--allow-download",
        action="store_true",
        help="explicitly permit resolving the model name when --model-path is omitted",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "smoke":
        if args.model_path is None and not args.allow_download:
            raise SystemExit(
                "smoke requires --model-path unless --allow-download is explicit"
            )
        if args.model_path is not None:
            corpus, queries = (
                load_smoke_texts(args.inputs) if args.inputs else (None, None)
            )
            snapshot = measure_model_smoke(
                args.model_path, revision=args.revision, corpus=corpus, queries=queries
            )
        else:
            if args.inputs:
                raise SystemExit(
                    "corpus resource measurements require a prepared local --model-path"
                )
            common_rss = _rss_mib()
            model, first_load_seconds = load_cpu_model(
                None,
                allow_download=True,
                revision=args.revision,
            )
            loaded_rss = _rss_mib()
            encode_normalized(
                model,
                [
                    "name=番茄炒蛋;ingredients=番茄,鸡蛋;cuisine=家常菜;cookingMethods=炒"
                ],
            )
            warmed_rss = _rss_mib()
            snapshot = EmbeddingResourceSnapshot(
                common_runtime_rss_mib=common_rss,
                loaded_model_rss_mib=loaded_rss,
                cache_ready_rss_mib=loaded_rss,
                warmed_rss_mib=warmed_rss,
                additional_rss_mib=max(0.0, loaded_rss - common_rss),
                model_disk_bytes=0,
                first_load_seconds=first_load_seconds,
                model_name=MODEL_NAME,
                model_revision=args.revision,
                device=MODEL_DEVICE,
                max_seq_length=MODEL_MAX_SEQ_LENGTH,
                embedding_dimension=embedding_dimension(model),
                token_truncation_count=0,
                cpu_threads=_cpu_thread_count(),
                runtime_versions=_runtime_versions(),
            )
        print(json.dumps(snapshot.__dict__, ensure_ascii=False, indent=2, default=str))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
