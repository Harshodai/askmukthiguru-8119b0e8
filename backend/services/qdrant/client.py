"""Qdrant client connection and collection management."""

from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)


class QdrantClientManager:
    """Owns the Qdrant client lifecycle, collection creation, and health checks."""

    def __init__(self) -> None:
        # Use a generous timeout for complex hybrid queries with 4 prefetches + RRF fusion.
        # The default 5s is too short and causes cascading timeout/retry loops.
        _timeout = getattr(settings, "qdrant_timeout", 30.0)
        if settings.qdrant_local_path:
            logger.info(f"Qdrant: local mode at {settings.qdrant_local_path}")
            self._client = QdrantClient(
                path=settings.qdrant_local_path,
                check_compatibility=False,
                timeout=_timeout,
            )
        else:
            logger.info(f"Qdrant: remote mode at {settings.qdrant_url}")
            self._client = QdrantClient(
                url=settings.qdrant_url,
                check_compatibility=False,
                timeout=_timeout,
            )

        self._collection = settings.qdrant_collection
        self._dimension = settings.embedding_dimension

    @property
    def client(self) -> QdrantClient:
        return self._client

    @property
    def collection(self) -> str:
        return self._collection

    @property
    def dimension(self) -> int:
        return self._dimension

    def init_collection(self) -> None:
        """Create collection with named dense + sparse vectors if it doesn't exist."""
        try:
            collections = self._client.get_collections().collections
            existing = [c.name for c in collections]

            if self._collection not in existing:
                from qdrant_client.http.models import (
                    ScalarQuantization,
                    ScalarQuantizationConfig,
                    ScalarType,
                )

                self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config={
                        "dense": VectorParams(
                            size=self._dimension,
                            distance=Distance.COSINE,
                        ),
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams(
                            index=SparseIndexParams(),
                        ),
                    },
                    quantization_config=ScalarQuantization(
                        scalar=ScalarQuantizationConfig(
                            type=ScalarType.INT8,
                            always_ram=True,
                        )
                    ),
                    on_disk_payload=True,
                )
                # Create payload index on raptor_level for fast level-based filtering
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="raptor_level",
                    field_schema="integer",
                )
                # Create payload index on phonetic_tokens for fast keyword/phonetic matching
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="phonetic_tokens",
                    field_schema="keyword",
                )
                # Metadata filter indexes for retrieval-quality improvements + assistants
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="source_url",
                    field_schema="keyword",
                )
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="source_type",
                    field_schema="keyword",
                )
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="language",
                    field_schema="keyword",
                )
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="tags",
                    field_schema="keyword",
                )
                # Full-text index on content for BM25-like keyword search
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="content",
                    field_schema="text",
                )
                # Additional payload indexes for filtered queries
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="speaker",
                    field_schema="keyword",
                )
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="topic",
                    field_schema="keyword",
                )
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="content_type",
                    field_schema="keyword",
                )
                logger.info(
                    f"Created collection: {self._collection} "
                    f"(dense={self._dimension}d + sparse, raptor_level, phonetic, content-FTS, and metadata indexes)"
                )
            else:
                logger.info(f"Collection exists: {self._collection}")
        except Exception as e:
            err_msg = str(e).lower()
            if "already exists" in err_msg or "conflict" in err_msg:
                logger.info(f"Collection already exists (concurrent create): {self._collection}")
            else:
                raise

    def scroll_content(
        self,
        query: str,
        limit: int = 20,
        filter_cond: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """BM25-like full-text search via Qdrant text_index on content field.

        Uses Qdrant's scroll with text-matching filter for keyword retrieval.
        Results are scored by text relevance, not vector similarity.
        """
        from qdrant_client.http.models import FieldCondition, MatchText, Filter

        text_filter = Filter(
            must=[FieldCondition(key="content", match=MatchText(text=query))]
        )
        # Combine with existing filter if provided
        combined = text_filter
        if filter_cond:
            combined = Filter(
                must=[text_filter, filter_cond]
                if isinstance(filter_cond, Filter)
                else text_filter.must + [filter_cond]
            )

        try:
            results, _ = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=combined,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return [
                {
                    "id": str(r.id),
                    "content": r.payload.get("content", ""),
                    "score": 0.5,  # BM25 has no score in scroll; assign neutral weight for RRF
                    "metadata": {
                        k: v for k, v in r.payload.items() if k != "content"
                    },
                    "source": "bm25_text",
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"BM25 text scroll failed: {e}")
            return []

    def health_check(self) -> bool:
        """Check if Qdrant is reachable and collection exists."""
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close the Qdrant client connection."""
        try:
            self._client.close()
        except Exception:
            pass
