#!/usr/bin/env python3
"""Launch gate: Neo4j graph readiness — availability, data quality, semantic quality.

"Technically populated" is not "production ready". This script checks three
independent things and refuses to let a large node/edge count stand in for
semantic quality, per docs/audits/LAUNCH_READINESS_GATES_2026-09-13.md.

Exit 0: all checks pass or are INFO/MEDIUM only.
Exit 1: any BLOCKER or HIGH check failed.

ponytail: stdlib + the driver already in requirements — no new dependency.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field


@dataclass
class Finding:
    severity: str  # BLOCKER | HIGH | MEDIUM | INFO
    name: str
    passed: bool
    detail: str
    remediation: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(
        self, severity: str, name: str, passed: bool, detail: str, remediation: str = ""
    ) -> None:
        self.findings.append(Finding(severity, name, passed, detail, remediation))

    def blocking_failures(self) -> list[Finding]:
        return [f for f in self.findings if not f.passed and f.severity in ("BLOCKER", "HIGH")]

    def print_report(self) -> None:
        for f in self.findings:
            status = "PASS" if f.passed else "FAIL"
            print(f"[{f.severity:8s}] [{status}] {f.name}: {f.detail}")
            if not f.passed and f.remediation:
                print(f"           remediation: {f.remediation}")


# DS-3: zero tolerance — a single untagged edge fails the gate. Pinned by
# test_edge_tenant_id_gate_is_zero_tolerance; do not lower without a
# tenant-isolation review.
EDGE_TENANT_ID_COVERAGE_MIN = 1.0


# Required uniqueness constraints as exact (label, property) targets. Mirrors
# backend/app/main.py::REQUIRED_NEO4J_CONSTRAINTS + _CONSTRAINT_LABEL_PROPERTY,
# which mirror backend/app/db/seed_ontology.py's migrations. Presence alone is
# not the gate: an unrelated index or existence constraint must not satisfy it,
# so each required target has to appear as a uniqueness constraint.
REQUIRED_UNIQUE_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("Teacher", "name"),
    ("Concept", "name"),
    ("Practice", "name"),
    ("User", "id"),
    ("GlobalMemory", "id"),
    ("SeekerTurn", "turn_id"),
    ("GuruTeaching", "name"),
    ("GuruResponse", "artifact_id"),
    ("State", "name"),
    ("InferenceActivity", "activity_id"),
    ("SoftwareAgent", "agent_id"),
    ("WisdomChunk", "chunk_id"),
)

_UNIQUENESS_TYPES = ("UNIQUENESS", "UNIQUE")


def _row_get(row: object, key: str) -> object:
    """Read a column from a driver row, tolerating rows that are not records."""
    getter = getattr(row, "get", None)
    if callable(getter):
        return getter(key)
    return None


def _unique_targets(rows: list) -> set[tuple[str, tuple[str, ...]]]:
    """The (label, properties) targets of every row that is a uniqueness constraint.

    Handles both shapes: Neo4j ``SHOW CONSTRAINTS`` (``labelsOrTypes``/``type``)
    and Memgraph ``SHOW CONSTRAINT INFO`` (``label``/``constraint_type``). Rows
    that carry neither label nor properties are skipped rather than guessed at.
    """
    targets: set[tuple[str, tuple[str, ...]]] = set()
    for row in rows:
        labels = _row_get(row, "labelsOrTypes") or _row_get(row, "label")
        properties = _row_get(row, "properties")
        if not labels or not properties:
            continue
        ctype = _row_get(row, "type") or _row_get(row, "constraint_type")
        if ctype is not None and str(ctype).upper() not in _UNIQUENESS_TYPES:
            continue
        label = labels[0] if isinstance(labels, (list, tuple)) else str(labels)
        targets.add((str(label), tuple(properties)))
    return targets


def main() -> int:
    from neo4j import GraphDatabase

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        print("NEO4J_PASSWORD not set — cannot run KG readiness gate.", file=sys.stderr)
        return 1

    report = Report()

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        report.add("BLOCKER", "neo4j_reachable", True, f"Connected to {uri}")
    except Exception as exc:
        report.add(
            "BLOCKER",
            "neo4j_reachable",
            False,
            f"Connection failed: {exc}",
            "Neo4j must be reachable and authenticated before any other KG gate can run.",
        )
        report.print_report()
        return 1

    with driver.session() as session:
        constraints = list(session.run("SHOW CONSTRAINTS"))
        present_targets = _unique_targets(constraints)
        missing_constraints = [
            f"{label}.{prop}"
            for label, prop in REQUIRED_UNIQUE_CONSTRAINTS
            if (label, (prop,)) not in present_targets
        ]
        report.add(
            "HIGH",
            "constraints_exist",
            not missing_constraints,
            f"{len(REQUIRED_UNIQUE_CONSTRAINTS) - len(missing_constraints)}/"
            f"{len(REQUIRED_UNIQUE_CONSTRAINTS)} required uniqueness constraints present"
            + (f"; missing: {', '.join(missing_constraints)}" if missing_constraints else ""),
            "Run the ontology seeder / migration that creates uniqueness constraints.",
        )

        node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        report.add("INFO", "node_count", True, f"{node_count} nodes")
        report.add("INFO", "rel_count", True, f"{rel_count} relationships")

        orphan_count = session.run("MATCH (n) WHERE NOT (n)--() RETURN count(n) AS c").single()["c"]
        orphan_rate = orphan_count / node_count if node_count else 0
        report.add(
            "MEDIUM",
            "orphan_node_rate",
            orphan_rate < 0.30,
            f"{orphan_count}/{node_count} nodes ({orphan_rate:.0%}) have zero relationships",
            "Orphan nodes contribute nothing to graph traversal — investigate the "
            "extraction step that creates disconnected nodes, or prune them.",
        )

        rel_types = list(
            session.run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n ORDER BY n DESC")
        )
        directed_count = next((r["n"] for r in rel_types if r["t"] == "DIRECTED"), 0)
        typed_ratio = 1 - (directed_count / rel_count) if rel_count else 0
        report.add(
            "HIGH",
            "typed_relationship_ratio",
            typed_ratio >= 0.20,
            f"{typed_ratio:.1%} of relationships are typed ontology edges "
            f"({rel_count - directed_count}/{rel_count}); the rest ({directed_count}) "
            f"are generic LightRAG DIRECTED co-occurrence, not doctrine reasoning",
            "This is a semantic-quality gate, not an existence gate — a graph can "
            "have thousands of edges and still contribute near-zero typed reasoning. "
            "Improve ingest/hyper_extract_adapter.py's extraction yield, or lower "
            "confidence in KG-assisted answers accordingly.",
        )

        tenant_tagged = session.run(
            "MATCH ()-[r]->() WHERE r.tenant_id IS NOT NULL RETURN count(r) AS c"
        ).single()["c"]
        tenant_tag_rate = tenant_tagged / rel_count if rel_count else 0
        report.add(
            "BLOCKER",
            "edge_tenant_id_coverage",
            tenant_tag_rate >= EDGE_TENANT_ID_COVERAGE_MIN,
            f"only {tenant_tag_rate:.1%} of relationships ({tenant_tagged}/{rel_count}) "
            f"carry an explicit tenant_id — the rest rely on "
            f"coalesce(r.tenant_id, 'oneness') at query time",
            "Zero tolerance: every relationship must carry an explicit tenant_id "
            "(coverage must be 100%). Any untagged edge fails the check. "
            "A second tenant's ingestion writing edges without tenant_id makes "
            "coalesce a cross-tenant leak, not a migration aid. Stamp tenant_id on "
            "every edge at write time before any second tenant's data enters the "
            "graph — this is a launch BLOCKER because the failure mode is silent "
            "data leakage, not an error.",
        )

    driver.close()
    report.print_report()
    return 1 if report.blocking_failures() else 0


if __name__ == "__main__":
    sys.exit(main())
