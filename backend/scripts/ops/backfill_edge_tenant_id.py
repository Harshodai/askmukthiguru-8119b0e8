#!/usr/bin/env python3
"""Idempotent backfill: stamp tenant_id + corpus_id on every Neo4j edge that lacks it.

Background
----------
LightRAG writes graph edges directly via its internal Neo4JStorage adapter,
bypassing ontology_writer.py entirely.  Those edges carry no tenant_id — only
LightRAG-internal properties (keywords, weight, description, source_id, created_at).
As of 2026-09-13: 4,128 of 4,170 edges (99%) lack an explicit tenant_id and rely
on the coalesce(r.tenant_id, 'oneness') fallback query-time.

This is a launch BLOCKER: a second tenant's ingestion writing edges without
tenant_id makes the coalesce a silent cross-tenant leak, not a migration aid
(docs/audits/LAUNCH_READINESS_GATES_2026-09-13.md §3, §6.1).

This script fixes the existing graph.  The forward fix for new edges is documented
in a companion comment in lightrag_service.py — because LightRAG's Neo4JStorage
writes bypass our code entirely, future ingestion runs must re-run this script
(or the post-ingestion hook described there) to stamp newly written edges.

Architecture decision (confirmed 2026-09-13)
--------------------------------------------
Unified model: one tenant_id='oneness' for all teachers.  Amma Bhagavan content
stays under tenant_id='oneness' with a distinct corpus_id / teacher_id.
Cross-teacher comparison queries are DESIRABLE, not a leak.
This is recorded in domain/spiritual_ontology.py per Gate 0.4.

Usage
-----
  # Dry-run (default): count unstamped edges, print breakdown, do NOT write.
  python3 -m scripts.ops.backfill_edge_tenant_id

  # Apply: stamp ALL unstamped edges, then verify zero remain.
  python3 -m scripts.ops.backfill_edge_tenant_id --apply

  # Override target values (e.g. for a future second tenant):
  python3 -m scripts.ops.backfill_edge_tenant_id --apply \\
      --tenant-id oneness --corpus-id askmukthiguru

Idempotency
-----------
The stamp Cypher uses WHERE r.tenant_id IS NULL so re-runs are safe.
Already-stamped edges are never touched.

Exit codes: 0 = success (dry-run always 0; apply: 0 if zero unstamped remain).
            1 = connection failure or unstamped edges remain after apply.

ponytail: stdlib + neo4j driver already in requirements.  No new dependencies.
"""

from __future__ import annotations

import argparse
import os
import sys

# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_COUNT_UNSTAMPED = """
MATCH ()-[r]->()
WHERE r.tenant_id IS NULL
RETURN count(r) AS total,
       collect(DISTINCT type(r))[..20] AS sample_types
"""

_COUNT_BY_TYPE = """
MATCH ()-[r]->()
WHERE r.tenant_id IS NULL
RETURN type(r) AS rel_type, count(r) AS n
ORDER BY n DESC
"""

# Plain MATCH SET — idempotent (WHERE r.tenant_id IS NULL), safe at 4k-edge scale.
# No CALL IN TRANSACTIONS needed: 4,128 edges fit comfortably in a single Neo4j tx.
_STAMP_CYPHER = """
MATCH ()-[r]->()
WHERE r.tenant_id IS NULL
SET r.tenant_id = $tenant_id,
    r.corpus_id = $corpus_id,
    r.backfill_source = 'backfill_edge_tenant_id_2026-09-13'
"""

_VERIFY_UNSTAMPED = """
MATCH ()-[r]->()
WHERE r.tenant_id IS NULL
RETURN count(r) AS remaining
"""


def _connect(uri: str, user: str, password: str):
    from neo4j import GraphDatabase  # type: ignore[import]

    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def _count_unstamped(driver) -> tuple[int, list[str], list[tuple[str, int]]]:
    with driver.session() as s:
        row = s.run(_COUNT_UNSTAMPED).single()
        total: int = row["total"]
        sample_types: list[str] = list(row["sample_types"])
        breakdown = [(r["rel_type"], r["n"]) for r in s.run(_COUNT_BY_TYPE)]
    return total, sample_types, breakdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write tenant_id/corpus_id onto unstamped edges (default: dry-run only)",
    )
    parser.add_argument(
        "--tenant-id", default="oneness", help="Value to set for tenant_id (default: oneness)"
    )
    parser.add_argument(
        "--corpus-id",
        default="askmukthiguru",
        help="Value to set for corpus_id (default: askmukthiguru)",
    )
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.environ.get("NEO4J_PASSWORD"))
    args = parser.parse_args(argv)

    if not args.neo4j_password:
        print("ERROR: NEO4J_PASSWORD not set (env or --neo4j-password)", file=sys.stderr)
        return 1

    try:
        driver = _connect(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
    except Exception as exc:
        print(f"ERROR: Cannot connect to Neo4j at {args.neo4j_uri}: {exc}", file=sys.stderr)
        return 1

    # --- dry-run count ---
    total, sample_types, breakdown = _count_unstamped(driver)

    print(f"{'DRY-RUN' if not args.apply else 'APPLY'} — Neo4j edge tenant_id backfill")
    print(f"  Target: tenant_id={args.tenant_id!r}  corpus_id={args.corpus_id!r}")
    print(f"  Neo4j:  {args.neo4j_uri}")
    print()
    print(f"  Unstamped edges (r.tenant_id IS NULL): {total}")
    if total == 0:
        print("  Nothing to do — all edges already have tenant_id.  Gate should now PASS.")
        driver.close()
        return 0

    print()
    print("  Breakdown by relationship type:")
    for rel_type, n in breakdown:
        print(f"    {rel_type:<30s} {n:>6d}")

    if not args.apply:
        print()
        print("  DRY-RUN complete.  No writes made.")
        print("  Review the breakdown above, then re-run with --apply to stamp.")
        driver.close()
        return 0

    # --- apply ---
    print()
    print(f"  Stamping {total} edges ...")
    try:
        with driver.session() as s:
            s.run(_STAMP_CYPHER, tenant_id=args.tenant_id, corpus_id=args.corpus_id)
    except Exception as exc:
        print(f"ERROR: Stamp failed: {exc}", file=sys.stderr)
        driver.close()
        return 1

    # --- verify ---
    with driver.session() as s:
        remaining = s.run(_VERIFY_UNSTAMPED).single()["remaining"]

    driver.close()

    if remaining == 0:
        print(f"  Done.  {total} edges stamped, 0 unstamped remain.")
        print()
        print("  Re-run launch_readiness_gates.sh — edge_tenant_id_coverage should now PASS.")
        return 0
    else:
        print(
            f"ERROR: {remaining} edges still lack tenant_id after stamp — investigate.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
