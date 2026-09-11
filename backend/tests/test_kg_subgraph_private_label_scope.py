"""The anonymous KG subgraph scan must never traverse per-seeker nodes.

GET /api/kg/subgraph is deliberately anonymous so the public /knowledge-graph
page renders without signing in. Its Cypher was an unlabelled `MATCH (n)` with
no tenant or user predicate, over a database that also stores private memory
(GlobalMemory.content / .insight), the User nodes linking people to them, and
SeekerTurn provenance (session_id, user_id_hash).

It returned no private data only because GlobalMemory happens not to carry an
`entity_id` property, so `toLower(null) CONTAINS $q` was null-not-true. That is
one extractor change away from an anonymous dump of other seekers' text — the
ontology extractor already sets entity_id on the entities it writes.

Isolation must come from the query, not from a property happening to be absent.
"""

from __future__ import annotations

import inspect

import pytest

from app.api.kg import PRIVATE_GRAPH_LABELS, kg_subgraph

SRC = inspect.getsource(kg_subgraph)


@pytest.mark.parametrize("label", ["User", "GlobalMemory", "SeekerTurn"])
def test_private_labels_are_declared(label: str):
    assert (
        label in PRIVATE_GRAPH_LABELS
    ), f"{label} holds per-seeker data and must be excluded from the anonymous scan"


def test_scan_excludes_private_labels():
    assert "private_labels" in SRC, "the Cypher does not reference the private-label list"
    assert SRC.count("NOT any(l IN labels(") >= 2, (
        "both the root match and the neighbour expansion must exclude private "
        "labels — scoping only the root still returns private neighbours"
    )


def test_scan_requires_entity_id_rather_than_relying_on_it_being_absent():
    assert "n.entity_id IS NOT NULL" in SRC
    assert "m.entity_id IS NOT NULL" in SRC


def test_private_labels_are_bound_as_a_parameter_not_interpolated():
    """Label list must reach Neo4j as a parameter, never as formatted Cypher."""
    assert "private_labels=list(PRIVATE_GRAPH_LABELS)" in SRC
    cypher_region = SRC.split("cypher =")[1][:900]
    assert 'f"""' not in cypher_region, "the subgraph Cypher must not be an f-string"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
