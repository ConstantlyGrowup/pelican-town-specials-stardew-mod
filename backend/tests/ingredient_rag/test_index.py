from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.ingredient_rag import index as index_module
from pelican_town_specials.ingredient_rag.index import (
    IndexCompatibilityError,
    StaticIngredientIndex,
    load_static_index,
    write_index_artifacts,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = (
    _REPO_ROOT
    / "resources"
    / "catalogs"
    / "stardew-1.6.15"
    / "vanilla-ingredients.json"
)


def _write_test_assets(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    catalog = VanillaCatalog.from_json(_CATALOG_PATH)
    model_path = tmp_path / "model_int8.onnx"
    tokenizer_path = tmp_path / "tokenizer.json"
    model_path.write_bytes(b"test quantized model")
    tokenizer_path.write_bytes(b"test tokenizer")
    output_dir = tmp_path / "index"
    vectors = np.zeros((len(catalog.ingredients), 384), dtype=np.float32)
    vectors[:, 0] = 1.0
    artifacts = write_index_artifacts(
        catalog_path=_CATALOG_PATH,
        output_dir=output_dir,
        embeddings=vectors,
        model_path=model_path,
        tokenizer_path=tokenizer_path,
    )
    return (
        model_path,
        tokenizer_path,
        artifacts.manifest_path,
        artifacts.vector_path,
        output_dir,
    )


@pytest.fixture
def catalog() -> VanillaCatalog:
    return VanillaCatalog.from_json(_CATALOG_PATH)


def test_index_artifact_is_exactly_253_by_384_float32(
    tmp_path: Path, catalog: VanillaCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokenizer_path = tmp_path / "test-tokenizer.json"
    tokenizer_path.write_bytes(b"test tokenizer")
    monkeypatch.setattr(
        index_module.constants,
        "TOKENIZER_SHA256",
        hashlib.sha256(tokenizer_path.read_bytes()).hexdigest().upper(),
    )
    model_path, tokenizer_path, manifest_path, vector_path, _ = _write_test_assets(
        tmp_path
    )
    monkeypatch.setattr(index_module.constants, "QUANTIZED_MODEL_SHA256", "")
    monkeypatch.setattr(index_module.constants, "VECTOR_INDEX_SHA256", "")

    index = load_static_index(
        catalog=catalog,
        catalog_path=_CATALOG_PATH,
        manifest_path=manifest_path,
        vector_path=vector_path,
        model_path=model_path,
        tokenizer_path=tokenizer_path,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(index.item_ids) == 253
    assert index.vectors.shape == (253, 384)
    assert index.vectors.dtype == np.dtype("<f4")
    assert vector_path.stat().st_size == 253 * 384 * 4
    assert manifest["rowCount"] == 253
    assert manifest["embeddingDimension"] == 384
    assert manifest["dtype"] == "float32"
    assert manifest["itemIds"] == [item.item_id for item in catalog.ingredients]
    assert manifest["vectorBytes"] == 253 * 384 * 4


def test_index_rejects_manifest_catalog_mismatch(
    tmp_path: Path, catalog: VanillaCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokenizer_path = tmp_path / "test-tokenizer.json"
    tokenizer_path.write_bytes(b"test tokenizer")
    monkeypatch.setattr(
        index_module.constants,
        "TOKENIZER_SHA256",
        hashlib.sha256(tokenizer_path.read_bytes()).hexdigest().upper(),
    )
    model_path, tokenizer_path, manifest_path, vector_path, _ = _write_test_assets(
        tmp_path
    )
    monkeypatch.setattr(index_module.constants, "QUANTIZED_MODEL_SHA256", "")
    monkeypatch.setattr(index_module.constants, "VECTOR_INDEX_SHA256", "")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["catalogSha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(IndexCompatibilityError, match="rag_index_invalid"):
        load_static_index(
            catalog=catalog,
            catalog_path=_CATALOG_PATH,
            manifest_path=manifest_path,
            vector_path=vector_path,
            model_path=model_path,
            tokenizer_path=tokenizer_path,
        )


def test_index_rejects_nonfinite_or_wrong_shape_vectors() -> None:
    with pytest.raises(IndexCompatibilityError, match="rag_index_invalid"):
        StaticIngredientIndex(
            item_ids=("176",), vectors=np.zeros((1, 383), dtype=np.float32)
        )

    invalid = np.zeros((253, 384), dtype=np.float32)
    invalid[0, 0] = np.nan
    with pytest.raises(IndexCompatibilityError, match="rag_index_invalid"):
        StaticIngredientIndex(item_ids=tuple(str(i) for i in range(253)), vectors=invalid)


def test_index_writer_rejects_wrong_row_count(tmp_path: Path) -> None:
    model_path = tmp_path / "model.onnx"
    tokenizer_path = tmp_path / "tokenizer.json"
    model_path.write_bytes(b"model")
    tokenizer_path.write_bytes(b"tokenizer")

    with pytest.raises(IndexCompatibilityError, match="rag_index_invalid"):
        write_index_artifacts(
            catalog_path=_CATALOG_PATH,
            output_dir=tmp_path / "output",
            embeddings=np.zeros((252, 384), dtype=np.float32),
            model_path=model_path,
            tokenizer_path=tokenizer_path,
        )
