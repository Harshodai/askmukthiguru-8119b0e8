"""
Mukthi Guru — Semantic Cache Service

Embedding-based semantic caching that matches similar queries (not just exact matches).
Uses cosine similarity between query embeddings to identify cache hits.

Example: "how to meditate" and "meditation technique" would hit the same cache
entry if their embedding similarity exceeds the threshold (default 0.92).

Architecture:
  - Redis stores: query_embedding (JSON) + response payload + TTL
  - On lookup: compute embedding for new query, compare with all cached embeddings
  - If cosine_similarity > threshold: cache HIT
  - If below threshold: cache MISS → full RAG pipeline runs

Design: Grounded in teachings — cached responses are ALWAYS from the RAG pipeline,
never AI-generated. The cache only skips re-running the pipeline for similar questions.
"""

import hashlib
import json
import logging
import time
from typing import Optional

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class SemanticCacheService:
    """
    Embedding-based semantic cache for RAG responses.

    Stores query embeddings in Redis and matches new queries
    by cosine similarity rather than exact string match.
    """

    def __init__(self, redis_url: str, embedding_service=None):
        self._embedder = embedding_service
        self._available = False
        self._redis = None
        self._hits = 0
        self._misses = 0
        self._ttl = settings.semantic_cache_ttl
        self._threshold = settings.semantic_cache_similarity

        if not settings.semantic_cache_enabled:
            logger.info("Semantic cache DISABLED via config")
            return

        try:
            import redis

            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            self._available = True
            logger.info(
                f"Semantic cache initialized (threshold={self._threshold}, ttl={self._ttl}s)"
            )
        except Exception as e:
            logger.warning(f"Semantic cache unavailable: {e}")

    def _cache_key(self, idx: int, user_id: str = "", tenant_id: str = "default") -> str:
        if user_id:
            return f"mukthiguru:semcache:{tenant_id}:{user_id}:{idx}"
        return f"mukthiguru:semcache:{tenant_id}:shared:{idx}"

    def _index_key(self, user_id: str = "", tenant_id: str = "default") -> str:
        if user_id:
            return f"mukthiguru:semcache:{tenant_id}:{user_id}:index"
        return f"mukthiguru:semcache:{tenant_id}:shared:index"

    def get(self, query: str, query_embedding: Optional[list[float]] = None, user_id: str = "", tenant_id: str = "default") -> Optional[dict]:
        if not self._available or not self._redis:
            return None

        if query_embedding is None:
            if self._embedder is None:
                return None
            try:
                enc = self._embedder.encode_single_full(query)
                query_embedding = (
                    enc["dense"].tolist() if hasattr(enc["dense"], "tolist") else enc["dense"]
                )
            except Exception as e:
                logger.warning(f"Semantic cache: failed to encode query: {e}")
                return None

        try:
            # Get all cached entry IDs
            index_data = self._redis.get(self._index_key(user_id=user_id, tenant_id=tenant_id))
            if not index_data:
                self._misses += 1
                return None

            entry_ids = json.loads(index_data)

            # OPTIMIZATION (Phase-1 / Truth-3): Collapse N Redis GETs into a
            # SINGLE pipelined MGET. Previously this loop made N round-trips
            # to Redis (one per cached entry); now it makes one. Cuts cache
            # lookup latency from ~N*RTT to ~1*RTT.
            cache_keys = [self._cache_key(eid, user_id=user_id, tenant_id=tenant_id) for eid in entry_ids]
            try:
                entry_blobs = self._redis.mget(cache_keys)
            except Exception as mget_err:
                logger.warning(
                    f"Semantic cache: mget failed ({mget_err}); falling back to per-key GET."
                )
                # --- LEGACY (preserved per "do not delete, just comment") ---
                entry_blobs = [self._redis.get(k) for k in cache_keys]
                # ------------------------------------------------------------

            best_score = 0.0
            best_entry = None

            for entry_data in entry_blobs:
                if not entry_data:
                    continue
                try:
                    entry = json.loads(entry_data)
                except (ValueError, TypeError):
                    continue
                cached_embedding = entry.get("embedding")
                if not cached_embedding:
                    continue

                score = _cosine_similarity(query_embedding, cached_embedding)
                if score > best_score:
                    best_score = score
                    best_entry = entry

            if best_score >= self._threshold and best_entry:
                # Block generic greeting responses from being served — they occur when a
                # specific question (e.g. "how to practice soul sync") matches a generic
                # cached intent (e.g. "casual" greeting) due to high semantic similarity.
                cached_intent = best_entry.get("intent", "").upper()
                response_text = best_entry.get("response", "")
                if cached_intent in ("CASUAL", "GREETING"):
                    self._misses += 1
                    return None
                self._hits += 1
                logger.info(
                    f"Semantic cache HIT (similarity={best_score:.4f}, "
                    f"threshold={self._threshold}, hits={self._hits})"
                )
                return {
                    "response": response_text,
                    "intent": cached_intent,
                    "citations": best_entry.get("citations", []),
                    "meditation_step": best_entry.get("meditation_step", 0),
                    "cached_at": best_entry.get("cached_at", 0),
                    "semantic_similarity": best_score,
                }

            self._misses += 1
            return None

        except Exception as e:
            logger.warning(f"Semantic cache lookup failed for query={query}: {e}")
            self._misses += 1
            return None

    def put(
        self,
        query: str,
        response: str,
        intent: str,
        citations: list[str],
        query_embedding: Optional[list[float]] = None,
        meditation_step: int = 0,
        user_id: str = "",
        tenant_id: str = "default",
    ) -> None:
        if not self._available or not self._redis:
            return

        if query_embedding is None:
            if self._embedder is None:
                return
            try:
                enc = self._embedder.encode_single_full(query)
                query_embedding = (
                    enc["dense"].tolist() if hasattr(enc["dense"], "tolist") else enc["dense"]
                )
            except Exception as e:
                logger.warning(f"Semantic cache: failed to encode for storage: {e}")
                return

        try:
            # Generate entry ID
            entry_id = int(hashlib.md5(query.encode()).hexdigest()[:8], 16)

            # Store the entry
            entry = {
                "query": query,
                "embedding": query_embedding,
                "response": response,
                "intent": intent,
                "citations": citations,
                "meditation_step": meditation_step,
                "cached_at": time.time(),
                "user_id": user_id,
            }

            cache_key = self._cache_key(entry_id, user_id=user_id, tenant_id=tenant_id)
            self._redis.setex(cache_key, self._ttl, json.dumps(entry))

            # Update index
            index_data = self._redis.get(self._index_key(user_id=user_id, tenant_id=tenant_id))
            entry_ids = json.loads(index_data) if index_data else []

            if entry_id not in entry_ids:
                entry_ids.append(entry_id)
                # Cap at 500 entries to prevent index bloat
                if len(entry_ids) > 500:
                    # Remove oldest entries
                    for old_id in entry_ids[: len(entry_ids) - 500]:
                        self._redis.delete(self._cache_key(old_id, user_id=user_id, tenant_id=tenant_id))
                    entry_ids = entry_ids[-500:]

                self._redis.setex(self._index_key(user_id=user_id, tenant_id=tenant_id), self._ttl * 2, json.dumps(entry_ids))

            logger.debug(f"Semantic cache: stored entry {entry_id} ({len(entry_ids)} total)")

        except Exception as e:
            logger.warning(f"Semantic cache store failed for query={query}: {e}")

    def invalidate_all(self) -> None:
        """Clear all semantic cache entries."""
        if not self._available or not self._redis:
            return

        try:
            count = 0
            for key in self._redis.scan_iter(match="mukthiguru:semcache:*"):
                self._redis.delete(key)
                count += 1
            logger.info(f"Semantic cache invalidated ({count} entries)")
        except Exception as e:
            logger.warning(f"Semantic cache invalidation failed: {e}")

    def invalidate_by_embedding(
        self,
        new_embedding: list[float],
        similarity_threshold: float = 0.85,
        user_id: str = "",
        tenant_id: str = "default",
    ) -> int:
        """
        Invalidate cache entries whose embeddings are similar to the new content.
        Used after ingestion to prevent serving stale answers.

        Args:
            new_embedding: Embedding vector of newly ingested content
            similarity_threshold: Cosine similarity above which to invalidate
            user_id: Optional user ID for per-user cache
            tenant_id: Optional tenant ID for multi-tenancy

        Returns:
            Number of entries invalidated
        """
        if not self._available or not self._redis:
            return 0

        try:
            index_data = self._redis.get(self._index_key(user_id=user_id, tenant_id=tenant_id))
            if not index_data:
                return 0

            entry_ids = json.loads(index_data)
            cache_keys = [self._cache_key(eid, user_id=user_id, tenant_id=tenant_id) for eid in entry_ids]
            entry_blobs = self._redis.mget(cache_keys)

            invalidated = 0
            for i, entry_data in enumerate(entry_blobs):
                if not entry_data:
                    continue
                try:
                    entry = json.loads(entry_data)
                except (ValueError, TypeError):
                    continue
                cached_embedding = entry.get("embedding")
                if not cached_embedding:
                    continue

                score = _cosine_similarity(new_embedding, cached_embedding)
                if score >= similarity_threshold:
                    self._redis.delete(cache_keys[i])
                    invalidated += 1
                    logger.debug(f"Semantic cache: invalidated entry {entry_ids[i]} (similarity={score:.4f})")

            if invalidated > 0:
                # Rebuild index without invalidated entries
                remaining_ids = [
                    eid for i, eid in enumerate(entry_ids)
                    if self._redis.exists(self._cache_key(eid, user_id=user_id, tenant_id=tenant_id))
                ]
                self._redis.setex(
                    self._index_key(user_id=user_id, tenant_id=tenant_id),
                    self._ttl * 2,
                    json.dumps(remaining_ids)
                )
                logger.info(f"Semantic cache: invalidated {invalidated} entries by embedding similarity")

            return invalidated

        except Exception as e:
            logger.warning(f"Semantic cache invalidation by embedding failed: {e}")
            return 0

    @property
    def stats(self) -> dict:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total:.1%}" if total > 0 else "N/A",
            "threshold": self._threshold,
            "available": self._available,
        }

    @property
    def is_available(self) -> bool:
        return self._available


