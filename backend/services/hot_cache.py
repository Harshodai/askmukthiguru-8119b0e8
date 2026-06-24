"""Mukthi Guru — Hot Cache facade.

The concrete implementation has moved to `services.cache.hot_cache_adapter`.
This module re-exports the public API for backward compatibility so existing
`from services.hot_cache import HotCache, hot_cache` callers continue to work.
"""

from services.cache.hot_cache_adapter import HotCache, hot_cache

__all__ = ["HotCache", "hot_cache"]
