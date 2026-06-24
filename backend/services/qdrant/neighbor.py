"""Neighbour-chunk lookup for context enrichment windows."""

from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
)

logger = logging.getLogger(__name__)


class QdrantNeighborLookup:
    """Retrieve chunks immediately before/after a target chunk."""

    def __init__(self, client: QdrantClient, collection: str) -> None:
        self._client = client
        self._collection = collection

    def get_neighbor_chunks(self, source_url: str, chunk_index: int, window: int = 1) -> list[dict]:
        """
        Retrieve chunks immediately before and after the target chunk.
        Used for the 'Context Enrichment Window' technique (RAG Made Simple Ch 8).
        """
        if not source_url:
            return []

        # Find indices within the window
        indices = list(range(chunk_index - window, chunk_index + window + 1))
        # Remove the target chunk itself if you only want neighbors,
        # but usually we want the whole window for sequence.

        try:
            results, _ = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="source_url", match=MatchValue(value=source_url)),
                        FieldCondition(key="chunk_index", match=MatchAny(any=indices)),
                        FieldCondition(key="raptor_level", match=MatchValue(value=0)),
                    ]
                ),
                limit=len(indices),
                with_payload=True,
            )

            # Sort by chunk_index to maintain sequence
            neighbors = sorted(results, key=lambda x: x.payload.get("chunk_index", 0))

            return [
                {
                    "text": hit.payload.get("text", ""),
                    "source_url": hit.payload.get("source_url", ""),
                    "title": hit.payload.get("title", ""),
                    "chunk_index": hit.payload.get("chunk_index", 0),
                    "raptor_level": hit.payload.get("raptor_level", 0),
                    "is_neighbor": hit.payload.get("chunk_index") != chunk_index,
                }
                for hit in neighbors
            ]
        except Exception as e:
            logger.warning(f"Failed to fetch neighbors for {source_url}:{chunk_index}: {e}")
            return []