class QdrantSemanticCache:
    """Qdrant HNSW-backed semantic cache for O(log n) lookup.

    Used when settings.use_qdrant_semantic_cache is True.
    """

    def __init__(self, qdrant_service=None, embedding_service=None):
        self._qdrant = qdrant_service
        self._embedder = embedding_service
        self._available = False
        self._collection_name = settings.semantic_cache_qdrant_collection

    async def initialize(self):
        if self._qdrant is None:
            logger.warning("QdrantSemanticCache: no Qdrant service available")
            return
        try:
            from qdrant_client.http.models import VectorParams, Distance, HnswConfigDiff

            try:
                self._qdrant.get_collection(self._collection_name)
            except Exception:
                logger.info(f"Creating Qdrant collection '{self._collection_name}' for semantic cache")
                self._qdrant.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(
                        size=1024,
                        distance=Distance.COSINE,
                        on_disk=True,
                    ),
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=settings.semantic_cache_hnsw_ef,
                    ),
                )
            self._available = True
            logger.info(f"Qdrant semantic cache ready (collection={self._collection_name}, hnsw_ef={settings.semantic_cache_hnsw_ef})")
        except Exception as e:
            logger.warning(f"Qdrant semantic cache init failed: {e}")

    async def lookup(self, query_embedding: list[float], threshold: float = None) -> dict | None:
        if not self._available or self._qdrant is None:
            return None
        threshold = threshold or settings.semantic_cache_similarity
        try:
            from qdrant_client.http.models import Filter, FieldCondition, Range

            t0 = time.time()
            import asyncio

            results = await asyncio.to_thread(
                self._qdrant.search,
                collection_name=self._collection_name,
                query_vector=query_embedding,
                limit=1,
                score_threshold=threshold,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="created_at",
                            range=Range(gte=time.time() - settings.semantic_cache_ttl),
                        )
                    ]
                ),
            )
            latency = (time.time() - t0) * 1000
            try:
                from app.metrics import SEMANTIC_CACHE_LOOKUP_LATENCY

                SEMANTIC_CACHE_LOOKUP_LATENCY.observe(latency)
            except Exception:
                pass
            if results:
                logger.debug(f"Qdrant semantic cache HIT (latency={latency:.1f}ms, score={results[0].score:.4f})")
                return results[0].payload
            logger.debug(f"Qdrant semantic cache MISS (latency={latency:.1f}ms)")
            return None
        except Exception as e:
            logger.warning(f"Qdrant semantic cache lookup failed: {e}")
            return None

    async def store(self, query_embedding: list[float], response_data: dict) -> bool:
        if not self._available or self._qdrant is None:
            return False
        try:
            from qdrant_client.http.models import PointStruct
            import uuid
            import asyncio

            point = PointStruct(
                id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_DNS,
                        str(response_data.get("response", ""))[:100],
                    )
                ),
                vector=query_embedding,
                payload={
                    "response": response_data.get("response", ""),
                    "intent": response_data.get("intent", "QUERY"),
                    "citations": response_data.get("citations", []),
                    "created_at": time.time(),
                    "ttl": settings.semantic_cache_ttl,
                },
            )
            await asyncio.to_thread(
                self._qdrant.upsert,
                self._collection_name,
                points=[point],
            )
            try:
                from app.metrics import CACHE_HIT_RATIO

                CACHE_HIT_RATIO.labels(cache_type="semantic_qdrant").set(1.0)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.warning(f"Qdrant semantic cache store failed: {e}")
            return False

    @property
    def is_available(self) -> bool:
        return self._available

    async def clear(self) -> None:
        if self._qdrant is None:
            return
        try:
            import asyncio

            await asyncio.to_thread(self._qdrant.delete_collection, self._collection_name)
            self._available = False
            await self.initialize()
        except Exception as e:
            logger.warning(f"Qdrant semantic cache clear failed: {e}")

    async def count(self) -> int:
        if not self._available or self._qdrant is None:
            return 0
        try:
            import asyncio

            result = await asyncio.to_thread(self._qdrant.count, self._collection_name)
            return result.count if hasattr(result, "count") else 0
        except Exception:
            return 0
