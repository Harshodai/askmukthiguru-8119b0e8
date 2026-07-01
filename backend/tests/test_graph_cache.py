"""
Phase 1.5a — Graph compile cache.

Asserts that ``build_rag_graph`` / ``build_fast_graph`` / ``build_deep_graph``
return the SAME compiled graph instance on repeated calls (lru_cache by
strategy name) and that the cached object is a runnable CompiledStateGraph.

A full ``ainvoke`` is intentionally NOT exercised here — it requires the
complete service graph (intent_router LLM call, distress check, retrieval,
...) and is covered by ``test_nodes.py`` and ``test_chat_endpoint.py``. The
cache contract is purely about identity and type, so that is what we check.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.graph as graph
from rag.graph_strategies import build_cached, clear_graph_cache


class _MockEmbedder:
    """Minimal embedder satisfying init_services' LettuceDetect construction."""

    def encode_single_full(self, text):
        return {"dense": [0.1] * 384, "sparse": {}}

    def encode_batch(self, texts):
        return {"dense": [[0.1] * 384 for _ in texts]}

    def encode_single(self, text):
        return [0.1] * 384


def _mock_services():
    return {
        "ollama_service": AsyncMock(),
        "embedding_service": _MockEmbedder(),
        "qdrant_service": MagicMock(),
        "lightrag_service": MagicMock(),
        "serene_mind_engine": MagicMock(),
        "web_search": None,
    }


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_graph_cache()
    yield
    clear_graph_cache()


@pytest.mark.parametrize(
    "build_fn, name",
    [
        (graph.build_rag_graph, "standard"),
        (graph.build_fast_graph, "fast"),
        (graph.build_deep_graph, "deep"),
    ],
)
def test_build_returns_cached_instance(build_fn, name):
    svc = _mock_services()
    g1 = build_fn(**svc)
    g2 = build_fn(**svc)
    assert g1 is g2, f"{name} graph not cached: expected identical instance"
    # lru_cache should report one miss (first compile) + one hit (second call)
    info = build_cached.cache_info()
    assert info.hits >= 1, f"{name}: expected at least one cache hit, got {info}"
    # Compiled graphs expose the async invoke entrypoint
    assert hasattr(g1, "ainvoke"), f"{name}: compiled graph missing .ainvoke"


def test_three_strategies_share_single_cache():
    svc = _mock_services()
    a = graph.build_rag_graph(**svc)
    b = graph.build_fast_graph(**svc)
    c = graph.build_deep_graph(**svc)
    # Distinct strategies yield distinct compiled graphs
    assert a is not b
    assert a is not c
    assert b is not c
    # All three live in the same lru_cache (maxsize=4)
    assert build_cached.cache_info().currsize == 3


def test_build_cached_unknown_strategy_raises():
    with pytest.raises(ValueError, match="unknown strategy"):
        build_cached("nonsense")