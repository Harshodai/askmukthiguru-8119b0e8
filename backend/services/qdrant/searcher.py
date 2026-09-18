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
from services.qdrant.multitenancy_guard import enforce_multitenancy
from services.qdrant.source_policy import is_blocked_source
from services.qdrant.utils import QdrantUtils
from services.tenant_context import TenantContext

logger = logging.getLogger(__name__)


def _extract_dense_vector(hit) -> Optional[list[float]]:
    """Pull the stored dense vector off a Qdrant result point.

    Returns the vector as a plain list when present and dimensionally valid,
    else None (caller falls back to re-encoding). Named-vector collections
    expose ``hit.vector`` as ``{"dense": [...], ...}``; unnamed ones as a
    bare list.
    """
    vec = getattr(hit, "vector", None)
    if vec is None:
        return None
    if isinstance(vec, dict):
        vec = vec.get("dense")
    if vec is None:
        return None
    try:
        dense = list(vec)
    except TypeError:
        return None
    if not dense or len(dense) != settings.embedding_dimension:
        return None
    return dense


def retry_with_backoff(max_retries=3, initial_delay=1):
    """Exponential backoff decorator for Qdrant operations with jitter."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import random

            delay = initial_delay
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        break
                    jittered = delay + random.uniform(0, delay)
                    logger.warning(
                        f"Qdrant {func.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {jittered:.2f}s..."
                    )
                    time.sleep(jittered)
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

    @enforce_multitenancy
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
        group_by: Optional[str] = None,
        group_size: int = 2,
        fusion_strategy: Optional[str] = None,
        **kwargs,
    ) -> list[dict]:
        """
        Hybrid search using Reciprocal Rank Fusion (RRF) or DBSF over dense + sparse vectors.
        Falls back to dense-only if sparse vector not provided.

        When ``group_by`` is specified (e.g. "video_id", "source_url", "parent_id"),
        uses Qdrant's Universal Query API ``query_points_groups`` to group hits
        and preserve source/parent document diversity.

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
            if scope.teacher_id in (
                "preethaji",
                "krishnaji",
                "sri-preethaji",
                "sri-krishnaji",
                "ekam",
            ):
                filter_conditions.append(
                    Filter(
                        should=[
                            FieldCondition(
                                key="teacher_ids", match=MatchValue(value=scope.teacher_id)
                            ),
                            FieldCondition(
                                key="teacher_id", match=MatchValue(value=scope.teacher_id)
                            ),
                        ]
                    )
                )
            else:
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
        grouping_keys = []
        if group_by:
            if group_by in ("video_id", "source_url", "parent_id"):
                hierarchy = ["video_id", "source_url", "parent_id"]
                hierarchy.remove(group_by)
                grouping_keys = [group_by] + hierarchy
            else:
                grouping_keys = [group_by, "video_id", "source_url", "parent_id"]

        active_fusion_name = (fusion_strategy or settings.qdrant_fusion_strategy).lower()
        fusion = Fusion.DBSF if active_fusion_name == "dbsf" else Fusion.RRF

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

                if grouping_keys:
                    hits = None
                    # Per-key outcome, so the failure log below can distinguish
                    # "Qdrant raised" from "Qdrant answered with zero groups".
                    # The previous log printed only last_grp_err, which is None
                    # in the successful-but-empty case -- producing the
                    # undiagnosable "failed for keys [...]: None" that fired on
                    # 10/10 searches in the 2026-09-17 run while never saying
                    # why parent grouping was dead.
                    grp_outcomes: list[str] = []
                    for grp_key in grouping_keys:
                        try:
                            grouped_res = self._client.query_points_groups(
                                collection_name=self._collection,
                                prefetch=prefetch_queries,
                                query=FusionQuery(fusion=fusion),
                                group_by=grp_key,
                                limit=internal_limit,
                                group_size=group_size,
                                with_payload=True,
                                with_vectors=True,
                            )
                            grp_hits = []
                            for grp in grouped_res.groups:
                                for pt in grp.hits:
                                    if pt.payload is not None:
                                        pt.payload["group_id"] = str(grp.id)
                                        pt.payload["grouped_by"] = grp_key
                                    grp_hits.append(pt)
                            if grp_hits:
                                hits = grp_hits
                                logger.debug(
                                    f"Hybrid group search ({active_fusion_name}): {len(hits)} results grouped by {grp_key}"
                                )
                                break
                            # A successful-but-empty group response must not win over
                            # a broader key (or the ungrouped fallback below) that
                            # might still find matches — keep trying.
                            grp_outcomes.append(f"{grp_key}=0hits/{len(grouped_res.groups)}groups")
                            continue
                        except Exception as grp_err:
                            grp_outcomes.append(
                                f"{grp_key}=raised({type(grp_err).__name__}: {grp_err})"
                            )
                            continue

                    if hits is None:
                        logger.warning(
                            "query_points_groups produced no usable hits (%s). "
                            "Falling back to flat query_points -- parent-document "
                            "diversity is NOT being applied on this search.",
                            "; ".join(grp_outcomes) or "no keys attempted",
                        )
                        results = self._client.query_points(
                            collection_name=self._collection,
                            prefetch=prefetch_queries,
                            query=FusionQuery(fusion=fusion),
                            limit=internal_limit,
                            with_payload=True,
                            with_vectors=True,
                        )
                        hits = results.points
                else:
                    results = self._client.query_points(
                        collection_name=self._collection,
                        prefetch=prefetch_queries,
                        query=FusionQuery(fusion=fusion),
                        limit=internal_limit,
                        with_payload=True,
                        with_vectors=True,
                    )
                    hits = results.points
                    logger.debug(f"Hybrid search ({active_fusion_name}): {len(hits)} results")
            except Exception as e:
                logger.warning(f"Hybrid search failed, falling back to dense: {e}")
                hits = self._dense_search(
                    query_vector,
                    internal_limit,
                    search_filter,
                    dense_search_params,
                    grouping_keys=grouping_keys,
                    group_size=group_size,
                )
        else:
            hits = self._dense_search(
                query_vector,
                internal_limit,
                search_filter,
                dense_search_params,
                grouping_keys=grouping_keys,
                group_size=group_size,
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
                        with_vectors=True,
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

        docs = [
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
                # NAME COLLISION GUARD: the Qdrant payload key `provenance` is a
                # flat chunk-classification STRING ("verbatim_speech", etc — see
                # services/provenance.py); `services/provenance_context.py` and
                # every consumer downstream of it (citation_service, contradiction_
                # resolver) expect `item["provenance"]` to be a structured DICT.
                # Exposing the payload string under that same key crashed
                # retrieve_documents in production (`dict("verbatim_speech")` ->
                # ValueError inside _screen_prompt_injection). Surface it under an
                # unambiguous key instead; do NOT rename it back to "provenance".
                "chunk_provenance": hit.payload.get("provenance", ""),
                "score": getattr(hit, "score", 0.0),
                "parent_id": hit.payload.get("parent_id"),
                "parent_text": hit.payload.get("parent_text"),
                "group_id": hit.payload.get("group_id"),
                "grouped_by": hit.payload.get("grouped_by"),
                "video_id": hit.payload.get("video_id", ""),
                "is_child": hit.payload.get("is_child", False),
                "speaker": hit.payload.get("speaker", "Unknown"),
                "topic": hit.payload.get("topic", "Spiritual"),
                "teacher_id": hit.payload.get("teacher_id", ""),
                "teacher_ids": hit.payload.get("teacher_ids", []),
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
        # Carry the stored dense vector so MMR/rerank reuse it instead of
        # re-encoding identical text (skips the embedding inference lock).
        for doc, hit in zip(docs, hits):
            dense = _extract_dense_vector(hit)
            if dense is not None:
                doc["_dense_embedding"] = dense
        return docs

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
        grouping_keys: Optional[list[str]] = None,
        group_size: int = 2,
    ):
        """Dense-only search using the named 'dense' vector, with optional grouping support."""
        effective_params = (
            search_params if search_params is not None else self._dense_quantization_search_params()
        )
        if grouping_keys:
            for grp_key in grouping_keys:
                try:
                    grouped_res = self._client.query_points_groups(
                        collection_name=self._collection,
                        query=query_vector,
                        using="dense",
                        group_by=grp_key,
                        limit=limit,
                        group_size=group_size,
                        query_filter=search_filter,
                        search_params=effective_params,
                        with_payload=True,
                        with_vectors=True,
                    )
                    hits = []
                    for grp in grouped_res.groups:
                        for pt in grp.hits:
                            if pt.payload is not None:
                                pt.payload["group_id"] = str(grp.id)
                                pt.payload["grouped_by"] = grp_key
                            hits.append(pt)
                    if hits:
                        return hits
                    # Empty-but-successful: try a broader key rather than
                    # returning no results when one might still exist.
                    continue
                except Exception:
                    continue
        try:
            results = self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                using="dense",
                limit=limit,
                query_filter=search_filter,
                search_params=effective_params,
                with_payload=True,
                with_vectors=True,
            )
            return results.points
        except Exception as e:
            # Log the actual error once; do NOT fall back to a second query that
            # omits the vector name — it causes 400 Bad Request on collections
            # that only have named vectors.
            logger.warning(f"Dense search failed: {e}. Returning empty results.")
            return []

    @enforce_multitenancy
    @retry_with_backoff(max_retries=1)
    @track_search_latency
    def search_groups(
        self,
        query_vector: list[float],
        group_by: str = "parent_id",
        group_size: int = 2,
        limit: int = 10,
        content_type: Optional[str] = None,
        sparse_vector: Optional[dict] = None,
        raptor_level: Optional[int] = None,
        teacher_id: Optional[str] = None,
        scope: Optional[CorpusScope] = None,
        fusion_strategy: Optional[str] = None,
        **kwargs,
    ) -> list[dict]:
        """Parent Document Group Search using Qdrant Universal Query API query_points_groups.

        Combines multi-vector prefetch (dense + sparse) with Universal Fusion (RRF/DBSF)
        and groups results by parent entity (video_id, source_url, or parent_id).
        """
        return self.search(
            query_vector=query_vector,
            limit=limit,
            content_type=content_type,
            sparse_vector=sparse_vector,
            raptor_level=raptor_level,
            teacher_id=teacher_id,
            scope=scope,
            group_by=group_by,
            group_size=group_size,
            fusion_strategy=fusion_strategy,
            **kwargs,
        )
