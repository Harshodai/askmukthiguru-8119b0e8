"""P1-BE-2 — LightRAG singleton locking + scoped cache invalidation.

Mocks only — the real LightRAG/Qdrant/Neo4j stack is never touched:
  * singleton thread-safety: concurrent first-touch construction across
    threads yields ONE instance with a single query cache;
  * ingestion invalidation: ainsert() evicts only cached results that mention
    the ingested source file, and leaves unrelated cached queries intact;
  * concurrency smoke: N parallel aquery() calls + an ingestion in between
    complete without exception or cache corruption.
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.lightrag_service import LightRAGService, _IndexingTTLCache


def _stub_service(rag=None):
    """A bare LightRAGService with a scripted internal rag component."""
    svc = LightRAGService.__new__(LightRAGService)
    svc._initialized = True
    svc._cache_ttl_seconds = 300
    svc._query_cache = _IndexingTTLCache(maxsize=2000, ttl=300)
    svc.rag = rag
    return svc


# ---------------------------------------------------------------------------
# Singleton thread-safety
# ---------------------------------------------------------------------------


def test_singleton_created_once_under_concurrency():
    """Concurrent first-touch construction must yield exactly one instance."""
    barrier = threading.Barrier(8)
    instances = []
    errors = []

    def build():
        try:
            barrier.wait(timeout=10)
            instances.append(LightRAGService())
        except Exception as e:  # pragma: no cover - failure path
            errors.append(e)

    threads = [threading.Thread(target=build) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"concurrent construction raised: {errors}"
    assert len({id(i) for i in instances}) == 1, "must be a single shared instance"
    # The shared instance must expose exactly one query cache.
    assert all(i._query_cache is instances[0]._query_cache for i in instances)


# ---------------------------------------------------------------------------
# Scoped cache invalidation on ingestion
# ---------------------------------------------------------------------------


def test_ainsert_evicts_only_overlapping_cached_queries():
    """Insertion invalidates cached results mentioning the source file; unrelated
    cached queries (and the no-file_paths no-op path) survive."""
    rag = MagicMock()
    rag.ainsert = AsyncMock()
    svc = _stub_service(rag)

    svc._query_cache["k1"] = "Karma per Sri Preethaji in talks/a.mp4"
    svc._query_cache["k2"] = "Serene Mind breathing technique"
    svc._query_cache["k3"] = "Suffering and oneness from transcript b.srt"

    asyncio.run(svc.ainsert("karma text", file_paths=["talks/a.mp4"]))

    assert "k1" not in svc._query_cache  # mentions talks/a.mp4 -> evicted
    assert "k2" in svc._query_cache  # unrelated -> kept
    assert "k3" in svc._query_cache  # mentions a different file -> kept
    rag.ainsert.assert_awaited_once()


def test_ainsert_without_file_paths_keeps_cache():
    """Insertion without provenance info must not flush unrelated cache entries."""
    rag = MagicMock()
    rag.ainsert = AsyncMock()
    svc = _stub_service(rag)

    svc._query_cache["k1"] = "Karma per Sri Preethaji in talks/a.mp4"
    asyncio.run(svc.ainsert("karma text"))
    assert "k1" in svc._query_cache  # no file_paths -> best-effort no-op


def test_ainsert_retry_path_also_scopes_invalidation():
    """The JsonDocStatusStorage-not-initialized retry path invalidates scoped too."""
    rag = MagicMock()
    rag.ainsert = AsyncMock(
        side_effect=[RuntimeError("JsonDocStatusStorage not initialized"), None]
    )
    rag.initialize_storages = AsyncMock()
    svc = _stub_service(rag)

    svc._query_cache["k1"] = "answer citing talks/a.mp4"
    svc._query_cache["k2"] = "unrelated cached query"
    asyncio.run(svc.ainsert("text", file_paths=["talks/a.mp4"]))

    assert rag.ainsert.await_count == 2
    assert "k1" not in svc._query_cache
    assert "k2" in svc._query_cache


# ---------------------------------------------------------------------------
# Concurrency smoke: parallel queries + an ingestion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_queries_with_interleaved_ingestion():
    """N concurrent aquery() calls plus an ainsert() in between must complete
    without exception, and the cache stays consistent (no corruption)."""
    rag = MagicMock()
    rag.aquery = AsyncMock(return_value="grounded answer mentioning talks/a.mp4")
    rag.ainsert = AsyncMock()
    svc = _stub_service(rag)

    async def query(i: int):
        return await svc.aquery(f"query number {i} about karma")

    async def run():
        first = await asyncio.gather(*(query(i) for i in range(10)))
        await svc.ainsert("new doctrine", file_paths=["talks/a.mp4"])
        second = await asyncio.gather(*(query(i) for i in range(10)))
        return first + second

    results = await asyncio.wait_for(run(), timeout=20)
    assert all(r == "grounded answer mentioning talks/a.mp4" for r in results)
    assert svc._query_cache is not None
    assert len(svc._query_cache) >= 1  # hits were cached, cache object intact


if __name__ == "__main__":
    # ponytail: one runnable self-check — run pytest on this module.
    raise SystemExit(pytest.main([__file__, "-v"]))
