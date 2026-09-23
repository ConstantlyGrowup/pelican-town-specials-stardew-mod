"""Resolve packed model resources without creating user workspace state."""

from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        return Path(meipass) if meipass else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[4]


def ingredient_rag_resource_dir() -> Path:
    root = application_root()
    if getattr(sys, "frozen", False):
        return root / "resources" / "ingredient-rag"
    generated = root / "output" / "m14-task65" / "ingredient-rag"
    bundled_style = root / "resources" / "ingredient-rag"
    return generated if generated.exists() else bundled_style


def catalog_resource_path() -> Path:
    return (
        application_root()
        / "resources"
        / "catalogs"
        / "stardew-1.6.15"
        / "vanilla-ingredients.json"
    )
