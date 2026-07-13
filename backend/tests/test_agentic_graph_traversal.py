"""
Unit tests for the Agentic Graph RAG traversal node and its deterministic tools.

Coverage:
- Gating: only COMPARATIVE intent or tier3_complex triggers traversal.
- Pure helpers: LLM decision parsing, meaningful-traversal check, doc formatting.
- Deterministic tools: get_concept_details / get_adjacent_concepts against a
  mocked Neo4j driver.
- Full ReAct loop: LLM returns DONE on the first step, context is formatted
  into relevant_docs.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys

import rag.nodes.agentic_graph_traversal  # noqa: F401  (loads submodule; pkg attr is shadowed)
agt = sys.modules["rag.nodes.agentic_graph_traversal"]
from rag.nodes.tools import (
    get_adjacent_concepts,
    get_concept_details,
    get_graph_traversal_context,
)
from rag.states import GraphState


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _base_state(**overrides) -> GraphState:
    """Minimal GraphState for traversal tests."""
    state = GraphState(
        question="How does Karma differ from the Beautiful State?",
        chat_history=[],
        request_id="test-req-001",
        intent="COMPARATIVE",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=[],
        is_complex=True,
        selected_clusters=[],
        hints=[],
        answer=None,
        citations=[],
        is_faithful=None,
        needs_correction=False,
        reflection_feedback=None,
        verification=None,
        confidence_score=None,
        input_blocked=False,
        output_blocked=False,
        block_reason=None,
        meditation_step=0,
        meditation_response=None,
        final_answer=None,
    )
    state["query_tier"] = "tier3_complex"
    state.update(overrides)
    return state


def _sample_node_record(entity_id="Karma", name="Karma", node_type="Concept"):
    """Build a fake Neo4j record for get_concept_details _query."""
    node = {"entity_id": entity_id, "name": name, "type": node_type,
            "description": "Action and consequence."}

    class _Rel:
        def __init__(self, rtype, end):
            self.type = rtype
            self.end_node = end
            self._desc = {"description": f"{rtype} link"}

        def get(self, k, default=None):
            return self._desc.get(k, default)

    child = {"entity_id": "Samsara", "name": "Samsara", "type": "Concept"}
    rel = _Rel("LEADS_TO", child)

    class _Record:
        def __init__(self, n, rels, parents):
            self._n, self._rels, self._parents = n, rels, parents

        def __getitem__(self, key):
            return {"n": self._n, "rels": self._rels, "parents": self._parents}[key]

        def single(self):
            return self

    return _Record(node, [rel], [])


def _make_driver_for_details():
    """Driver whose session().execute_read runs the callback with a tx-like object."""
    class _Tx:
        def run(self, cypher, entity_id=None):
            return _sample_node_record()

    def _execute_read(fn):
        return fn(_Tx())

    driver = MagicMock()
    session_mock = MagicMock()
    session_mock.execute_read = _execute_read
    driver.session.return_value = session_mock
    return driver


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #
def test_gating_ignores_non_comparative_simple_tier():
    state = _base_state(intent="FACTUAL", query_tier="standard")
    result = asyncio.run(agt.agentic_graph_traversal(state))
    assert result == {}, "Should bypass traversal for non-COMPARATIVE / non-complex"


def test_gating_triggers_for_comparative_tier2():
    # COMPARATIVE + a non-tier3 tier should still trigger (intent gate wins)
    state = _base_state(intent="COMPARATIVE", query_tier="standard")
    # Provide traversal context so we skip the Neo4j init path
    state["graph_traversal_context"] = [
        {"concept_id": "Karma", "node_data": {"entity_id": "Karma", "name": "Karma"}, "step": 0}
    ]
    with patch("services.ollama_service.OllamaService") as MockOllama:
        instance = MockOllama.return_value
        instance._generate_fast = AsyncMock(return_value='{"action": "DONE", "reasoning": "enough"}')
        result = asyncio.run(agt.agentic_graph_traversal(state))
    assert "relevant_docs" in result
    assert result["graph_traversal_done"] is True


def test_gating_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(agt, "ENABLED", False)
    state = _base_state(intent="COMPARATIVE", query_tier="tier3_complex")
    assert asyncio.run(agt.agentic_graph_traversal(state)) == {}


def test_gating_tier3_complex_triggers_without_comparative():
    state = _base_state(intent="FACTUAL", query_tier="tier3_complex")
    state["graph_traversal_context"] = [
        {"concept_id": "Karma", "node_data": {"entity_id": "Karma", "name": "Karma"}, "step": 0}
    ]
    with patch("services.ollama_service.OllamaService") as MockOllama:
        instance = MockOllama.return_value
        instance._generate_fast = AsyncMock(return_value='{"action": "DONE", "reasoning": "done"}')
        result = asyncio.run(agt.agentic_graph_traversal(state))
    assert "relevant_docs" in result


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_parse_llm_decision_done():
    out = agt._parse_llm_traversal_decision("Action: DONE, we have enough", {"concepts_found": []})
    assert out["action"] == "DONE"
    assert out["done"] is True


def test_parse_llm_decision_stop():
    out = agt._parse_llm_traversal_decision(
        "stop: something went wrong", {"concepts_found": []}
    )
    assert out["action"] == "STOP"


def test_parse_llm_decision_explore_with_entity():
    out = agt._parse_llm_traversal_decision(
        'explore karma for detail', {"concepts_found": []}
    )
    assert out["action"] == "EXPLORE"
    assert "karma" in out["entity_id"]


def test_parse_llm_decision_navigate_quoted():
    out = agt._parse_llm_traversal_decision(
        'navigate to "Beautiful State"', {"concepts_found": []}
    )
    assert out["action"] == "NAVIGATE"
    assert out["entity_id"] == "Beautiful State"


def test_has_meaningful_traversal_true():
    ctx = [{"concept_id": "X", "node_data": {"entity_id": "X"}}]
    assert agt._has_meaningful_traversal(ctx) is True


def test_has_meaningful_traversal_false():
    assert agt._has_meaningful_traversal([]) is False
    assert agt._has_meaningful_traversal([{"concept_id": "X"}]) is False


def test_format_traversal_as_document():
    ctx = [
        {"concept_id": "Karma", "node_data": {
            "entity_id": "Karma", "name": "Karma", "type": "Concept",
            "description": "Cause and effect.", "properties": {}}, "step": 0},
        {"concept_id": "Karma", "adjacent_concepts": [
            {"entity_id": "Samsara", "name": "Samsara", "relation_type": "LEADS_TO",
             "relation_description": "leads to"}], "step": 1},
    ]
    doc = agt._format_traversal_as_document(ctx)
    assert doc["source"] == "neo4j_agentic_traversal"
    assert "Karma" in doc["text"]
    assert "Samsara" in doc["text"]
    assert doc["content_type"] == "graph_traversal"


def test_prepare_context_summary_empty():
    summary = agt._prepare_context_summary([])
    assert summary["traversal_summary"] == "Starting traversal from scratch"
    assert summary["concepts_found"] == []


def test_prepare_context_summary_populated():
    ctx = [
        {"concept_id": "Karma", "node_data": {"entity_id": "Karma", "name": "Karma",
                                              "type": "Concept", "description": "d"}, "step": 0},
        {"concept_id": "adj", "adjacent_concepts": [
            {"entity_id": "Samsara", "relation_type": "R", "relation_description": "x"}], "step": 1},
    ]
    summary = agt._prepare_context_summary(ctx)
    assert len(summary["concepts_found"]) == 1
    assert len(summary["connections"]) == 1


# --------------------------------------------------------------------------- #
# Tools (mocked driver)
# --------------------------------------------------------------------------- #
def test_get_concept_details():
    container = MagicMock()
    container.neo4j_driver = _make_driver_for_details()
    with patch("app.dependencies.get_container", return_value=container):
        result = asyncio.run(get_concept_details("Karma", _base_state()))
    assert result["node_data"]["entity_id"] == "Karma"
    assert result["source"] == "neo4j_ontology"
    assert any("Samsara" in hint for hint in result["navigation_hints"])


def test_get_concept_details_no_driver():
    container = MagicMock()
    container.neo4j_driver = None
    with patch("app.dependencies.get_container", return_value=container):
        result = asyncio.run(get_concept_details("Karma", _base_state()))
    assert result["node_data"] is None
    assert result["source"] == "neo4j_ontology_error"


def test_get_adjacent_concepts():
    class _Rec:
        def __init__(self, **kw):
            self._d = kw

        def __getitem__(self, k):
            return self._d[k]

    recs = [
        _Rec(source="Karma", target="Samsara", relation_type="LEADS_TO",
             relation_description="leads to", target_name="Samsara", target_type="Concept"),
    ]

    class _Result:
        def __init__(self, recs):
            self._recs = recs

        def __iter__(self):
            return iter(self._recs)

    class _Tx:
        def run(self, cypher, entity_id=None):
            return _Result(recs)

    def _execute_read(fn):
        return fn(_Tx())

    container = MagicMock()
    driver = MagicMock()
    session_mock = MagicMock()
    session_mock.execute_read = _execute_read
    driver.session.return_value = session_mock
    container.neo4j_driver = driver
    with patch("app.dependencies.get_container", return_value=container):
        result = asyncio.run(get_adjacent_concepts("Karma", _base_state()))
    assert result["adjacent_concepts"][0]["entity_id"] == "Samsara"
    assert result["relation_summary"] == {"LEADS_TO": 1}
    assert result["source"] == "neo4j_ontology"


def test_get_graph_traversal_context():
    state = _base_state(
        graph_traversal_context=[{"x": 1}],
        graph_traversal_steps=2,
        graph_traversal_done=True,
    )
    ctx = asyncio.run(get_graph_traversal_context(state))
    assert ctx["traversed_concepts"] == [{"x": 1}]
    assert ctx["traversal_step"] == 2
    assert ctx["traversal_done"] is True


# --------------------------------------------------------------------------- #
# Full ReAct loop (mocked LLM + init)
# --------------------------------------------------------------------------- #
def test_full_react_loop_first_step_done():
    state = _base_state()
    state["graph_traversal_context"] = [
        {"concept_id": "Karma", "node_data": {"entity_id": "Karma", "name": "Karma",
                                              "type": "Concept", "description": "d"}, "step": 0}
    ]
    with patch("services.ollama_service.OllamaService") as MockOllama, \
         patch("ingest.pipeline.extract_doctrine_tags", return_value=["Karma"]):
        instance = MockOllama.return_value
        instance._generate_fast = AsyncMock(
            return_value='{"action": "DONE", "reasoning": "enough context"}'
        )
        result = asyncio.run(agt.agentic_graph_traversal(state))
    assert result["graph_traversal_done"] is True
    assert len(result["relevant_docs"]) == 1
    assert result["relevant_docs"][0]["content_type"] == "graph_traversal"
