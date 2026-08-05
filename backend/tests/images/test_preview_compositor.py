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


def test_compose_preview_is_deterministic_and_preserves_source_size(
    snapshot: PreviewSnapshot,
) -> None:
    first = compose_preview(snapshot)
    second = compose_preview(snapshot)

    assert first == second
    image = Image.open(io.BytesIO(first))
    assert image.size == (640, 360)
    assert image.mode == "RGBA"


def test_compose_preview_keeps_photo_pixels_outside_card(snapshot: PreviewSnapshot) -> None:
    output = Image.open(io.BytesIO(compose_preview(snapshot))).convert("RGBA")
    source = Image.open(io.BytesIO(snapshot.original_image)).convert("RGBA")

    # The deterministic card is placed in the top-right corner. A distant
    # source pixel must be copied exactly, proving the photo remains the base.
    assert output.getpixel((0, 0)) == source.getpixel((0, 0))
    assert output.getpixel((source.width // 2, source.height - 1)) == source.getpixel(
        (source.width // 2, source.height - 1)
    )


def test_compose_preview_uses_icon_and_not_a_replacement_photo(
    snapshot: PreviewSnapshot,
) -> None:
    output = Image.open(io.BytesIO(compose_preview(snapshot))).convert("RGBA")
    source = Image.open(io.BytesIO(snapshot.original_image)).convert("RGBA")

    assert output.size == source.size
    # The source is green and the supplied icon is red; the red card icon is
    # visible in the overlay rather than a generated full-image replacement.
    assert any(
        (pixel := output.getpixel((x, y)))[0] > 180 and pixel[1] < 80
        for x in range(500, 640)
        for y in range(150)
    )


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
        original_image=snapshot.original_image,
        icon_16=snapshot.icon_16,
        presentation=changed_presentation,
        gameplay=snapshot.gameplay,
    )

    assert compose_preview(changed) != base


def test_long_display_name_last_char_changes_output(snapshot: PreviewSnapshot) -> None:
    name_a = "长" * 59 + "甲"
    name_b = "长" * 59 + "乙"
    a = PreviewSnapshot(
        original_image=snapshot.original_image,
        icon_16=snapshot.icon_16,
        presentation=snapshot.presentation.model_copy(update={"display_name": name_a}),
        gameplay=snapshot.gameplay,
    )
    b = PreviewSnapshot(
        original_image=snapshot.original_image,
        icon_16=snapshot.icon_16,
        presentation=snapshot.presentation.model_copy(update={"display_name": name_b}),
        gameplay=snapshot.gameplay,
    )

    assert compose_preview(a) != compose_preview(b)
