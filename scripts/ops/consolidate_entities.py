#!/usr/bin/env python3
"""
Mukthi Guru — Entity Consolidation Script
Identifies and merges duplicate entities in Neo4j (e.g., 'Sri Krishnaji' and 'Krishnaji').

Dedup signals (union of two independent methods — a node pair caught by either
one is merged, matching cognee's tasks/memify/consolidate_entities.py design,
topoteretes/cognee, Apache-2.0):
  1. Normalized-name match: honorific-stripped, lowercased name, same entity_type.
     (cognee itself just lowercases + strips non-alphanumeric; the honorific
     stripping here is domain-specific — "Sri Krishnaji" / "Krishnaji" / "Krishnaji Ji".)
  2. Embedding-similarity match: cosine >= 0.85 against the node's own vector in
     lightrag_vdb_entities_baai_bge_m3_1024d, filtered to the same entity_type.
     Catches near-duplicates the string match misses (paraphrases, unrelated
     casing/hyphenation drift like "God Realization" / "God-realization").
Both methods are gated to the SAME entity_type (cognee's allow_cross_type=False
default) — a "Concept" node and a "Teacher" node never merge just because their
names collide. Confirmed necessary: the 2026-09-03 ruthless audit found the
prior (type-blind) version of this script would have been a merge hazard.

Safety:
- Run with dry-run by default.
- Specify --execute to apply changes to the database.
- Embedding leg is opt-in via --embeddings (needs QDRANT_URL reachable); the
  script runs name-match-only without it, never fails if Qdrant is unreachable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase

_repo_root = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv  # type: ignore

    for _env_path in (_repo_root / "backend" / ".env", _repo_root / ".env"):
        if _env_path.exists():
            load_dotenv(dotenv_path=_env_path, override=False)
            break
except ImportError:
    pass  # env vars may already be exported by the caller

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
ENTITY_COLLECTION = os.getenv("LIGHTRAG_ENTITY_COLLECTION", "lightrag_vdb_entities_baai_bge_m3_1024d")

# localhost fallback when running outside Docker (the "neo4j" hostname won't resolve).
if "neo4j:7687" in NEO4J_URI:
    import socket

    try:
        socket.getaddrinfo("neo4j", 7687)
    except socket.gaierror:
        NEO4J_URI = NEO4J_URI.replace("neo4j:7687", "localhost:7687")
        print("  Warning: 'neo4j' hostname not resolvable, using localhost:7687 instead")

EMBEDDING_SIMILARITY_THRESHOLD = 0.85  # cognee's default


def clean_name(name):
    # Remove honorifics and common prefixes/suffixes for matching
    cleaned = name.strip()
    cleaned = re.sub(r'^(sri|shri|sree|guruji|guru|swami|swamiji|acharya)\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+(ji|deva|dev|maharaj|swami|swamiji)$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip().lower()


def normalize_name(name):
    """Lowercase, strip non-alphanumeric — cognee's own normalization, applied
    on top of clean_name so 'God-Realization' and 'God Realization' collide."""
    return re.sub(r"[^a-z0-9]", "", clean_name(name))


def get_node_degree(session, node_id):
    query = """
    MATCH (n:base) WHERE elementId(n) = $node_id
    RETURN COUNT { (n)-[]-() } as degree
    """
    res = session.run(query, node_id=node_id).single()
    return res["degree"] if res else 0


def find_duplicates(session):
    print("Fetching nodes from Neo4j...")
    query = """
    MATCH (n:base)
    WHERE n.entity_id IS NOT NULL
    RETURN elementId(n) as id, n.entity_id as name, n.entity_type as type, n.description as desc
    """
    result = session.run(query)

    nodes = []
    for r in result:
        nodes.append({
            "id": r["id"],
            "name": r["name"],
            "type": r["type"] or "unknown",
            "desc": r["desc"] or ""
        })

    print(f"Total entity nodes found: {len(nodes)}")

    # Group by (normalized name, entity_type) — same-type gate per cognee's
    # allow_cross_type=False. A bare name-only key was the prior bug: it could
    # merge a Concept and a Teacher that happen to share a cleaned name.
    groups = defaultdict(list)
    for node in nodes:
        normalized = normalize_name(node["name"])
        if len(normalized) < 3:
            continue
        groups[(normalized, node["type"])].append(node)

    duplicate_groups = {}
    for key, group in groups.items():
        if len(group) > 1:
            duplicate_groups[key] = group

    return duplicate_groups, nodes


def find_embedding_duplicates(nodes, node_by_id):
    """Second dedup signal: cosine similarity >= 0.85 against each node's own
    vector in Qdrant, filtered to the same entity_type. Returns cluster lists
    in the same shape as find_duplicates, keyed by a synthetic ("emb", i) key
    so callers can just concatenate the two dicts' values.
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
    except ImportError:
        print("  qdrant-client not installed — skipping embedding leg (pip install qdrant-client)")
        return {}

    try:
        client = QdrantClient(url=QDRANT_URL, timeout=10)
        client.get_collection(ENTITY_COLLECTION)
    except Exception as e:
        print(f"  Qdrant unreachable ({e}) — skipping embedding leg")
        return {}

    print(f"Fetching entity vectors from {ENTITY_COLLECTION}...")
    name_to_point = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=ENTITY_COLLECTION,
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        for p in points:
            entity_name = (p.payload or {}).get("entity_name")
            if entity_name and p.vector:
                name_to_point[entity_name] = p
        if not offset:
            break
    print(f"  {len(name_to_point)} entity vectors indexed by name")

    # union-find over Neo4j node ids so overlapping name+embedding hits merge into one cluster
    parent = {n["id"]: n["id"] for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    matched_pairs = 0
    for node in nodes:
        point = name_to_point.get(node["name"])
        if point is None:
            continue
        try:
            hits = client.search(
                collection_name=ENTITY_COLLECTION,
                query_vector=point.vector,
                query_filter=Filter(
                    must=[FieldCondition(key="entity_type", match=MatchValue(value=node["type"]))]
                ) if node["type"] and node["type"] != "unknown" else None,
                score_threshold=EMBEDDING_SIMILARITY_THRESHOLD,
                limit=5,
            )
        except Exception:
            continue
        for hit in hits:
            hit_name = (hit.payload or {}).get("entity_name")
            if not hit_name or hit_name == node["name"]:
                continue
            hit_node = next((n for n in nodes if n["name"] == hit_name and n["type"] == node["type"]), None)
            if hit_node is None:
                continue
            union(node["id"], hit_node["id"])
            matched_pairs += 1

    clusters = defaultdict(list)
    for n in nodes:
        clusters[find(n["id"])].append(n)
    embedding_groups = {("emb", root): members for root, members in clusters.items() if len(members) > 1}
    print(f"  {matched_pairs} embedding-similarity pair(s) found, forming {len(embedding_groups)} cluster(s)")
    return embedding_groups


def merge_duplicate_group(session, group_key, group, execute=False):
    print(f"\nProcessing Group: key={group_key}")

    # Choose master node
    node_metrics = []
    for node in group:
        deg = get_node_degree(session, node["id"])
        node_metrics.append((deg, len(node["desc"]), len(node["name"]), node))

    node_metrics.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    master = node_metrics[0][3]
    duplicates = [x[3] for x in node_metrics[1:]]

    print(f"  Master Node selected: '{master['name']}' (ID: {master['id']}, Description: '{master['desc'][:60]}...')")
    for dup in duplicates:
        print(f"  Duplicate Node to merge: '{dup['name']}' (ID: {dup['id']}, Description: '{dup['desc'][:60]}...')")

    if not execute:
        print("  [Dry-run] Would merge these nodes.")
        return len(duplicates)

    merged_count = 0
    with session.begin_transaction() as tx:
        for dup in duplicates:
            # Transfer outgoing relationships, preserving the original relationship
            # type and properties via apoc.merge.relationship (Cypher can't
            # parameterize a relationship type directly).
            tx.run("""
            MATCH (master:base) WHERE elementId(master) = $master_id
            MATCH (dup:base)-[r]->(target)
            WHERE elementId(dup) = $dup_id AND elementId(target) <> $master_id
            CALL apoc.merge.relationship(master, type(r), properties(r), properties(r), target, {}) YIELD rel
            DELETE r
            """, dup_id=dup["id"], master_id=master["id"])

            # Transfer incoming relationships (same fix, reversed direction)
            tx.run("""
            MATCH (master:base) WHERE elementId(master) = $master_id
            MATCH (source)-[r]->(dup:base)
            WHERE elementId(dup) = $dup_id AND elementId(source) <> $master_id
            CALL apoc.merge.relationship(source, type(r), properties(r), properties(r), master, {}) YIELD rel
            DELETE r
            """, dup_id=dup["id"], master_id=master["id"])

            # Merge descriptions
            if dup["desc"] and dup["desc"] != master["desc"]:
                combined_desc = master["desc"] + " | " + dup["desc"]
                if len(combined_desc) > 2000:
                    combined_desc = combined_desc[:1997] + "..."
                tx.run("""
                MATCH (m:base) WHERE elementId(m) = $master_id
                SET m.description = $desc
                """, master_id=master["id"], desc=combined_desc)
                master["desc"] = combined_desc

            # Delete duplicate node
            tx.run("MATCH (dup:base) WHERE elementId(dup) = $dup_id DETACH DELETE dup", dup_id=dup["id"])
            merged_count += 1

    print(f"  Successfully merged {merged_count} duplicate nodes into '{master['name']}'")
    return merged_count


def combine_groups(name_groups: dict, embedding_groups: dict, all_nodes: list[dict]) -> dict:
    """Union name_groups and embedding_groups using connected components (union-find).

    Ensures that if node A and B are grouped by name, and B and C are grouped by embedding,
    they are unified into a single group {A, B, C}. Also strictly preserves entity_type scoping.
    """
    parent = {n["id"]: n["id"] for n in all_nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Union all pairs within each name group
    for group in name_groups.values():
        if len(group) > 1:
            first_id = group[0]["id"]
            for node in group[1:]:
                if node.get("type") == group[0].get("type"):
                    union(first_id, node["id"])

    # Union all pairs within each embedding group
    for group in embedding_groups.values():
        if len(group) > 1:
            first_id = group[0]["id"]
            for node in group[1:]:
                if node.get("type") == group[0].get("type"):
                    union(first_id, node["id"])

    # Collect connected components
    clusters = defaultdict(list)
    for n in all_nodes:
        root = find(n["id"])
        clusters[root].append(n)

    # Return only groups with >1 node
    unified_groups = {}
    for root, members in clusters.items():
        if len(members) > 1:
            primary_name = members[0]["name"]
            primary_type = members[0].get("type", "unknown")
            unified_groups[(primary_name, primary_type)] = members

    return unified_groups


def get_node_relationships(session, node_id: str) -> list[dict]:
    """Fetch all incoming and outgoing relationships for a node for backup before mutation."""
    result = session.run("""
    MATCH (n:base)-[r]-(other)
    WHERE elementId(n) = $node_id
    RETURN type(r) AS type, properties(r) AS properties,
           elementId(startNode(r)) = $node_id AS is_outgoing,
           elementId(other) AS other_id, other.name AS other_name
    """, node_id=node_id)
    relationships = []
    for record in result:
        relationships.append({
            "type": record["type"],
            "properties": dict(record["properties"] or {}),
            "is_outgoing": record["is_outgoing"],
            "other_id": record["other_id"],
            "other_name": record["other_name"],
        })
    return relationships


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate entities in Neo4j.")
    parser.add_argument("--execute", action="store_true", help="Apply changes to the database (defaults to dry-run)")
    parser.add_argument("--embeddings", action="store_true", help="Also run the embedding-similarity dedup leg (needs Qdrant)")
    args = parser.parse_args()

    driver = None
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            name_groups, all_nodes = find_duplicates(session)
            print(f"\nFound {len(name_groups)} name-match duplicate group(s).")

            embedding_groups = {}
            if args.embeddings:
                node_by_id = {n["id"]: n for n in all_nodes}
                embedding_groups = find_embedding_duplicates(all_nodes, node_by_id)

            all_groups = combine_groups(name_groups, embedding_groups, all_nodes)
            total_groups = len(all_groups)
            print(f"\nTotal duplicate groups to process (name + embedding): {total_groups}")

            if total_groups == 0:
                print("No duplicates found.")
                return

            if args.execute:
                backup_dir = _repo_root / "data"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"neo4j_consolidation_backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"

                # Capture all node relationships for rollback/audit safety
                enriched_groups = []
                for key, group in all_groups.items():
                    enriched_members = []
                    for node in group:
                        rels = get_node_relationships(session, node["id"])
                        node_copy = dict(node)
                        node_copy["relationships"] = rels
                        enriched_members.append(node_copy)
                    enriched_groups.append({"key": str(key), "members": enriched_members})

                backup_data = {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "groups": enriched_groups,
                }
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(backup_data, f, indent=2, default=str)
                print(f"Pre-mutation backup written: {backup_path}\n")

            total_merged = 0
            for group_key, group in all_groups.items():
                if len(group) > 1:
                    total_merged += merge_duplicate_group(session, group_key, group, execute=args.execute)

            if not args.execute:
                print(f"\n[Dry-run Complete] Total nodes that would be merged: {total_merged}")
                print("Run with --execute to apply changes. Add --embeddings to also catch non-string-match near-duplicates.")
            else:
                print(f"\n[Execution Complete] Total duplicate nodes merged: {total_merged}")

    except Exception as e:
        print(f"Error during consolidation: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if driver is not None:
            driver.close()


if __name__ == "__main__":
    main()
