"""Graph strategy wiring regression tests.

Ensures that the Fast, Standard, and Deep RAG graph strategies compile into a
valid LangGraph and contain the expected node topology.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rag.graph_strategies import DeepGraphStrategy, FastGraphStrategy, StandardGraphStrategy


@pytest.fixture
def mock_init_services(monkeypatch):
    """Patch the service initializer so strategies compile without real backends."""
    monkeypatch.setattr(
        "rag.graph_strategies.init_services",
        lambda *args, **kwargs: None,
    )


@pytest.fixture
def mock_build_kwargs():
    """Return a minimal set of service kwargs for graph construction."""
    return {
        "ollama_service": MagicMock(),
        "embedding_service": MagicMock(),
        "qdrant_service": MagicMock(),
        "lightrag_service": MagicMock(),
    }


def _expected_nodes():
    """Nodes that every strategy must expose at compile time."""
    return {
        "__start__",
        "intent_router",
        "retrieve_documents",
        "generate_answer",
        "format_final_answer",
        "handle_casual",
        "handle_distress",
        "handle_meditation",
        "handle_fallback",
        "web_search",
    }


def test_fast_graph_compiles(mock_init_services, mock_build_kwargs):
    """The FastGraphStrategy must compile and contain the fast-path nodes."""
    strategy = FastGraphStrategy()
    compiled = strategy.build(**mock_build_kwargs)

    assert compiled is not None
    nodes = set(compiled.nodes.keys())
    assert _expected_nodes().issubset(nodes)
    assert "_map_docs_to_relevant" in nodes
    assert "resolve_followup" not in nodes
    assert "rerank_documents" not in nodes
    assert "verify_answer" not in nodes


def test_standard_graph_compiles(mock_init_services, mock_build_kwargs):
    """The StandardGraphStrategy must compile with the full anti-hallucination chain."""
    strategy = StandardGraphStrategy()
    compiled = strategy.build(**mock_build_kwargs)

    assert compiled is not None
    nodes = set(compiled.nodes.keys())
    assert _expected_nodes().issubset(nodes)
    assert "resolve_followup" in nodes
    assert "decompose_query" in nodes
    assert "navigate_and_hyde" in nodes
    assert "rerank_documents" in nodes
    assert "grade_documents" in nodes
    assert "reflect_on_answer" in nodes
    assert "verify_answer" in nodes
    assert "explain_retrieval" not in nodes
    assert "check_contradiction" not in nodes


def test_deep_graph_compiles(mock_init_services, mock_build_kwargs):
    """The DeepGraphStrategy must compile and include the contradiction check."""
    strategy = DeepGraphStrategy()
    compiled = strategy.build(**mock_build_kwargs)

    assert compiled is not None
    nodes = set(compiled.nodes.keys())
    assert _expected_nodes().issubset(nodes)
    assert "resolve_followup" in nodes
    assert "decompose_query" in nodes
    assert "navigate_and_hyde" in nodes
    assert "rerank_documents" in nodes
    assert "grade_documents" in nodes
    assert "reflect_on_answer" in nodes
    assert "verify_answer" in nodes
    assert "explain_retrieval" not in nodes
    assert "check_contradiction" not in nodes


def test_graph_strategy_names():
    """Each strategy advertises a stable name used for routing/observability."""
    assert FastGraphStrategy().name == "fast"
    assert StandardGraphStrategy().name == "standard"
    assert DeepGraphStrategy().name == "deep"
