from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "backend" / "src"))

import evaluate_canonical_memory as evaluation_module
import evaluation_embedding as embedding_module
from evaluate_canonical_memory import (
    EvaluationInputError,
    EvaluationLabel,
    EvaluationQuery,
    EvaluationResult,
    ManifestRepository,
    build_fixture_registration,
    build_seed_manifest,
    compute_metrics,
    execute_recall,
    load_evaluation_bundle,
    register_fixture,
    seed_fixtures,
    validate_manifest_files,
)
from evaluation_embedding import (
    CpuEmbeddingRetriever,
    RankedCanonicalCandidate,
    _is_token_truncated,
    _token_count,
    linear_percentile,
    load_smoke_texts,
    measure_model_smoke,
    serialize_embedding_text,
)
from pelican_town_specials.domain.canonical import (
    CanonicalRecallCandidate,
    RecallDecision,
)
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.dish import (
    DishAnalysis,
    SemanticIngredient,
)
from pelican_town_specials.persistence.canonical_registry import (
    SQLiteCanonicalRegistry,
)
from pelican_town_specials.persistence.workspace import WorkspacePaths
from pelican_town_specials.providers.contracts import (
    CanonicalMatchResponse,
)


def _candidate(record: Any) -> CanonicalRecallCandidate:
    return CanonicalRecallCandidate(
        canonicalId=record.canonical_id,
        dishSignature=record.dish_signature,
        language=record.language,
        catalogVersion=record.catalog_version,
        recallDocument=record.recall_document,
        displayName=record.presentation.display_name,
        registeredAt=datetime(2026, 9, 3, tzinfo=UTC),
        useCount=getattr(record, "use_count", 0),
        lastUsedAt=getattr(record, "last_used_at", None),
    )


def _analysis(record: Any) -> DishAnalysis:
    document = record.recall_document
    return DishAnalysis(
        recognizedDish=document.recognized_dish,
        summary=document.summary,
        cuisine=document.cuisine,
        cookingMethods=list(document.cooking_methods),
        flavorProfile=list(document.flavor_profile),
        semanticIngredients=[
            SemanticIngredient(
                name=ingredient.name,
                normalizedName=ingredient.normalized_name,
                visibleConfidence=ingredient.visible_confidence,
                quantityHint=ingredient.quantity_hint,
            )
            for ingredient in document.semantic_ingredients
        ],
        confidence=0.99,
        safetyNotes=[],
    )


class _FakeRegistry:
    catalog_version = "stardew-1.6.15"

    def __init__(self, record: Any) -> None:
        self.candidate = _candidate(record)
        self.canonical = record

    def count_valid(self) -> int:
        return 2

    def list_recall_candidate_pool(
        self,
        *,
        language: Language,
        catalog_version: str,
    ) -> list[CanonicalRecallCandidate]:
        if (
            language is self.candidate.language
            and catalog_version == self.catalog_version
        ):
            return [self.candidate]
        return []

    def get_valid(self, canonical_id: UUID) -> Any | None:
        return self.canonical if canonical_id == self.canonical.canonical_id else None

    def load_owned_icon(self, canonical_id: UUID, kind: object) -> bytes:
        del kind
        if canonical_id != self.canonical.canonical_id:
            raise ValueError("unknown canonical")
        return b"owned-icon"


class _FixedRetriever:
    def __init__(self, candidate: CanonicalRecallCandidate) -> None:
        self.candidate = candidate

    def retrieve(self, analysis: Any, candidates: Any, **_: Any) -> list[Any]:
        del analysis, candidates
        return [
            RankedCanonicalCandidate(
                candidate=self.candidate,
                ingredient_score=1.0,
                name_score=1.0,
                context_score=1.0,
                score=1.0,
            )
        ]


