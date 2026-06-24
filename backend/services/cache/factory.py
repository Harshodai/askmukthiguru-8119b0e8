"""Cache factory that selects adapters based on configured cache mode."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from app.config import settings
from services.cache.memory_adapter import InMemoryCacheAdapter
from services.cache.redis_adapter import RedisCacheAdapter
from services.cache.semantic_adapter import SemanticCacheAdapter
from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class CacheMode(str, Enum):
    """Supported cache modes."""

    MEMORY = "memory"
    REDIS = "redis"
    BEST_EFFORT = "best_effort"


class CacheFactory:
    """Factory for exact and semantic cache adapters."""

    @staticmethod
    def _resolve_mode(override: Optional[str] = None) -> str:
        mode = (override or getattr(settings, "cache_mode", CacheMode.BEST_EFFORT.value)).lower()
        valid = {m.value for m in CacheMode}
        if mode not in valid:
            logger.warning(f"Invalid cache_mode '{mode}'; falling back to '{CacheMode.BEST_EFFORT.value}'")
            mode = CacheMode.BEST_EFFORT.value
        return mode

    @classmethod
    def create_exact_cache(cls, override: Optional[str] = None) -> RedisCacheAdapter | InMemoryCacheAdapter:
        """Create the configured exact (query -> response) cache adapter.

        - memory: always use in-memory cache.
        - redis: require Redis; raise CacheInitializationError if unavailable.
        - best_effort: try Redis, fall back to in-memory if unavailable.
        """
        mode = cls._resolve_mode(override)

        if mode == CacheMode.MEMORY.value:
            logger.info("Exact cache mode: in-memory (configured)")
            return InMemoryCacheAdapter()

        redis_mode = "fail_closed" if mode == CacheMode.REDIS.value else "best_effort"
        try:
            adapter = RedisCacheAdapter(redis_url=settings.redis_url, mode=redis_mode)
        except Exception:
            if mode == CacheMode.REDIS.value:
                raise
            logger.info("Exact cache mode: Redis unavailable, falling back to in-memory")
            return InMemoryCacheAdapter()

        if mode == CacheMode.BEST_EFFORT.value and not adapter.is_available:
            logger.info("Exact cache mode: Redis unavailable, falling back to in-memory")
            return InMemoryCacheAdapter()

        logger.info(f"Exact cache mode: Redis ({redis_mode})")
        return adapter

    @classmethod
    def create_semantic_cache(
        cls,
        embedding_service: EmbeddingService,
        override: Optional[str] = None,
    ) -> Optional[SemanticCacheAdapter]:
        """Create the configured semantic cache adapter.

        - memory: semantic cache is disabled (no vector store required).
        - redis: require Redis + Qdrant; raise CacheInitializationError if unavailable.
        - best_effort: try Redis + Qdrant, disable on failure.
        """
        mode = cls._resolve_mode(override)

        if mode == CacheMode.MEMORY.value:
            logger.info("Semantic cache disabled: in-memory-only mode configured")
            return None

        redis_mode = "fail_closed" if mode == CacheMode.REDIS.value else "best_effort"
        try:
            adapter = SemanticCacheAdapter(
                embedding_service=embedding_service,
                redis_url=settings.redis_url,
                qdrant_url=settings.qdrant_url if not settings.qdrant_local_path else None,
                qdrant_path=settings.qdrant_local_path if settings.qdrant_local_path else None,
                mode=redis_mode,
            )
        except Exception:
            if mode == CacheMode.REDIS.value:
                raise
            logger.warning("Semantic cache disabled: Qdrant/Redis unavailable")
            return None

        if mode == CacheMode.BEST_EFFORT.value and not adapter.is_available:
            logger.warning("Semantic cache disabled: Qdrant/Redis unavailable")
            return None

        logger.info(f"Semantic cache mode: Qdrant+Redis ({redis_mode})")
        return adapter
