"""Build the pinned local E5 CPU INT8 model and static ingredient index."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.ingredient_rag import constants
from pelican_town_specials.ingredient_rag.encoder import (
    OnnxE5Encoder,
    sentencepiece_input_ids,
)
from pelican_town_specials.ingredient_rag.errors import IngredientRagUnavailable
from pelican_town_specials.ingredient_rag.index import write_index_artifacts
from pelican_town_specials.ingredient_rag.retriever import build_passage


def main() -> int:
    args = _parse_args()
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    _verify_build_versions()

    from huggingface_hub import hf_hub_download
    from onnxruntime.quantization import (  # type: ignore[import-untyped]
        QuantType,
        quantize_dynamic,
    )

    catalog_path = args.catalog.resolve()
    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    catalog = VanillaCatalog.from_json(catalog_path)
    catalog_hash = _sha256_file(catalog_path)
    if (
        catalog.version != constants.CATALOG_VERSION
        or catalog_hash != constants.CATALOG_SHA256
        or len(catalog.ingredients) != constants.CATALOG_ELIGIBLE_ROWS
    ):
        raise SystemExit("catalog does not match the frozen ingredient-RAG source")

    cache_dir.mkdir(parents=True, exist_ok=True)
    source_model = Path(
        hf_hub_download(
            repo_id=constants.MODEL_ID,
            filename="onnx/model.onnx",
            revision=constants.MODEL_REVISION,
            cache_dir=cache_dir,
            token=False,
        )
    )
    source_reference_tokenizer = Path(
        hf_hub_download(
            repo_id=constants.MODEL_ID,
            filename="tokenizer.json",
            revision=constants.MODEL_REVISION,
            cache_dir=cache_dir,
            token=False,
        )
    )
    source_tokenizer = Path(
        hf_hub_download(
            repo_id=constants.MODEL_ID,
            filename="sentencepiece.bpe.model",
            revision=constants.MODEL_REVISION,
            cache_dir=cache_dir,
            token=False,
        )
    )
    _verify_source_artifact(
        source_model,
        constants.SOURCE_MODEL_SHA256,
        constants.SOURCE_MODEL_BYTES,
        "official E5 ONNX source",
    )
    _verify_source_artifact(
        source_reference_tokenizer,
        constants.REFERENCE_TOKENIZER_SHA256,
        constants.REFERENCE_TOKENIZER_BYTES,
        "official E5 tokenizer.json reference",
    )
    _verify_source_artifact(
        source_tokenizer,
        constants.TOKENIZER_SHA256,
        constants.TOKENIZER_BYTES,
        "official E5 SentencePiece model",
    )
    _validate_tokenizer_parity(source_reference_tokenizer, source_tokenizer, catalog)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="ingredient-rag-stage-", dir=output_dir.parent
    ) as stage_name:
        stage_dir = Path(stage_name)
        model_path = stage_dir / constants.MODEL_FILE_NAME
        tokenizer_path = stage_dir / constants.TOKENIZER_FILE_NAME
        vector_path = stage_dir / constants.VECTOR_FILE_NAME
        manifest_path = stage_dir / constants.MANIFEST_FILE_NAME
        shutil.copyfile(source_tokenizer, tokenizer_path)

        quantize_dynamic(
            model_input=str(source_model),
            model_output=str(model_path),
            weight_type=QuantType.QInt8,
            per_channel=True,
            op_types_to_quantize=list(constants.QUANTIZED_OP_TYPES),
        )

        encoder = OnnxE5Encoder(
            model_path=model_path,
            tokenizer_path=tokenizer_path,
        )
        embeddings = [encoder.encode(build_passage(item)) for item in catalog.ingredients]
        artifacts = write_index_artifacts(
            catalog_path=catalog_path,
            output_dir=stage_dir,
            embeddings=np.asarray(embeddings, dtype=np.float32),
            model_path=model_path,
            tokenizer_path=tokenizer_path,
        )
        if artifacts.vector_path != vector_path or artifacts.manifest_path != manifest_path:
            raise SystemExit("ingredient index writer selected an unexpected output path")
        encoder.encode(f"{constants.QUERY_PREFIX}egg")

        output_dir.mkdir(parents=True, exist_ok=True)
        for filename in (
            constants.MODEL_FILE_NAME,
            constants.TOKENIZER_FILE_NAME,
            constants.VECTOR_FILE_NAME,
            constants.MANIFEST_FILE_NAME,
        ):
            os.replace(stage_dir / filename, output_dir / filename)

    print(f"model_sha256={_sha256_file(output_dir / constants.MODEL_FILE_NAME)}")
    print(f"tokenizer_sha256={_sha256_file(output_dir / constants.TOKENIZER_FILE_NAME)}")
    print(f"index_sha256={_sha256_file(output_dir / constants.VECTOR_FILE_NAME)}")
    print(f"output_dir={output_dir}")
    return 0


def _parse_args() -> argparse.Namespace:
    default_output = REPO_ROOT / "output" / "m14-task65" / "ingredient-rag-spm"
    default_cache = REPO_ROOT / "output" / "m14-task65" / "hf-cache"
    default_catalog = (
        REPO_ROOT
        / "resources"
        / "catalogs"
        / "stardew-1.6.15"
        / "vanilla-ingredients.json"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=default_catalog)
    parser.add_argument("--output-dir", type=Path, default=default_output)
    parser.add_argument("--cache-dir", type=Path, default=default_cache)
    return parser.parse_args()


def _verify_source_artifact(
    path: Path, expected_hash: str, expected_size: int, description: str
) -> None:
    if path.stat().st_size != expected_size or _sha256_file(path) != expected_hash:
        raise SystemExit(f"{description} failed pinned size/SHA-256 validation")


def _verify_build_versions() -> None:
    expected = {
        "numpy": constants.NUMPY_VERSION,
        "onnx": constants.ONNX_VERSION,
        "onnxruntime": constants.ONNXRUNTIME_VERSION,
        "tokenizers": constants.TOKENIZERS_VERSION,
        "sentencepiece": constants.SENTENCEPIECE_VERSION,
    }
    mismatches = []
    for package, expected_version in expected.items():
        actual_version = version(package)
        if actual_version != expected_version:
            mismatches.append(f"{package}={actual_version} (expected {expected_version})")
    if mismatches:
        raise SystemExit(
            "ingredient-RAG build dependencies are not pinned: "
            + ", ".join(mismatches)
        )


def _validate_tokenizer_parity(
    reference_tokenizer_path: Path,
    sentencepiece_path: Path,
    catalog: VanillaCatalog,
) -> None:
    """Compare pinned runtime IDs with the official fast-tokenizer reference."""
    from sentencepiece import SentencePieceProcessor
    from tokenizers import Tokenizer

    query_fixture_path = REPO_ROOT / "tests" / "fixtures" / "m14_ingredient_queries.json"
    if _sha256_file(query_fixture_path) != constants.QUERY_FIXTURE_SHA256:
        raise SystemExit("frozen Task64 query fixture failed pinned SHA-256 validation")
    query_fixture = json.loads(query_fixture_path.read_text(encoding="utf-8"))
    queries = sorted(
        {
            str(entry["normalized_name"])
            for dish in query_fixture["dishes"]
            for entry in dish["ingredients"]
        }
    )
    if len(queries) != 50:
        raise SystemExit("frozen Task64 query fixture must contain 50 distinct queries")

    reference = Tokenizer.from_file(str(reference_tokenizer_path))
    reference.enable_truncation(max_length=constants.MAX_SEQUENCE_LENGTH)
    runtime = SentencePieceProcessor(model_file=str(sentencepiece_path))
    passages = [build_passage(item) for item in catalog.ingredients]
    query_inputs = [f"{constants.QUERY_PREFIX}{query}" for query in queries]
    boundary_inputs = [
        f"{constants.QUERY_PREFIX}{_normalize_query('  Ｆｕｌｌｗｉｄｔｈ　　Egg  ')}",
        f"{constants.QUERY_PREFIX}{_normalize_query(' Egg\t\n Plant  ')}",
        f"{constants.QUERY_PREFIX}{_normalize_query('é')}",
        f"{constants.QUERY_PREFIX}{_normalize_query('ÉGG')} !?",
        f"{constants.QUERY_PREFIX}{_normalize_query('鳕鱼')} "+("egg " * 200),
    ]
    reserved_input = f"{constants.QUERY_PREFIX}<s> </s> <unk> <pad> <mask>"

    match_count = 0
    for text in (*passages, *query_inputs, *boundary_inputs):
        runtime_ids = sentencepiece_input_ids(runtime, text)
        reference_ids = reference.encode(text).ids
        if runtime_ids != reference_ids:
            raise SystemExit("SentencePiece IDs differ from official tokenizer reference")
        match_count += 1
    if match_count != constants.CATALOG_ELIGIBLE_ROWS + len(queries) + len(boundary_inputs):
        raise SystemExit("tokenizer parity corpus did not match the frozen input count")
    try:
        sentencepiece_input_ids(runtime, reserved_input)
    except IngredientRagUnavailable as exc:
        if exc.reason_code != "rag_tokenizer_input_unsupported":
            raise SystemExit("reserved tokenizer control text did not fail safely") from exc
    else:
        raise SystemExit("reserved tokenizer control text must fail open to the legacy mapper")
    print(f"tokenizer_parity_matches={match_count}")
    print("tokenizer_reserved_literal_policy=legacy-fallback")


def _normalize_query(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalized.split())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if __name__ == "__main__":
    raise SystemExit(main())
