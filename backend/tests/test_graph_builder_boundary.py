"""Boundary tests for the RAGGraphBuilder facade (C3b).

These tests exercise ONLY the facade's public contract:
  - tier dispatch (fast/standard/deep)
  - invalid-tier rejection
  - build_all() returns all three tiers
  - lru_cache returns the same compiled graph on repeated calls

They do NOT test strategy internals (node topology is covered by
test_graph_strategy_wiring.py). All services are mocked so the suite
runs without Docker / Ollama / Qdrant.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langgraph.graph.state import CompiledStateGraph

from rag.graph_builder import RAGGraphBuilder, clear_graph_builder_cache


@pytest.fixture
def mock_services() -> MagicMock:
    """Mock ServiceContainer with the attributes _prepare_kwargs reads."""
    services = MagicMock()
    services.ollama = MagicMock(name="ollama")
    services.embedding = MagicMock(name="embedding")
    services.qdrant = MagicMock(name="qdrant")
    services.lightrag = MagicMock(name="lightrag")
    services.serene_mind_engine = MagicMock(name="serene_mind_engine")
    services.web_search = MagicMock(name="web_search")
    services.semantic_cache = MagicMock(name="semantic_cache")
    services.sarvam_cloud = MagicMock(name="sarvam_cloud")
    return services


@pytest.fixture(autouse=True)
def _patch_init_services(monkeypatch):
    """Stop the facade from calling the real init_services (which would
    instantiate RerankerService / LettuceDetectService and load models).
    Strategies' own build() also skips init_services when no kwargs passed.
    """
    monkeypatch.setattr("rag.graph_builder.init_services", lambda *a, **kw: None)
    yield
    clear_graph_builder_cache()


@pytest.fixture
def builder(mock_services) -> RAGGraphBuilder:
    return RAGGraphBuilder(mock_services)


def _assert_compiled_graph(obj) -> None:
    """Boundary check: the facade must return a compiled LangGraph."""
    assert obj is not None, "build() returned None"
    # CompiledStateGraph exposes async + sync invoke/stream entrypoints.
    assert hasattr(obj, "ainvoke") or hasattr(obj, "invoke"), (
        "expected a compiled graph with invoke/ainvoke"
    )
    assert hasattr(obj, "stream") or hasattr(obj, "astream"), (
        "expected a compiled graph with stream/astream"
    )
    assert isinstance(obj, CompiledStateGraph), (
        f"expected CompiledStateGraph, got {type(obj).__name__}"
    )


def test_build_fast_tier(builder):
    """build('fast') returns a compiled graph."""
    compiled = builder.build("fast")
    _assert_compiled_graph(compiled)


def test_build_standard_tier(builder):
    """build('standard') returns a compiled graph."""
    compiled = builder.build("standard")
    _assert_compiled_graph(compiled)


def test_build_deep_tier(builder):
    """build('deep') returns a compiled graph."""
    compiled = builder.build("deep")
    _assert_compiled_graph(compiled)


def test_tier_selection_invalid(builder):
    """build(<unknown tier>) raises ValueError (facade translates KeyError)."""
    with pytest.raises(ValueError):
        builder.build("invalid")


def test_build_all_returns_three_graphs(builder):
    """build_all() returns a dict with exactly fast/standard/deep keys,
    each mapping to a compiled graph.
    """
    graphs = builder.build_all()
    assert isinstance(graphs, dict)
    assert set(graphs.keys()) == {"fast", "standard", "deep"}
    for tier, compiled in graphs.items():
        _assert_compiled_graph(compiled)


def test_build_caches_repeated_calls(builder):
    """lru_cache: two build('fast') calls return the SAME compiled object."""
    first = builder.build("fast")
    second = builder.build("fast")
    assert first is second, "lru_cache should return the same graph instance"


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))