"""
Mukthi Guru -- Response Cache Service (facade)

The concrete implementations have been moved to the `services.cache` subpackage.
This module re-exports the public API for backward compatibility so existing
`from services.cache_service import ...` callers continue to work.

Design Patterns:
  - Cache-Aside Pattern: Check cache before pipeline, populate after
  - TTL-based Expiration: Entries expire after 1 hour
  - Semantic Key: Uses normalized query embedding similarity for cache hits

Zero-cost caching using Python stdlib. No external dependencies.
Invalidated automatically when new content is ingested.
"""

from services.cache import (
    CacheFactory,
    CacheInitializationError,
    CacheMode,
    EmbeddingCache,
    InMemoryCacheAdapter,
    RedisCacheAdapter,
    SearchResultCache,
    SemanticCacheAdapter,
    init_llm_cache,
)

__all__ = [
    "CacheFactory",
    "CacheInitializationError",
    "CacheMode",
    "EmbeddingCache",
    "InMemoryCacheAdapter",
    "init_llm_cache",
    "RedisCacheAdapter",
    "SearchResultCache",
    "SemanticCacheAdapter",
]
