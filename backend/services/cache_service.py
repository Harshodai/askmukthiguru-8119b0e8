"""
Mukthi Guru -- Response Cache Service

Design Patterns:
  - Cache-Aside Pattern: Check cache before pipeline, populate after
  - TTL-based Expiration: Entries expire after 1 hour
  - Semantic Key: Uses normalized query embedding similarity for cache hits

Zero-cost caching using Python stdlib. No external dependencies.
Invalidated automatically when new content is ingested.
"""

import hashlib
import logging
import time
from typing import Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Cache config
_CACHE_MAX_SIZE = 200  # Max cached responses
_CACHE_TTL = 3600  # 1 hour in seconds

from domain.ports.cache_port import ICacheRepository

class InMemoryCacheAdapter(ICacheRepository):
    """
    In-memory response cache with TTL expiration.

    Cache key: SHA-256 hash of normalized (lowercased, stripped) query.
    Cache value: dict with 'response', 'intent', 'citations', 'cached_at'.
    """

    def __init__(self, max_size: int = _CACHE_MAX_SIZE, ttl: int = _CACHE_TTL) -> None:
        self._cache: TTLCache = TTLCache(maxsize=max_size, ttl=ttl)
        self._hits = 0
        self._misses = 0

    def _make_key(self, query: str) -> str:
        """Normalize query and generate cache key."""
        normalized = query.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[dict]:
        """
        Look up a cached response for the given query.

        Returns cached dict or None if not found / expired.
        """
        key = self._make_key(query)
        result = self._cache.get(key)

        if result is not None:
            self._hits += 1
            logger.info(f"Cache HIT (hits={self._hits}, misses={self._misses})")
            return result

        self._misses += 1
        return None

    def put(self, query: str, response: str, intent: str, citations: list[str],
            meditation_step: int = 0) -> None:
        """Store a response in the cache."""
        key = self._make_key(query)
        self._cache[key] = {
            "response": response,
            "intent": intent,
            "citations": citations,
            "meditation_step": meditation_step,
            "cached_at": time.time(),
        }

    def invalidate_all(self) -> None:
        """Clear the entire cache (call after new content ingestion)."""
        size = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache invalidated ({size} entries cleared)")

    @property
    def stats(self) -> dict:
        """Return cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self._cache.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (
                f"{self._hits / (self._hits + self._misses):.1%}"
                if (self._hits + self._misses) > 0
                else "N/A"
            ),
        }

import json

class RedisCacheAdapter(ICacheRepository):
    """
    Redis-based semantic response cache (BE-6).
    """

    def __init__(self, redis_url: str, ttl: int = _CACHE_TTL) -> None:
        import redis
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def _make_key(self, query: str) -> str:
        """Normalize query and generate cache key."""
        normalized = query.strip().lower()
        key_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"mukthiguru:cache:{key_hash}"

    def get(self, query: str) -> Optional[dict]:
        """Look up a cached response for the given query."""
        key = self._make_key(query)
        result = self._redis.get(key)

        if result is not None:
            self._hits += 1
            logger.info(f"Redis Cache HIT (hits={self._hits}, misses={self._misses})")
            return json.loads(result)

        self._misses += 1
        return None

    def put(self, query: str, response: str, intent: str, citations: list[str],
            meditation_step: int = 0) -> None:
        """Store a response in the cache with TTL."""
        key = self._make_key(query)
        payload = {
            "response": response,
            "intent": intent,
            "citations": citations,
            "meditation_step": meditation_step,
            "cached_at": time.time(),
        }
        self._redis.setex(key, self._ttl, json.dumps(payload))

    def invalidate_all(self) -> None:
        """Clear the entire cache via namespace deletion using non-blocking SCAN batched pipeline."""
        pipe = self._redis.pipeline()
        count = 0
        for key in self._redis.scan_iter(match="mukthiguru:cache:*"):
            pipe.delete(key)
            count += 1
            # Execute in batches of 1000 to prevent large memory spikes or blocking
            if count % 1000 == 0:
                pipe.execute()
                pipe = self._redis.pipeline()
        logger.info(f"Redis Cache invalidated ({count} entries cleared)")


from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from services.embedding_service import EmbeddingService
from app.config import settings

class SemanticCacheAdapter(ICacheRepository):
    """
    Semantic response cache using Qdrant for vector similarity and Redis for TTL payload storage.
    """

    def __init__(self, embedding_service: EmbeddingService, qdrant_url: str = None, qdrant_path: str = None, redis_url: str = None, ttl: int = _CACHE_TTL) -> None:
        import redis
        self._redis = redis.from_url(redis_url, decode_responses=True)
        if qdrant_path:
            self._qdrant = QdrantClient(path=qdrant_path)
        else:
            self._qdrant = QdrantClient(url=qdrant_url, check_compatibility=False)
        self._embedder = embedding_service
        self._ttl = ttl
        self._collection = "mukthi_semantic_cache"
        self._threshold = 0.95  # 95% similarity required for a hit
        self._hits = 0
        self._misses = 0

        self._init_collection()

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
        # Qdrant requires UUIDs or integers. We'll use UUIDv5.
        import uuid
        namespace = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
        return str(uuid.uuid5(namespace, normalized))

    def get(self, query: str) -> Optional[dict]:
        """Look up a cached response semantically."""
        # Encode query
        emb = self._embedder.encode_single(query)
        
        try:
            # Search Qdrant
            results = self._qdrant.query_points(
                collection_name=self._collection,
                query=emb,
                limit=1,
                score_threshold=self._threshold
            ).points
            
            if results:
                hit = results[0]
                point_id = hit.id
                
                # Fetch payload from Redis (using the point_id as key)
                redis_key = f"mukthiguru:semcache:{point_id}"
                payload_str = self._redis.get(redis_key)
                
                if payload_str:
                    self._hits += 1
                    logger.info(f"Semantic Cache HIT (score={hit.score:.3f}, hits={self._hits}, misses={self._misses})")
                    return json.loads(payload_str)
                else:
                    # Redis TTL expired, but Qdrant vector remains. Act as miss.
                    pass
        except Exception as e:
            logger.error(f"Semantic cache get error: {e}")

        self._misses += 1
        return None

    def put(self, query: str, response: str, intent: str, citations: list[str], meditation_step: int = 0) -> None:
        """Store a response semantically."""
        point_id = self._make_id(query)
        emb = self._embedder.encode_single(query)
        
        payload = {
            "response": response,
            "intent": intent,
            "citations": citations,
            "meditation_step": meditation_step,
            "cached_at": time.time(),
        }
        
        try:
            # Upsert vector to Qdrant (payload is minimal, just original query for debugging)
            self._qdrant.upsert(
                collection_name=self._collection,
                points=[PointStruct(id=point_id, vector=emb, payload={"query": query})]
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
        return True

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

def init_llm_cache():
    """
    Initializes the global LangChain cache using GPTCache.
    This intercepts redundant LLM calls (particularly during LightRAG extraction)
    to drastically cut down latency and repetition.
    
    Gracefully skips if gptcache is not installed.
    """
    try:
        import os
        from gptcache import Cache
        from gptcache.manager.factory import manager_factory
        from gptcache.processor.pre import get_prompt
        from langchain.globals import set_llm_cache
        from langchain_community.cache import GPTCache
        
        os.makedirs("data/gptcache", exist_ok=True)
        
        def init_gptcache(cache_obj: Cache, llm: str):
            data_manager = manager_factory(
                "sqlite", 
                data_dir="data/gptcache",
                max_size=5000
            )
            cache_obj.init(
                pre_embedding_func=get_prompt,
                data_manager=data_manager,
            )

        set_llm_cache(GPTCache(init_gptcache))
        logger.info("GPTCache successfully attached to LangChain global cache.")
    except ImportError:
        logger.info("GPTCache not installed — skipping LLM call caching. Install with: pip install gptcache")
    except Exception as e:
        logger.error(f"Failed to initialize GPTCache: {e}")

