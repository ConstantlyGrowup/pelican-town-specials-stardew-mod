"""Lazy CPU-only ONNX Runtime encoder for the pinned multilingual E5 model."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np

from . import constants
from .errors import IngredientRagUnavailable


class OnnxE5Encoder:
    """Mean-pool masked token embeddings and return a unit 384-vector."""

    __slots__ = ("_input_names", "_lock", "_session", "_tokenizer")

    def __init__(self, *, model_path: Path, tokenizer_path: Path) -> None:
        try:
            import onnxruntime as ort  # type: ignore[import-untyped]
            from sentencepiece import SentencePieceProcessor

            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            session = ort.InferenceSession(
                str(model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            tokenizer = SentencePieceProcessor(model_file=str(tokenizer_path))
            input_names = frozenset(value.name for value in session.get_inputs())
            if not {"input_ids", "attention_mask"}.issubset(input_names):
                raise ValueError("ONNX model inputs do not match E5 contract")
        except Exception as exc:
            raise IngredientRagUnavailable("rag_model_unavailable") from exc

        self._lock = RLock()
        self._session = session
        self._tokenizer = tokenizer
        self._input_names = input_names

    def encode(self, text: str) -> np.ndarray:
        try:
            input_ids_list = sentencepiece_input_ids(self._tokenizer, text)
            input_ids = np.asarray([input_ids_list], dtype=np.int64)
            attention_mask = np.ones_like(input_ids, dtype=np.int64)
            with self._lock:
                feed = {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                }
                if "token_type_ids" in self._input_names:
                    feed["token_type_ids"] = np.asarray(
                        np.zeros_like(input_ids), dtype=np.int64
                    )
                output = self._session.run(None, feed)[0]
            token_embeddings = np.asarray(output, dtype=np.float32)
            if (
                token_embeddings.ndim != 3
                or token_embeddings.shape[0] != 1
                or token_embeddings.shape[2] != constants.EMBEDDING_DIMENSION
            ):
                raise ValueError("ONNX output does not match E5 embedding contract")
            mask = attention_mask.astype(np.float32)[..., None]
            denominator = float(mask.sum())
            if denominator <= 0:
                raise ValueError("tokenizer returned an empty attention mask")
            pooled = (token_embeddings * mask).sum(axis=1)[0] / denominator
            norm = float(np.linalg.norm(pooled.astype(np.float64)))
            if not np.isfinite(pooled).all() or not np.isfinite(norm) or norm <= 0:
                raise ValueError("ONNX output could not be normalized")
            return np.asarray(pooled / np.float32(norm), dtype=np.float32)
        except IngredientRagUnavailable:
            raise
        except Exception as exc:
            raise IngredientRagUnavailable("rag_query_failed") from exc


def sentencepiece_input_ids(
    tokenizer: Any, text: str
) -> list[int]:
    """Apply the frozen XLM-R postprocessor around the pinned SentencePiece model.

    The fast reference tokenizer treats its AddedToken strings as control
    tokens, while SentencePiece would split those strings as ordinary text.
    Refuse that rare input so the caller can fail open to the legacy mapper.
    """
    if any(special in text for special in constants.TOKENIZER_SPECIAL_TOKENS):
        raise IngredientRagUnavailable("rag_tokenizer_input_unsupported")
    try:
        encoded = tokenizer.encode(text, out_type=int)
        content_ids = [_map_sentencepiece_id(tokenizer, token_id) for token_id in encoded]
    except IngredientRagUnavailable:
        raise
    except Exception as exc:
        raise IngredientRagUnavailable("rag_query_failed") from exc
    content_limit = constants.MAX_SEQUENCE_LENGTH - 2
    return [
        constants.TOKENIZER_BOS_ID,
        *content_ids[:content_limit],
        constants.TOKENIZER_EOS_ID,
    ]


def _map_sentencepiece_id(tokenizer: Any, token_id: int) -> int:
    if token_id == tokenizer.unk_id():
        return constants.TOKENIZER_UNK_ID
    if token_id == tokenizer.bos_id():
        return constants.TOKENIZER_BOS_ID
    if token_id == tokenizer.eos_id():
        return constants.TOKENIZER_EOS_ID
    return token_id + constants.TOKENIZER_VOCAB_OFFSET
