"""Qdrant hybrid/dense search with metadata filtering."""

from __future__ import annotations

import functools
import logging
import time
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    Prefetch,
)

from services.phonetic import IndicPhoneticMatcher
from services.qdrant.filters import QdrantFilterBuilder
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


class QdrantSearcher:
    """Hybrid and dense retrieval with metadata filtering hooks."""

    def __init__(self, client: QdrantClient, collection: str, utils: Optional[QdrantUtils] = None) -> None:
        self._client = client
        self._collection = collection
        self._utils = utils or QdrantUtils()
        self._filter_builder = QdrantFilterBuilder()

    @retry_with_backoff(max_retries=1)
    def search(
        self,
        query_vector: list[float],
        limit: int = 20,
        content_type: Optional[str] = None,
        sparse_vector: Optional[dict] = None,
        raptor_level: Optional[int] = None,
        teacher_id: Optional[str] = None,
        **kwargs,
    ) -> list[dict]:
        """
        Hybrid search using Reciprocal Rank Fusion (RRF) over dense + sparse vectors.
        Falls back to dense-only if sparse vector not provided.

        When ``teacher_id`` is provided, a ``must`` filter on the ``teacher_id``
        payload field is applied, enabling per-teacher content isolation
        (payload-based multitenancy).
        """
        # Keep internal over-fetch small — fewer prefetches means lower Qdrant latency
        # and less chance of cascading timeout/retry loops on simple FAQ queries.
        internal_limit = limit + 5

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
        if teacher_id:
            filter_conditions.append(
                FieldCondition(key="teacher_id", match=MatchValue(value=teacher_id))
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

        tag_must, tag_must_not = self._utils.build_tag_conditions(kwargs.get("knowledge_tags", []))
        filter_conditions.extend(tag_must)
        search_filter = Filter(
            must=filter_conditions if filter_conditions else None,
            must_not=tag_must_not if tag_must_not else None,
        )

        # Extract Indic phonetic tokens from query for misspelling tolerance
        query_str = kwargs.get("query", "")
        query_phonetic_tokens = (
            IndicPhoneticMatcher.get_phonetic_tokens(query_str) if query_str else []
        )

        # Hybrid search with Multi-Vector Prefetching (Ch 6 RAG Made Simple)
        if sparse_vector:
            sparse_qvec = self._utils.sparse_dict_to_vector(sparse_vector)
            # ONLY include sparse prefetch if vector has meaningful data
            if len(sparse_qvec.indices) == 0 or len(sparse_qvec.values) == 0:
                logger.warning("Sparse vector is empty, skipping sparse lexical match prefetch")
                sparse_vector = None  # Disable sparse prefetch

        # Hybrid search: only dense + sparse on the requested level.
        # Dropping the extra summary/phonetic prefetches cuts Qdrant CPU and network
        # time roughly in half, eliminating the hybrid-timeout path on simple queries.
        if sparse_vector:
            try:
                prefetch_queries = [
                    Prefetch(
                        query=query_vector,
                        using="dense",
                        limit=internal_limit,
                        filter=search_filter,
                    ),
                    Prefetch(
                        query=sparse_qvec,
                        using="sparse",
                        limit=internal_limit,
                        filter=search_filter,
                    ),
                ]

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
        hits = [hit for hit in hits if not self._utils.is_poisoned_node(hit.payload.get("text", ""))]
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
                "teacher_id": hit.payload.get("teacher_id", ""),
            }
            for hit in hits
        ]

    @staticmethod
    def _merge_filter(
        base_filter: Optional[Filter],
        extra_must: list[FieldCondition],
        extra_should: Optional[list[FieldCondition]] = None,
    ) -> Filter:
        """Merge extra must/should conditions into ``base_filter``.

        Preserves existing ``must_not`` conditions (e.g. hard ``sky`` exclusion).
        """
        must = list(base_filter.must) if base_filter and base_filter.must else []
        must.extend(extra_must)
        must_not = list(base_filter.must_not) if base_filter and base_filter.must_not else None
        should = list(base_filter.should) if base_filter and base_filter.should else []
        if extra_should:
            should.extend(extra_should)
        return Filter(
            must=must if must else None,
            must_not=must_not,
            should=should if should else None,
        )

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
