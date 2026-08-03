"""Build a deterministic bilingual Stardew vanilla ingredient catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GAME_VERSION = "stardew-1.6.15"
GENERATOR_VERSION = "vanilla-catalog-builder-1"


class CatalogSourceError(ValueError, TypeError):
    """Raised when a raw catalog export violates the supported shape."""

_DISPLAY_TOKEN = re.compile(r"^\[LocalizedText Strings\\Objects:(?P<name>[A-Za-z0-9_]+)_Name\]$")
_FOOD_TYPES = frozenset({"Basic", "Cooking", "Fish"})
_REQUIRED_FIELDS = ("Name", "DisplayName", "Type", "Category", "Price", "Edibility")


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read JSON source: {path.name}") from exc


def _localization_path(source: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if source.name == "Objects.json":
        return source.with_name("Objects.zh-CN.json")
    raise ValueError("localization source is required unless source is named Objects.json")


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _name_key(raw_display_name: str) -> str:
    match = _DISPLAY_TOKEN.fullmatch(raw_display_name)
    if match is None:
        raise CatalogSourceError("unrecognized DisplayName localization token")
    return f"{match.group('name')}_Name"

def _clean_aliases(*names: str) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for name in names:
        cleaned = " ".join(name.split())
        folded = cleaned.casefold()
        if cleaned and folded not in seen:
            aliases.append(cleaned)
            seen.add(folded)
    return aliases


def _sort_id(value: str) -> tuple[int, int | str, str]:
    try:
        return (0, int(value), value)
    except ValueError:
        return (1, value, value)


def _make_item(item_id: str, raw: dict[str, Any], localization: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in _REQUIRED_FIELDS if field not in raw]
    if missing:
        raise ValueError(f"item {item_id} missing required field: {missing[0]}")
    if not isinstance(raw["Name"], str) or not raw["Name"].strip():
        raise ValueError(f"item {item_id} has an invalid English name")
    if not isinstance(raw["DisplayName"], str):
        raise CatalogSourceError(f"item {item_id} has an invalid display token")

    english_name = " ".join(raw["Name"].split())
    chinese_name = localization.get(_name_key(raw["DisplayName"]))
    if not isinstance(chinese_name, str) or not chinese_name.strip():
        raise ValueError(f"item {item_id} missing Chinese name")

    category = str(raw["Category"])
    edibility = raw["Edibility"]
    sell_price = raw["Price"]
    if not isinstance(edibility, int) or not isinstance(sell_price, int):
        raise CatalogSourceError(f"item {item_id} has invalid numeric source fields")

    return {
        "itemId": item_id,
        "displayNameEn": english_name,
        "displayNameZh": " ".join(chinese_name.split()),
        "aliases": _clean_aliases(english_name, chinese_name),
        "category": category,
        "type": str(raw["Type"]),
        "usableAsIngredient": str(raw["Type"]) in _FOOD_TYPES and edibility >= 0,
        "isCategory": False,
        "edibility": edibility,
        "sellPrice": sell_price,
    }


def _category_item(category_id: str) -> dict[str, Any]:
    return {
        "itemId": category_id,
        "displayNameEn": f"Category {category_id}",
        "displayNameZh": f"分类 {category_id}",
        "aliases": _clean_aliases(f"Category {category_id}", f"分类 {category_id}"),
        "category": category_id,
        "type": "Category",
        "usableAsIngredient": False,
        "isCategory": True,
        "edibility": None,
        "sellPrice": None,
    }


def build_catalog(source: Path, output: Path, localization_source: Path | None = None) -> dict[str, Any]:
    """Build ``output`` and its sibling provenance file from raw exports."""
    raw = _read_json(source)
    if not isinstance(raw, dict) or not raw or any(not isinstance(key, str) for key in raw):
        raise ValueError("source must be a numeric item dictionary")
    localization_path = _localization_path(source, localization_source)
    localization = _read_json(localization_path)
    if not isinstance(localization, dict):
        raise CatalogSourceError("localization source must be a string-keyed dictionary")

    parsed: list[tuple[tuple[int, int | str, str], dict[str, Any]]] = []
    for item_id, item in raw.items():
        if not isinstance(item, dict):
            raise CatalogSourceError(f"item {item_id} must be an object")
        parsed_item = _make_item(item_id, item, localization)
        if item_id == "-5":
            parsed_item = _category_item("-5")
        parsed.append((_sort_id(item_id), parsed_item))
    if "-5" not in raw:
        parsed.append((_sort_id("-5"), _category_item("-5")))
    parsed.sort(key=lambda pair: pair[0])

    document = {"catalogVersion": f"{GAME_VERSION}-v1", "items": [item for _, item in parsed]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    provenance: dict[str, Any] = {
        "gameVersion": GAME_VERSION,
        "assetName": source.name,
        "extractedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "sourceMethod": "Stardew Data/Objects export with Objects.zh-CN Name_Name merge",
        "sourceSha256": _source_hash(source),
        "sources": {
            "english": {"assetName": source.name, "sha256": _source_hash(source)},
            "chinese": {"assetName": localization_path.name, "sha256": _source_hash(localization_path)},
        },
        "generatorVersion": GENERATOR_VERSION,
    }
    output.with_name("provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--localization", type=Path)
    args = parser.parse_args()
    try:
        build_catalog(args.source, args.output, args.localization)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
