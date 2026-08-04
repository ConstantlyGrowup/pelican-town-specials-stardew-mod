"""Deterministic preview composition and golden-hash tests."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image

from pelican_town_specials.images.preview_compositor import (
    PreviewSnapshot,
    compose_preview,
)

_GOLDEN_PATH = Path(__file__).resolve().parents[1] / "golden" / "preview_v1.sha256"


def test_compose_preview_is_deterministic_and_960x540(snapshot: PreviewSnapshot) -> None:
    first = compose_preview(snapshot)
    second = compose_preview(snapshot)

    assert first == second
    image = Image.open(io.BytesIO(first))
    assert image.size == (960, 540)
    assert image.mode == "RGBA"


def test_golden_hash_matches(snapshot: PreviewSnapshot) -> None:
    expected = _GOLDEN_PATH.read_text(encoding="utf-8").strip()

    actual = hashlib.sha256(compose_preview(snapshot)).hexdigest()

    assert actual == expected


def test_changing_structured_field_changes_output(snapshot: PreviewSnapshot) -> None:
    base = compose_preview(snapshot)
    changed_presentation = snapshot.presentation.model_copy(
        update={"display_name": "一碗非常非常长的南瓜浓汤名字"}
    )
    changed = PreviewSnapshot(
        generated_art=snapshot.generated_art,
        presentation=changed_presentation,
        gameplay=snapshot.gameplay,
    )

    assert compose_preview(changed) != base


def test_long_display_name_last_char_changes_output(snapshot: PreviewSnapshot) -> None:
    name_a = "长" * 59 + "甲"
    name_b = "长" * 59 + "乙"
    a = PreviewSnapshot(
        generated_art=snapshot.generated_art,
        presentation=snapshot.presentation.model_copy(update={"display_name": name_a}),
        gameplay=snapshot.gameplay,
    )
    b = PreviewSnapshot(
        generated_art=snapshot.generated_art,
        presentation=snapshot.presentation.model_copy(update={"display_name": name_b}),
        gameplay=snapshot.gameplay,
    )

    assert compose_preview(a) != compose_preview(b)
