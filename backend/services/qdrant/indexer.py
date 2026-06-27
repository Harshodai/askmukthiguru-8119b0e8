"""Qdrant indexing operations: upsert, delete, backup, count, scroll."""

from __future__ import annotations

import functools
import logging
import time
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from app.config import settings
from services.tenant_context import TenantContext, get_tenant_collection

from services.phonetic import IndicPhoneticMatcher
from services.qdrant.utils import QdrantUtils

logger = logging.getLogger(__name__)


def retry_with_backoff(max_retries=3, initial_delay=1):
    """Exponential backoff decorator for Qdrant operations."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        break
                    logger.warning(
                        f"Qdrant {func.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                    delay *= 2

            logger.error(f"Qdrant {func.__name__} failed after {max_retries} attempts.")
            raise last_exception

        return wrapper

    return decorator


class QdrantIndexer:
    """Handles chunk upsert, source-level deletion, backup, and counts."""

    def __init__(self, client: QdrantClient, collection: Optional[str] = None) -> None:
        from services.tenant_context import TenantContext, get_tenant_collection
        
        self._client = client
        if collection:
            self._collection = collection
        else:
            # Use tenant context for collection name to support multi-tenancy
            self._collection = get_tenant_collection(settings.qdrant_collection)
        self._utils = QdrantUtils()

    @retry_with_backoff(max_retries=3)
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
            point_id = self._utils.make_point_id(source_url, chunk_index, raptor_level)

            # Build named vector dict
            vector_dict = {"dense": vector}
            if sparse_vectors and i < len(sparse_vectors):
                sparse_vec = sparse_vectors[i]
                # Only include sparse if it has meaningful data to avoid 400 Bad Request
                if sparse_vec and (len(sparse_vec.get("indices", [])) > 0 or len(sparse_vec) > 0):
                    vector_dict["sparse"] = self._utils.sparse_dict_to_vector(sparse_vec)

            # Generate Indic phonetic tokens for misspelling tolerance
            phonetic_tokens = IndicPhoneticMatcher.get_phonetic_tokens(text)

            point = PointStruct(
                id=point_id,
                vector=vector_dict,
                payload={"text": text, "phonetic_tokens": phonetic_tokens, **meta},
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
                limit=1000,  # Sources rarely have more than 1000 chunks
                with_payload=True,
                with_vectors=True,
            )

            if not points:
                return False

            # Convert to PointStruct for upsert
            backup_points = []
            for p in points:
                backup_points.append(PointStruct(id=p.id, vector=p.vector, payload=p.payload))

            self._client.upsert(collection_name=backup_collection, points=backup_points)
            logger.info(
                f"Backed up {len(backup_points)} points for {source_url} to {backup_collection}"
            )
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
                        must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
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
