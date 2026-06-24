"""Mukthi Guru cache adapters and helpers.

Public exports are preserved so existing `from services.cache_service import ...`
callers continue to work after the package split.
"""
from services.cache.exceptions import CacheInitializationError
from services.cache.factory import CacheFactory, CacheMode
from services.cache.hot_cache_adapter import HotCache, hot_cache
from services.cache.llm_cache import init_llm_cache
from services.cache.memory_adapter import EmbeddingCache, InMemoryCacheAdapter, SearchResultCache
from services.cache.redis_adapter import RedisCacheAdapter
from services.cache.semantic_adapter import SemanticCacheAdapter

__all__ = [
    "CacheFactory",
    "CacheInitializationError",
    "CacheMode",
    "EmbeddingCache",
    "HotCache",
    "InMemoryCacheAdapter",
    "hot_cache",
    "init_llm_cache",
    "RedisCacheAdapter",
    "SearchResultCache",
    "SemanticCacheAdapter",
]
