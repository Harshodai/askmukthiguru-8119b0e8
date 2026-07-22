"""
Mukthi Guru — Qdrant Vector Database Service (facade)

The concrete implementations have been moved to the `services.qdrant` subpackage.
This module re-exports the public API for backward compatibility so existing
`from services.qdrant_service import QdrantService` callers continue to work.

Supports:
  - Named vectors: 'dense' (1024d cosine) + 'sparse' (lexical weights from bge-m3)
  - Hybrid search via Reciprocal Rank Fusion (RRF)
  - RAPTOR level filtering for structured retrieval
  - Deterministic point IDs for ingestion deduplication
  - Docker mode (QDRANT_URL) and local mode (QDRANT_LOCAL_PATH)
"""

from __future__ import annotations

import logging
from typing import Optional

from qdrant_client.http.models import FieldCondition, Filter, MatchAny, MatchValue

from services.qdrant.client import QdrantClientManager
from services.qdrant.filters import QdrantFilterBuilder
from services.qdrant.indexer import QdrantIndexer
from services.qdrant.mmr import QdrantMMR
from services.qdrant.neighbor import QdrantNeighborLookup
from services.qdrant.raptor import QdrantRaptorStore
from services.qdrant.searcher import QdrantSearcher
from services.qdrant.utils import QdrantUtils

logger = logging.getLogger(__name__)


# Sentinel tag that requires explicit opt-in on every search
_SKY_TAG = "sky"


def _build_tag_conditions(knowledge_tags: list[str]) -> tuple[list[FieldCondition], list[FieldCondition]]:
    """
    Build (must, must_not) tag filter conditions.

    - If tags are requested, the chunk must match at least one requested tag.
    - The 'sky' tag is always excluded unless it is explicitly in the request.
    """
    must: list[FieldCondition] = []
    must_not: list[FieldCondition] = []

    requested = list({t.strip().lower() for t in (knowledge_tags or []) if t and t.strip()})
    if requested:
        must.append(FieldCondition(key="tags", match=MatchAny(any=requested)))

    if _SKY_TAG not in requested:
        must_not.append(FieldCondition(key="tags", match=MatchValue(value=_SKY_TAG)))

    return must, must_not


def _merge_filter(base_filter: Optional[Filter], extra_must: list[FieldCondition]) -> Filter:
    """Return a new filter that merges ``extra_must`` into ``base_filter``.

    Preserves any existing ``must_not`` conditions (e.g. the hard ``sky`` exclusion).
    """
    if not base_filter:
        return Filter(must=extra_must)

    must = list(base_filter.must) if base_filter.must else []
    must.extend(extra_must)
    return Filter(must=must, must_not=base_filter.must_not)


