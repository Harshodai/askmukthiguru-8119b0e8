#!/usr/bin/env python3
"""
Mukthi Guru — Self-Healing Data Quality Tool
Applies corrective fixes to Neo4j and Qdrant to resolve data inconsistencies.
"""

import os
from qdrant_client import QdrantClient
from neo4j import GraphDatabase

QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
NEO4J_URI   = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER  = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS  = os.getenv("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")

def main():
    print("=== Mukthi Guru Data Self-Healing ===")
    
    # 1. Clean Neo4j Orphans and Corrupted Nodes
    print("\n1. Healing Neo4j Graph...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            # Delete orphans
            orphans_before = session.run("MATCH (n:base) WHERE NOT (n)-[]-() RETURN count(n) as c").single()["c"]
            print(f"  Found {orphans_before} orphaned nodes in Neo4j.")
            if orphans_before > 0:
                session.run("MATCH (n:base) WHERE NOT (n)-[]-() DETACH DELETE n")
                print("  -> Deleted orphaned nodes successfully.")
                
            # Clean corrupted types
            corrupted_query = """
                MATCH (n:base) 
                WHERE n.entity_type IS NOT NULL AND (
                    n.entity_type CONTAINS '"' OR 
                    n.entity_type CONTAINS '\\\\' OR 
                    size(n.entity_type) > 50
                )
                RETURN count(n) as c
            """
            corrupted_before = session.run(corrupted_query).single()["c"]
            print(f"  Found {corrupted_before} nodes with corrupted/malformed entity_type.")
            if corrupted_before > 0:
                session.run("""
                    MATCH (n:base) 
                    WHERE n.entity_type IS NOT NULL AND (
                        n.entity_type CONTAINS '"' OR 
                        n.entity_type CONTAINS '\\\\' OR 
                        size(n.entity_type) > 50
                    )
                    DETACH DELETE n
                """)
                print("  -> Deleted corrupted entity type nodes successfully.")
                
            # Fetch remaining entities for cross check
            res = session.run("MATCH (n:base) WHERE n.entity_id IS NOT NULL RETURN n.entity_id as name")
            neo4j_entities = {r["name"].strip().lower() for r in res if r["name"]}
            print(f"  Active entities in Neo4j: {len(neo4j_entities)}")
        driver.close()
    except Exception as e:
        print(f"  ❌ Neo4j healing failed: {e}")
        return

    # 2. Heal Qdrant Cross-Database Inconsistencies
    print("\n2. Healing Qdrant Mismatches...")
    try:
        qdrant = QdrantClient(url=QDRANT_URL, timeout=15)
        all_cols = {c.name for c in qdrant.get_collections().collections}
        entity_cols = [c for c in all_cols if c.startswith("lightrag_vdb_entities_")]
        
        total_deleted_points = 0
        for col in entity_cols:
            cnt = qdrant.count(col, exact=True).count
            if cnt == 0:
                continue
                
            print(f"  Scanning collection: {col} ({cnt} points)")
            res, _ = qdrant.scroll(collection_name=col, limit=min(cnt, 10000), with_payload=True)
            
            points_to_delete = []
            for p in res:
                pay = p.payload or {}
                ent_name = pay.get("entity_name") or pay.get("entity_id") or pay.get("id")
                if ent_name:
                    ent_name_clean = str(ent_name).strip().lower()
                    if ent_name_clean not in neo4j_entities:
                        points_to_delete.append(p.id)
            
            if points_to_delete:
                print(f"    Found {len(points_to_delete)} orphaned vector points in Qdrant.")
                qdrant.delete(
                    collection_name=col,
                    points_selector=points_to_delete
                )
                print(f"    -> Deleted {len(points_to_delete)} points from {col}.")
                total_deleted_points += len(points_to_delete)
                
        print(f"  Successfully deleted {total_deleted_points} mismatched/orphaned vector points from Qdrant.")
    except Exception as e:
        print(f"  ❌ Qdrant healing failed: {e}")
        
    print("\n=== Healing Complete! Run audit again to verify. ===")

if __name__ == "__main__":
    main()
