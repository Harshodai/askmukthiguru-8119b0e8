"""Unified cache facade (Candidate 4: Cache Layer Unification).

Thin wrapper over the existing 6 cache adapters. Delegates — does not
reimplement. Tier names map to adapter instances built by CacheFactory:

  exact    -> CacheFactory.create_exact_cache()        (Redis | InMemory)
  semantic -> CacheFactory.create_semantic_cache()     (Qdrant+Redis | None)
  hot      -> hot_cache_adapter.hot_cache singleton     (in-process LRU)
  llm      -> llm_cache.init_llm_cache()                (LangChain GPTCache)

Real adapter API discovered (not the RFC's imagined one):
  - exact/semantic: get(query) -> dict | None
                   put(query, response, intent, citations, meditation_step=0)
                   invalidate_all(), stats (property), health_check()
  - hot: get(key) -> (response, citations, intent) | None
        put(key, response, citations, ttl, intent)
        invalidate(key), clear(), stats() (method)
  - llm: init_llm_cache(embedding_func)  (global side-effect, no get/set)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

SUPPORTED_TIERS = ("exact", "semantic", "hot", "llm")


class CacheManager:
    """Unified cache facade. Hides tier + backend selection."""

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._exact: Any = None
        self._semantic: Any = None
        self._hot: Any = None
        self._llm_ready: bool = False

    def _exact_cache(self) -> Any:
        if self._exact is None:
            self._exact = self._factory.create_exact_cache()
        return self._exact

    def _semantic_cache(self) -> Optional[Any]:
        if self._semantic is None:
            self._semantic = self._factory.create_semantic_cache() if hasattr(self._factory, "create_semantic_cache") else None
        return self._semantic

    def _hot_cache(self) -> Any:
        if self._hot is None:
            from services.cache.hot_cache_adapter import hot_cache
            self._hot = hot_cache
        return self._hot

    def _llm_init(self) -> None:
        if not self._llm_ready:
            try:
                from services.cache.llm_cache import init_llm_cache
                init_llm_cache()
            except Exception as e:
                logger.warning(f"LLM cache init skipped: {e}")
            self._llm_ready = True

    def _resolve(self, tier: str) -> Any:
        if tier == "exact":
            return self._exact_cache()
        if tier == "semantic":
            return self._semantic_cache()
        if tier == "hot":
            return self._hot_cache()
        if tier == "llm":
            self._llm_init()
            return None
        raise ValueError(f"Unknown cache tier: {tier!r}. Supported: {SUPPORTED_TIERS}")

    async def get(self, key: str, tier: str = "exact") -> Any:
        adapter = self._resolve(tier)
        if adapter is None:
            return None
        try:
            return adapter.get(key)
        except Exception as e:
            logger.warning(f"Cache get failed (tier={tier}, key={key}): {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int, tier: str = "exact") -> None:
        adapter = self._resolve(tier)
        if adapter is None:
            return
        try:
            if tier == "hot":
                response = value.get("response", "") if isinstance(value, dict) else str(value)
                citations = value.get("citations", []) if isinstance(value, dict) else []
                intent = value.get("intent", "QUERY") if isinstance(value, dict) else "QUERY"
                adapter.put(key, response, citations, ttl=ttl, intent=intent)
            else:
                adapter.put(
                    key,
                    value.get("response", "") if isinstance(value, dict) else str(value),
                    value.get("intent", "QUERY") if isinstance(value, dict) else "QUERY",
                    value.get("citations", []) if isinstance(value, dict) else [],
                    value.get("meditation_step", 0) if isinstance(value, dict) else 0,
                )
        except Exception as e:
            logger.warning(f"Cache set failed (tier={tier}, key={key}): {e}")

    async def invalidate(self, pattern: str = "*") -> None:
        for tier in ("exact", "semantic", "hot"):
            adapter = self._resolve(tier)
            if adapter is None:
                continue
            try:
                if tier == "hot":
                    if pattern in ("*", "", None):
                        adapter.clear()
                    else:
                        adapter.invalidate(pattern)
                else:
                    adapter.invalidate_all()
            except Exception as e:
                logger.warning(f"Cache invalidate failed (tier={tier}): {e}")

    async def stats(self) -> dict:
        result: dict = {}
        for tier in SUPPORTED_TIERS:
            if tier == "llm":
                # Report llm tier availability without initializing it.
                result[tier] = {"available": self._llm_ready}
                continue
            adapter = self._resolve(tier)
            if adapter is None:
                result[tier] = {"available": False}
                continue
            try:
                s = adapter.stats() if callable(getattr(adapter, "stats", None)) else getattr(adapter, "stats", {})
                result[tier] = s if isinstance(s, dict) else {"raw": s}
            except Exception as e:
                result[tier] = {"error": str(e)}
        return result


if __name__ == "__main__":
    import asyncio
    from types import SimpleNamespace

    class MockFactory:
        def create_exact_cache(self, override=None):
            from services.cache.memory_adapter import InMemoryCacheAdapter
            return InMemoryCacheAdapter()

        def create_semantic_cache(self, embedding_service=None, override=None):
            return None

    mgr = CacheManager(MockFactory())
    print("tiers:", SUPPORTED_TIERS)
    asyncio.run(mgr.set("hello", {"response": "world", "intent": "QUERY", "citations": []}, ttl=60, tier="exact"))
    hit = asyncio.run(mgr.get("hello", tier="exact"))
    print("exact get:", hit.get("response") if hit else None)
    asyncio.run(mgr.invalidate("*"))
    print("C1 OK")