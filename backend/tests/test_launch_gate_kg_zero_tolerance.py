"""DS-3: the KG launch gate is zero-tolerance on untagged edges.

Pins EDGE_TENANT_ID_COVERAGE_MIN at 1.0 and proves a single untagged edge
in a 1,000-edge graph fails the predicate the gate uses. Live evidence:
backfill --apply stamped the 3 untagged SYNONYMOUS_WITH edges 2026-10-14
(0 remain) and the gate passes on the live graph.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops.launch_gate_kg_readiness import EDGE_TENANT_ID_COVERAGE_MIN  # noqa: E402


def test_edge_tenant_id_gate_is_zero_tolerance():
    assert EDGE_TENANT_ID_COVERAGE_MIN == 1.0


def test_one_untagged_edge_fails_the_gate(monkeypatch):
    from unittest.mock import MagicMock

    import neo4j

    from scripts.ops.launch_gate_kg_readiness import main

    monkeypatch.setenv("NEO4J_PASSWORD", "mock-password")

    mock_driver = MagicMock()
    mock_driver.verify_connectivity.return_value = None
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    queries = []

    def fake_run(query, *args, **kwargs):
        queries.append(query)
        res = MagicMock()
        if "SHOW CONSTRAINTS" in query:
            res.__iter__.return_value = ["constraint_1"]
        elif "MATCH (n) RETURN count(n)" in query:
            res.single.return_value = {"c": 500}
        elif "WHERE NOT (n)--()" in query:
            res.single.return_value = {"c": 10}
        elif "WHERE r.tenant_id IS NOT NULL" in query:
            res.single.return_value = {"c": 999}
        elif "ORDER BY n DESC" in query:
            res.__iter__.return_value = [{"t": "SOME_TYPE", "n": 800}, {"t": "DIRECTED", "n": 200}]
        elif "MATCH ()-[r]->() RETURN count(r)" in query:
            res.single.return_value = {"c": 1000}
        else:
            res.single.return_value = {"c": 0}
            res.__iter__.return_value = []
        return res

    mock_session.run.side_effect = fake_run
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda *a, **kw: mock_driver)

    assert main() == 1
    # The gate must have actually run the edge tenant-tagged coverage query —
    # not merely returned 1 for an unrelated reason (e.g. a missing driver).
    assert any(
        "MATCH ()-[r]->() WHERE r.tenant_id IS NOT NULL RETURN count(r)" in q for q in queries
    ), "edge_tenant_id_coverage query never ran"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