class _FakeMatcher:
    def __init__(self, response: CanonicalMatchResponse | Exception) -> None:
        self.response = response
        self.requests: list[Any] = []

    async def match_canonical(self, request: Any, *, json_only: bool = False) -> Any:
        assert json_only is False
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_query_schema_rejects_expected_label_and_fixture_does_not_leak_it(
    tmp_path: Path,
) -> None:
    fixture = build_fixture_registration()
    query = EvaluationQuery(
        queryId=uuid4(),
        analysis=_analysis(fixture.registration),
        language=Language.ZH_CN,
        contextText=None,
    )
    query_path = tmp_path / "queries.jsonl"
    payload = query.model_dump(by_alias=True, mode="json")
    payload["expectedCanonicalId"] = str(fixture.registration.canonical_id)
    query_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        EvaluationQuery.model_validate(payload)

    label = EvaluationLabel(
        queryId=query.query_id,
        kind="positive",
        expectedCanonicalId=fixture.registration.canonical_id,
    )
    assert "expectedCanonicalId" not in query.analysis.model_dump(by_alias=True)
    assert label.expected_canonical_id == fixture.registration.canonical_id


def test_seed_jsonl_manifest_round_trip_validates_after_registry_reopen(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "evaluation"
    workspace_root = tmp_path / "workspace"
    fixtures = (
        build_fixture_registration(index=1),
        build_fixture_registration(
            index=2,
            display_name="米饭蔬菜",
            ingredients=("米饭", "蔬菜"),
        ),
    )
    records = seed_fixtures(workspace_root, output_dir, fixtures)
    queries = [
        EvaluationQuery(
            queryId=uuid4(),
            analysis=_analysis(record),
            language=Language.ZH_CN,
            contextText=None,
        )
        for record in records
    ]
    labels = [
        EvaluationLabel(
            queryId=query.query_id,
            kind="positive",
            expectedCanonicalId=records[index].canonical_id,
        )
        for index, query in enumerate(queries)
    ]
    (output_dir / "queries.jsonl").write_text(
        "".join(
            json.dumps(query.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
            + "\n"
            for query in queries
        ),
        encoding="utf-8",
    )
    (output_dir / "labels.jsonl").write_text(
        "".join(
            json.dumps(label.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
            + "\n"
            for label in labels
        ),
        encoding="utf-8",
    )
    bundle = load_evaluation_bundle(output_dir, require_manifest=True)
    assert len(bundle.canonicals) == 2
    assert len(bundle.queries) == 2
    assert bundle.manifest is not None


def test_real_registry_fixture_registration_is_idempotent_and_manifest_complete(
    tmp_path: Path,
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    registry = SQLiteCanonicalRegistry(workspace)
    fixture = build_fixture_registration()
    first = register_fixture(registry, fixture)
    second = register_fixture(registry, fixture)
    assert second.canonical_id == first.canonical_id
    assert registry.count_valid() == 1

    manifest = build_seed_manifest([first])
    validate_manifest_files(
        manifest,
        root=workspace.canonical_assets_dir,
        registry=registry,
    )
    scoped = ManifestRepository(registry, manifest)
    assert scoped.get_valid(first.canonical_id) == first
    with pytest.raises(EvaluationInputError):
        scoped.load_owned_icon(uuid4(), object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_runner_merges_labels_after_recall_and_keeps_provider_errors_in_denominator() -> (
    None
):
    fixture = build_fixture_registration()
    candidate = _candidate(fixture.registration)
    registry = _FakeRegistry(fixture.registration)
    query = EvaluationQuery(
        queryId=uuid4(),
        analysis=_analysis(fixture.registration),
        language=Language.ZH_CN,
        contextText="fresh context",
    )
    label = EvaluationLabel(
        queryId=query.query_id,
        kind="positive",
        expectedCanonicalId=candidate.canonical_id,
    )
    matcher = _FakeMatcher(
        CanonicalMatchResponse(candidateId=candidate.canonical_id, confidence=0.99)
    )
    results = await execute_recall(
        registry=registry,
        matcher=matcher,
        retriever=_FixedRetriever(candidate),
        queries=[query],
        labels=[label],
        max_calls=1,
    )
    assert matcher.requests
    assert "expectedCanonicalId" not in matcher.requests[0].model_dump(by_alias=True)
    assert compute_metrics(results).positive_hit_success == 1

    wrong_id = uuid4()
    wrong_result = EvaluationResult(
        queryId=uuid4(),
        kind="positive",
        expectedCanonicalId=candidate.canonical_id,
        candidateIds=[wrong_id],
        selectedId=wrong_id,
        decision=RecallDecision.MATCH_HIT.value,
        confidence=0.99,
    )
    provider_result = EvaluationResult(
        queryId=uuid4(),
        kind="positive",
        expectedCanonicalId=candidate.canonical_id,
        candidateIds=[],
        selectedId=None,
        decision=RecallDecision.FALLBACK_ERROR.value,
        confidence=None,
        errorCategory="provider_error",
    )
    metrics = compute_metrics([wrong_result, provider_result])
    assert metrics.positive_hit_success == 0
    assert metrics.positive_total == 2
    assert metrics.error_count == 1
    assert metrics.provider_error_count == 1


def test_embedding_serialization_and_percentiles_are_fixed_and_local() -> None:
    fixture = build_fixture_registration()
    serialized = serialize_embedding_text(fixture.registration.recall_document)
    assert serialized.text.startswith("name=")
    assert "ingredients=" in serialized.text
    assert "cuisine=" in serialized.text
    assert "cookingMethods=" in serialized.text
    assert fixture.registration.presentation.description not in serialized.text
    assert str(fixture.registration.canonical_id) not in serialized.text
    assert linear_percentile([0.0, 10.0, 20.0, 30.0], 95) == pytest.approx(28.5)


class _BatchEncoding(Mapping[str, object]):
    def __init__(self, input_ids: list[int]) -> None:
        self._payload = {"input_ids": input_ids}

    def __getitem__(self, key: str) -> object:
        return self._payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)


class _TokenizerModel:
    max_seq_length = 128

    def __init__(self, token_count: int) -> None:
        self.token_count = token_count

    def tokenizer(self, _text: str, **_: Any) -> _BatchEncoding:
        return _BatchEncoding(list(range(self.token_count)))


def test_batch_encoding_tokenizer_count_records_real_truncation_boundary() -> None:
    model = _TokenizerModel(752)
    assert _token_count(model, "long text") == 752
    assert _is_token_truncated(model, "long text") is True


class _VectorModel:
    max_seq_length = 128

    def encode(self, sentences: list[str], **_: Any) -> list[list[float]]:
        return [
            [1.0, 0.0] if "番茄" in sentence else [0.0, 1.0] for sentence in sentences
        ]


def test_embedding_retriever_precomputes_corpus_and_returns_top_k() -> None:
    first = build_fixture_registration(index=1)
    second = build_fixture_registration(
        index=2, display_name="米饭蔬菜", ingredients=("米饭", "蔬菜")
    )
    candidates = [_candidate(first.registration), _candidate(second.registration)]
    retriever = CpuEmbeddingRetriever(_VectorModel(), top_k=5)
    retriever.prepare(
        candidates, language=Language.ZH_CN, catalog_version="stardew-1.6.15"
    )
    ranked = retriever.retrieve(
        _analysis(first.registration),
        candidates,
        language=Language.ZH_CN,
        catalog_version="stardew-1.6.15",
    )
    assert [item.candidate.canonical_id for item in ranked] == [
        candidates[0].canonical_id,
        candidates[1].canonical_id,
    ]


def test_templates_and_seed_preserve_populated_artifacts_and_reuse_ids(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "evaluation"
    output_dir.mkdir()
    existing = {
        "canonicals.jsonl": '{"existing":"canonical"}\n',
        "queries.jsonl": '{"existing":"query"}\n',
        "labels.jsonl": '{"existing":"label"}\n',
        "current_results.csv": "existing,current\n",
        "baseline_results.csv": "existing,baseline\n",
        "retrieval_comparison.csv": "existing,comparison\n",
        "e2e_results.csv": "existing,e2e\n",
        "seed_manifest.json": '{"existing":"manifest"}\n',
    }
    for name, content in existing.items():
        (output_dir / name).write_text(content, encoding="utf-8")

    evaluation_module.write_templates(output_dir)

    assert {
        name: (output_dir / name).read_text(encoding="utf-8") for name in existing
    } == existing

    seeded_output = tmp_path / "seeded"
    workspace = tmp_path / "workspace"
    first_fixtures = (
        build_fixture_registration(index=1),
        build_fixture_registration(
            index=2,
            display_name="米饭蔬菜",
            ingredients=("米饭", "蔬菜"),
        ),
    )
    first = seed_fixtures(workspace, seeded_output, first_fixtures)
    first_canonicals = (seeded_output / "canonicals.jsonl").read_text(encoding="utf-8")
    first_manifest = (seeded_output / "seed_manifest.json").read_text(encoding="utf-8")
    second_fixtures = (
        build_fixture_registration(index=1),
        build_fixture_registration(
            index=2,
            display_name="米饭蔬菜",
            ingredients=("米饭", "蔬菜"),
        ),
    )
    second = seed_fixtures(workspace, seeded_output, second_fixtures)

    assert [record.canonical_id for record in second] == [
        record.canonical_id for record in first
    ]
    assert (seeded_output / "canonicals.jsonl").read_text(
        encoding="utf-8"
    ) == first_canonicals
    assert (seeded_output / "seed_manifest.json").read_text(
        encoding="utf-8"
    ) == first_manifest
    registry = SQLiteCanonicalRegistry(WorkspacePaths.create(workspace))
    assert registry.count_valid() == 2


def test_seed_collision_preflight_does_not_register_or_overwrite(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "evaluation"
    workspace = tmp_path / "workspace"
    first_fixture = build_fixture_registration(index=1)
    first = seed_fixtures(workspace, output_dir, (first_fixture,))[0]
    old_canonicals = (output_dir / "canonicals.jsonl").read_text(encoding="utf-8")
    old_manifest = (output_dir / "seed_manifest.json").read_text(encoding="utf-8")

    conflicting = build_fixture_registration(
        index=1,
        display_name="另一道菜",
        ingredients=("另一种原料", "鸡蛋"),
        canonical_id=first.canonical_id,
        source_archive_id=first.source_archive_id,
    )
    new_fixture = build_fixture_registration(
        index=2,
        display_name="米饭蔬菜",
        ingredients=("米饭", "蔬菜"),
    )
    with pytest.raises(EvaluationInputError):
        seed_fixtures(workspace, output_dir, (new_fixture, conflicting))

    registry = SQLiteCanonicalRegistry(WorkspacePaths.create(workspace))
    assert registry.count_valid() == 1
    assert (output_dir / "canonicals.jsonl").read_text(
        encoding="utf-8"
    ) == old_canonicals
    assert (output_dir / "seed_manifest.json").read_text(
        encoding="utf-8"
    ) == old_manifest


def test_bundle_and_source_provenance_include_content_and_relevant_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = build_fixture_registration()
    query_id = uuid4()
    query = EvaluationQuery(
        queryId=query_id,
        analysis=_analysis(fixture.registration),
        language=Language.ZH_CN,
        contextText="first context",
    )
    label = EvaluationLabel(
        queryId=query_id,
        kind="positive",
        expectedCanonicalId=fixture.registration.canonical_id,
    )
    bundle = evaluation_module.EvaluationBundle(
        canonicals=(fixture.registration,),
        queries=(query,),
        labels=(label,),
    )
    changed_query = EvaluationQuery(
        queryId=query_id,
        analysis=_analysis(fixture.registration),
        language=Language.EN_US,
        contextText="changed context",
    )
    changed_bundle = evaluation_module.EvaluationBundle(
        canonicals=(fixture.registration,),
        queries=(changed_query,),
        labels=(label,),
    )
    assert (
        evaluation_module._bundle_summary(bundle)["fingerprint"]
        != evaluation_module._bundle_summary(changed_bundle)["fingerprint"]
    )

    source_path = tmp_path / "relevant-source.py"
    source_path.write_text("first", encoding="utf-8")
    monkeypatch.setattr(evaluation_module, "_RELEVANT_SOURCE_FILES", (source_path,))
    first_source = evaluation_module._git_snapshot()["sourceFilesSha256"]
    source_path.write_text("second", encoding="utf-8")
    second_source = evaluation_module._git_snapshot()["sourceFilesSha256"]
    assert first_source != second_source

    metadata_path = tmp_path / "run.json"
    evaluation_module._write_run_metadata(
        metadata_path,
        mode="current",
        bundle=bundle,
        live=True,
        matcher_config={
            "base_url": "https://example.invalid/v1",
            "text_model": "text-model",
            "prompt_version": "canonical-match-v1",
            "chat_timeout_seconds": 90,
            "max_automatic_retries": 1,
        },
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["matcherConfig"]["chat_timeout_seconds"] == 90
    assert metadata["matcherConfig"]["max_automatic_retries"] == 1
    assert "api_key" not in metadata_path.read_text(encoding="utf-8")


def test_manifest_repository_validates_frozen_pool_and_reuses_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    registry = SQLiteCanonicalRegistry(workspace)
    fixtures = (
        build_fixture_registration(index=1),
        build_fixture_registration(
            index=2,
            display_name="米饭蔬菜",
            ingredients=("米饭", "蔬菜"),
        ),
    )
    records = tuple(register_fixture(registry, fixture) for fixture in fixtures)
    manifest = build_seed_manifest(list(records))
    original_pool = registry.list_recall_candidate_pool(
        language=manifest.language,
        catalog_version=manifest.catalog_version,
    )
    calls = 0

    def changing_pool(
        *, language: Language, catalog_version: str
    ) -> list[CanonicalRecallCandidate]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_pool
        return []

    monkeypatch.setattr(registry, "list_recall_candidate_pool", changing_pool)
    scoped = ManifestRepository(
        registry,
        manifest,
        root=workspace.canonical_assets_dir,
        canonicals=records,
    )
    first = scoped.prepare_snapshot()
    second = scoped.list_recall_candidate_pool(
        language=manifest.language,
        catalog_version=manifest.catalog_version,
    )
    assert [candidate.canonical_id for candidate in second] == [
        candidate.canonical_id for candidate in first
    ]
    assert calls == 1
    assert scoped.snapshot_digest

    modified_payload = records[0].model_dump(by_alias=True, mode="json")
    modified_payload["presentation"]["displayName"] = "被篡改的输入"
    with pytest.raises(EvaluationInputError):
        validate_manifest_files(
            manifest,
            root=workspace.canonical_assets_dir,
            registry=registry,
            canonicals=[
                type(records[0]).model_validate(
                    evaluation_module._normalise_canonical_payload(modified_payload)
                ),
                records[1],
            ],
        )


class _ResourceTokenizerModel(_VectorModel):
    def tokenizer(self, text: str, **_: Any) -> Mapping[str, object]:
        return {"input_ids": list(range(len(text)))}


def test_model_smoke_reports_corpus_cache_warm_rss_and_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_path = tmp_path / "model" / "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
    model_path.mkdir(parents=True)
    (model_path / "model.safetensors").write_bytes(b"model")
    model = _ResourceTokenizerModel()
    rss_values = iter((100.0, 200.0, 220.0, 240.0))
    monkeypatch.setattr(
        embedding_module, "load_cpu_model", lambda *args, **kwargs: (model, 0.5)
    )
    monkeypatch.setattr(embedding_module, "_rss_mib", lambda: next(rss_values))
    snapshot = measure_model_smoke(
        model_path,
        corpus=("a" * 140,),
        queries=("query",),
    )
    assert snapshot.cache_ready_rss_mib == 220.0
    assert snapshot.warmed_rss_mib == 240.0
    assert snapshot.additional_rss_mib == 140.0
    assert snapshot.corpus_observations["characterTruncatedCount"] == 0
    assert snapshot.corpus_observations["tokenTruncatedCount"] == 1
    assert snapshot.query_observations["count"] == 1


def test_smoke_input_loader_accepts_corpus_and_queries(tmp_path: Path) -> None:
    path = tmp_path / "smoke.json"
    path.write_text(
        json.dumps({"corpus": ["corpus text"], "queries": ["query text"]}),
        encoding="utf-8",
    )
    corpus, queries = load_smoke_texts(path)
    assert corpus == ["corpus text"]
    assert queries == ["query text"]


@pytest.mark.parametrize("damage", ["missing", "incompatible", "corrupt", "changed"])
def test_live_preflight_rejects_pool_damage_before_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    workspace_root = tmp_path / "workspace"
    inputs = tmp_path / "inputs"
    records = seed_fixtures(workspace_root, inputs, (build_fixture_registration(),))
    (inputs / "queries.jsonl").write_text("", encoding="utf-8")
    (inputs / "labels.jsonl").write_text("", encoding="utf-8")
    workspace = WorkspacePaths.create(workspace_root)
    registry = SQLiteCanonicalRegistry(workspace)
    if damage == "missing":
        monkeypatch.setattr(registry, "get_valid", lambda _: None)
    elif damage == "incompatible":
        monkeypatch.setattr(registry, "list_recall_candidate_pool", lambda **_: [])
    elif damage == "corrupt":
        (workspace.canonical_assets_dir / records[0].icon_16.relative_path).write_bytes(
            b"bad"
        )
    else:
        payload = records[0].model_dump(mode="json", by_alias=True)
        payload["presentation"]["displayName"] = "changed dish"
        changed = type(records[0]).model_validate(
            evaluation_module._normalise_canonical_payload(payload)
        )
        monkeypatch.setattr(registry, "get_valid", lambda _: changed)
    monkeypatch.setattr(
        evaluation_module, "SQLiteCanonicalRegistry", lambda _: registry
    )

    def forbidden_gateway(*_: Any) -> Any:
        pytest.fail("gateway must not be created for damaged inputs")

    monkeypatch.setattr(evaluation_module, "_build_live_gateway", forbidden_gateway)
    args = evaluation_module._parse_args().parse_args(
        [
            "run",
            "--input-dir",
            str(inputs),
            "--workspace",
            str(workspace_root),
            "--mode",
            "current",
            "--live",
            "--max-calls",
            "1",
        ]
    )
    with pytest.raises(EvaluationInputError):
        evaluation_module._run_cli(args)


def test_embedding_actual_input_observations_are_exported_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = build_fixture_registration()
    analysis = _analysis(fixture.registration)
    model = _ResourceTokenizerModel()
    retriever = CpuEmbeddingRetriever(model, max_text_characters=20)
    candidates = [_candidate(fixture.registration)]
    retriever.prepare(candidates)
    for _ in range(3):
        retriever.retrieve(analysis, candidates)
    observations = retriever.observations([analysis])
    assert observations["corpus"]["characterTruncatedCount"] == 1
    assert observations["queries"]["count"] == 1
    assert observations["queries"]["characterTruncatedCount"] == 1
    monkeypatch.setattr(evaluation_module, "runtime_versions", dict)
    monkeypatch.setattr(evaluation_module, "cpu_thread_count", lambda: 4)
    path = tmp_path / "run.json"
    evaluation_module._write_run_metadata(
        path,
        mode="embedding",
        live=True,
        bundle=evaluation_module.EvaluationBundle((fixture.registration,), (), ()),
        candidate_snapshot_digest="pool-digest",
        truncation_observations=observations,
    )
    metadata = json.loads(path.read_text(encoding="utf-8"))
    assert metadata["truncationObservations"] == observations
    assert metadata["candidateSnapshotSha256"] == "pool-digest"
