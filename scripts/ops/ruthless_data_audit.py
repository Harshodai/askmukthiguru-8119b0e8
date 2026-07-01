#!/usr/bin/env python3
"""
Mukthi Guru — Ruthless Data Quality Audit Tool
Performs deep-dive audits of Qdrant and Neo4j for hybrid consistency,
identifying orphans, duplicates, broken schemas, and cross-database mismatches.
"""

import os
import sys
import json
import argparse
from collections import defaultdict
from qdrant_client import QdrantClient
from neo4j import GraphDatabase

# Configuration
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
NEO4J_URI   = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER  = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS  = os.getenv("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")

def format_table(headers, rows):
    """Simple terminal table formatter to avoid tabulate dependency."""
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            widths[idx] = max(widths[idx], len(str(val)))
    
    header_str = " | ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers))
    separator = "-+-".join("-" * w for w in widths)
    
    output = [header_str, separator]
    for row in rows:
        row_str = " | ".join(f"{str(val):<{widths[i]}}" for i, val in enumerate(row))
        output.append(row_str)
    return "\n".join(output)

class RuthlessAuditor:
    def __init__(self):
        self.qdrant = QdrantClient(url=QDRANT_URL, timeout=15)
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        self.report = {
            "qdrant": {},
            "neo4j": {},
            "cross_db": {},
            "inconsistencies": []
        }

    def close(self):
        self.neo4j_driver.close()

    def audit_qdrant(self):
        print("\n=== Auditing Qdrant Vector DB ===")
        collections = self.qdrant.get_collections().collections
        self.report["qdrant"]["collections"] = []
        
        for col in collections:
            name = col.name
            cnt = self.qdrant.count(name, exact=True).count
            
            # Audit payload structure for sample points
            sample_points = []
            payload_status = "Unknown"
            has_payload_errors = False
            duplicate_chunks = 0
            seen_texts = set()
            
            if cnt > 0:
                try:
                    # Scroll a batch of points to inspect payload quality
                    res, _ = self.qdrant.scroll(
                        collection_name=name,
                        limit=min(cnt, 200),
                        with_payload=True,
                        with_vectors=False
                    )
                    
                    for p in res:
                        pay = p.payload or {}
                        # Check typical fields: text/content, source, etc.
                        txt = pay.get("text") or pay.get("content") or ""
                        if not txt:
                            has_payload_errors = True
                        else:
                            txt_clean = txt.strip().lower()
                            if txt_clean in seen_texts:
                                duplicate_chunks += 1
                            seen_texts.add(txt_clean)
                    
                    payload_status = "⚠️ Missing fields" if has_payload_errors else "✅ Valid"
                except Exception as ex:
                    payload_status = f"❌ Error: {ex}"
            else:
                payload_status = "Empty"

            col_data = {
                "name": name,
                "points": cnt,
                "payload_status": payload_status,
                "duplicate_chunks_sample": duplicate_chunks
            }
            self.report["qdrant"]["collections"].append(col_data)
            
            if duplicate_chunks > 0:
                self.report["inconsistencies"].append({
                    "database": "qdrant",
                    "collection": name,
                    "type": "duplicate_chunks",
                    "severity": "LOW",
                    "description": f"Found {duplicate_chunks} duplicate chunks in sample of 200 points."
                })
            if has_payload_errors:
                self.report["inconsistencies"].append({
                    "database": "qdrant",
                    "collection": name,
                    "type": "payload_malformed",
                    "severity": "HIGH",
                    "description": "Payload is missing core fields (text or content)."
                })

        headers = ["Collection Name", "Point Count", "Payload Status", "Sample Duplicates"]
        rows = [[c["name"], c["points"], c["payload_status"], c["duplicate_chunks_sample"]] for c in self.report["qdrant"]["collections"]]
        print(format_table(headers, rows))

    def audit_neo4j(self):
        print("\n=== Auditing Neo4j Knowledge Graph ===")
        with self.neo4j_driver.session() as session:
            # 1. Node counts by type
            res = session.run("MATCH (n:base) RETURN n.entity_type as t, count(n) as c")
            types_counts = {r["t"] or "none": r["c"] for r in res}
            self.report["neo4j"]["node_types"] = types_counts
            
            # 2. Orphans check
            orphans_res = session.run("MATCH (n:base) WHERE NOT (n)-[]-() RETURN count(n) as c").single()
            orphans = orphans_res["c"] if orphans_res else 0
            self.report["neo4j"]["orphaned_nodes"] = orphans
            
            # 3. Invalid schemas
            missing_ids_res = session.run("MATCH (n:base) WHERE n.entity_id IS NULL AND n.file_path IS NULL RETURN count(n) as c").single()
            missing_ids = missing_ids_res["c"] if missing_ids_res else 0
            self.report["neo4j"]["missing_keys"] = missing_ids
            
            # 4. Out-of-bounds descriptions
            empty_desc_res = session.run("MATCH (n:base) WHERE n.entity_id IS NOT NULL AND (n.description IS NULL OR n.description = '') RETURN count(n) as c").single()
            empty_desc = empty_desc_res["c"] if empty_desc_res else 0
            self.report["neo4j"]["empty_descriptions"] = empty_desc

            # 5. Missing source document link
            missing_source_res = session.run("MATCH (n:base) WHERE n.entity_type = 'document' AND n.source_id IS NULL RETURN count(n) as c").single()
            missing_source = missing_source_res["c"] if missing_source_res else 0
            self.report["neo4j"]["chunks_missing_source_link"] = missing_source

        print(f"Node Counts: {json.dumps(types_counts, indent=2)}")
        print(f"Orphaned Nodes (0 connections): {orphans}")
        print(f"Nodes Missing Keys: {missing_ids}")
        print(f"Entities with Empty Descriptions: {empty_desc}")
        print(f"Documents Missing Source Links: {missing_source}")
        
        if orphans > 0:
            self.report["inconsistencies"].append({
                "database": "neo4j",
                "type": "orphaned_nodes",
                "severity": "MEDIUM",
                "description": f"Found {orphans} nodes in the graph with 0 relationships (unreachable during RAG walks)."
            })
        if missing_ids > 0:
            self.report["inconsistencies"].append({
                "database": "neo4j",
                "type": "missing_keys",
                "severity": "HIGH",
                "description": f"Found {missing_ids} nodes missing both entity_id and file_path identifiers."
            })
        if empty_desc > 0:
            self.report["inconsistencies"].append({
                "database": "neo4j",
                "type": "empty_descriptions",
                "severity": "LOW",
                "description": f"Found {empty_desc} entities with empty descriptions."
            })

    def audit_cross_consistency(self):
        print("\n=== Auditing Cross-Database Consistency (Qdrant ↔ Neo4j) ===")
        # Get active collections in Qdrant
        all_cols = {c.name for c in self.qdrant.get_collections().collections}
        
        entity_cols = [c for c in all_cols if c.startswith("lightrag_vdb_entities_")]
        chunk_cols = [c for c in all_cols if c.startswith("lightrag_vdb_chunks_")]
        
        # 1. Fetch Neo4j canonical entities
        with self.neo4j_driver.session() as session:
            res = session.run("MATCH (n:base) WHERE n.entity_id IS NOT NULL RETURN n.entity_id as name")
            neo4j_entities = {r["name"].strip().lower() for r in res if r["name"]}
            
            # Neo4j in LightRAG only stores entities and relationships; chunks reside in Qdrant.
            neo4j_chunks = set()


        print(f"Neo4j Entities: {len(neo4j_entities)}, Neo4j Chunks: {len(neo4j_chunks)}")
        
        # 2. Match entities
        qdrant_entities = set()
        for col in entity_cols:
            cnt = self.qdrant.count(col, exact=True).count
            if cnt > 0:
                try:
                    res, _ = self.qdrant.scroll(collection_name=col, limit=min(cnt, 5000), with_payload=True)
                    for p in res:
                        pay = p.payload or {}
                        ent_id = pay.get("entity_name") or pay.get("entity_id") or pay.get("id")
                        if ent_id:
                            qdrant_entities.add(str(ent_id).strip().lower())
                except Exception as e:
                    print(f"Error scrolling entities from {col}: {e}")

        # 3. Match chunks
        qdrant_chunks = set()
        for col in chunk_cols:
            cnt = self.qdrant.count(col, exact=True).count
            if cnt > 0:
                try:
                    res, _ = self.qdrant.scroll(collection_name=col, limit=min(cnt, 5000), with_payload=True)
                    for p in res:
                        pay = p.payload or {}
                        # Chunks have a unique hash or ID in payload
                        c_id = pay.get("id") or pay.get("chunk_id") or pay.get("source_id")
                        if c_id:
                            qdrant_chunks.add(str(c_id))
                except Exception as e:
                    print(f"Error scrolling chunks from {col}: {e}")

        print(f"Qdrant Entities Scrolled: {len(qdrant_entities)}, Qdrant Chunks Scrolled: {len(qdrant_chunks)}")
        
        # Inconsistencies: Entities in Qdrant but missing in Neo4j (Broken linkages)
        mismatched_entities = qdrant_entities - neo4j_entities
        mismatched_chunks = qdrant_chunks - neo4j_chunks
        
        self.report["cross_db"] = {
            "neo4j_entities_count": len(neo4j_entities),
            "qdrant_entities_count": len(qdrant_entities),
            "mismatched_entities": list(mismatched_entities)[:50],
            "mismatched_entities_count": len(mismatched_entities),
            "mismatched_chunks_count": len(mismatched_chunks)
        }
        
        print(f"Entities in Qdrant but missing in Neo4j: {len(mismatched_entities)}")
        print(f"Chunks in Qdrant but missing in Neo4j: {len(mismatched_chunks)}")
        
        if len(mismatched_entities) > 0:
            self.report["inconsistencies"].append({
                "database": "cross_db",
                "type": "mismatched_entities",
                "severity": "HIGH",
                "description": f"Found {len(mismatched_entities)} entities that have vector embeddings in Qdrant but no corresponding node in Neo4j (Broken RAG graph links)."
            })
        if len(mismatched_chunks) > 0:
            self.report["inconsistencies"].append({
                "database": "cross_db",
                "type": "mismatched_chunks",
                "severity": "MEDIUM",
                "description": f"Found {len(mismatched_chunks)} chunks in Qdrant but missing in Neo4j."
            })

    def run_all(self):
        self.audit_qdrant()
        self.audit_neo4j()
        self.audit_cross_consistency()
        
        # Save JSON report
        os.makedirs("logs", exist_ok=True)
        report_file = "logs/ruthless_data_audit_report.json"
        with open(report_file, "w") as f:
            json.dump(self.report, f, indent=2)
        print(f"\nAudit complete! Report saved to {report_file}")
        
        # Generate resolution actions
        print("\n=== Self-Healing Resolution Plan ===")
        actions = []
        for inc in self.report["inconsistencies"]:
            db = inc["database"]
            itype = inc["type"]
            sev = inc["severity"]
            desc = inc["description"]
            
            action = "No action planned"
            if itype == "orphaned_nodes":
                action = "Cypher: MATCH (n:base) WHERE NOT (n)-[]-() DETACH DELETE n;"
            elif itype == "missing_keys":
                action = "Cypher: MATCH (n:base) WHERE n.entity_id IS NULL AND n.file_path IS NULL DETACH DELETE n;"
            elif itype == "empty_descriptions":
                action = "Trigger re-extraction / summarization for nodes with empty description properties."
            elif itype == "mismatched_entities":
                action = "Delete corresponding orphaned entity points from Qdrant vector collections to restore consistency."
            
            actions.append([db, itype, sev, desc[:60], action])
            
        if actions:
            headers = ["Database", "Inconsistency Type", "Severity", "Description", "Recommended Action"]
            print(format_table(headers, actions))
        else:
            print("✅ No inconsistencies found! Both databases are in perfect synchrony.")

if __name__ == "__main__":
    auditor = RuthlessAuditor()
    try:
        auditor.run_all()
    finally:
        auditor.close()
