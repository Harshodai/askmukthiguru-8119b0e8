"""Embedding Service Protocol — defines the contract for embedding providers.

Supports dense, sparse, and ColBERT-style encodings with optional caching.
"""

from __future__ import annotations

from typing import Any, Protocol


class EmbeddingService(Protocol):
    """Unified interface for text embedding providers (BAAI/bge-m3, E5, etc.)."""

    def encode_single_full(self, text: str) -> dict[str, Any]:
        """Encode a single text into dense + sparse vectors.

        Returns:
            {
                "dense": list[float],  # e.g. 1024-dim for bge-m3
                "sparse": dict,        # sparse representation for lexical search
            }
        """
        ...

    def encode_batch(self, texts: list[str]) -> dict[str, Any]:
        """Batch encode multiple texts into dense vectors.

        Returns:
            {
                "dense": list[list[float]],  # shape (batch, dim)
            }
        """
        ...

    def cascaded_rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        *,
        colbert_top_k: int = 20,
        cross_top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Two-stage reranking: ColBERT then CrossEncoder.

        Args:
            query: the user query
            documents: list of doc dicts with at least a "text" key
            colbert_top_k: how many to pass to ColBERT stage
            cross_top_k: how many to return after CrossEncoder
            min_score: minimum score threshold

        Returns:
            Reranked document list, highest-scoring first.
        """
        ...

    def health_check(self) -> bool:
        """Return True if the embedding service is loaded and ready."""
        ...
