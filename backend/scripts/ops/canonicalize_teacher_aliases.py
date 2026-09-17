#!/usr/bin/env python3
"""
Memgraph Semantic Entity Resolution & Alias Canonicalization.

Scans Memgraph/Neo4j knowledge graph for teacher entity variations
(e.g., "Sri Bhagavan", "Kalki Bhagavan", "Bhagavan", "Preethaji", "Krishnaji")
and links them via explicit [:ALIAS_OF] edges to canonical :Teacher nodes.

Key Features:
1. Canonical Nodes: Ensures canonical nodes exist with labels :Teacher:base:
   - Sri Amma Bhagavan
   - Sri Preethaji
   - Sri Krishnaji
   - Sadhguru
2. Non-Destructive Alias Linking: Connects alias nodes to canonical nodes with [:ALIAS_OF]:
   (alias:Teacher)-[:ALIAS_OF {canonical_name: ..., confidence: 1.0, method: 'deterministic_teacher_ontology'}]->(canonical:Teacher)
   Preserves original source provenance while enabling unified traversal across aliases.
3. Multi-Tenant Stamping: Stamped with tenant_id='oneness' and corpus_id='askmukthiguru'
   consistent with the 2026-09-13 lineage invariants.
4. Dry-Run & Apply modes with comprehensive diagnostic statistics.

Usage:
  # Dry-run (default): scan, inspect aliases, report pending links without modifying graph:
  python3 -m scripts.ops.canonicalize_teacher_aliases

  # Apply: create canonical nodes, add :Teacher labels, and create [:ALIAS_OF] edges:
  python3 -m scripts.ops.canonicalize_teacher_aliases --apply
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("canonicalize_teacher_aliases")

# Canonical Teacher Targets and their recognized aliases
TEACHER_CANONICAL_TARGETS: dict[str, dict[str, Any]] = {
    "Sri Amma Bhagavan": {
        "aliases": [
            "Sri Bhagavan",
            "Kalki Bhagavan",
            "Bhagavan",
            "Amma Bhagavan",
            "Amma_Bhagavan",
            "Sri Amma Bhagavan",
            "Kalki",
            "Sri Amma",
            "Amma",
            "Kalki Avatar",
            "Bhagwan",
            "Sri Kalki Bhagavan",
            "AmmaBhagavan",
            "Bhagvan",
        ],
        "bio": "Founders of the Oneness movement and Ekam lineage, parents of Sri Krishnaji.",
    },
    "Sri Preethaji": {
        "aliases": [
            "Preethaji",
            "Sri Preethaji",
            "Shri Preethaji",
            "Sri Sri Preethaji",
            "Preetha",
            "Preetha ji",
            "Sreepreethaji",
            "Acharya Preethaji",
        ],
        "bio": "Co-founder of Ekam and O&O Academy, co-author of The Four Sacred Secrets.",
    },
    "Sri Krishnaji": {
        "aliases": [
            "Krishnaji",
            "Sri Krishnaji",
            "Shri Krishnaji",
            "Sri Sri Krishnaji",
            "Krishna",
            "Krishna ji",
            "Sreekrishnaji",
            "Acharya Krishnaji",
        ],
        "bio": "Co-founder of Ekam and O&O Academy, philosopher and spiritual teacher.",
    },
    "Sadhguru": {
        "aliases": [
            "Sadhguru",
            "Jaggi Vasudev",
            "Jaggi",
            "Sadhguru Jaggi Vasudev",
        ],
        "bio": "Founder of Isha Foundation (recognized external reference).",
    },
}

# ---------------------------------------------------------------------------
# Cypher Queries
# ---------------------------------------------------------------------------

_ENSURE_CANONICAL_NODE = """
MERGE (c:Teacher {name: $canonical_name})
ON CREATE SET
    c:base,
    c.entity_id = $canonical_name,
    c.entity_type = 'Teacher',
    c.bio = $bio,
    c.tenant_id = $tenant_id,
    c.corpus_id = $corpus_id,
    c.created_at = datetime()
ON MATCH SET
    c:base,
    c.entity_id = $canonical_name,
    c.entity_type = 'Teacher',
    c.tenant_id = coalesce(c.tenant_id, $tenant_id),
    c.corpus_id = coalesce(c.corpus_id, $corpus_id)
RETURN id(c) AS canonical_id, c.name AS name
"""

_FIND_ALIAS_CANDIDATES = """
MATCH (n)
WHERE (n:base OR n:Teacher)
  AND (toLower(coalesce(n.entity_id, '')) IN $alias_lowers OR toLower(coalesce(n.name, '')) IN $alias_lowers)
  AND NOT (toLower(coalesce(n.entity_id, '')) = $canonical_lower AND toLower(coalesce(n.name, '')) = $canonical_lower)