class QdrantService:
    """
    Vector database service with native hybrid search support.

    Uses named vectors (dense + sparse) and Reciprocal Rank Fusion (RRF)
    for hybrid retrieval. Supports RAPTOR level filtering and deterministic
    point IDs for automatic deduplication.

    This class is a thin facade over the `services.qdrant` subpackage.
    New code should use the subpackage classes directly; this facade is
    retained for backward compatibility.
    """

    def __init__(self) -> None:
        self._client_manager = QdrantClientManager()
        self._client = self._client_manager.client
        self._collection = self._client_manager.collection
        self._dimension = self._client_manager.dimension
        self._utils = QdrantUtils()
        self._indexer = QdrantIndexer(self._client, self._collection)
        self._searcher = QdrantSearcher(self._client, self._collection, self._utils)
        self._neighbor = QdrantNeighborLookup(self._client, self._collection)
        self._raptor = QdrantRaptorStore(self._client, self._collection, self._utils)

    # === Client / collection delegation ======================================

    def init_collection(self) -> None:
        """Create collection with named dense + sparse vectors if it doesn't exist."""
        self._client_manager.init_collection()

    def health_check(self) -> bool:
        """Check if Qdrant is reachable and collection exists."""
        return self._client_manager.health_check()

    def get_stats(self) -> dict:
        """Return per-collection statistics: points, indexed vectors, status, vector size."""
        stats = {}
        cols = self._client.get_collections()
        for c in cols.collections:
            try:
                info = self._client.get_collection(c.name)
                cfg = info.config.params
                vector_size = None
                if cfg.vectors:
                    if isinstance(cfg.vectors, dict):
                        dense = cfg.vectors.get("dense")
                        if dense:
                            vector_size = dense.size
                        elif cfg.vectors:
                            first = next(iter(cfg.vectors.values()), None)
                            vector_size = first.size if first else None
                    else:
                        vector_size = getattr(cfg.vectors, "size", None)
                stats[c.name] = {
                    "points": info.points_count,
                    "indexed_vectors": info.indexed_vectors_count,
                    "status": str(info.status),
                    "vector_size": vector_size,
                }
            except Exception:
                stats[c.name] = {"error": f"Failed to query collection '{c.name}'"}
        return stats

    def close(self) -> None:
        """Close the Qdrant client connection."""
        self._client_manager.close()

    # === Static helpers delegated to QdrantUtils =============================

    @staticmethod
    def make_point_id(source_url: str, chunk_index: int, raptor_level: int = 0) -> str:
        """Generate a deterministic point ID for deduplication."""
        return QdrantUtils.make_point_id(source_url, chunk_index, raptor_level)

    @staticmethod
    def _is_poisoned_node(text: str) -> bool:
        """Check if a node contains template/parser leftover logs."""
        return QdrantUtils.is_poisoned_node(text)

    @staticmethod
    def _sparse_dict_to_vector(sparse_dict: dict):
        """Convert bge-m3 lexical_weights dict to Qdrant SparseVector."""
        return QdrantUtils.sparse_dict_to_vector(sparse_dict)

    # === Indexing delegation =================================================

    def upsert_chunks(
        self,
        texts: list[str],
        vectors: list[list[float]],
        metadatas: list[dict],
        sparse_vectors: Optional[list[dict]] = None,
    ) -> int:
        """Batch upsert text chunks with dense + optional sparse vectors."""
        return self._indexer.upsert_chunks(texts, vectors, metadatas, sparse_vectors)

    def check_source_exists(self, source_url: str) -> bool:
        """Check if any points with this source_url already exist (dedup check)."""
        return self._indexer.check_source_exists(source_url)

    def backup_source(self, source_url: str, backup_collection: str) -> bool:
        """Copy all points for a source to a backup collection."""
        return self._indexer.backup_source(source_url, backup_collection)

    def restore_from_backup(self, source_url: str, backup_collection: str) -> bool:
        """Restore a source's points from a backup collection (Iceberg-style rollback)."""
        return self._indexer.restore_from_backup(source_url, backup_collection)

    def prune_backups(self, prefix: str, max_backups: int = 5) -> None:
        """Keep only the last N backup collections matching the prefix."""
        return self._indexer.prune_backups(prefix, max_backups)

    def delete_by_source(self, source_url: str) -> None:
        """Delete all points with a given source_url (for re-ingestion)."""
        return self._indexer.delete_by_source(source_url)

    def get_all_texts(self, page_size: int = 10000) -> list[dict]:
        """Retrieve all stored texts with metadata via paginated scroll."""
        return self._indexer.get_all_texts(page_size)

    def count(self) -> int:
        """Get total number of indexed chunks."""
        return self._indexer.count()

    # === Search delegation ===================================================

    def search(
        self,
        query_vector: list[float],
        limit: int = 20,
        content_type: Optional[str] = None,
        sparse_vector: Optional[dict] = None,
        raptor_level: Optional[int] = None,
        **kwargs,
    ) -> list[dict]:
        """Hybrid search using Reciprocal Rank Fusion (RRF) over dense + sparse vectors."""
        return self._searcher.search(
            query_vector, limit, content_type, sparse_vector, raptor_level, **kwargs
        )

    def _dense_search(self, query_vector, limit, search_filter):
        """Dense-only search using the named 'dense' vector."""
        return self._searcher._dense_search(query_vector, limit, search_filter)

    def scroll_content(
        self, query: str, limit: int = 20, filter_cond=None
    ) -> list[dict]:
        """BM25-like full-text search via Qdrant text_index on text field."""
        return self._client_manager.scroll_content(query, limit, filter_cond)

    # === Neighbor / RAPTOR delegation =======================================

    def get_neighbor_chunks(self, source_url: str, chunk_index: int, window: int = 1) -> list[dict]:
        """Retrieve chunks immediately before and after the target chunk."""
        return self._neighbor.get_neighbor_chunks(source_url, chunk_index, window)

    def get_summary_nodes(
        self, query_vector: Optional[list[float]] = None, limit: int = 15
    ) -> list[dict]:
        """Retrieve RAPTOR level-1 summary nodes for tree navigation."""
        return self._raptor.get_summary_nodes(query_vector, limit)

    # === Static MMR / filter helpers ========================================

    @staticmethod
    def mmr_select(
        query_embedding: list[float],
        documents: list[dict],
        doc_embeddings: list[list[float]],
        top_k: int = 5,
        lambda_param: float = 0.7,
    ) -> list[dict]:
        """Maximal Marginal Relevance (MMR) selection for diversity."""
        return QdrantMMR.mmr_select(query_embedding, documents, doc_embeddings, top_k, lambda_param)

    @staticmethod
    def build_source_url_filter(source_url: str) -> Filter:
        """Return a Qdrant filter matching a specific source URL."""
        return QdrantFilterBuilder.build_source_url_filter(source_url)

    @staticmethod
    def build_source_type_filter(source_type: str) -> Filter:
        """Return a Qdrant filter matching a source_type."""
        return QdrantFilterBuilder.build_source_type_filter(source_type)

    @staticmethod
    def build_language_filter(language: str) -> Filter:
        """Return a Qdrant filter matching a detected language code."""
        return QdrantFilterBuilder.build_language_filter(language)

    @staticmethod
    def build_tags_filter(tags: list[str] | str) -> Filter:
        """Return a Qdrant filter matching one or more tags."""
        return QdrantFilterBuilder.build_tags_filter(tags)

    @staticmethod
    def build_title_filter(title: str) -> Filter:
        """Return a Qdrant filter matching an exact title."""
        return QdrantFilterBuilder.build_title_filter(title)

    @classmethod
    async def delete_points(self, collection_name: str, point_ids: list[str]) -> None:
        """Delete specific points from a collection by ID."""
        self._client.delete(
            collection_name=collection_name,
            points_selector=point_ids,
        )

    def build_metadata_filter(
        cls,
        source_url: Optional[str] = None,
        source_type: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[list[str] | str] = None,
        title: Optional[str] = None,
        content_type: Optional[str] = None,
        raptor_level: Optional[int] = None,
    ) -> Filter:
        """Compose a Qdrant filter from available metadata fields."""
        return QdrantFilterBuilder.build_metadata_filter(
            source_url=source_url,
            source_type=source_type,
            language=language,
            tags=tags,
            title=title,
            content_type=content_type,
            raptor_level=raptor_level,
        )
