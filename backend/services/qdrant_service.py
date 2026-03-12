"""
Mukthi Guru — Qdrant Vector Database Service

Supports:
  - Named vectors: 'dense' (1024d cosine) + 'sparse' (lexical weights from bge-m3)
  - Hybrid search via Reciprocal Rank Fusion (RRF)
  - RAPTOR level filtering for structured retrieval
  - Deterministic point IDs for ingestion deduplication
  - Docker mode (QDRANT_URL) and local mode (QDRANT_LOCAL_PATH)
"""

import logging
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    SparseVector,
    Filter,
    FilterSelector,
    FieldCondition,
    MatchValue,
    Prefetch,
    FusionQuery,
    Fusion,
)

from app.config import settings

logger = logging.getLogger(__name__)

# Namespace for deterministic UUIDs (ingestion dedup)
_NAMESPACE_URL = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # UUID NAMESPACE_URL


class QdrantService:
    """
    Vector database service with native hybrid search support.

    Uses named vectors (dense + sparse) and Reciprocal Rank Fusion (RRF)
    for hybrid retrieval. Supports RAPTOR level filtering and deterministic
    point IDs for automatic deduplication.
    """

    def __init__(self) -> None:
        if settings.qdrant_local_path:
            logger.info(f"Qdrant: local mode at {settings.qdrant_local_path}")
            self._client = QdrantClient(path=settings.qdrant_local_path)
        else:
            logger.info(f"Qdrant: remote mode at {settings.qdrant_url}")
            self._client = QdrantClient(url=settings.qdrant_url)

        self._collection = settings.qdrant_collection
        self._dimension = settings.embedding_dimension

    def init_collection(self) -> None:
        """Create collection with named dense + sparse vectors if it doesn't exist."""
        try:
            collections = self._client.get_collections().collections
            existing = [c.name for c in collections]

            if self._collection not in existing:
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
                )
                # Create payload index on raptor_level for fast level-based filtering
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name="raptor_level",
                    field_schema="integer",
                )
                logger.info(
                    f"Created collection: {self._collection} "
                    f"(dense={self._dimension}d + sparse, raptor_level index)"
                )
            else:
                logger.info(f"Collection exists: {self._collection}")
        except Exception as e:
            err_msg = str(e).lower()
            if "already exists" in err_msg or "conflict" in err_msg:
                logger.info(f"Collection already exists (concurrent create): {self._collection}")
            else:
                raise

    @staticmethod
    def make_point_id(source_url: str, chunk_index: int, raptor_level: int = 0) -> str:
        """Generate a deterministic point ID for deduplication."""
        key = f"{source_url}:{chunk_index}:{raptor_level}"
        return str(uuid.uuid5(_NAMESPACE_URL, key))

    @staticmethod
    def _sparse_dict_to_vector(sparse_dict: dict) -> SparseVector:
        """Convert bge-m3 lexical_weights dict to Qdrant SparseVector."""
        if not sparse_dict:
            return SparseVector(indices=[], values=[])
        indices = [int(k) for k in sparse_dict.keys()]
        values = [float(v) for v in sparse_dict.values()]
        return SparseVector(indices=indices, values=values)

    def upsert_chunks(
        self,
        texts: list[str],
        vectors: list[list[float]],
        metadatas: list[dict],
        sparse_vectors: Optional[list[dict]] = None,
    ) -> int:
        """
        Batch upsert text chunks with dense + optional sparse vectors.

        Uses deterministic IDs based on source_url:chunk_index:raptor_level
        for automatic deduplication on re-ingestion.
        """
        len_texts, len_vectors, len_metadatas = len(texts), len(vectors), len(metadatas)
        if not (len_texts == len_vectors == len_metadatas):
            raise ValueError(
                f"upsert_chunks: length mismatch — texts={len_texts}, "
                f"vectors={len_vectors}, metadatas={len_metadatas}"
            )

        points = []
        for i, (text, vector, meta) in enumerate(zip(texts, vectors, metadatas)):
            # Deterministic ID for deduplication
            source_url = meta.get("source_url", "")
            chunk_index = meta.get("chunk_index", i)
            raptor_level = meta.get("raptor_level", 0)
            point_id = self.make_point_id(source_url, chunk_index, raptor_level)

            # Build named vector dict
            vector_dict = {"dense": vector}
            if sparse_vectors and i < len(sparse_vectors):
                vector_dict["sparse"] = self._sparse_dict_to_vector(sparse_vectors[i])

            point = PointStruct(
                id=point_id,
                vector=vector_dict,
                payload={"text": text, **meta},
            )
            points.append(point)

        # Batch upsert in chunks of 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self._client.upsert(
                collection_name=self._collection,
                points=batch,
            )

        logger.info(f"Upserted {len(points)} chunks to {self._collection}")
        return len(points)

    def search(
        self,
        query_vector: list[float],
        limit: int = 20,
        content_type: Optional[str] = None,
        sparse_vector: Optional[dict] = None,
        raptor_level: Optional[int] = None,
        **kwargs,
    ) -> list[dict]:
        """
        Hybrid search using Reciprocal Rank Fusion (RRF) over dense + sparse vectors.
        Falls back to dense-only if sparse vector not provided.
        """
        # Build filter conditions
        filter_conditions = []
        if content_type:
            filter_conditions.append(
                FieldCondition(key="content_type", match=MatchValue(value=content_type))
            )
        if raptor_level is not None:
            filter_conditions.append(
                FieldCondition(key="raptor_level", match=MatchValue(value=raptor_level))
            )
        search_filter = Filter(must=filter_conditions) if filter_conditions else None

        # Hybrid search with RRF fusion
        if sparse_vector:
            try:
                sparse_qvec = self._sparse_dict_to_vector(sparse_vector)
                prefetch_queries = [
                    Prefetch(
                        query=query_vector, using="dense",
                        limit=limit, filter=search_filter,
                    ),
                    Prefetch(
                        query=sparse_qvec, using="sparse",
                        limit=limit, filter=search_filter,
                    ),
                ]
                results = self._client.query_points(
                    collection_name=self._collection,
                    prefetch=prefetch_queries,
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=limit,
                    with_payload=True,
                )
                hits = results.points
                logger.debug(f"Hybrid search (RRF): {len(hits)} results")
            except Exception as e:
                logger.warning(f"Hybrid search failed, falling back to dense: {e}")
                hits = self._dense_search(query_vector, limit, search_filter)
        else:
            hits = self._dense_search(query_vector, limit, search_filter)

        return [
            {
                "text": hit.payload.get("text", ""),
                "source_url": hit.payload.get("source_url", ""),
                "title": hit.payload.get("title", ""),
                "content_type": hit.payload.get("content_type", ""),
                "chunk_index": hit.payload.get("chunk_index", 0),
                "raptor_level": hit.payload.get("raptor_level", 0),
                "score": getattr(hit, "score", 0.0),
            }
            for hit in hits
        ]

    def _dense_search(self, query_vector, limit, search_filter):
        """Dense-only search using the named 'dense' vector."""
        try:
            results = self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                using="dense",
                limit=limit,
                query_filter=search_filter,
                with_payload=True,
            )
            return results.points
        except Exception:
            # Final fallback for legacy collections without named vectors
            results = self._client.search(
                collection_name=self._collection,
                query_vector=query_vector,
                limit=limit,
                query_filter=search_filter,
            )
            return results

    def check_source_exists(self, source_url: str) -> bool:
        """Check if any points with this source_url already exist (dedup check)."""
        try:
            results, _ = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
                ),
                limit=1,
                with_payload=False,
            )
            return len(results) > 0
        except Exception:
            return False

    def delete_by_source(self, source_url: str) -> None:
        """Delete all points with a given source_url (for re-ingestion)."""
        try:
            self._client.delete(
                collection_name=self._collection,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(
                            key="source_url", match=MatchValue(value=source_url)
                        )]
                    )
                ),
            )
            logger.info(f"Deleted existing points for source: {source_url}")
        except Exception as e:
            logger.error(f"Failed to delete points for {source_url}: {e}")

    def get_all_texts(self, page_size: int = 10000) -> list[dict]:
        """Retrieve all stored texts with metadata via paginated scroll."""
        all_records = []
        offset = None

        while True:
            records, next_offset = self._client.scroll(
                collection_name=self._collection,
                limit=page_size,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            all_records.extend(records)

            if next_offset is None or len(records) == 0:
                break
            offset = next_offset

        return [
            {
                "text": r.payload.get("text", ""),
                "source_url": r.payload.get("source_url", ""),
                "title": r.payload.get("title", ""),
                "content_type": r.payload.get("content_type", ""),
                "raptor_level": r.payload.get("raptor_level", 0),
            }
            for r in all_records
        ]

    def count(self) -> int:
        """Get total number of indexed chunks."""
        info = self._client.get_collection(self._collection)
        return info.points_count

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
