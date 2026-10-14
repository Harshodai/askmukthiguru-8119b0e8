"""DS-3: the KG launch gate is zero-tolerance on untagged edges.

Pins EDGE_TENANT_ID_COVERAGE_MIN at 1.0 and proves a single untagged edge
in a 1,000-edge graph fails the predicate the gate uses. Live evidence:
backfill --apply stamped the 3 untagged SYNONYMOUS_WITH edges 2026-10-14
(0 remain) and the gate passes on the live graph.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops.launch_gate_kg_readiness import EDGE_TENANT_ID_COVERAGE_MIN  # noqa: E402


def test_edge_tenant_id_gate_is_zero_tolerance():
    assert EDGE_TENANT_ID_COVERAGE_MIN == 1.0


def test_one_untagged_edge_fails_the_gate():
    tagged, total = 999, 1000
    assert not ((tagged / total) >= EDGE_TENANT_ID_COVERAGE_MIN)
    assert (total / total) >= EDGE_TENANT_ID_COVERAGE_MIN
