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
        report.add(
            "HIGH",
            "constraints_exist",
            len(constraints) > 0,
            f"{len(constraints)} constraints found",
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
            tenant_tag_rate >= 0.90,
            f"only {tenant_tag_rate:.1%} of relationships ({tenant_tagged}/{rel_count}) "
            f"carry an explicit tenant_id — the rest rely on "
            f"coalesce(r.tenant_id, 'oneness') at query time",
            "This is not a legacy-edge edge case, it is nearly the entire graph. "
            "A second tenant's ingestion writing edges without tenant_id makes the "
            "coalesce a cross-tenant leak, not a migration aid (research synthesis "
            "§3.2). Stamp tenant_id on every edge at write time before any second "
            "tenant's data enters the graph — this is a launch BLOCKER, not HIGH, "
            "because the failure mode is silent data leakage, not an error.",
        )

    driver.close()
    report.print_report()
    return 1 if report.blocking_failures() else 0


if __name__ == "__main__":
    sys.exit(main())
