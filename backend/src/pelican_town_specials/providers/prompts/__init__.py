"""Versioned, side-effect-free provider prompts."""

from .canonical_match_v1 import canonical_match_prompt_for
from .icon_similarity_v1 import icon_similarity_prompt_for

__all__ = ["canonical_match_prompt_for", "icon_similarity_prompt_for"]
