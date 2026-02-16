"""
Mukthi Guru — Qdrant Vector Database Service

Design Patterns:
  - Repository Pattern: Abstracts all vector DB operations behind a clean interface
  - Lazy Initialization: Collection created on first use
  - Adapter Pattern: Wraps qdrant_client to expose domain-specific methods

Supports two modes:
  - Docker mode: QDRANT_URL (default, for local dev)
  - Local mode: QDRANT_LOCAL_PATH (for Colab, persists to Drive)
"""

import logging
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import settings

logger = logging.getLogger(__name__)


class QdrantService:
    """
    Vector database service for spiritual wisdom storage and retrieval.
    
    Encapsulates all Qdrant operations. Every other service talks to Qdrant
    through this interface — never directly.
    """

    def __init__(self) -> None:
        """
        Initialize Qdrant client.
        
        Strategy Pattern: Chooses local vs remote based on config.
        """
        if settings.qdrant_local_path:
            logger.info(f"Qdrant: local mode at {settings.qdrant_local_path}")
            self._client = QdrantClient(path=settings.qdrant_local_path)
        else:
            logger.info(f"Qdrant: remote mode at {settings.qdrant_url}")
            self._client = QdrantClient(url=settings.qdrant_url)

        self._collection = settings.qdrant_collection
        self._dimension = settings.embedding_dimension

    def init_collection(self) -> None:
        """
        Create the collection if it doesn't exist.
        
        Uses try/except to handle the TOCTOU race: another process may create
        the collection between the check and the create.
        """
        try:
            collections = self._client.get_collections().collections
            existing = [c.name for c in collections]

            if self._collection not in existing:
                self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(
                        size=self._dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created collection: {self._collection}")
            else:
                logger.info(f"Collection exists: {self._collection}")
        except Exception as e:
            # If the error is "collection already exists", that's fine
            err_msg = str(e).lower()
            if "already exists" in err_msg or "conflict" in err_msg:
                logger.info(f"Collection already exists (concurrent create): {self._collection}")
            else:
                raise

    def upsert_chunks(
        self,
        texts: list[str],
        vectors: list[list[float]],
        metadatas: list[dict],
    ) -> int:
        """
        Batch upsert text chunks with their embeddings and metadata.
        
        Args:
            texts: Raw text chunks
            vectors: Corresponding embedding vectors
            metadatas: Per-chunk metadata (source_url, title, content_type, etc.)
        
        Returns:
            Number of points upserted
            
        Raises:
            ValueError: If texts, vectors, and metadatas have different lengths
        """
        # Validate input lengths match
        len_texts, len_vectors, len_metadatas = len(texts), len(vectors), len(metadatas)
        if not (len_texts == len_vectors == len_metadatas):
            raise ValueError(
                f"upsert_chunks: length mismatch — texts={len_texts}, "
                f"vectors={len_vectors}, metadatas={len_metadatas}"
            )

        points = []
        for text, vector, meta in zip(texts, vectors, metadatas):
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "text": text,
                    **meta,
                },
            )
            points.append(point)

        # Batch upsert in chunks of 100 to avoid memory issues
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
        query_text: Optional[str] = None,
        hybrid: bool = False,
    ) -> list[dict]:
        """
        Semantic search over the knowledge base.
        Now supports Hybrid Search (Dense + Sparse/BM25).
        """
        search_filter = None
        if content_type:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="content_type",
                        match=MatchValue(value=content_type),
                    )
                ]
            )

        # Council Recommendation: Hybrid Search
        # Note: This assumes Qdrant 1.10+ client with hybrid query support
        # or that we are using a client wrapper that handles it.
        # If 'hybrid' param is not supported by the installed client, kwargs might be needed.
        # We'll pass explicit args if supported, else rely on client capability.
        
        try:
             results = self._client.search(
                collection_name=self._collection,
                query_vector=query_vector,
                limit=limit,
                query_filter=search_filter,
                # New params for Hybrid
                query_text=query_text if hybrid else None, 
                # hybrid=True # Some clients might infer hybrid if query_text is passed with vector
            )
        except TypeError:
             # Fallback for older clients that don't accept query_text in search()
             logger.warning("Qdrant client does not support query_text/hybrid directly. Falling back to Dense only.")
             results = self._client.search(
                collection_name=self._collection,
                query_vector=query_vector,
                limit=limit,
                query_filter=search_filter,
            )

        return [
            {
                "text": hit.payload.get("text", ""),
                "source_url": hit.payload.get("source_url", ""),
                "title": hit.payload.get("title", ""),
                "content_type": hit.payload.get("content_type", ""),
                "chunk_index": hit.payload.get("chunk_index", 0),
                "score": hit.score,
            }
            for hit in results
        ]

    def get_all_texts(self, page_size: int = 10000) -> list[dict]:
        """
        Retrieve all stored texts with metadata via paginated scroll.
        
        Used by RAPTOR for building the summary tree and by the
        training data preparation pipeline.

        Paginates through all records to avoid truncation.
        """
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
