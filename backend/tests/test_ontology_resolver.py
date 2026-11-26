from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock
try:
    from services.ontology_resolver import (
        resolve_query_concepts_llm,
        resolve_query_concepts_llm_async,
        _fallback_token_concepts,
    )
except ImportError:
    from backend.services.ontology_resolver import (
        resolve_query_concepts_llm,
        resolve_query_concepts_llm_async,
        _fallback_token_concepts,
    )


@pytest.mark.asyncio
async def test_resolve_query_concepts_llm_async_with_mock_llm():
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value='{"concepts": ["Relationship", "Hurt", "Forgiveness"]}')
    
    concepts = await resolve_query_concepts_llm_async("How do I heal hurt with my spouse?", llm_service=mock_llm)
    assert "Relationship" in concepts
    assert "Hurt" in concepts
    assert "Forgiveness" in concepts


def test_fallback_token_concepts():
    query = "How do I deal with intense anger and grief?"
    tokens = _fallback_token_concepts(query)
    assert "Deal" in tokens or "Anger" in tokens
    assert "Grief" in tokens
    assert "How" not in tokens
    assert "The" not in tokens


def test_resolve_query_concepts_llm_sync_fallback():
    # Calling without LLM service should cleanly fall back to token extraction
    concepts = resolve_query_concepts_llm("How to dissolve suffering in relationships?", llm_service=None)
    assert len(concepts) > 0
    assert any("Suffering" in c or "Relationships" in c for c in concepts)


@pytest.mark.asyncio
async def test_ontology_resolver_24h_redis_cache_roundtrip(monkeypatch):
    import services.ontology_resolver as mod

    mod._RESOLVER_CACHE.clear()
    fake_store: dict[str, tuple[int, str]] = {}

    class _FakeRedis:
        def get(self, key: str):
            entry = fake_store.get(key)
            return entry[1] if entry else None

        def setex(self, key: str, ttl: int, val: str):
            fake_store[key] = (ttl, val)

    monkeypatch.setattr(mod, "_get_redis_client", lambda: _FakeRedis())
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value='{"concepts": ["Forgiveness", "Relationship"]}')

    first = await mod.resolve_query_concepts_llm_async("How do I forgive my partner?", llm_service=mock_llm)
    assert first == ["Forgiveness", "Relationship"]
    assert len(fake_store) == 1
    ttl, _ = next(iter(fake_store.values()))
    assert ttl == 86400

    # Clear in-memory cache and confirm hit comes from Redis without calling LLM again
    mod._RESOLVER_CACHE.clear()
    second = await mod.resolve_query_concepts_llm_async("How do I forgive my partner?", llm_service=mock_llm)
    assert second == ["Forgiveness", "Relationship"]
    assert mock_llm.generate.await_count == 1



@pytest.mark.asyncio
async def test_sync_provider_adapter_runs_off_the_event_loop(monkeypatch) -> None:
    import services.ontology_resolver as mod

    mod._RESOLVER_CACHE.clear()
    monkeypatch.setattr(mod, "_redis_get_concepts", lambda _key: None)
    monkeypatch.setattr(mod, "_redis_set_concepts", lambda *_args: None)
    loop_thread = threading.get_ident()
    provider_threads: list[int] = []

    def sync_generate(**_kwargs):
        provider_threads.append(threading.get_ident())
        return '{"concepts": ["Emotional Hurt", "Forgiveness"]}'

    llm = SimpleNamespace(generate=sync_generate)
    concepts = await mod.resolve_query_concepts_llm_async(
        "sync adapter offload regression case 9f2e7",
        llm_service=llm,
        timeout_s=1.0,
    )

    assert concepts == ["Emotional Hurt", "Forgiveness"]
    assert provider_threads
    assert provider_threads[0] != loop_thread
