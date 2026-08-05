"""ID derivation and validation for Content Patcher packs.

Implements the ID rules from the technical design section 14.3:

- manifest ``UniqueID``: ``D20260801.PelicanTownSpecials.<PackSlug>``;
- object/recipe IDs: ``{{ModId}}_<internalName>``;
- ``PackSlug`` and ``internalName`` only use letters, digits and
  underscores, starting with a letter (3-48 characters).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_AUTHOR_NAME_PATTERN = re.compile(r"^D[0-9]{8}$")
_TOKEN_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,47}$")
_MOD_PREFIX = "PelicanTownSpecials"


@dataclass(frozen=True)
class ModIds:
    """Namespaced IDs for one compiled dish within a pack."""

    mod_id: str
    item_id: str


def validate_internal_name(name: str) -> bool:
    """Return True when the name is a safe internal name token."""
    return isinstance(name, str) and _TOKEN_PATTERN.fullmatch(name) is not None


def sanitize_token(value: str) -> str:
    """Replace characters that are unsafe in game IDs with underscores."""
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def build_mod_id(*, author_name: str, pack_slug: str) -> str:
    """Derive the manifest UniqueID from the author identity and pack slug."""
    if not isinstance(author_name, str) or _AUTHOR_NAME_PATTERN.fullmatch(author_name) is None:
        raise ValueError("author_name must match D<YYYYMMDD>")
    if not validate_internal_name(pack_slug):
        raise ValueError("pack_slug must match the required slug format")
    return f"{author_name}.{_MOD_PREFIX}.{pack_slug}"


def derive_ids(*, author_name: str, pack_slug: str, internal_name: str) -> ModIds:
    """Derive the stable manifest ID and namespaced item ID for a dish."""
    if not validate_internal_name(internal_name):
        raise ValueError("internal_name must match the required token format")
    return ModIds(
        mod_id=build_mod_id(author_name=author_name, pack_slug=pack_slug),
        item_id=f"{{{{ModId}}}}_{internal_name}",
    )
