"""Non-sensitive internal errors for the fail-open ingredient retriever."""

from __future__ import annotations


class IngredientRagUnavailable(RuntimeError):
    """Signals a safe RAG disable reason without including query content."""

    def __init__(self, reason_code: str) -> None:
        if reason_code not in {
            "rag_model_unavailable",
            "rag_index_invalid",
            "rag_query_failed",
            "rag_tokenizer_input_unsupported",
        }:
            raise ValueError("invalid ingredient RAG reason code")
        super().__init__(reason_code)
        self.reason_code = reason_code
