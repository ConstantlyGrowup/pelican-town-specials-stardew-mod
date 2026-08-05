"""ContentPatcherCompiler integration tests: determinism, ZIP, golden, validation."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.validation import ValidationSeverity
from pelican_town_specials.mod_compiler.compiler import (
    CompileInput,
    ContentPatcherCompiler,
    ModCompileError,
)
from pelican_town_specials.mod_compiler.validator import (
    ExportValidationError,
    validate_export,
)

from .conftest import (
    archive_from_doc,
    content_hash_of,
    export_spec,
    load_archive_doc,
)

_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden" / "mod"
_PACK_ROOT = "[CP] Pelican Town Specials - FamilyMenu"


def _compile(
    compiler: ContentPatcherCompiler,
    source: CompileInput,
    tmp_path: Path,
) -> tuple[object, Path]:
    staging = tmp_path / "staging"
    staging.mkdir()
    artifact = compiler.compile(source.spec, source.dishes, staging)
    return artifact, artifact.zip_path


def _content_document(compiler: ContentPatcherCompiler, source: CompileInput, tmp_path: Path) -> dict[str, object]:
    _, zip_path = _compile(compiler, source, tmp_path)
    with zipfile.ZipFile(zip_path) as handle:
        document = json.loads(handle.read(f"{_PACK_ROOT}/content.json").decode("utf-8"))
    return document


# --- T16-DETERMINISM-001 -----------------------------------------------------


def test_same_snapshot_produces_same_zip_hash(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput
) -> None:
    first = compiler.compile_to_bytes(export_fixture)
    second = compiler.compile_to_bytes(export_fixture)
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()


# --- T16-ZIP-001 / T16-SAFETY-001 --------------------------------------------


def test_zip_has_single_pack_root_and_safe_entries(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    _, zip_path = _compile(compiler, export_fixture, tmp_path)

    with zipfile.ZipFile(zip_path) as handle:
        names = handle.namelist()
        assert len(names) == 6
        assert sorted(names) == names
        roots = {name.partition("/")[0] for name in names}
        assert roots == {_PACK_ROOT}
        for name in names:
            assert not name.startswith("/")
            assert "\\" not in name
            assert ".." not in name.split("/")
        for name in names:
            data = handle.read(name)
            if name.endswith(".json"):
                assert json.loads(data.decode("utf-8")) is not None
            elif name.endswith(".png"):
                with Image.open(io.BytesIO(data)) as image:
                    assert image.mode == "RGBA"
                    assert image.size == (256, 16)


def test_artifact_manifest_and_sha256(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    artifact, zip_path = _compile(compiler, export_fixture, tmp_path)

    assert set(artifact.file_manifest) == {
        "manifest.json",
        "content.json",
        "i18n/default.json",
        "i18n/zh.json",
        "assets/objects.png",
        "README.txt",
    }
    with zipfile.ZipFile(zip_path) as handle:
        for relative, digest in artifact.file_manifest.items():
            data = handle.read(f"{_PACK_ROOT}/{relative}")
            assert digest == hashlib.sha256(data).hexdigest()
    assert artifact.zip_sha256 == hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert artifact.spritesheet_dimensions == (256, 16)
    assert artifact.staging_dir == zip_path.parent


# --- T16-OBJECTS-001 / T16-RECIPES-002 / T16-BUFFS-001 / T16-I18N-001 -------


def test_object_entries_frozen_fields(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    document = _content_document(compiler, export_fixture, tmp_path)

    changes = document["Changes"]
    assert isinstance(changes, list)
    assert changes[0] == {
        "Action": "Load",
        "Target": "Mods/{{ModId}}/Objects",
        "FromFile": "assets/objects.png",
    }
    objects = changes[1]["Entries"]
    assert isinstance(objects, dict)
    tomato = objects["{{ModId}}_TomatoStew"]
    assert tomato["Type"] == "Cooking"
    assert tomato["Category"] == -7
    assert tomato["Texture"] == "Mods/{{ModId}}/Objects"
    assert tomato["Edibility"] == 80
    assert tomato["IsDrink"] is False
    assert tomato["Price"] == 220
    assert "Buffs" not in tomato


def test_sprite_indices_stable_and_incremental(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    document = _content_document(compiler, export_fixture, tmp_path)

    objects = document["Changes"][1]["Entries"]
    assert objects["{{ModId}}_ParsnipSoup"]["SpriteIndex"] == 0
    assert objects["{{ModId}}_TomatoStew"]["SpriteIndex"] == 1


def test_recipe_values_use_sorted_pairs_and_default_unlock(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    document = _content_document(compiler, export_fixture, tmp_path)

    recipes = document["Changes"][2]["Entries"]
    assert isinstance(recipes, dict)
    assert (
        recipes["{{ModId}}_TomatoStew"]
        == "24 1 256 2/0 0/{{ModId}}_TomatoStew/default/{{i18n:recipe.TomatoStew.name}}"
    )
    assert (
        recipes["{{ModId}}_ParsnipSoup"]
        == "24 2/0 0/{{ModId}}_ParsnipSoup/default/{{i18n:recipe.ParsnipSoup.name}}"
    )


def test_buff_maps_to_data_objects_buffs_entry(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    document = _content_document(compiler, export_fixture, tmp_path)

    changes = document["Changes"]
    buff_patch = changes[-1]
    assert buff_patch["Action"] == "EditData"
    assert buff_patch["Target"] == "Data/Objects.Buffs"
    buffs = buff_patch["Entries"]
    assert isinstance(buffs, dict)
    entry = buffs["{{ModId}}_TomatoStew"]
    assert entry["Id"] == "{{ModId}}_TomatoStew_speed"
    assert entry["Duration"] == 600_000
    assert entry["IsDebuff"] is False
    assert entry["CustomAttributes"] == "Speed 1"
    assert "{{ModId}}_ParsnipSoup" not in buffs


def test_no_buffs_patch_for_buffless_dishes(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    source = export_fixture
    only_blueprint = CompileInput(
        spec=export_spec([source.dishes[1].dish_id]), dishes=[source.dishes[1]]
    )

    document = _content_document(compiler, only_blueprint, tmp_path)

    changes = document["Changes"]
    assert [patch["Target"] for patch in changes] == [
        "Mods/{{ModId}}/Objects",
        "Data/Objects",
        "Data/CookingRecipes",
    ]


def test_i18n_uses_internal_name_keys_and_original_text(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    _, zip_path = _compile(compiler, export_fixture, tmp_path)

    with zipfile.ZipFile(zip_path) as handle:
        default = json.loads(handle.read(f"{_PACK_ROOT}/i18n/default.json").decode("utf-8"))
        zh = json.loads(handle.read(f"{_PACK_ROOT}/i18n/zh.json").decode("utf-8"))

    assert default == zh
    assert set(default) == {
        "item.ParsnipSoup.name",
        "item.ParsnipSoup.description",
        "item.TomatoStew.name",
        "item.TomatoStew.description",
        "recipe.ParsnipSoup.name",
        "recipe.TomatoStew.name",
    }
    assert default["item.TomatoStew.name"] == "番茄炖菜"
    assert default["item.TomatoStew.description"] == "慢炖番茄与欧防风，暖胃又满足。"
    assert default["recipe.ParsnipSoup.name"] == "欧防风浓汤"


# --- T16-GOLDEN-001 ----------------------------------------------------------


def _golden_bytes(name: str) -> bytes:
    return (_GOLDEN_DIR / name).read_bytes()


def test_golden_manifest(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    _, zip_path = _compile(compiler, export_fixture, tmp_path)
    with zipfile.ZipFile(zip_path) as handle:
        extracted = handle.read(f"{_PACK_ROOT}/manifest.json")
    assert extracted == _golden_bytes("manifest.json")


def test_golden_content(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    _, zip_path = _compile(compiler, export_fixture, tmp_path)
    with zipfile.ZipFile(zip_path) as handle:
        extracted = handle.read(f"{_PACK_ROOT}/content.json")
    assert extracted == _golden_bytes("content.json")


def test_golden_i18n_default(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    _, zip_path = _compile(compiler, export_fixture, tmp_path)
    with zipfile.ZipFile(zip_path) as handle:
        extracted = handle.read(f"{_PACK_ROOT}/i18n/default.json")
    assert extracted == _golden_bytes("i18n-default.json")


# --- T16-VALIDATION-001 / T16-VALIDATION-002 ---------------------------------


def _codes(report: object) -> set[str]:
    return {issue.code for issue in report.issues}  # type: ignore[attr-defined]


def test_validate_export_accepts_valid_fixture(
    catalog: VanillaCatalog, export_fixture: CompileInput
) -> None:
    report = validate_export(export_fixture.spec, export_fixture.dishes, catalog)

    assert report.valid is True
    assert report.issues == []
    assert report.validator_version == "task16-export-validator-v1"


def test_validate_export_rejects_unknown_ingredient(
    catalog: VanillaCatalog, export_fixture: CompileInput, tmp_path: Path
) -> None:
    source = export_fixture
    doc = load_archive_doc("ask-gus-dish")
    doc["gameplay"]["ingredients"][0]["itemId"] = "NotReal"
    doc["visuals"]["icon16AssetId"] = str(source.dishes[0].visuals.icon_16_asset_id)
    doc["contentHash"] = content_hash_of(doc)
    dish = archive_from_doc(doc)
    spec = export_spec([dish.dish_id])

    report = validate_export(spec, [dish], catalog)

    assert report.valid is False
    assert "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN" in _codes(report)
    issue = next(
        issue for issue in report.issues if issue.code == "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN"
    )
    assert issue.severity is ValidationSeverity.ERROR
    assert issue.path == "dishes[0].ingredients[0].itemId"
    assert issue.details == {}


def test_validate_export_rejects_missing_dish(
    catalog: VanillaCatalog, export_fixture: CompileInput
) -> None:
    source = export_fixture
    spec = export_spec([source.dishes[0].dish_id, uuid4()])

    report = validate_export(spec, source.dishes, catalog)

    assert report.valid is False
    assert "PTS_VALIDATION_DISH_MISSING" in _codes(report)


def test_validate_export_rejects_unreferenced_dish(
    catalog: VanillaCatalog, export_fixture: CompileInput
) -> None:
    source = export_fixture
    spec = export_spec([source.dishes[0].dish_id])

    report = validate_export(spec, source.dishes, catalog)

    assert report.valid is False
    assert "PTS_VALIDATION_DISH_UNREFERENCED" in _codes(report)


def test_validate_export_rejects_duplicate_internal_name(
    catalog: VanillaCatalog, export_fixture: CompileInput
) -> None:
    source = export_fixture
    doc = load_archive_doc("blueprint-dish")
    doc["presentation"]["internalName"] = "TomatoStew"
    doc["dishId"] = str(uuid4())
    doc["visuals"]["icon16AssetId"] = str(source.dishes[1].visuals.icon_16_asset_id)
    doc["contentHash"] = content_hash_of(doc)
    duplicate = archive_from_doc(doc)
    dishes = [source.dishes[0], duplicate]
    spec = export_spec([dish.dish_id for dish in dishes])

    report = validate_export(spec, dishes, catalog)

    assert report.valid is False
    assert "PTS_VALIDATION_DUPLICATE_INTERNAL_NAME" in _codes(report)


def test_validate_export_rejects_content_hash_mismatch(
    catalog: VanillaCatalog, export_fixture: CompileInput
) -> None:
    source = export_fixture
    doc = load_archive_doc("ask-gus-dish")
    doc["visuals"]["icon16AssetId"] = str(source.dishes[0].visuals.icon_16_asset_id)
    doc["contentHash"] = "b" * 64
    dish = archive_from_doc(doc)
    spec = export_spec([dish.dish_id])

    report = validate_export(spec, [dish], catalog)

    assert report.valid is False
    assert "PTS_VALIDATION_CONTENT_HASH_MISMATCH" in _codes(report)


def test_validate_export_rejects_missing_icon(
    catalog: VanillaCatalog, export_fixture: CompileInput
) -> None:
    doc = load_archive_doc("ask-gus-dish")
    doc["visuals"]["icon16AssetId"] = None
    doc["contentHash"] = content_hash_of(doc)
    dish = archive_from_doc(doc)
    spec = export_spec([dish.dish_id])

    report = validate_export(spec, [dish], catalog)

    assert report.valid is False
    assert "PTS_VALIDATION_ICON_16_MISSING" in _codes(report)


def test_validate_export_soft_warnings_do_not_invalidate(
    catalog: VanillaCatalog, export_fixture: CompileInput
) -> None:
    source = export_fixture
    doc = load_archive_doc("blueprint-dish")
    doc["gameplay"]["recovery"]["edibility"] = 300
    doc["gameplay"]["sellPrice"] = 6000
    doc["visuals"]["icon16AssetId"] = str(source.dishes[1].visuals.icon_16_asset_id)
    doc["contentHash"] = content_hash_of(doc)
    dish = archive_from_doc(doc)
    spec = export_spec([dish.dish_id])

    report = validate_export(spec, [dish], catalog)

    assert report.valid is True
    assert {
        "PTS_VALIDATION_GAMEPLAY_EDIBILITY_OUTSIDE_OBSERVED_RANGE",
        "PTS_VALIDATION_GAMEPLAY_SELL_PRICE_OUTSIDE_OBSERVED_RANGE",
    } <= _codes(report)
    assert {issue.severity for issue in report.issues} == {ValidationSeverity.WARNING}


# --- compile-time guards ------------------------------------------------------


def test_compile_rejects_invalid_export_without_zip(
    compiler: ContentPatcherCompiler, export_fixture: CompileInput, tmp_path: Path
) -> None:
    source = export_fixture
    spec = export_spec([source.dishes[0].dish_id, uuid4()])
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(ExportValidationError):
        compiler.compile(spec, source.dishes, staging)

    assert not (staging / "pack.zip").exists()
    assert not (staging / _PACK_ROOT).exists()


def test_compile_rejects_missing_icon_without_zip(
    compiler: ContentPatcherCompiler, tmp_path: Path
) -> None:
    doc = load_archive_doc("ask-gus-dish")
    doc["visuals"]["icon16AssetId"] = None
    doc["contentHash"] = content_hash_of(doc)
    dish = archive_from_doc(doc)
    spec = export_spec([dish.dish_id])
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(ExportValidationError):
        compiler.compile(spec, [dish], staging)

    assert not (staging / "pack.zip").exists()


def test_compile_rejects_unregistered_icon_without_zip(
    compiler: ContentPatcherCompiler, tmp_path: Path
) -> None:
    doc = load_archive_doc("blueprint-dish")
    doc["visuals"]["icon16AssetId"] = "deadbeef-dead-4ead-8ead-deadbeefdead"
    doc["contentHash"] = content_hash_of(doc)
    dish = archive_from_doc(doc)
    spec = export_spec([dish.dish_id])
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(ModCompileError):
        compiler.compile(spec, [dish], staging)

    assert not (staging / "pack.zip").exists()