RETURN id(n) AS alias_id,
       labels(n) AS labels,
       coalesce(n.entity_id, n.name, '') AS surface_name,
       coalesce(n.name, n.entity_id, '') AS node_name
"""

_CHECK_EXISTING_ALIAS_EDGE = """
MATCH (alias)-[r:ALIAS_OF]->(canonical)
WHERE id(alias) = $alias_id AND id(canonical) = $canonical_id
RETURN count(r) AS count
"""

_LINK_ALIAS_CYPHER = """
MATCH (alias), (canonical:Teacher {name: $canonical_name})
WHERE id(alias) = $alias_id AND id(alias) <> id(canonical)
MERGE (alias)-[r:ALIAS_OF]->(canonical)
SET r.canonical_name = $canonical_name,
    r.alias_name = $alias_name,
    r.confidence = 1.0,
    r.method = 'deterministic_teacher_ontology',
    r.tenant_id = $tenant_id,
    r.corpus_id = $corpus_id,
    r.updated_at = datetime()
SET alias:Teacher
RETURN count(r) AS linked
"""

_COUNT_ALIAS_RELATIONSHIPS = """
MATCH (alias)-[r]->(target)
WHERE id(alias) = $alias_id AND type(r) <> 'ALIAS_OF'
RETURN type(r) AS rel_type, count(r) AS count
"""

_VERIFY_SUMMARY_CYPHER = """
MATCH (alias)-[r:ALIAS_OF]->(canonical:Teacher)
RETURN canonical.name AS canonical_teacher,
       coalesce(alias.name, alias.entity_id) AS alias_name,
       type(r) AS rel_type,
       r.confidence AS confidence,
       r.method AS method
