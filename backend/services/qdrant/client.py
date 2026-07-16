"""Qdrant client connection and collection management."""

from __future__ import annotations

import logging
import re

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    HnswConfigDiff,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)


def _bm25_overlap_score(query: str, text: str) -> float:
    """Word-overlap relevance score in [0.0, 1.0] for BM25 scroll results.

    Qdrant's scroll API returns no native BM25 score, so we approximate relevance
    as the fraction of query tokens present in the matched text.
    """
    q_tokens = set(re.findall(r"\w+", query.lower()))
    if not q_tokens:
        return 0.0
    t_tokens = set(re.findall(r"\w+", text.lower()))
    return len(q_tokens & t_tokens) / len(q_tokens)


class QdrantClientManager:
    """Owns the Qdrant client lifecycle, collection creation, and health checks."""

    def __init__(self, collection: Optional[str] = None) -> None:
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
                prefer_grpc=False,
                check_compatibility=False,
                timeout=_timeout,
            )

        # Use tenant context for collection name to support multi-tenancy
        from services.tenant_context import TenantContext
        if collection:
            self._collection = collection
        else:
            from services.tenant_context import get_tenant_collection
            self._collection = get_tenant_collection(settings.qdrant_collection)

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
                    hnsw_config=HnswConfigDiff(
                        m=32,
                        ef_construct=200,
                        full_scan_threshold=10000,
                    ),
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
                # Full-text index on text for BM25-like keyword search
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="text",
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
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="title",
                    field_schema="keyword",
                )
                # Multi-teacher payload partitioning index (per-teacher isolation)
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="teacher_id",
                    field_schema="keyword",
                )
                logger.info(
                    f"Created collection: {self._collection} "
                    f"(dense={self._dimension}d + sparse, raptor_level, phonetic, text-FTS, teacher_id, and metadata indexes)"
                )
            else:
                logger.info(f"Collection exists: {self._collection}")
                self._verify_collection_dimension()
                # Ensure text-FTS index exists on already-created collections.
                # Older collections may only have the stale `content` index; create
                # the `text` index idempotently so BM25 search matches ingested payloads.
                try:
                    self._client.create_payload_index(
                        collection_name=self._collection,
                        field_name="text",
                        field_schema="text",
                    )
                    logger.info(f"Created text-FTS index on existing collection: {self._collection}")
                except Exception as idx_err:
                    err_msg = str(idx_err).lower()
                    if "already exists" in err_msg or "conflict" in err_msg:
                        logger.info(f"text-FTS index already exists on {self._collection}")
                    else:
                        logger.warning(f"Failed to ensure text-FTS index on {self._collection}: {idx_err}")

                # Ensure teacher_id index exists on already-created collections
                # (added in Phase E5 for multi-teacher payload partitioning).
                try:
                    self._client.create_payload_index(
                        collection_name=self._collection,
                        field_name="teacher_id",
                        field_schema="keyword",
                    )
                    logger.info(f"Created teacher_id index on existing collection: {self._collection}")
                except Exception as idx_err:
                    err_msg = str(idx_err).lower()
                    if "already exists" in err_msg or "conflict" in err_msg:
                        logger.info(f"teacher_id index already exists on {self._collection}")
                    else:
                        logger.warning(f"Failed to ensure teacher_id index on {self._collection}: {idx_err}")
        except Exception as e:
            err_msg = str(e).lower()
            if "already exists" in err_msg or "conflict" in err_msg:
                logger.info(f"Collection already exists (concurrent create): {self._collection}")
            else:
                raise

    def _verify_collection_dimension(self) -> None:
        """Fail loud if the existing collection's dense-vector size disagrees with config.

        A collection is created once with whatever dimension was active at the
        time (see init_collection above) and never migrated. If
        EMBEDDING_DIMENSION changes afterwards — or an encoder silently
        resolves to a different dimension, see embedding_service.py's
        _ensure_encoder — every dense search 400s with a Qdrant-side "Vector
        dimension error" while the app looks healthy (2026-07-16 incident).
        Catch that at startup instead of discovering it query-by-query.
        """
        try:
            existing = self._client.get_collection(self._collection)
            actual_dim = existing.config.params.vectors["dense"].size
        except Exception as shape_err:
            logger.warning(
                f"Could not verify collection dimension for '{self._collection}' "
                f"(skipping check): {shape_err}"
            )
            return
        if actual_dim != self._dimension:
            raise RuntimeError(
                f"Qdrant collection '{self._collection}' is {actual_dim}-dim but "
                f"settings.embedding_dimension is {self._dimension}-dim. Every dense "
                f"search will fail until this is resolved — recreate the collection "
                f"at the correct dimension or fix EMBEDDING_DIMENSION."
            )

    def scroll_content(
        self,
        query: str,
        limit: int = 20,
        filter_cond: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """BM25-like full-text search via Qdrant text_index on text field.

        Uses Qdrant's scroll with text-matching filter for keyword retrieval.
        Results are scored by text relevance, not vector similarity.
        """
        from qdrant_client.http.models import FieldCondition, MatchText, Filter

        text_filter = Filter(
            must=[FieldCondition(key="text", match=MatchText(text=query))]
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
                    "content": r.payload.get("text", ""),
                    "score": _bm25_overlap_score(query, r.payload.get("text", "")),
                    "metadata": {
                        k: v for k, v in r.payload.items() if k != "text"
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
