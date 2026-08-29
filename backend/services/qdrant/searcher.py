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
    QuantizationSearchParams,
    SearchParams,
)

from app.config import settings
from rag.corpus_scope import CorpusScope
from services.qdrant.filters import QdrantFilterBuilder
from services.qdrant.metrics import track_search_latency
from services.qdrant.source_policy import is_blocked_source
from services.qdrant.utils import QdrantUtils
from services.tenant_context import TenantContext

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
            if last_exception is not None:
                raise last_exception
            raise RuntimeError(f"Qdrant {func.__name__} failed after {max_retries} attempts.")

        return wrapper

    return decorator


class QdrantSearcher:
    """Hybrid and dense retrieval with metadata filtering hooks."""

    def __init__(
        self, client: QdrantClient, collection: str, utils: Optional[QdrantUtils] = None
    ) -> None:
        self._client = client
        self._collection = collection
        self._utils = utils or QdrantUtils()
        self._filter_builder = QdrantFilterBuilder()

    @retry_with_backoff(max_retries=1)
    @track_search_latency
    def search(
        self,
        query_vector: list[float],
        limit: int = 20,
        content_type: Optional[str] = None,
        sparse_vector: Optional[dict] = None,
        raptor_level: Optional[int] = None,
        teacher_id: Optional[str] = None,
        scope: Optional[CorpusScope] = None,
        **kwargs,
    ) -> list[dict]:
        """
        Hybrid search using Reciprocal Rank Fusion (RRF) over dense + sparse vectors.
        Falls back to dense-only if sparse vector not provided.

        When ``teacher_id`` is provided, a ``must`` filter on the ``teacher_id``
        payload field is applied, enabling per-teacher content isolation
        (payload-based multitenancy).
        """
        tenant_id = TenantContext.get()
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            tenant_id = settings.default_tenant_id
        corpus_id = getattr(settings, "default_corpus_id", "askmukthiguru")
        if not isinstance(corpus_id, str) or not corpus_id.strip():
            corpus_id = "askmukthiguru"
        scope = scope or CorpusScope(
            tenant_id=tenant_id,
            corpus_id=corpus_id,
            teacher_id=teacher_id,
        )
        # Keep internal over-fetch small — fewer prefetches means lower Qdrant latency
        # and less chance of cascading timeout/retry loops on simple FAQ queries.
        internal_limit = limit + 5

        # Build filter conditions. Tenant and corpus scope are mandatory for every search.
        filter_conditions = [
            FieldCondition(key="tenant_id", match=MatchValue(value=scope.tenant_id)),
            FieldCondition(key="corpus_id", match=MatchValue(value=scope.corpus_id)),
        ]
        if content_type:
            filter_conditions.append(
                FieldCondition(key="content_type", match=MatchValue(value=content_type))
            )
        if raptor_level is not None:
            filter_conditions.append(
                FieldCondition(key="raptor_level", match=MatchValue(value=raptor_level))
            )
        if scope.teacher_id:
            filter_conditions.append(
                FieldCondition(key="teacher_id", match=MatchValue(value=scope.teacher_id))
            )
        if scope.required_rights_status:
            filter_conditions.append(
                FieldCondition(
                    key="domain_rights_status",
                    match=MatchValue(value=scope.required_rights_status),
                )
            )
        if kwargs.get("cluster_ids"):
            filter_conditions.append(
                FieldCondition(key="cluster_id", match=MatchAny(any=kwargs["cluster_ids"]))
            )

        # Optional graph-linked prefetch: it is an additional candidate channel,
        # never a mandatory filter. Legacy chunks without graph metadata remain
        # eligible through the ordinary dense/sparse path.
        graph_entity_ids = kwargs.get("graph_entity_ids") or kwargs.get("entity_ids")
        graph_prefetch_enabled = bool(kwargs.get("graph_prefetch_enabled", False))

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
                filter_conditions.append(FieldCondition(key="tags", match=MatchAny(any=tag_values)))
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

        # No phonetic token extraction here: the prefetch that consumed it was
        # removed (see below), so computing it was per-query work with no reader.

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
        dense_search_params = self._dense_quantization_search_params()
        if sparse_vector:
            # Read config OUTSIDE the try below. That `except` exists to survive a
            # Qdrant transport failure, and it falls back to dense-only — a real
            # retrieval-quality drop. A misconfigured multiplier is not a transport
            # failure, and letting it land in that handler would silently disable
            # hybrid search on every query while health stayed green.
            dense_limit = max(1, round(internal_limit * settings.qdrant_dense_prefetch_multiplier))
            sparse_limit = max(
                1, round(internal_limit * settings.qdrant_sparse_prefetch_multiplier)
            )
            fusion = Fusion.DBSF if settings.qdrant_fusion_strategy == "dbsf" else Fusion.RRF
            try:
                prefetch_queries = [
                    Prefetch(
                        query=query_vector,
                        using="dense",
                        limit=dense_limit,
                        filter=search_filter,
                        params=dense_search_params,
                    ),
                    Prefetch(
                        query=sparse_qvec,
                        using="sparse",
                        limit=sparse_limit,
                        filter=search_filter,
                    ),
                ]

                if graph_prefetch_enabled and graph_entity_ids:
                    graph_filter = Filter(
                        must=list(filter_conditions),
                        should=[
                            FieldCondition(
                                key="entity_ids",
                                match=MatchAny(any=list(graph_entity_ids)),
                            ),
                            FieldCondition(
                                key="graph_node_ids",
                                match=MatchAny(any=list(graph_entity_ids)),
                            ),
                        ],
                    )
                    prefetch_queries.append(
                        Prefetch(
                            query=query_vector,
                            using="dense",
                            limit=max(1, internal_limit // 2),
                            filter=graph_filter,
                            params=dense_search_params,
                        )
                    )
                results = self._client.query_points(
                    collection_name=self._collection,
                    prefetch=prefetch_queries,
                    query=FusionQuery(fusion=fusion),
                    limit=internal_limit,
                    with_payload=True,
                )
                hits = results.points
                logger.debug(f"Hybrid search (RRF): {len(hits)} results")
            except Exception as e:
                logger.warning(f"Hybrid search failed, falling back to dense: {e}")
                hits = self._dense_search(
                    query_vector, internal_limit, search_filter, dense_search_params
                )
        else:
            hits = self._dense_search(
                query_vector, internal_limit, search_filter, dense_search_params
            )
            if graph_prefetch_enabled and graph_entity_ids:
                try:
                    graph_filter = Filter(
                        must=list(filter_conditions),
                        should=[
                            FieldCondition(
                                key="entity_ids",
                                match=MatchAny(any=list(graph_entity_ids)),
                            ),
                            FieldCondition(
                                key="graph_node_ids",
                                match=MatchAny(any=list(graph_entity_ids)),
                            ),
                        ],
                    )
                    graph_results = self._client.query_points(
                        collection_name=self._collection,
                        query=query_vector,
                        using="dense",
                        limit=max(1, internal_limit // 2),
                        query_filter=graph_filter,
                        search_params=dense_search_params,
                        with_payload=True,
                    )
                    hits.extend(graph_results.points)
                except Exception as exc:
                    logger.info("Optional graph-linked Qdrant prefetch failed open: %s", exc)

        # Filter out poisoned nodes and quarantined rights-risk sources before
        # converting payloads into generation-ready documents. This remains a
        # serving-time defense even while legacy vector points are being removed
        # through a separate, audited maintenance operation.
        screened_hits = []
        for hit in hits:
            payload = hit.payload or {}
            if self._utils.is_poisoned_node(payload.get("text", "")):
                continue
            if is_blocked_source(payload):
                continue
            screened_hits.append(hit)
        hits = screened_hits[:limit]

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
                "licensed_domain": hit.payload.get("licensed_domain", ""),
                "domain_rights_status": hit.payload.get("domain_rights_status", ""),
                "tenant_id": hit.payload.get("tenant_id", ""),
                "corpus_id": hit.payload.get("corpus_id", ""),
                "entity_ids": hit.payload.get("entity_ids", []),
                "graph_node_ids": hit.payload.get("graph_node_ids", []),
                "context_cluster_ids": hit.payload.get("context_cluster_ids", []),
                "source_segment_ids": hit.payload.get("source_segment_ids", []),
                "ontology_version": hit.payload.get("ontology_version"),
                "entity_resolution_confidence": hit.payload.get("entity_resolution_confidence"),
                "chunk_id": hit.payload.get("chunk_id") or hit.id,
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

    def _dense_quantization_search_params(self) -> Optional[SearchParams]:
        """Return search params with rescore + oversampling for non-scalar quantizers.

        Scalar INT8 is Qdrant's default quantization baseline and does not need
        extra search-time parameters. Binary and TurboQuant benefit from
        oversampling + rescoring against the original full-precision vectors.
        """
        if settings.qdrant_quantization == "scalar_int8":
            return None
        return SearchParams(
            quantization=QuantizationSearchParams(
                rescore=True,
                oversampling=settings.qdrant_quantization_oversampling,
            )
        )

    def _dense_search(
        self,
        query_vector,
        limit,
        search_filter,
        search_params: Optional[SearchParams] = None,
    ):
        """Dense-only search using the named 'dense' vector."""
        try:
            results = self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                using="dense",
                limit=limit,
                query_filter=search_filter,
                search_params=search_params
                if search_params is not None
                else self._dense_quantization_search_params(),
                with_payload=True,
            )
            return results.points
        except Exception as e:
            # Log the actual error once; do NOT fall back to a second query that
            # omits the vector name — it causes 400 Bad Request on collections
            # that only have named vectors.
            logger.warning(f"Dense search failed: {e}. Returning empty results.")
            return []
