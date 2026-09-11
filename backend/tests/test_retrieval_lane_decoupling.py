"""Disabling the knowledge graph must disable only the knowledge graph.

`retrieval_lane` describes how much retrieval work the QUESTION deserves.
Graph availability is a separate axis, gated on its own by the
knowledge_graph_query_enabled check on the kg_coro block.

Collapsing a standard-tier query to the "fast" lane when the graph was off
coupled three unrelated behaviours to one flag:

  * the BM25 sparse fan-out is skipped when retrieval_lane == "fast"
  * primary_query_limit drops from 2 to 1
  * the lane takes an earlier budget-exhaustion exit

That also made graph ablation meaningless — turning the graph off changed the
sparse retriever and the query budget at the same time, so any measured delta
could not be attributed to the graph.
"""

from __future__ import annotations

import inspect
import re

import pytest

from rag.nodes.retrieval import retrieve_documents

SRC = inspect.getsource(retrieve_documents)


def _lane_assignment_statements() -> str:
    """Executable lines that assign retrieval_lane, comments stripped.

    Comments are excluded deliberately: the branch carries an explanation that
    names the graph flag, and this test is about what the code does.
    """
    return "\n".join(
        line
        for line in SRC.splitlines()
        if "retrieval_lane = " in line and not line.lstrip().startswith("#")
    )


def test_standard_tier_lane_does_not_depend_on_the_graph_flag():
    branch = _lane_assignment_statements()
    assert 'retrieval_lane = "relational"' in branch
    assert "knowledge_graph_query_enabled" not in branch, (
        "the standard-tier lane must not branch on the knowledge-graph flag — "
        "that couples BM25 and primary_query_limit to graph availability"
    )


def test_graph_work_is_still_gated_on_its_own_flag():
    """Decoupling the lane must not accidentally enable the graph unconditionally."""
    assert re.search(
        r'retrieval_lane\s*!=\s*"fast"\s*\n\s*and getattr\(\s*settings,\s*"knowledge_graph_query_enabled"',
        SRC,
    ), "the kg_coro block must still check knowledge_graph_query_enabled itself"


def test_bm25_gate_keys_off_query_tier_not_graph_availability():
    bm25_gate = next(
        line for line in SRC.splitlines() if "bm25_retrieval_enabled" in line and "if " in line
    )
    assert "query_tier not in" in bm25_gate, (
        "BM25 must be skipped based on how simple the query is, not on which "
        "lane the graph flag happened to select"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
