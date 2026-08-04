"""Focused tests for the deterministic vanilla catalog builder."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from scripts import build_vanilla_catalog

from pelican_town_specials.catalog.models import CatalogCandidate, CatalogItem
from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.errors import AppError

ROOT = Path(__file__).parents[3]
SOURCE = ROOT / "resources/catalogs/stardew-1.6.15/Objects.json"


def _items(path: Path) -> list[dict[str, object]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return document["items"]


def test_real_source_merges_bilingual_names_and_preserves_category(
    tmp_path: Path,
) -> None:
    output = tmp_path / "catalog.json"
    provenance = build_vanilla_catalog.build_catalog(SOURCE, output)
    by_id = {item["itemId"]: item for item in _items(output)}

    assert by_id["256"]["displayNameEn"] == "Tomato"
    assert by_id["256"]["displayNameZh"] == "西红柿"
    assert by_id["256"]["usableAsIngredient"] is True
    assert by_id["-5"]["isCategory"] is True
    assert by_id["-5"]["usableAsIngredient"] is False
    for item_id in ("349", "351", "434"):
        assert by_id[item_id]["usableAsIngredient"] is False
    assert (
        provenance["sourceSha256"]
        == "6CBC66CAECFED0AAC884958E21834D572014DBF4E41E64A0AF1B190E8390FF90"
    )
    assert provenance["sources"] == {
        "english": {
            "assetName": "Objects.json",
            "sha256": "6CBC66CAECFED0AAC884958E21834D572014DBF4E41E64A0AF1B190E8390FF90",
        },
        "chinese": {
            "assetName": "Objects.zh-CN.json",
            "sha256": "E51B2EF545E519E268A793BDB9EC0905B9ED6A3F7E1BFD7EEA84D5EE79051F07",
        },
    }


def test_rebuilding_same_source_is_byte_for_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    build_vanilla_catalog.build_catalog(SOURCE, first)
    build_vanilla_catalog.build_catalog(SOURCE, second)

    assert first.read_bytes() == second.read_bytes()
    assert "\r" not in first.read_text(encoding="utf-8")
    assert [item["itemId"] for item in _items(first)[:4]] == ["-5", "0", "2", "4"]


def test_cli_derives_localization_sibling_and_serializes_stable_layout(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Objects.json"
    source.write_text(
        json.dumps(
            {
                "256": {
                    "Name": " Tomato ",
                    "DisplayName": "[LocalizedText Strings\\Objects:Tomato_Name]",
                    "Type": "Basic",
                    "Category": -75,
                    "Price": 60,
                    "Edibility": 8,
                }
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    (tmp_path / "Objects.zh-CN.json").write_text(
        json.dumps({"Tomato_Name": "西红柿"}), encoding="utf-8", newline="\n"
    )
    output = tmp_path / "catalog.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_vanilla_catalog.py",
            "--source",
            str(source),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stderr == ""
    assert (
        output.read_text(encoding="utf-8")
        == """{
  "catalogVersion": "stardew-1.6.15-v1",
  "items": [
    {
      "itemId": "-5",
      "displayNameEn": "Category -5",
      "displayNameZh": "分类 -5",
      "aliases": [
        "Category -5",
        "分类 -5"
      ],
      "category": "-5",
      "type": "Category",
      "usableAsIngredient": false,
      "isCategory": true,
      "edibility": null,
      "sellPrice": null
    },
    {
      "itemId": "256",
      "displayNameEn": "Tomato",
      "displayNameZh": "西红柿",
      "aliases": [
        "Tomato",
        "西红柿"
      ],
      "category": "-75",
      "type": "Basic",
      "usableAsIngredient": true,
      "isCategory": false,
      "edibility": 8,
      "sellPrice": 60
    }
  ]
}
"""
    )
    provenance = json.loads((tmp_path / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["assetName"] == "Objects.json"
    assert "extractedAt" in provenance
    assert str(tmp_path) not in output.read_text(encoding="utf-8")


def test_malformed_source_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "Objects.json"
    source.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="numeric item dictionary"):
        build_vanilla_catalog.build_catalog(source, tmp_path / "output.json")


def test_unrecognized_display_name_token_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "Objects.json"
    source.write_text(
        json.dumps(
            {
                "1": {
                    "Name": "Parsnip",
                    "DisplayName": "Parsnip",
                    "Type": "Basic",
                    "Category": -75,
                    "Price": 35,
                    "Edibility": 8,
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Objects.zh-CN.json").write_text(
        json.dumps({"Parsnip_Name": "防风草"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="unrecognized DisplayName localization token"):
        build_vanilla_catalog.build_catalog(source, tmp_path / "output.json")


def test_missing_chinese_name_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "Objects.json"
    source.write_text(
        json.dumps(
            {
                "1": {
                    "Name": "Parsnip",
                    "DisplayName": "[LocalizedText Strings\\Objects:Parsnip_Name]",
                    "Type": "Basic",
                    "Category": -75,
                    "Price": 35,
                    "Edibility": 8,
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Objects.zh-CN.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="missing Chinese name"):
        build_vanilla_catalog.build_catalog(source, tmp_path / "output.json")


def _write_catalog(tmp_path: Path, items: list[dict[str, object]]) -> Path:
    path = tmp_path / "vanilla-ingredients.json"
    path.write_text(
        json.dumps({"catalogVersion": "stardew-1.6.15-v1", "items": items}),
        encoding="utf-8",
    )
    return path


def _catalog_item(item_id: str, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "itemId": item_id,
        "displayNameEn": f"Item {item_id}",
        "displayNameZh": f"物品 {item_id}",
        "aliases": [f"Item {item_id}", f"物品 {item_id}"],
        "category": "-75",
        "type": "Basic",
        "usableAsIngredient": True,
        "isCategory": False,
        "edibility": 8,
        "sellPrice": 60,
    }
    item.update(overrides)
    return item


def test_repository_loads_required_fields_and_category(tmp_path: Path) -> None:
    path = _write_catalog(
        tmp_path,
        [
            _catalog_item("256", displayNameEn="Tomato", displayNameZh="西红柿"),
            _catalog_item("-5", isCategory=True, usableAsIngredient=False),
        ],
    )

    catalog = VanillaCatalog.from_json(path)

    assert catalog.version == "stardew-1.6.15-v1"
    assert catalog.require("256") == CatalogItem(
        item_id="256",
        display_name_en="Tomato",
        display_name_zh="西红柿",
        aliases=("Item 256", "物品 256"),
        category="-75",
        type="Basic",
        usable_as_ingredient=True,
        is_category=False,
        edibility=8,
        sell_price=60,
    )
    assert catalog.require("-5").is_category is True


@pytest.mark.parametrize(
    ("items", "match"),
    [
        ([_catalog_item("1"), _catalog_item("1")], "duplicate itemId"),
        ([_catalog_item("-1")], "negative itemId"),
        ([_catalog_item("-5")], "category"),
        ([{**_catalog_item("1"), "displayNameEn": 42}], "field types"),
        ([{**_catalog_item("1"), "type": 42}], "field types"),
    ],
)
def test_repository_rejects_duplicate_invalid_and_wrong_typed_items(
    tmp_path: Path, items: list[dict[str, object]], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        VanillaCatalog.from_json(_write_catalog(tmp_path, items))


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"catalogVersion": "stardew-1.6.15-v1"},
        {"catalogVersion": "stardew-1.6.15-v1", "items": []},
        {"catalogVersion": "stardew-1.6.15-v1", "items": [{"itemId": "1"}]},
    ],
)
def test_repository_rejects_wrong_top_level_or_missing_fields(
    tmp_path: Path, document: object
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        VanillaCatalog.from_json(path)


def test_require_unknown_id_uses_safe_stable_error(tmp_path: Path) -> None:
    catalog = VanillaCatalog.from_json(_write_catalog(tmp_path, [_catalog_item("256")]))

    with pytest.raises(AppError) as caught:
        catalog.require("999999-secret-input")

    assert caught.value.code == "PTS_VALIDATION_INGREDIENT_ID_UNKNOWN"
    assert caught.value.http_status == 422
    assert caught.value.retryable is False
    assert "999999-secret-input" not in caught.value.message
    assert "999999-secret-input" not in repr(caught.value.details)


def test_search_uses_fixed_priority_and_deterministic_ties(tmp_path: Path) -> None:
    catalog = VanillaCatalog.from_json(
        _write_catalog(
            tmp_path,
            [
                _catalog_item(
                    "2",
                    displayNameEn="Tomato Soup",
                    displayNameZh="番茄汤",
                    aliases=["Tomato Soup", "番茄汤"],
                ),
                _catalog_item(
                    "10",
                    displayNameEn="Tomato",
                    displayNameZh="西红柿",
                    aliases=["Tomato", "西红柿"],
                ),
                _catalog_item(
                    "3",
                    displayNameEn="Soup Base",
                    displayNameZh="汤底",
                    aliases=["Soup Base", "汤底"],
                ),
                _catalog_item(
                    "4",
                    displayNameEn="Wild Tomato Leaf",
                    displayNameZh="野番茄叶",
                    aliases=["Wild Tomato Leaf", "野番茄叶"],
                ),
            ],
        )
    )

    assert [item.item_id for item in catalog.search("10")] == ["10"]
    assert [item.item_id for item in catalog.search("  TOMATO  ")] == ["10", "2", "4"]
    assert [item.item_id for item in catalog.search("tom")] == ["10", "2"]
    assert [item.item_id for item in catalog.search("tomato leaf")] == ["4", "2", "10"]
    assert [item.item_id for item in catalog.search("tomato", limit=2)] == ["10", "2"]


def test_search_empty_over_limit_and_tie_order_are_safe(tmp_path: Path) -> None:
    catalog = VanillaCatalog.from_json(
        _write_catalog(
            tmp_path,
            [
                _catalog_item("20", displayNameEn="Apple", aliases=["Fruit"]),
                _catalog_item("3", displayNameEn="Apricot", aliases=["Fruit"]),
            ],
        )
    )

    assert catalog.search("   ") == []
    assert catalog.search("fruit") == [catalog.require("3"), catalog.require("20")]
    assert catalog.search("fruit", limit=0) == []
    assert catalog.search("fruit", limit=10_000) == [
        catalog.require("3"),
        catalog.require("20"),
    ]


def test_loaded_models_and_results_are_read_only(tmp_path: Path) -> None:
    catalog = VanillaCatalog.from_json(_write_catalog(tmp_path, [_catalog_item("1")]))
    item = catalog.require("1")

    with pytest.raises(FrozenInstanceError):
        item.item_id = "2"  # type: ignore[misc]
    results = catalog.search("item")
    results.clear()
    assert catalog.require("1").item_id == "1"


def test_catalog_candidate_is_frozen_and_validates_score() -> None:
    candidate = CatalogCandidate(item_id="1", score=0.5)
    assert candidate.item_id == "1"
    with pytest.raises(FrozenInstanceError):
        candidate.score = 1.0  # type: ignore[misc]


def test_catalog_constructor_and_loaded_index_cannot_be_mutated(tmp_path: Path) -> None:
    catalog = VanillaCatalog.from_json(_write_catalog(tmp_path, [_catalog_item("1")]))

    with pytest.raises(TypeError):
        catalog._items["2"] = catalog.require("1")  # type: ignore[index]
    with pytest.raises(AttributeError):
        catalog._version = "tampered"  # type: ignore[misc]
    with pytest.raises(TypeError, match="from_json"):
        VanillaCatalog("stardew-1.6.15-v1", (catalog.require("1"),))


@pytest.mark.parametrize("item_id", ["Not Real", "Not-Real", "-1", "-6", ""])
def test_repository_rejects_text_and_non_required_negative_ids(
    tmp_path: Path, item_id: str
) -> None:
    with pytest.raises(ValueError, match="itemId|negative|category"):
        VanillaCatalog.from_json(_write_catalog(tmp_path, [_catalog_item(item_id)]))


def test_search_normalizes_unicode_and_bounds_all_limit_edges(tmp_path: Path) -> None:
    catalog = VanillaCatalog.from_json(
        _write_catalog(
            tmp_path,
            [
                _catalog_item(
                    "2",
                    displayNameEn="Straße",
                    displayNameZh="咖啡",
                    aliases=["Straße", "咖啡"],
                ),
                _catalog_item(
                    "10",
                    displayNameEn="Strasse",
                    displayNameZh="咖啡",
                    aliases=["Strasse", "咖啡"],
                ),
            ],
        )
    )

    assert [item.item_id for item in catalog.search("  STRASSE  ")] == ["2", "10"]
    assert [item.item_id for item in catalog.search("咖啡")] == ["2", "10"]
    assert catalog.search("咖啡", limit=-1) == []
    assert catalog.search("咖啡", limit=0) == []
    assert [item.item_id for item in catalog.search("咖啡", limit=10**9)] == ["2", "10"]


def test_builder_does_not_duplicate_existing_category_id(tmp_path: Path) -> None:
    source = tmp_path / "Objects.json"
    source.write_text(
        json.dumps(
            {
                "-5": {
                    "Name": "Category Marker",
                    "DisplayName": "[LocalizedText Strings\\Objects:CategoryMarker_Name]",
                    "Type": "Basic",
                    "Category": -5,
                    "Price": 0,
                    "Edibility": -300,
                },
                "1": {
                    "Name": "Parsnip",
                    "DisplayName": "[LocalizedText Strings\\Objects:Parsnip_Name]",
                    "Type": "Basic",
                    "Category": -75,
                    "Price": 35,
                    "Edibility": 8,
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Objects.zh-CN.json").write_text(
        json.dumps({"CategoryMarker_Name": "分类标记", "Parsnip_Name": "防风草"}),
        encoding="utf-8",
    )

    output = tmp_path / "catalog.json"
    build_vanilla_catalog.build_catalog(source, output)
    items = _items(output)

    assert [item["itemId"] for item in items].count("-5") == 1
    assert next(item for item in items if item["itemId"] == "-5")["isCategory"] is True



def test_repository_accepts_stardew_named_id_fixture(tmp_path: Path) -> None:
    catalog = VanillaCatalog.from_json(
        _write_catalog(
            tmp_path,
            [_catalog_item("Broccoli", displayNameEn="Broccoli", usableAsIngredient=True)],
        )
    )

    assert catalog.require("Broccoli").display_name_en == "Broccoli"


def test_repository_loads_real_catalog_named_ids() -> None:
    path = ROOT / "resources/catalogs/stardew-1.6.15/vanilla-ingredients.json"
    catalog = VanillaCatalog.from_json(path)
    named_ids = [
        item.item_id
        for item in catalog.items
        if item.item_id != "-5" and not item.item_id.isdigit()
    ]

    assert catalog.version == "stardew-1.6.15-v1"
    assert len(catalog.items) == 808
    assert len(named_ids) == 85
    assert catalog.require("Broccoli").usable_as_ingredient is True


def test_search_ingredients_only_returns_usable_items() -> None:
    path = ROOT / "resources/catalogs/stardew-1.6.15/vanilla-ingredients.json"
    catalog = VanillaCatalog.from_json(path)

    results = catalog.search_ingredients("tomat", limit=10)

    assert results
    assert all(item.usable_as_ingredient for item in results)
    assert all(item.item_id != "-5" for item in results)

    exact = catalog.search_ingredients("24", limit=10)
    assert exact and exact[0].item_id == "24"

    non_usable = catalog.search_ingredients("349", limit=10)
    assert non_usable == []
