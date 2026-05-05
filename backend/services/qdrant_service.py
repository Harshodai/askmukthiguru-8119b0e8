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
    MatchAny,
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
        if kwargs.get("cluster_ids"):
            filter_conditions.append(
                FieldCondition(key="cluster_id", match=MatchAny(any=kwargs["cluster_ids"]))
            )
        search_filter = Filter(must=filter_conditions) if filter_conditions else None

        # Hybrid search with Multi-Vector Prefetching (Ch 6 RAG Made Simple)
        if sparse_vector:
            try:
                sparse_qvec = self._sparse_dict_to_vector(sparse_vector)
                prefetch_queries = [
                    # Prefetch 1: Leaf Chunks (Level 0)
                    Prefetch(
                        query=query_vector, using="dense",
                        limit=limit, filter=Filter(must=[FieldCondition(key="raptor_level", match=MatchValue(value=0))]),
                    ),
                    # Prefetch 2: Summaries (Level 1)
                    Prefetch(
                        query=query_vector, using="dense",
                        limit=limit // 2, filter=Filter(must=[FieldCondition(key="raptor_level", match=MatchValue(value=1))]),
                    ),
                    # Prefetch 3: Sparse Lexical Match
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
                    "is_neighbor": hit.payload.get("chunk_index") != chunk_index
                }
                for hit in neighbors
            ]
        except Exception as e:
            logger.warning(f"Failed to fetch neighbors for {source_url}:{chunk_index}: {e}")
            return []

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

    def backup_source(self, source_url: str, backup_collection: str) -> bool:
        """
        Copy all points for a source to a backup collection.
        Acts as a safety net before re-processing.
        """
        try:
            # Ensure backup collection exists
            collections = [c.name for c in self._client.get_collections().collections]
            if backup_collection not in collections:
                source_config = self._client.get_collection(self._collection).config.params
                self._client.create_collection(
                    collection_name=backup_collection,
                    vectors_config=source_config.vectors,
                    sparse_vectors_config=source_config.sparse_vectors,
                )
                logger.info(f"Created backup collection: {backup_collection}")

            # Scroll all points for this source
            points, _ = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
                ),
                limit=1000, # Sources rarely have more than 1000 chunks
                with_payload=True,
                with_vectors=True,
            )

            if not points:
                return False

            # Convert to PointStruct for upsert
            backup_points = []
            for p in points:
                backup_points.append(PointStruct(
                    id=p.id,
                    vector=p.vector,
                    payload=p.payload
                ))

            self._client.upsert(collection_name=backup_collection, points=backup_points)
            logger.info(f"Backed up {len(backup_points)} points for {source_url} to {backup_collection}")
            return True
        except Exception as e:
            logger.error(f"Backup failed for {source_url}: {e}")
            return False

    def prune_backups(self, prefix: str, max_backups: int = 5) -> None:
        """
        List all collections with the given prefix and keep only the last N.
        Deletes the oldest collections based on alphanumeric order (works with timestamps).
        """
        try:
            collections = [c.name for c in self._client.get_collections().collections]
            backups = sorted([c for c in collections if c.startswith(prefix)])
            
            if len(backups) > max_backups:
                to_delete = backups[: len(backups) - max_backups]
                for coll in to_delete:
                    logger.info(f"Pruning old backup collection: {coll}")
                    self._client.delete_collection(coll)
        except Exception as e:
            logger.error(f"Failed to prune backups: {e}")

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
                "speaker": r.payload.get("speaker", "Unknown"),
                "topic": r.payload.get("topic", "Spiritual"),
                "chunk_index": r.payload.get("chunk_index", 0),
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

    def get_summary_nodes(self) -> list[dict]:
        """
        Retrieve all RAPTOR level-1 summary nodes for tree navigation.

        Returns a list of dicts with text, cluster_id, topic_label, titles,
        and source_urls — the "table of contents" for reasoning-based retrieval.
        """
        try:
            results, _ = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="raptor_level",
                            match=MatchValue(value=1),
                        )
                    ]
                ),
                limit=100,  # Unlikely to have more than 100 summary nodes
                with_payload=True,
            )

            nodes = []
            for point in results:
                payload = point.payload or {}
                nodes.append({
                    "cluster_id": payload.get("cluster_id", 0),
                    "text": payload.get("text", ""),
                    "topic_label": payload.get("topic_label", ""),
                    "titles": payload.get("titles", []),
                    "source_urls": payload.get("source_urls", []),
                })

            logger.info(f"Tree navigation: retrieved {len(nodes)} summary nodes")
            return nodes

        except Exception as e:
            logger.error(f"Failed to retrieve summary nodes: {e}")
            return []

    def close(self) -> None:
        """Close the Qdrant client connection."""
        try:
            self._client.close()
        except Exception:
            pass

    @staticmethod
    def mmr_select(
        query_embedding: list[float],
        documents: list[dict],
        doc_embeddings: list[list[float]],
        top_k: int = 5,
        lambda_param: float = 0.7,
    ) -> list[dict]:
        """
        Maximal Marginal Relevance (MMR) selection for diversity.

        Iteratively selects documents that are relevant to the query
        but dissimilar to already-selected documents.

        Args:
            query_embedding: Dense embedding of the query
            documents: List of document dicts
            doc_embeddings: Dense embeddings of each document
            top_k: Number of documents to select
            lambda_param: Balance relevance (1.0) vs diversity (0.0)

        Returns:
            List of selected document dicts (diverse and relevant)
        """
        import numpy as np

        if len(documents) <= top_k:
            return documents

        query_vec = np.array(query_embedding)
        doc_vecs = np.array(doc_embeddings)

        # Normalize for cosine similarity
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        doc_norms = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)

        # Query-document similarity
        query_sim = doc_norms @ query_norm

        selected_indices = []
        remaining = list(range(len(documents)))

        for _ in range(min(top_k, len(documents))):
            if not remaining:
                break

            if not selected_indices:
                # First pick: most relevant to query
                best_idx = remaining[np.argmax([query_sim[i] for i in remaining])]
            else:
                # Subsequent picks: MMR score
                best_score = -float('inf')
                best_idx = remaining[0]

                selected_vecs = doc_norms[selected_indices]
                for idx in remaining:
                    relevance = query_sim[idx]
                    # Max similarity to any already-selected document
                    redundancy = np.max(doc_norms[idx] @ selected_vecs.T)
                    mmr_score = lambda_param * relevance - (1 - lambda_param) * redundancy

                    if mmr_score > best_score:
                        best_score = mmr_score
                        best_idx = idx

            selected_indices.append(best_idx)
            remaining.remove(best_idx)

        return [documents[i] for i in selected_indices]
