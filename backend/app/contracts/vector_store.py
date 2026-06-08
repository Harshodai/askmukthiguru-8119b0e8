"""Vector Store Protocol — defines the contract for vector databases.

Supports dense search, sparse search, and hybrid retrieval (RRF).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol


class VectorStore(Protocol):
    """Unified interface for vector database providers (Qdrant, Pinecone, etc.)."""

    def search(
        self,
        *,
        query_vector: list[float],
        limit: int = 10,
        sparse_vector: Optional[dict[str, Any]] = None,
        raptor_level: int = 0,
        cluster_ids: Optional[list[str]] = None,
        query: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Search the vector store for relevant documents.

        Args
        ----
        query_vector: dense embedding of the query
        limit: maximum number of results
        sparse_vector: optional sparse vector for hybrid search
        raptor_level: RAPTOR hierarchy level (0=leaf, 1=summary)
        cluster_ids: optional list of cluster UUIDs to restrict search
        query: raw query string (optional, for logging / re-ranking hints)

        Returns:
            List of document dicts with keys like text, title, source_url, score, etc.
        """
        ...

    def upsert_chunks(self, chunks: list[dict[str, Any]], **kwargs: Any) -> None:
        """Upsert (insert or update) document chunks into the store.

        Args:
            chunks: list of chunk dicts with embedding, text, metadata, etc.
        """
        ...

    def get_neighbor_chunks(
        self,
        source_url: str,
        chunk_index: int,
        *,
        window: int = 2,
    ) -> list[dict[str, Any]]:
        """Fetch neighbor chunks around a given chunk index (temporal window).

        Args:
            source_url: the parent document's source URL
            chunk_index: the central chunk index
            window: number of chunks before and after to fetch

        Returns:
            List of neighbor chunk dicts.
        """
        ...

    def count(self) -> int:
        """Return total number of indexed chunks."""
        ...

    def health_check(self) -> bool:
        """Return True if the store is reachable and healthy."""
        ...
