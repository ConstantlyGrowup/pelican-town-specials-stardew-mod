"""Task 16 mod compiler fixtures: real asset store and immutable archives."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from PIL import Image

from pelican_town_specials.catalog.repository import VanillaCatalog
from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.assets import AssetKind, MediaType
from pelican_town_specials.domain.common import Language
from pelican_town_specials.domain.export import ExportSpec
from pelican_town_specials.mod_compiler.compiler import (
    CompileInput,
    ContentPatcherCompiler,
)
from pelican_town_specials.persistence.asset_store import AssetMetadata, FileAssetStore
from pelican_town_specials.persistence.repositories import _validate_model_payload
from pelican_town_specials.persistence.workspace import WorkspacePaths

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = (
    _REPO_ROOT / "resources" / "catalogs" / "stardew-1.6.15" / "vanilla-ingredients.json"
)
_ARCHIVES_DIR = _REPO_ROOT / "backend" / "tests" / "fixtures" / "archives"

AUTHOR_NAME = "D20260801"
PACK_SLUG = "FamilyMenu"


def load_archive_doc(name: str) -> dict[str, Any]:
    """Read an immutable ArchivedDish fixture document (camelCase JSON)."""
    path = _ARCHIVES_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def content_hash_of(doc: dict[str, Any]) -> str:
    """Recompute the canonical content hash over the deserialized snapshot.

    The hash mirrors the archiver (application/drafts.py) and therefore runs
    over the model dump, so tampered documents (for example recovery edits)
    always produce the hash the compiler will verify.
    """
    dish = archive_from_doc({**doc, "contentHash": "a" * 64})
    payload = {
        "presentation": dish.presentation.model_dump(by_alias=True, mode="json"),
        "gameplay": dish.gameplay.model_dump(by_alias=True, mode="json"),
        "visuals": dish.visuals.model_dump(by_alias=True, mode="json"),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def put_icon(
    asset_store: FileAssetStore, *, size: int = 16, color: str = "seagreen"
) -> UUID:
    """Register a square RGBA PNG icon and return its asset id."""
    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), color).save(buffer, format="PNG")
    ref = asset_store.put(
        buffer.getvalue(),
        AssetMetadata(
            kind=AssetKind.ICON_16,
            mediaType=MediaType.PNG,
            fileExtension=".png",
            width=size,
            height=size,
        ),
    )
    return ref.asset_id


def archive_from_doc(doc: dict[str, Any]) -> ArchivedDish:
    """Deserialize a fixture document through the production archive path."""
    return _validate_model_payload(ArchivedDish)(doc)


def archive_dish(name: str, asset_store: FileAssetStore) -> ArchivedDish:
    """Load an immutable archive fixture and point its icon at a real asset."""
    doc = load_archive_doc(name)
    doc["visuals"]["icon16AssetId"] = str(put_icon(asset_store))
    doc["contentHash"] = content_hash_of(doc)
    return archive_from_doc(doc)


def export_spec(dish_ids: Sequence[UUID]) -> ExportSpec:
    return ExportSpec(
        dishIds=list(dish_ids),
        packDisplayName="家庭菜单",
        packSlug=PACK_SLUG,
        version="1.0.0",
        description="一份装满鹈鹕镇风味的菜单。",
        language=Language.ZH_CN,
    )


@pytest.fixture
def asset_store(tmp_path: Path) -> FileAssetStore:
    workspace = WorkspacePaths.create(tmp_path / "workspace")
    return FileAssetStore(workspace)


@pytest.fixture
def catalog() -> VanillaCatalog:
    return VanillaCatalog.from_json(_CATALOG_PATH)


@pytest.fixture
def export_fixture(asset_store: FileAssetStore) -> CompileInput:
    dishes = [
        archive_dish("ask-gus-dish", asset_store),
        archive_dish("blueprint-dish", asset_store),
    ]
    spec = export_spec([dishes[0].dish_id, dishes[1].dish_id])
    return CompileInput(spec=spec, dishes=dishes)


@pytest.fixture
def compiler(asset_store: FileAssetStore) -> ContentPatcherCompiler:
    return ContentPatcherCompiler(asset_store=asset_store, author_name=AUTHOR_NAME)
