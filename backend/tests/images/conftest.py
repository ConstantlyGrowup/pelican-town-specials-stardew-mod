"""Task 12 image test fixtures."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from pelican_town_specials.domain.dish import (
    GameIngredient,
    GameplaySpec,
    PresentationSpec,
    RecoverySpec,
)
from pelican_town_specials.images.preview_compositor import PreviewSnapshot


def png_bytes(*, size: tuple[int, int] = (64, 64), color: str = "red") -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def rgba_png() -> bytes:
    return png_bytes()


@pytest.fixture
def presentation() -> PresentationSpec:
    return PresentationSpec(
        displayName="南瓜浓汤",
        internalName="PumpkinSoup",
        categoryLabel="汤类",
        description="香甜的南瓜浓汤。",
        tags=[],
    )


@pytest.fixture
def gameplay() -> GameplaySpec:
    return GameplaySpec(
        ingredients=[
            GameIngredient(
                itemId="24",
                displayName="Parsnip",
                quantity=1,
                mappingReason="catalog match",
                catalogVersion="stardew-1.6.15-v1",
            )
        ],
        recovery=RecoverySpec(edibility=80),
        sellPrice=220,
        isDrink=False,
    )


@pytest.fixture
def snapshot(
    rgba_png: bytes,
    presentation: PresentationSpec,
    gameplay: GameplaySpec,
) -> PreviewSnapshot:
    return PreviewSnapshot(
        generated_art=rgba_png,
        presentation=presentation,
        gameplay=gameplay,
    )
