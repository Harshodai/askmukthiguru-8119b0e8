"""Graph strategy wiring regression tests.

Ensures that the Fast, Standard, and Deep RAG graph strategies compile into a
valid LangGraph and contain the expected node topology.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rag.graph_strategies import (
    DeepGraphStrategy,
    FastGraphStrategy,
    StandardGraphStrategy,
    _map_docs_to_relevant,
)


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
    # 2026-09-22: Fast lane now reranks too (see graph_strategies.py comment
    # on the rerank_documents node) -- the candidate set is small (~5-7 docs
    # for fast/tier2_simple) and the node has its own high-confidence bypass,
    # so this was a real gap (simple queries reached generation unranked),
    # not intentional lane behavior.
    assert "rerank_documents" in nodes
    assert "reflect_on_answer" in nodes
    assert "verify_answer" in nodes
    assert "extract_citations" in nodes


def test_standard_graph_compiles(mock_init_services, mock_build_kwargs):
    """The StandardGraphStrategy must compile with the full anti-hallucination chain."""
    strategy = StandardGraphStrategy()
    compiled = strategy.build(**mock_build_kwargs)

    assert compiled is not None
    nodes = set(compiled.nodes.keys())
    assert _expected_nodes().issubset(nodes)
    assert "resolve_followup" in nodes
    # B22 latency fix (2026-09-12): decompose_query is no longer its own graph
    # node -- it runs inside navigate_and_hyde's asyncio.gather (see
    # rag/nodes/retrieval.py) since it, navigate_knowledge_tree, and
    # generate_hyde all read only state["question"] and share no dependency,
    # so serializing them behind two graph edges cost an extra LLM round trip.
    assert "decompose_query" not in nodes
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
    assert "decompose_query" not in nodes
    assert "navigate_and_hyde" in nodes
    assert "rerank_documents" in nodes
    assert "grade_documents" in nodes
    assert "reflect_on_answer" in nodes
    assert "verify_answer" in nodes
    assert "explain_retrieval" not in nodes
    assert "check_contradiction" not in nodes


def test_map_docs_to_relevant_caps_reranked_docs():
    """N3-adjacent regression: reranked_docs must be capped at 5, same as the
    documents[:5] fallback -- otherwise reranking (which can return more
    candidates than the fallback path ever would) silently widens how many
    docs reach generate_answer/extract_citations on the fast lane."""
    reranked = [{"text": f"doc {i}"} for i in range(12)]
    state = {"reranked_docs": reranked, "documents": []}

    result = _map_docs_to_relevant(state)

    assert len(result["relevant_docs"]) == 5
    assert result["relevant_docs"] == reranked[:5]


def test_map_docs_to_relevant_falls_back_when_no_reranked_docs():
    """Fallback path (empty/missing reranked_docs) still caps at 5."""
    documents = [{"text": f"doc {i}"} for i in range(12)]
    state = {"reranked_docs": [], "documents": documents}

    result = _map_docs_to_relevant(state)

    assert len(result["relevant_docs"]) == 5
    assert result["relevant_docs"] == documents[:5]


def test_graph_strategy_names():
    """Each strategy advertises a stable name used for routing/observability."""
    assert FastGraphStrategy().name == "fast"
    assert StandardGraphStrategy().name == "standard"
    assert DeepGraphStrategy().name == "deep"
