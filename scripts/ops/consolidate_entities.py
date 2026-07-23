#!/usr/bin/env python3
"""
Mukthi Guru — Entity Consolidation Script
Identifies and merges duplicate entities in Neo4j (e.g., 'Sri Krishnaji' and 'Krishnaji').

Safety:
- Run with dry-run by default.
- Specify --execute to apply changes to the database.
"""

import os
import re
import argparse
from collections import defaultdict
from neo4j import GraphDatabase

NEO4J_URI   = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER  = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS  = os.getenv("NEO4J_PASSWORD", "")

def clean_name(name):
    # Remove honorifics and common prefixes/suffixes for matching
    cleaned = name.strip()
    cleaned = re.sub(r'^(sri|shri|sree|guruji|guru|swami|swamiji|acharya)\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+(ji|deva|dev|maharaj|swami|swamiji)$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip().lower()

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
    
    # Group by cleaned name
    groups = defaultdict(list)
    for node in nodes:
        cleaned = clean_name(node["name"])
        if len(cleaned) < 3:
            continue
        groups[cleaned].append(node)
        
    duplicate_groups = {}
    for cleaned, group in groups.items():
        if len(group) > 1:
            names = {n["name"] for n in group}
            duplicate_groups[cleaned] = group
            
    return duplicate_groups

def merge_duplicate_group(session, cleaned_root, group, execute=False):
    print(f"\nProcessing Group: root='{cleaned_root}'")
    
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
            # parameterize a relationship type directly). The prior version used
            # `MERGE (master:base)-[new_r:DIRECTED]->(target)` with `master` unbound
            # to $master_id — Neo4j would match *any* :base node already carrying a
            # :DIRECTED edge to `target`, or silently CREATE a brand-new blank node,
            # and it collapsed every relationship type (TEACHES, EXPOUNDS, ...) into
            # a generic "DIRECTED" label.
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

def main():
    parser = argparse.ArgumentParser(description="Merge duplicate entities in Neo4j.")
    parser.add_argument("--execute", action="store_true", help="Apply changes to the database (defaults to dry-run)")
    args = parser.parse_args()
    
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            duplicates = find_duplicates(session)
            total_groups = len(duplicates)
            print(f"\nFound {total_groups} groups of duplicate nodes.")
            
            if total_groups == 0:
                print("No duplicates found.")
                return
                
            total_merged = 0
            for cleaned_root, group in duplicates.items():
                if len(group) > 1:
                    total_merged += merge_duplicate_group(session, cleaned_root, group, execute=args.execute)
            
            if not args.execute:
                print(f"\n[Dry-run Complete] Total nodes that would be merged: {total_merged}")
                print("Run with --execute to apply changes.")
            else:
                print(f"\n[Execution Complete] Total duplicate nodes merged: {total_merged}")
                
        driver.close()
    except Exception as e:
        print(f"Error during consolidation: {e}")

if __name__ == "__main__":
    main()
