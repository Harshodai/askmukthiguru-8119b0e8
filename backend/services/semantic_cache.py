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
            logger.warning(f"Semantic cache lookup failed: {e}")
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
            logger.warning(f"Semantic cache store failed: {e}")

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