ORDER BY canonical_teacher, alias_name
"""


def _connect(uri: str, user: str, password: str):
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password) if password else None)
    driver.verify_connectivity()
    return driver


def canonicalize_teacher_aliases_in_graph(
    driver,
    apply: bool = False,
    tenant_id: str = "oneness",
    corpus_id: str = "askmukthiguru",
    custom_targets: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Scan Memgraph for alias nodes matching teacher variations and link them to canonical nodes.

    Args:
        driver: Active Neo4j/Memgraph driver instance.
        apply: If True, writes changes to graph; if False, performs dry-run analysis.
        tenant_id: Tenant namespace for multi-tenant graph stamping (default: 'oneness').
        corpus_id: Corpus identifier (default: 'askmukthiguru').
        custom_targets: Optional override dictionary of canonical teachers and aliases.

    Returns:
        Summary dict containing scan and linking statistics.
    """
    targets = custom_targets or TEACHER_CANONICAL_TARGETS
    stats: dict[str, Any] = {
        "apply": apply,
        "canonical_teachers": len(targets),
        "total_aliases_found": 0,
        "edges_created": 0,
        "edges_already_existing": 0,
        "relationships_linked": 0,
        "details": [],
    }

    with driver.session() as session:
        for canonical_name, data in targets.items():
            bio = data.get("bio", "")
            aliases = data.get("aliases", [])
            alias_lowers = [a.strip().lower() for a in aliases if a.strip()]
            canonical_lower = canonical_name.strip().lower()

            # 1. Ensure canonical node
            canonical_id = None
            if apply:
                res = session.run(
                    _ENSURE_CANONICAL_NODE,
                    canonical_name=canonical_name,
                    bio=bio,
                    tenant_id=tenant_id,
                    corpus_id=corpus_id,
                ).single()
                if res:
                    canonical_id = res["canonical_id"]
            else:
                check_canonical = session.run(
                    "MATCH (c:Teacher {name: $name}) RETURN id(c) AS cid",
                    name=canonical_name,
                ).single()
                if check_canonical:
                    canonical_id = check_canonical["cid"]

            # 2. Find alias nodes
            alias_records = session.run(
                _FIND_ALIAS_CANDIDATES,
                alias_lowers=alias_lowers,
                canonical_lower=canonical_lower,
            ).data()

            teacher_detail = {
                "canonical_name": canonical_name,
                "canonical_exists": canonical_id is not None,
                "aliases_found": len(alias_records),
                "items": [],
            }

            for rec in alias_records:
                alias_id = rec["alias_id"]
                surface_name = rec["surface_name"]
                node_name = rec["node_name"]
                display_alias = surface_name or node_name or f"node-{alias_id}"

                stats["total_aliases_found"] += 1

                # Check if ALIAS_OF already exists
                has_edge = 0
                if canonical_id is not None:
                    check_edge = session.run(
                        _CHECK_EXISTING_ALIAS_EDGE,
                        alias_id=alias_id,
                        canonical_id=canonical_id,
                    ).single()
                    if check_edge:
                        has_edge = check_edge["count"]

                # Count existing relationships on alias node
                rels = session.run(_COUNT_ALIAS_RELATIONSHIPS, alias_id=alias_id).data()
                rel_count = sum(r["count"] for r in rels)
                rel_summary = ", ".join(f"{r['rel_type']}:{r['count']}" for r in rels)

                item_info = {
                    "alias_id": alias_id,
                    "alias_name": display_alias,
                    "already_linked": has_edge > 0,
                    "connected_relations": rel_count,
                    "rel_breakdown": rel_summary,
                }

                if has_edge > 0:
                    stats["edges_already_existing"] += 1
                else:
                    if apply:
                        session.run(
                            _LINK_ALIAS_CYPHER,
                            alias_id=alias_id,
                            canonical_name=canonical_name,
                            alias_name=display_alias,
                            tenant_id=tenant_id,
                            corpus_id=corpus_id,
                        )
                        stats["edges_created"] += 1
                        stats["relationships_linked"] += rel_count
                    else:
                        stats["edges_created"] += 1
                        stats["relationships_linked"] += rel_count

                teacher_detail["items"].append(item_info)

            stats["details"].append(teacher_detail)

        # In apply mode, fetch verification summary
        if apply:
            verification = session.run(_VERIFY_SUMMARY_CYPHER).data()
            stats["verification"] = verification

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write [:ALIAS_OF] edges and canonical :Teacher nodes (default: dry-run only)",
    )
    parser.add_argument(
        "--tenant-id",
        default=os.environ.get("TENANT_ID", "oneness"),
        help="Tenant ID for edge/node property stamping (default: oneness)",
    )
    parser.add_argument(
        "--corpus-id",
        default=os.environ.get("CORPUS_ID", "askmukthiguru"),
        help="Corpus ID for edge/node property stamping (default: askmukthiguru)",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        help="Memgraph / Neo4j Bolt connection URI",
    )
    parser.add_argument(
        "--neo4j-user",
        default=os.environ.get("NEO4J_USER", os.environ.get("NEO4J_USERNAME", "neo4j")),
        help="Database user",
    )
    parser.add_argument(
        "--neo4j-password",
        default=os.environ.get("NEO4J_PASSWORD", ""),
        help="Database password",
    )
    args = parser.parse_args(argv)

    print("=" * 80)
    print(
        f"{'APPLY' if args.apply else 'DRY-RUN'} — Memgraph Teacher Entity Resolution & Alias Canonicalization"
    )
    print(f"  Target URI:  {args.neo4j_uri}")
    print(f"  Tenant ID:   {args.tenant_id}")
    print(f"  Corpus ID:   {args.corpus_id}")
    print("=" * 80)

    try:
        driver = _connect(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
    except Exception as exc:
        print(f"❌ Connection failed to Memgraph at {args.neo4j_uri}: {exc}", file=sys.stderr)
        return 1

    try:
        stats = canonicalize_teacher_aliases_in_graph(
            driver,
            apply=args.apply,
            tenant_id=args.tenant_id,
            corpus_id=args.corpus_id,
        )

        for td in stats["details"]:
            canon = td["canonical_name"]
            found = td["aliases_found"]
            print(f"\n📌 Canonical Teacher: {canon} ({found} alias nodes detected)")
            if not td["canonical_exists"] and not args.apply:
                print(
                    "   ℹ️ Canonical node does not yet exist in graph (will be created on --apply)"
                )
            for it in td["items"]:
                status = (
                    "ALREADY_LINKED"
                    if it["already_linked"]
                    else ("LINKED" if args.apply else "PENDING_LINK")
                )
                rels_str = f" [{it['rel_breakdown']}]" if it["rel_breakdown"] else ""
                print(f"   - Node #{it['alias_id']}: '{it['alias_name']}' -> {status}{rels_str}")

        print("\n" + "-" * 80)
        print("SUMMARY:")
        print(f"  Total alias nodes found:     {stats['total_aliases_found']}")
        print(f"  [:ALIAS_OF] edges already in graph: {stats['edges_already_existing']}")
        print(
            f"  [:ALIAS_OF] edges {'created' if args.apply else 'to create'}:  {stats['edges_created']}"
        )
        print(f"  Relationships unified:       {stats['relationships_linked']}")
        print("-" * 80)

        if not args.apply:
            print(
                "\n💡 DRY-RUN complete. No mutations made. Run with --apply to commit [:ALIAS_OF] edges."
            )
        else:
            print(
                "\n✅ Successfully canonicalized teacher aliases and linked [:ALIAS_OF] edges in Memgraph."
            )

    finally:
        driver.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
