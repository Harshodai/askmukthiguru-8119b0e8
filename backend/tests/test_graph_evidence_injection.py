"""Neo4j relationships must reach the prompt as labelled, bounded evidence.

Before 2026-09-12 no Neo4j-derived text reached an answer at all:
`query_neo4j_subgraph` had zero production callers, and the one live graph path
contributed query terms that were usually truncated away. Two defects had to be
fixed for the graph to work: the Cypher matched `entity_id` exactly against
lowercase doctrine tags while the graph stores Title Case, and an uncapped dump
of generic DIRECTED edges crowded out the teachings.
"""

import inspect

from app.config import Settings
from rag.nodes import retrieval
from rag.nodes.retrieval import _entity_id_forms


def test_entity_id_forms_cover_the_graph_casing():
    forms = _entity_id_forms("soul sync")
    assert "Soul Sync" in forms, "the graph stores Title Case entity_ids"
    assert "soul sync" in forms
    assert _entity_id_forms("") == []


def test_subgraph_match_is_index_friendly():
    src = inspect.getsource(retrieval.query_neo4j_subgraph)
    assert "n1.entity_id IN $concept_forms" in src
    # A toLower() on the stored property would defeat the entity_id index.
    assert "toLower(n1.entity_id)" not in src


def test_typed_edges_are_preferred_and_capped():
    src = inspect.getsource(retrieval.query_neo4j_subgraph)
    assert "rag_graph_context_max_relations" in src
    assert '"-[DIRECTED]->" in line' in src, "generic co-occurrence edges must sort last"


def test_injection_triggers_on_multi_concept_queries():
    src = inspect.getsource(retrieval.retrieve_documents)
    assert "_graph_multi_concept" in src
    assert "extract_doctrine_tags" in src
    # Lane alone is not enough: a two-hop question lands on the fast lane.
    assert 'retrieval_lane in ("relational", "deep") or _graph_multi_concept' in src


def test_graph_evidence_cannot_outrank_a_teaching():
    s = Settings()
    assert s.rag_graph_context_score < 1.0
    assert s.rag_graph_context_timeout <= 5.0, "the graph must never cost an answer"


def test_injection_is_fail_open():
    src = inspect.getsource(retrieval.retrieve_documents)
    head, _, tail = src.partition("KG evidence injection")
    assert "except Exception" in tail or "fail-open" in tail
