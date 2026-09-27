"""Freeze the local, deliberately easy cross-category JEV calibration set."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCES = (
    ROOT / "tests/fixtures/m14_ingredient_queries.json",
    ROOT / "tests/fixtures/m14_ingredient_holdout_queries.json",
)
CATALOG = ROOT / "resources/catalogs/stardew-1.6.15/vanilla-ingredients.json"
DATA = HERE / "data"
CASES = DATA / "cases.jsonl"
MANIFEST = DATA / "manifest.json"
SEED = 20260925


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _item(items: dict[str, dict], item_id: str) -> dict:
    try:
        return items[item_id]
    except KeyError as exc:
        raise ValueError(f"Unknown catalog item ID: {item_id}") from exc


def build() -> tuple[list[dict], dict]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = {str(item["itemId"]): item for item in catalog["items"]}
    if catalog["catalogVersion"] != "stardew-1.6.15-v1":
        raise ValueError("Unexpected catalog version")

    dishes: list[dict] = []
    for path in SOURCES:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc["catalog_version"] != catalog["catalogVersion"]:
            raise ValueError(f"Catalog version mismatch: {path.name}")
        dishes.extend(doc["dishes"])
    if len(dishes) != 120 or sum(len(d["ingredients"]) for d in dishes) != 360:
        raise ValueError("Expected the frozen 120-dish/360-ingredient corpus")
    if len({d["dish_id"] for d in dishes}) != len(dishes):
        raise ValueError("Duplicate dish ID")

    cases: list[dict] = []
    seen_query_ids: set[str] = set()
    for dish in dishes:
        for ingredient in dish["ingredients"]:
            query_id = ingredient["query_id"]
            if query_id in seen_query_ids:
                raise ValueError(f"Duplicate query ID: {query_id}")
            seen_query_ids.add(query_id)
            acceptable = [str(value) for value in ingredient["acceptable_item_ids"]]
            if not acceptable:
                raise ValueError(f"Missing Gold mapping: {query_id}")
            positive_id = acceptable[0]
            positive_item = _item(items, positive_id)
            if not positive_item["usableAsIngredient"]:
                raise ValueError(f"Gold item is not usable: {query_id}/{positive_id}")

            # The negative is an intentionally clear cross-category mismatch.
            # Its semantic validity is not inferred merely from being outside Gold.
            fish_gold = all(_item(items, item_id)["type"] == "Fish" for item_id in acceptable)
            pool = ("246", "256") if fish_gold else ("139", "129")
            choice = int(hashlib.sha256(query_id.encode("utf-8")).hexdigest(), 16) % len(pool)
            negative_id = pool[choice]
            if negative_id in acceptable:
                raise ValueError(f"Distractor is in Gold: {query_id}/{negative_id}")
            negative_item = _item(items, negative_id)
            if not negative_item["usableAsIngredient"]:
                raise ValueError(f"Distractor is not a usable ingredient: {negative_id}")

            shared = {
                "dish_id": dish["dish_id"],
                "dish_zh": dish["name_zh"],
                "dish_en": dish["name_en"],
                "query_id": query_id,
                "ingredient": ingredient["name"],
                "normalized_name": ingredient["normalized_name"],
            }
            for suffix, item, answer, reason in (
                (
                    "positive",
                    positive_item,
                    "reasonable",
                    ingredient.get("gold_note") or "Frozen project Gold mapping",
                ),
                (
                    "negative",
                    negative_item,
                    "unreasonable",
                    "事前选定的明显跨类食材：鱼与非鱼类原料，或鱼类与面粉/番茄；不代表所有非 Gold ID 都不合理。",
                ),
            ):
                cases.append(
                    {
                        **shared,
                        "case_id": f"{query_id}-{suffix}",
                        "item_id": str(item["itemId"]),
                        "item_en": item["displayNameEn"],
                        "item_zh": item["displayNameZh"],
                        "gold_choice": answer,
                        "gold_reason": reason,
                        "case_type": suffix,
                        "difficulty": "known_gold" if suffix == "positive" else "clear_cross_category",
                    }
                )

    # Stable order is shared by serial and parallel runs; pair order is shuffled.
    random.Random(SEED).shuffle(cases)
    states = {
        (
            case["dish_en"], case["dish_zh"], case["ingredient"], case["normalized_name"], case["item_id"]
        )
        for case in cases
    }
    distribution = Counter(case["gold_choice"] for case in cases)
    if distribution != {"reasonable": 360, "unreasonable": 360}:
        raise ValueError("Expected balanced 360/360 labels")
    source_hashes = {path.name: digest(path) for path in (*SOURCES, CATALOG)}
    lines = "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in cases)
    cases_sha = hashlib.sha256(lines.encode("utf-8")).hexdigest().upper()
    manifest = {
        "schema_version": "temp-jev-video-v1",
        "dish_count": len(dishes),
        "ingredient_count": len(seen_query_ids),
        "case_count": len(cases),
        "positive_count": distribution["reasonable"],
        "negative_count": distribution["unreasonable"],
        "unique_state_count": len(states),
        "sha256": cases_sha,
        "source_sha256": source_hashes,
        "seed": SEED,
        "label_status": "rule_curated_cross_category",
        "negative_rule": "For Gold fish choose Wheat Flour/Tomato; otherwise choose Salmon/Anchovy. All are explicitly cross-category; not a hard-negative benchmark.",
        "translation_rule": "ID 246 English Wheat Flour is authoritative despite Chinese display 大麦粉.",
    }
    return cases, manifest


def freeze() -> dict:
    cases, manifest = build()
    lines = "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in cases)
    DATA.mkdir(exist_ok=True)
    if CASES.exists() or MANIFEST.exists():
        if not CASES.exists() or not MANIFEST.exists():
            raise ValueError("Only part of the frozen dataset exists")
        if CASES.read_text(encoding="utf-8") != lines:
            raise ValueError("Existing cases differ from regenerated frozen inputs")
        if json.loads(MANIFEST.read_text(encoding="utf-8")) != manifest:
            raise ValueError("Existing manifest differs from regenerated frozen inputs")
        return manifest
    CASES.write_text(lines, encoding="utf-8", newline="\n")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


if __name__ == "__main__":
    print(json.dumps(freeze(), ensure_ascii=False, indent=2))
