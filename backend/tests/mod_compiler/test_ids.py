"""ID derivation tests (plan Task 16 Step 1)."""

from __future__ import annotations

import pytest

from pelican_town_specials.mod_compiler.ids import derive_ids, validate_internal_name


def test_manifest_and_item_ids() -> None:
    ids = derive_ids(
        author_name="D20260801",
        pack_slug="FamilyMenu",
        internal_name="TomatoStew",
    )
    assert ids.mod_id == "D20260801.PelicanTownSpecials.FamilyMenu"
    assert ids.item_id == "{{ModId}}_TomatoStew"


def test_internal_name_accepts_valid_pattern() -> None:
    for name in ("TomatoStew", "Parsnip_Soup2", "AAA", "A" * 48):
        assert validate_internal_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Tomato Stew",
        "Tomato-Stew",
        "Tomato.Stew",
        "Tomato/Stew",
        "1Tomato",
        "_Tomato",
        "To",
        "x",
        "",
        "A" * 49,
        "Tomatoé",
        "Tomato\tStew",
    ],
)
def test_internal_name_rejects_spaces_hyphens_and_other_invalid_chars(name: str) -> None:
    assert validate_internal_name(name) is False


def test_derive_ids_rejects_invalid_author_name() -> None:
    with pytest.raises(ValueError):
        derive_ids(
            author_name="20260801",
            pack_slug="FamilyMenu",
            internal_name="TomatoStew",
        )
    with pytest.raises(ValueError):
        derive_ids(
            author_name="D20260801x",
            pack_slug="FamilyMenu",
            internal_name="TomatoStew",
        )


def test_derive_ids_rejects_invalid_pack_slug() -> None:
    with pytest.raises(ValueError):
        derive_ids(
            author_name="D20260801",
            pack_slug="Family Menu",
            internal_name="TomatoStew",
        )


def test_derive_ids_rejects_invalid_internal_name() -> None:
    with pytest.raises(ValueError):
        derive_ids(
            author_name="D20260801",
            pack_slug="FamilyMenu",
            internal_name="Tomato-Stew",
        )


def test_build_mod_id_is_stable_across_dishes() -> None:
    first = derive_ids(
        author_name="D20260801",
        pack_slug="FamilyMenu",
        internal_name="TomatoStew",
    )
    second = derive_ids(
        author_name="D20260801",
        pack_slug="FamilyMenu",
        internal_name="ParsnipSoup",
    )
    assert first.mod_id == second.mod_id
    assert first.item_id != second.item_id
