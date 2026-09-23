"""Local, read-only ingredient retrieval assets for Ask Gus."""

from .errors import IngredientRagUnavailable
from .retriever import IngredientRagRetriever

__all__ = ["IngredientRagRetriever", "IngredientRagUnavailable"]
