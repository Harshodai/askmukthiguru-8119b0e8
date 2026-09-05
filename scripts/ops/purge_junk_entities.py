#!/usr/bin/env python3
"""
purge_junk_entities.py — Remove unambiguous non-doctrine noise from Neo4j
=============================================================================

Three precise, low-false-positive criteria, each independently verified
against production before this script was written (2026-09-04):

1. Hard junk entity_type — grammatical/NLP-parse-error categories that are
   definitionally never a spiritual concept regardless of the entity's name
   (a node typed "verb" or "preposition" is a parser artifact by
   construction): verb, adverb, adjective, noun, conjunction, preposition,
   instantjudgment, verbphrase, possessivepronoun. (Unclassified/missing types
   such as text, data, category, number, action, none, and unknown are
   deliberately excluded to prevent false-positive purging of doctrine).

2. Self-flagged placeholder descriptions — the extraction LLM's own
   description literally says 'is a placeholder for ...' (e.g. "Today is a
   placeholder for a specific day or time"). This is the model hedging that
   it couldn't determine what the entity actually was — the LLM is telling
   us itself this isn't real content, same poison class scripts/ops/
   heal_neo4j_poison.py exists for, different manifestation.

3. Short disconnected fragments — entity_id <=3 characters AND zero graph
   degree (orphaned). Sample verified: "CNN", "BBC", "N/A", "or", "in",
   "the", "k", single letters — ASR/extraction noise, not doctrine.

Deliberately NOT purged: entity_type='other' nodes with substantive
descriptions (the 2026-09-04 audit found ~50% of "other"/unknown_source
nodes are legitimate concept-adjacent content) — no safe automatic rule
exists for that bucket; it needs human or LLM-judgment review, not a
blanket delete. Also NOT purged: Sadhguru/ISKCON/other recognized-but-
unlicensed teacher domains — see domain/spiritual_ontology.py, they are
deliberately kept as reference entities, gated at query time instead.

Backs up every deleted node (+ its relationships) to JSON before deleting.

Usage:
    cd /path/to/askmukthiguru  (repo root)
    python3 scripts/ops/purge_junk_entities.py --dry-run
    python3 scripts/ops/purge_junk_entities.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

_repo_root = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv  # type: ignore

    for _env_path in (_repo_root / "backend" / ".env", _repo_root / ".env"):
        if _env_path.exists():
            load_dotenv(dotenv_path=_env_path, override=False)
            break
except ImportError:
    pass

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
# production-audit finding lightrag-2: this script used to delete junk
# entities/relationships from Neo4j only, leaving their LightRAG-authored
# Qdrant vectors behind — a live entity_name/src_id/tgt_id match against a
# node that no longer exists in Neo4j. LightRAG's Qdrant collection naming
# is model-suffixed (services/lightrag_service.py); hardcode the current
# live names rather than re-deriving the naming scheme here.
QDRANT_ENTITIES_COLLECTION = "lightrag_vdb_entities_baai_bge_m3_1024d"
QDRANT_RELATIONSHIPS_COLLECTION = "lightrag_vdb_relationships_baai_bge_m3_1024d"

if "neo4j:7687" in NEO4J_URI:
    import socket

    try:
        socket.getaddrinfo("neo4j", 7687)
    except socket.gaierror:
        NEO4J_URI = NEO4J_URI.replace("neo4j:7687", "localhost:7687")
        print("  Warning: 'neo4j' hostname not resolvable, using localhost:7687 instead")

HARD_JUNK_TYPES = [
    # Categorically-unambiguous linguistic POS tags only. A node literally
    # typed "verb"/"adverb"/etc. is an NLP-parse artifact by construction —
    # cannot be a real concept regardless of its entity_id string.
    #
    # Deliberately NOT included here (removed after a dry-run false-positive
    # check on 2026-09-04): "none"/None/"unknown"/"UNKNOWN"/"text"/"data"/
    # "category"/"number"/"action", and entity_type IS NULL. These mean "the
    # extractor didn't classify this" — a mix of junk AND legitimate content.
    # The dry-run caught real doctrine in this bucket: 'Atma' (type=None,
    # Sanskrit for Self/Soul), 'Witness Awareness'/'साक्षी भाव' (type=None),
    # 'Mahabharata' (type='text', a scripture reference). Unclassified is not
    # the same signal as misclassified — only misclassified is safe to purge.
    "verb", "adverb", "adjective", "noun", "conjunction", "preposition",
    "instantjudgment", "verbphrase", "possessivepronoun",
]

FIND_CANDIDATES_QUERY = """
MATCH (n:base)
WHERE n.entity_type IN $hard_junk_types
   OR toLower(coalesce(n.description, '')) CONTAINS 'placeholder for'
   OR (n.entity_id IS NOT NULL AND size(n.entity_id) <= 3 AND COUNT { (n)--() } = 0)
RETURN elementId(n) AS eid, n.entity_id AS entity_id, n.entity_type AS entity_type,
       n.description AS description, COUNT { (n)--() } AS degree
