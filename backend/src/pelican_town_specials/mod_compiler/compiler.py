"""Deterministic Content Patcher pack compiler.

``ContentPatcherCompiler`` turns an ``ExportSpec`` plus immutable
``ArchivedDish`` snapshots into a byte-stable content pack ZIP. The compile
pipeline implements design 14.7 steps 5-9: generate spritesheet, i18n,
manifest, content and README into the staging folder, write a deterministic
ZIP, then reopen and re-audit it. Structural validation runs first; any
failure produces no downloadable ZIP.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pelican_town_specials.domain.archive import ArchivedDish
from pelican_town_specials.domain.export import ExportSpec
from pelican_town_specials.persistence.asset_store import FileAssetStore

from .spritesheet import build_spritesheet
from .templates import README_TEXT, build_content, build_i18n, build_manifest
from .validator import ExportValidationError, validate_export_structure
from .zip_writer import verify_zip, write_zip

PACK_FOLDER_PREFIX = "[CP] Pelican Town Specials - "
_PACK_ZIP_NAME = "pack.zip"


class ModCompileError(Exception):
    """Raised when a compiled pack fails a compile-time invariant."""


@dataclass(frozen=True)
class CompileInput:
    """Compile input bundle: the export spec and its archived dishes."""

    spec: ExportSpec
    dishes: list[ArchivedDish]


@dataclass(frozen=True)
class ExportArtifact:
    """Result of one compile: staging layout, manifest and ZIP digest.

    ``file_manifest`` maps content-pack-relative paths to their SHA-256.
    """

    staging_dir: Path
    file_manifest: dict[str, str]
    zip_path: Path
    zip_sha256: str
    spritesheet_dimensions: tuple[int, int]


class ContentPatcherCompiler:
    def __init__(self, *, asset_store: FileAssetStore, author_name: str) -> None:
        self._asset_store = asset_store
        self._author_name = author_name

    def compile_to_bytes(self, source: CompileInput) -> bytes:
        """Compile into a throwaway staging folder and return the ZIP bytes."""
        with tempfile.TemporaryDirectory(prefix="pts-mod-compile-") as temp_dir:
            artifact = self.compile(source.spec, list(source.dishes), Path(temp_dir))
            return artifact.zip_path.read_bytes()

    def compile(
        self,
        spec: ExportSpec,
        dishes: list[ArchivedDish],
        staging: Path,
    ) -> ExportArtifact:
        """Compile a content pack into an already-created staging directory."""
        report = validate_export_structure(spec, dishes)
        if not report.valid:
            raise ExportValidationError(report)

        pack_slug = spec.pack_slug
        pack_folder = f"{PACK_FOLDER_PREFIX}{pack_slug}"

        try:
            sprite_bytes, sprite_indices = build_spritesheet(dishes, self._asset_store)
        except ValueError as exc:
            raise ModCompileError(f"spritesheet build failed: {exc}") from exc

        manifest = build_manifest(
            author_name=self._author_name,
            pack_slug=pack_slug,
            version=spec.version,
            description=spec.description,
        )
        content = build_content(
            author_name=self._author_name,
            pack_slug=pack_slug,
            dishes=dishes,
            sprite_indices=sprite_indices,
        )
        i18n = build_i18n(dishes)

        files: dict[str, bytes] = {
            "manifest.json": _json_bytes(manifest),
            "content.json": _json_bytes(content),
            "i18n/default.json": _json_bytes(i18n),
            "i18n/zh.json": _json_bytes(i18n),
            "assets/objects.png": sprite_bytes,
            "README.txt": README_TEXT.encode("utf-8"),
        }

        pack_root = staging / pack_folder
        for relative_path, data in files.items():
            target = pack_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        zip_path = staging / _PACK_ZIP_NAME
        entries = {
            f"{pack_folder}/{relative_path}": data
            for relative_path, data in files.items()
        }
        write_zip(zip_path, entries)
        try:
            verify_zip(zip_path)
        except ValueError as exc:
            raise ModCompileError(f"compiled pack failed reopen verification: {exc}") from exc

        rows = (len(dishes) + 15) // 16
        return ExportArtifact(
            staging_dir=staging,
            file_manifest={
                relative_path: hashlib.sha256(data).hexdigest()
                for relative_path, data in files.items()
            },
            zip_path=zip_path,
            zip_sha256=hashlib.sha256(zip_path.read_bytes()).hexdigest(),
            spritesheet_dimensions=(16 * 16, max(rows, 1) * 16),
        )


def _json_bytes(payload: dict[str, Any]) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{text}\n".encode()
