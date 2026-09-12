"""Discarded retrieval expansions must be visible.

Knowledge-graph neighbours are appended last to `expansion_queries` and then
truncated to `remaining_budget = 2 - len(primary_queries)`, which is 0 whenever
the query decomposed into two or more sub-queries. The graph work is paid for
and thrown away, silently — so "is Neo4j helping?" had no telemetry answer.
"""

import inspect

from rag.nodes import retrieval


def test_discarded_expansions_are_logged():
    src = inspect.getsource(retrieval.retrieve_documents)
    assert "Retrieval expansion discarded" in src
    assert "remaining_budget == 0" in src


def test_budget_formula_is_unchanged():
    src = inspect.getsource(retrieval.retrieve_documents)
    assert "remaining_budget = max(0, 2 - len(primary_queries))" in src
