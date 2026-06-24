"""
Mukthi Guru — Qdrant Vector Database Service

Supports:
  - Named vectors: 'dense' (1024d cosine) + 'sparse' (lexical weights from bge-m3)
  - Hybrid search via Reciprocal Rank Fusion (RRF)
  - RAPTOR level filtering for structured retrieval
  - Deterministic point IDs for ingestion deduplication
  - Docker mode (QDRANT_URL) and local mode (QDRANT_LOCAL_PATH)
"""

from __future__ import annotations

import functools
import logging
import time
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)


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


from app.config import settings

logger = logging.getLogger(__name__)

# Namespace for deterministic UUIDs (ingestion dedup)
_NAMESPACE_URL = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # UUID NAMESPACE_URL


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


class QdrantService:
    """
    Vector database service with native hybrid search support.

    Uses named vectors (dense + sparse) and Reciprocal Rank Fusion (RRF)
    for hybrid retrieval. Supports RAPTOR level filtering and deterministic
    point IDs for automatic deduplication.
    """

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
                logger.info(
                    f"Created collection: {self._collection} "
                    f"(dense={self._dimension}d + sparse, raptor_level, phonetic, and metadata indexes)"
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
    def _is_poisoned_node(text: str) -> bool:
        """Check if a node contains template/parser leftover logs."""
        if not text:
            return False
        low = text.lower()
        poison_indicators = [
            "analyze the user's request",
            "deconstruct the request",
            "as a text correction expert",
            "as a spiritual teachings summarizer",
            "generate a short topic label",
            "3-6 words",
            "constraint:",
            "examples: \"meditation and inner peace\"",
            "specific teachings were not provided",
            "text correction expert for the 'mukthi guru'",
            "analyze the input",
            "each proposition on a new line",
            "the prompt asks me",
            "critique of a spiritual",
            "meta-commentary",
            "transcription errors",
            "transcription error",
            "misheard as",
            "the author questions",
            "the provided text is",
            "core task:",
            "decompose a spiritual",
            "decompose the following",
            "independent, self-contained propositions",
            "homophon",
            "let's check the other rules",
        ]
        return any(indicator in low for indicator in poison_indicators)

    @staticmethod
    def _sparse_dict_to_vector(sparse_dict: dict) -> SparseVector:
        """Convert bge-m3 lexical_weights dict to Qdrant SparseVector."""
        if not sparse_dict:
            return SparseVector(indices=[], values=[])
        indices = [int(k) for k in sparse_dict.keys()]
        values = [float(v) for v in sparse_dict.values()]
        return SparseVector(indices=indices, values=values)

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
            point_id = self.make_point_id(source_url, chunk_index, raptor_level)

            # Build named vector dict
            vector_dict = {"dense": vector}
            if sparse_vectors and i < len(sparse_vectors):
                sparse_vec = sparse_vectors[i]
                # Only include sparse if it has meaningful data to avoid 400 Bad Request
                if sparse_vec and (len(sparse_vec.get("indices", [])) > 0 or len(sparse_vec) > 0):
                    vector_dict["sparse"] = self._sparse_dict_to_vector(sparse_vec)

            # Generate Indic phonetic tokens for misspelling tolerance
            from services.phonetic import IndicPhoneticMatcher

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

    @retry_with_backoff(max_retries=1)
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
        # Increase limit internally to account for filtered poisoned nodes
        internal_limit = limit + 20

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

        # Metadata filters for retrieval-quality improvements + assistants
        source_url = kwargs.get("source_url")
        source_type = kwargs.get("source_type")
        language = kwargs.get("language")
        tags = kwargs.get("tags")
        title_contains = kwargs.get("title_contains")

        if source_url:
            filter_conditions.append(
                FieldCondition(key="source_url", match=MatchValue(value=source_url))
            )
        if source_type:
            filter_conditions.append(
                FieldCondition(key="source_type", match=MatchValue(value=source_type))
            )
        if language:
            filter_conditions.append(
                FieldCondition(key="language", match=MatchValue(value=language))
            )
        if tags:
            tag_values = tags if isinstance(tags, list) else [tags]
            if len(tag_values) == 1:
                filter_conditions.append(
                    FieldCondition(key="tags", match=MatchValue(value=tag_values[0]))
                )
            else:
                filter_conditions.append(
                    FieldCondition(key="tags", match=MatchAny(any=tag_values))
                )
        if title_contains:
            filter_conditions.append(
                FieldCondition(key="title", match=MatchValue(value=title_contains))
            )

        tag_must, tag_must_not = _build_tag_conditions(kwargs.get("knowledge_tags", []))
        filter_conditions.extend(tag_must)
        search_filter = Filter(
            must=filter_conditions if filter_conditions else None,
            must_not=tag_must_not if tag_must_not else None,
        )

        # Extract Indic phonetic tokens from query for misspelling tolerance
        from services.phonetic import IndicPhoneticMatcher

        query_str = kwargs.get("query", "")
        query_phonetic_tokens = (
            IndicPhoneticMatcher.get_phonetic_tokens(query_str) if query_str else []
        )

        # Hybrid search with Multi-Vector Prefetching (Ch 6 RAG Made Simple)
        if sparse_vector:
            sparse_qvec = self._sparse_dict_to_vector(sparse_vector)
            # ONLY include sparse prefetch if vector has meaningful data
            if len(sparse_qvec.indices) == 0 or len(sparse_qvec.values) == 0:
                logger.warning("Sparse vector is empty, skipping sparse lexical match prefetch")
                sparse_vector = None  # Disable sparse prefetch

        if sparse_vector or query_phonetic_tokens:
            try:
                leaf_filter = _merge_filter(
                    search_filter,
                    [FieldCondition(key="raptor_level", match=MatchValue(value=0))],
                )
                summary_filter = _merge_filter(
                    search_filter,
                    [FieldCondition(key="raptor_level", match=MatchValue(value=1))],
                )

                prefetch_queries = [
                    # Prefetch 1: Leaf Chunks (Level 0)
                    Prefetch(
                        query=query_vector,
                        using="dense",
                        limit=internal_limit,
                        filter=leaf_filter,
                    ),
                    # Prefetch 2: Summaries (Level 1)
                    Prefetch(
                        query=query_vector,
                        using="dense",
                        limit=internal_limit // 2,
                        filter=summary_filter,
                    ),
                ]

                # Prefetch 3: Sparse Lexical Match
                if sparse_vector:
                    prefetch_queries.append(
                        Prefetch(
                            query=sparse_qvec,
                            using="sparse",
                            limit=internal_limit,
                            filter=search_filter,
                        )
                    )

                # Prefetch 4: Indic Phonetic Matching (Phonetically-filtered dense search)
                if query_phonetic_tokens:
                    phonetic_should = [
                        FieldCondition(key="phonetic_tokens", match=MatchValue(value=tok))
                        for tok in query_phonetic_tokens
                    ]
                    if search_filter:
                        phonetic_filter = Filter(
                            must=list(search_filter.must) if search_filter.must else [],
                            should=phonetic_should,
                            must_not=search_filter.must_not,
                        )
                    else:
                        phonetic_filter = Filter(should=phonetic_should)
                    prefetch_queries.append(
                        Prefetch(
                            query=query_vector,
                            using="dense",
                            filter=phonetic_filter,
                            limit=internal_limit,
                        )
                    )

                results = self._client.query_points(
                    collection_name=self._collection,
                    prefetch=prefetch_queries,
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=internal_limit,
                    with_payload=True,
                )
                hits = results.points
                logger.debug(f"Hybrid search (RRF): {len(hits)} results")
            except Exception as e:
                logger.warning(f"Hybrid search failed, falling back to dense: {e}")
                hits = self._dense_search(query_vector, internal_limit, search_filter)
        else:
            hits = self._dense_search(query_vector, internal_limit, search_filter)

        # Filter out poisoned nodes
        hits = [hit for hit in hits if not self._is_poisoned_node(hit.payload.get("text", ""))]
        hits = hits[:limit]

        return [
            {
                "text": hit.payload.get("text", ""),
                "source_url": hit.payload.get("source_url", ""),
                "title": hit.payload.get("title", ""),
                "content_type": hit.payload.get("content_type", ""),
                "source_type": hit.payload.get("source_type", hit.payload.get("content_type", "")),
                "language": hit.payload.get("language", "en"),
                "tags": hit.payload.get("tags", []),
                "chunk_index": hit.payload.get("chunk_index", 0),
                "raptor_level": hit.payload.get("raptor_level", 0),
                "score": getattr(hit, "score", 0.0),
                "parent_id": hit.payload.get("parent_id"),
                "parent_text": hit.payload.get("parent_text"),
                "is_child": hit.payload.get("is_child", False),
                "speaker": hit.payload.get("speaker", "Unknown"),
                "topic": hit.payload.get("topic", "Spiritual"),
            }
            for hit in hits
        ]

    @retry_with_backoff(max_retries=3)
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
        except Exception as e:
            # Log the actual error once; do NOT fall back to a second query that
            # omits the vector name — it causes 400 Bad Request on collections
            # that only have named vectors.
            logger.warning(f"Dense search failed: {e}. Returning empty results.")
            return []

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

    def health_check(self) -> bool:
        """Check if Qdrant is reachable and collection exists."""
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def get_summary_nodes(
        self, query_vector: Optional[list[float]] = None, limit: int = 15
    ) -> list[dict]:
        """
        Retrieve RAPTOR level-1 summary nodes for tree navigation.
        If query_vector is provided, searches by similarity; otherwise scrolls.
        """
        try:
            if query_vector is not None:
                query_res = self._client.query_points(
                    collection_name=self._collection,
                    query=query_vector,
                    using="dense",
                    query_filter=Filter(
                        must=[
                            FieldCondition(
                                key="raptor_level",
                                match=MatchValue(value=1),
                            )
                        ]
                    ),
                    limit=limit,
                    with_payload=True,
                )
                results = query_res.points
            else:
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
                text = payload.get("text", "")
                if self._is_poisoned_node(text):
                    continue
                nodes.append(
                    {
                        "cluster_id": payload.get("cluster_id", 0),
                        "text": text,
                        "topic_label": payload.get("topic_label", ""),
                        "titles": payload.get("titles", []),
                        "source_urls": payload.get("source_urls", []),
                    }
                )

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
                best_score = -float("inf")
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

    @staticmethod
    def build_source_url_filter(source_url: str) -> Filter:
        """Return a Qdrant filter matching a specific source URL."""
        return Filter(
            must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
        )

    @staticmethod
    def build_source_type_filter(source_type: str) -> Filter:
        """Return a Qdrant filter matching a source_type (youtube/image/text/video/etc.)."""
        return Filter(
            must=[FieldCondition(key="source_type", match=MatchValue(value=source_type))]
        )

    @staticmethod
    def build_language_filter(language: str) -> Filter:
        """Return a Qdrant filter matching a detected language code."""
        return Filter(
            must=[FieldCondition(key="language", match=MatchValue(value=language))]
        )

    @staticmethod
    def build_tags_filter(tags: list[str] | str) -> Filter:
        """Return a Qdrant filter matching one or more tags."""
        tag_values = tags if isinstance(tags, list) else [tags]
        if len(tag_values) == 1:
            return Filter(
                must=[FieldCondition(key="tags", match=MatchValue(value=tag_values[0]))]
            )
        return Filter(
            must=[FieldCondition(key="tags", match=MatchAny(any=tag_values))]
        )

    @staticmethod
    def build_title_filter(title: str) -> Filter:
        """Return a Qdrant filter matching an exact title (useful for scoped retrieval)."""
        return Filter(
            must=[FieldCondition(key="title", match=MatchValue(value=title))]
        )

    @classmethod
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
        """
        Compose a Qdrant filter from available metadata fields.

        All provided conditions are combined with AND semantics.
        """
        conditions: list[FieldCondition] = []
        if source_url:
            conditions.append(FieldCondition(key="source_url", match=MatchValue(value=source_url)))
        if source_type:
            conditions.append(FieldCondition(key="source_type", match=MatchValue(value=source_type)))
        if language:
            conditions.append(FieldCondition(key="language", match=MatchValue(value=language)))
        if tags:
            tag_values = tags if isinstance(tags, list) else [tags]
            if len(tag_values) == 1:
                conditions.append(FieldCondition(key="tags", match=MatchValue(value=tag_values[0])))
            else:
                conditions.append(FieldCondition(key="tags", match=MatchAny(any=tag_values)))
        if title:
            conditions.append(FieldCondition(key="title", match=MatchValue(value=title)))
        if content_type:
            conditions.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))
        if raptor_level is not None:
            conditions.append(FieldCondition(key="raptor_level", match=MatchValue(value=raptor_level)))

        return Filter(must=conditions)
