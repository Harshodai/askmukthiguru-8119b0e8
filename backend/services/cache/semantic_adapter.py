"""Qdrant + Redis semantic cache adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.config import settings
from domain.ports.cache_port import ICacheRepository
from services.cache.constants import _CACHE_TTL
from services.cache.exceptions import CacheInitializationError
from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class SemanticCacheAdapter(ICacheRepository):
    """
    Semantic response cache using Qdrant for vector similarity and Redis for TTL payload storage.

    Init modes:
      - best_effort (default): try Qdrant + Redis, disable semantic caching on failure.
      - fail_closed: raise CacheInitializationError if Redis or Qdrant is unavailable.
        Use this when semantic caching is required for correctness.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        qdrant_url: str = None,
        qdrant_path: str = None,
        redis_url: str = None,
        ttl: int = None,
        mode: str = "best_effort",
    ) -> None:
        import redis

        self._embedder = embedding_service
        self._ttl = ttl if ttl is not None else getattr(settings, "semantic_cache_ttl", _CACHE_TTL)
        self._collection = f"mukthi_semantic_cache_{settings.embedding_dimension}d"
        self._threshold = getattr(settings, "semantic_cache_similarity", 0.78)
        self._hits = 0
        self._misses = 0
        self._redis = None
        self._qdrant = None
        self._available = False
        self._mode = mode

        try:
            self._redis = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            if qdrant_path:
                self._qdrant = QdrantClient(path=qdrant_path)
            else:
                self._qdrant = QdrantClient(url=qdrant_url, check_compatibility=False, timeout=60.0)
            self._init_collection()
            self._available = True
        except Exception as e:
            if mode == "fail_closed":
                raise CacheInitializationError(
                    f"Semantic cache is required but unavailable (mode={mode}, qdrant={qdrant_url or qdrant_path}, redis={redis_url}): {e}"
                ) from e
            logger.warning(f"SemanticCacheAdapter init failed: {e}. Semantic caching disabled.")
            self._redis = None
            self._qdrant = None

    @property
    def mode(self) -> str:
        return self._mode

    def health_check(self) -> bool:
        """Verify Qdrant and Redis connections are alive."""
        if not self._available or self._qdrant is None or self._redis is None:
            return False
        try:
            qdrant_ok = self._qdrant.get_collections() is not None
            redis_ok = self._redis.ping()
            return qdrant_ok and redis_ok
        except Exception:
            return False

    def _init_collection(self):
        try:
            collections = [c.name for c in self._qdrant.get_collections().collections]
            if self._collection not in collections:
                self._qdrant.create_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(
                        size=settings.embedding_dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created semantic cache collection: {self._collection}")
        except Exception as e:
            logger.warning(f"Semantic cache collection init issue: {e}")

    def _make_id(self, query: str) -> str:
        """Deterministic ID based on query string."""
        normalized = query.strip().lower()
        namespace = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
        return str(uuid.uuid5(namespace, normalized))

    def get(self, query: str) -> Optional[dict]:
        """Look up a cached response semantically."""
        # Split language prefix if present, and embed using encode_single_full
        parts = query.split(":", 1)
        if len(parts) == 2 and len(parts[0]) <= 5:
            lang, raw_query = parts[0], parts[1]
        else:
            lang, raw_query = "en", query

        emb_dict = self._embedder.encode_single_full(raw_query)
        emb = emb_dict["dense"]

        try:
            # Search Qdrant
            results = self._qdrant.query_points(
                collection_name=self._collection,
                query=emb,
                limit=1,
                score_threshold=self._threshold,
            ).points

            if results:
                hit = results[0]
                point_id = hit.id

                # Fetch payload from Redis (using the point_id as key)
                redis_key = f"mukthiguru:semcache:{point_id}"
                payload_str = self._redis.get(redis_key)

                if payload_str:
                    cached = json.loads(payload_str)
                    cached_lang = cached.get("language", "en")
                    if cached_lang != lang:
                        logger.info(
                            f"Semantic Cache language mismatch: cached={cached_lang}, requested={lang}. Treating as miss."
                        )
                    else:
                        self._hits += 1
                        logger.info(
                            f"Semantic Cache HIT (score={hit.score:.3f}, lang={lang}, hits={self._hits}, misses={self._misses})"
                        )
                        return cached
                else:
                    # Redis TTL expired, but Qdrant vector remains. Act as miss.
                    pass
        except Exception as e:
            logger.error(f"Semantic cache get error: {e}")

        self._misses += 1
        return None

    def put(
        self, query: str, response: str, intent: str, citations: list[str], meditation_step: int = 0
    ) -> None:
        """Store a response semantically."""
        point_id = self._make_id(query)

        parts = query.split(":", 1)
        if len(parts) == 2 and len(parts[0]) <= 5:
            lang, raw_query = parts[0], parts[1]
        else:
            lang, raw_query = "en", query

        emb_dict = self._embedder.encode_single_full(raw_query)
        emb = emb_dict["dense"]

        payload = {
            "response": response,
            "intent": intent,
            "citations": citations,
            "meditation_step": meditation_step,
            "cached_at": time.time(),
            "language": lang,
        }

        try:
            # Upsert vector to Qdrant (payload is minimal, just original query for debugging)
            self._qdrant.upsert(
                collection_name=self._collection,
                points=[PointStruct(id=point_id, vector=emb, payload={"query": query})],
            )

            # Save actual response payload to Redis with TTL
            redis_key = f"mukthiguru:semcache:{point_id}"
            self._redis.setex(redis_key, self._ttl, json.dumps(payload))
        except Exception as e:
            logger.error(f"Semantic cache put error: {e}")

    def invalidate_all(self) -> None:
        """Clear the semantic cache."""
        try:
            self._qdrant.delete_collection(self._collection)
            self._init_collection()

            # Clear Redis keys
            pipe = self._redis.pipeline()
            count = 0
            for key in self._redis.scan_iter(match="mukthiguru:semcache:*"):
                pipe.delete(key)
                count += 1
            pipe.execute()
            logger.info(f"Semantic Cache invalidated ({count} entries cleared)")
        except Exception as e:
            logger.error(f"Semantic cache invalidation error: {e}")

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total:.1%}" if total > 0 else "N/A",
            "threshold": self._threshold,
            "available": True,
        }