"""

BACKUP_NODE_QUERY = """
MATCH (n) WHERE elementId(n) = $eid
OPTIONAL MATCH (n)-[r]-(o)
RETURN properties(n) AS node_props, labels(n) AS labels,
       collect({type: type(r), other_entity_id: o.entity_id, direction:
         CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END}) AS rels
"""

DELETE_QUERY = "MATCH (n) WHERE elementId(n) = $eid DETACH DELETE n"


def classify(node: dict) -> str:
    reasons = []
    et = node["entity_type"]
    if et in HARD_JUNK_TYPES:
        reasons.append(f"hard_junk_type={et!r}")
    desc = (node["description"] or "").lower()
    if "placeholder for" in desc:
        reasons.append("placeholder_description")
    eid = node["entity_id"] or ""
    if len(eid) <= 3 and node["degree"] == 0:
        reasons.append("short_orphan_fragment")
    return ";".join(reasons)


def main(dry_run: bool) -> None:
    print("\n" + "=" * 60)
    print("Purge Junk Entities")
    print(f"  URI: {NEO4J_URI}")
    print(f"  Dry-run: {dry_run}")
    print("=" * 60 + "\n")

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        driver.verify_connectivity()
        print("Connected to Neo4j\n")
    except Exception as e:
        print(f"Cannot connect to Neo4j: {e}")
        sys.exit(1)

    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)

    with driver.session() as session:
        print("Step 1: finding candidates...")
        result = session.run(FIND_CANDIDATES_QUERY, hard_junk_types=HARD_JUNK_TYPES)
        candidates = [dict(r) for r in result]
        print(f"  {len(candidates)} candidate node(s) found\n")

        for c in candidates:
            c["reasons"] = classify(c)

        print("Sample (first 20):")
        for c in candidates[:20]:
            print(f"  {c['entity_id']!r} (type={c['entity_type']!r}, degree={c['degree']}) -> {c['reasons']}")
        if len(candidates) > 20:
            print(f"  ... and {len(candidates) - 20} more")
        print()

        if not candidates:
            print("Nothing to purge.")
            driver.close()
            return

        print("Step 2: backing up full node + relationship data before any deletion...")
        backup_entries = []
        for c in candidates:
            rec = session.run(BACKUP_NODE_QUERY, eid=c["eid"]).single()
            backup_entries.append({
                "eid": c["eid"],
                "reasons": c["reasons"],
                "node_props": dict(rec["node_props"]) if rec else {},
                "labels": rec["labels"] if rec else [],
                "relationships": rec["rels"] if rec else [],
            })

        backup_dir = _repo_root / "data"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"neo4j_junk_purge_backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump({"created_at": datetime.now(timezone.utc).isoformat(), "entries": backup_entries},
                      f, indent=2, default=str)
        print(f"  Backup written: {backup_path}\n")

        if dry_run:
            print("DRY-RUN: no Neo4j writes performed.")
            driver.close()
            return

        print("Step 3: deleting...")
        deleted = 0
        qdrant_entities_deleted = 0
        qdrant_relationships_deleted = 0
        for c in candidates:
            entity_id = c["entity_id"]
            try:
                session.run(DELETE_QUERY, eid=c["eid"])
                deleted += 1
            except Exception as e:
                print(f"  SKIP {c['entity_id']!r}: {e}")
                continue

            # Mirror the Neo4j delete into LightRAG's paired Qdrant vectors —
            # without this, a purged entity's embedding stays retrievable and
            # can surface stale content or dangling neighbor references during
            # graph-expansion retrieval even though the Neo4j node is gone.
            if not entity_id:
                continue
            try:
                res = qdrant.delete(
                    collection_name=QDRANT_ENTITIES_COLLECTION,
                    points_selector=Filter(
                        must=[FieldCondition(key="entity_name", match=MatchValue(value=entity_id))]
                    ),
                )
                if getattr(res, "status", None) is not None:
                    qdrant_entities_deleted += 1
            except Exception as e:
                print(f"  Qdrant entities delete failed for {entity_id!r}: {e}")

            try:
                qdrant.delete(
                    collection_name=QDRANT_RELATIONSHIPS_COLLECTION,
                    points_selector=Filter(
                        should=[
                            FieldCondition(key="src_id", match=MatchValue(value=entity_id)),
                            FieldCondition(key="tgt_id", match=MatchValue(value=entity_id)),
                        ]
                    ),
                )
                qdrant_relationships_deleted += 1
            except Exception as e:
                print(f"  Qdrant relationships delete failed for {entity_id!r}: {e}")

        print(f"  deleted {deleted}/{len(candidates)} Neo4j node(s)")
        print(
            f"  mirrored Qdrant deletes attempted for {qdrant_entities_deleted} "
            f"entities, {qdrant_relationships_deleted} relationship lookups\n"
        )

    print("=" * 60)
    print("Purge Complete")
    print(f"  Backup at: {backup_path}")
    print("=" * 60)
    driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge unambiguous junk entities from Neo4j")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("pass --dry-run or --apply")
    main(dry_run=args.dry_run)
