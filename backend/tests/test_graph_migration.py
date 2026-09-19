"""Regression tests for the Bolt graph migration utility.

These cover the parts that fail silently and destructively: Cypher identifier
interpolation, edge identity (parallel edges), label-set batching, and the
verify comparison that is the migration's only proof of success.

The end-to-end drill (live Memgraph -> live Neo4j) is an ops procedure, not a
unit test; see docs/BACKUP_RESTORE.md.
"""

from __future__ import annotations

import pytest

from scripts.ops.migrate_neo4j_to_memgraph import (
    NODE_MARKER_LABEL,
    NODE_MARKER_PROP,
    REL_MARKER_PROP,
    MigrationError,
    _check_identifier,
    _import_nodes,
    _import_relationships,
    _report_mismatches,
)


class _StubResult:
    def consume(self) -> None:
        return None


class _StubSession:
    """Captures the Cypher issued so batching and interpolation can be asserted."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.statements.append((cypher, params))
        return _StubResult()


# --------------------------------------------------------------- identifier guard


@pytest.mark.parametrize(
    "payload",
    [
        "Concept`) DELETE n //",
        "base WHERE 1=1 DETACH DELETE n",
        "has-a-dash",
        "9LeadingDigit",
        "",
    ],
)
def test_check_identifier_rejects_injection(payload: str) -> None:
    with pytest.raises(MigrationError):
        _check_identifier(payload, "label")


def test_check_identifier_accepts_real_labels() -> None:
    for label in ("base", "Teacher", "_MigrationNode", "IS_TAUGHT_BY"):
        assert _check_identifier(label, "label") == label


def test_import_relationships_refuses_unsafe_type() -> None:
    session = _StubSession()
    rels = [
        {
            "rel_id": "1",
            "start_elem_id": "a",
            "end_elem_id": "b",
            "rel_type": "DIRECTED]->() DETACH DELETE a //",
            "props": {},
        }
    ]
    with pytest.raises(MigrationError):
        _import_relationships(session, rels, batch_size=10)


# --------------------------------------------------------------- batching


def test_import_nodes_batches_by_label_set_not_by_row() -> None:
    """6 nodes across 2 label sets must issue 2 statements, not 6."""
    nodes = [
        {"elem_id": f"n{i}", "labels": ["base"] if i % 2 else ["Concept"], "props": {"k": i}}
        for i in range(6)
    ]
    session = _StubSession()
    _import_nodes(session, nodes, batch_size=500)

    assert len(session.statements) == 2
    for cypher, params in session.statements:
        assert cypher.startswith("UNWIND $rows AS row")
        assert NODE_MARKER_LABEL in cypher
        assert f"{NODE_MARKER_PROP}: row.id" in cypher
        # `+=` not `=`: an `=` would wipe the marker the MERGE just keyed on.
        assert "SET n += row.props" in cypher
        assert len(params["rows"]) == 3


def test_import_relationships_keys_each_edge_on_its_own_id() -> None:
    """Parallel same-type edges between one pair must survive as distinct edges.

    The live graph contains such a pair. A MERGE without a distinguishing
    property collapses them into one and the loss is silent.
    """
    rels = [
        {
            "rel_id": "r1",
            "start_elem_id": "a",
            "end_elem_id": "b",
            "rel_type": "DIRECTED",
            "props": {},
        },
        {
            "rel_id": "r2",
            "start_elem_id": "a",
            "end_elem_id": "b",
            "rel_type": "DIRECTED",
            "props": {},
        },
    ]
    session = _StubSession()
    _import_relationships(session, rels, batch_size=500)

    cypher, params = session.statements[0]
    assert f"{REL_MARKER_PROP}: row.rid" in cypher
    assert [row["rid"] for row in params["rows"]] == ["r1", "r2"]


def test_import_relationships_falls_back_to_index_when_dump_lacks_rel_ids() -> None:
    """Older dumps carry no rel_id; identity falls back to dump position."""
    rels = [
        {"start_elem_id": "a", "end_elem_id": "b", "rel_type": "DIRECTED", "props": {}},
        {"start_elem_id": "a", "end_elem_id": "b", "rel_type": "DIRECTED", "props": {}},
    ]
    session = _StubSession()
    _import_relationships(session, rels, batch_size=500)

    _, params = session.statements[0]
    rids = [row["rid"] for row in params["rows"]]
    assert rids == ["idx:0", "idx:1"]
    assert len(set(rids)) == 2


# --------------------------------------------------------------- verify comparison


def _dump(nodes: int = 3, rels: int = 2) -> dict:
    return {
        "node_count": nodes,
        "relationship_count": rels,
        "label_histogram": {"base": 2, "Concept": 1},
        "reltype_histogram": {"DIRECTED": 2},
    }


def test_report_mismatches_passes_on_identical_graph() -> None:
    assert _report_mismatches(_dump(), _dump()) is True


def test_report_mismatches_fails_on_missing_nodes() -> None:
    live = _dump()
    live["node_count"] = 2
    assert _report_mismatches(_dump(), live) is False


def test_report_mismatches_fails_on_missing_relationships() -> None:
    live = _dump()
    live["relationship_count"] = 1
    assert _report_mismatches(_dump(), live) is False


def test_report_mismatches_fails_when_counts_match_but_labels_do_not() -> None:
    """Totals can match while the graph is wrong -- histograms are what catch that."""
    live = _dump()
    live["label_histogram"] = {"base": 3}
    assert _report_mismatches(_dump(), live) is False


def test_report_mismatches_fails_on_extra_relationship_type() -> None:
    live = _dump()
    live["reltype_histogram"] = {"DIRECTED": 1, "UNEXPECTED": 1}
    assert _report_mismatches(_dump(), live) is False
