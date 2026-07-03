#!/usr/bin/env python3
"""Cross-store audit: LightRAG entities/chunks ↔ Neo4j ↔ Qdrant ↔ working dir."""

import os, sys, json, glob
from pathlib import Path
from collections import defaultdict

from qdrant_client import QdrantClient
from neo4j import GraphDatabase


QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")
LIGHTRAG_DIR = "data/lightrag"
LIGHTRAG_COLLECTION = os.getenv("QDRANT_COLLECTION", "ekam_lightrag")


def format_table(headers, rows):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(str(v)))
    sep = "-+-".join("-" * w for w in widths)
    out = [" | ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers)), sep]
    for row in rows:
        out.append(" | ".join(f"{str(v):<{widths[i]}}" for i, v in enumerate(row)))
    return "\n".join(out)


class CrossStoreAuditor:
    def __init__(self):
        self.qdrant = QdrantClient(url=QDRANT_URL, timeout=15)
        self.neo4j = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        self.report = {"entities": {}, "chunks": {}, "working_dir": {}, "inconsistencies": []}

    def close(self):
        self.neo4j.close()

    def _inc(self, db, typ, sev, desc):
        self.report["inconsistencies"].append(
            {"database": db, "type": typ, "severity": sev, "description": desc}
        )

    def audit_entities(self):
        print("\n=== Entity Cross-Store Audit ===")
        with self.neo4j.session() as s:
            our_res = s.run(
                "MATCH (n:base) WHERE n.entity_id IS NOT NULL "
                "RETURN n.entity_id AS id, n.entity_type AS type, n.description AS desc"
            )
            our_entities = {}
            for r in our_res:
                eid = (r.get("id") or "").strip().lower()
                if eid:
                    our_entities[eid] = {
                        "type": r.get("type") or "",
                        "desc": (r.get("desc") or "")[:60],
                    }

            lr_res = s.run(
                "MATCH (n:LIGHTRAG) WHERE n.entity_id IS NOT NULL "
                "RETURN n.entity_id AS id, labels(n) AS labels, n.entity_type AS type "
                "LIMIT 10000"
            )
            lr_entities = {(r.get("id") or "").strip().lower() for r in lr_res}

        qdrant_entity_cols = [
            c.name for c in self.qdrant.get_collections().collections
            if c.name.startswith(f"{LIGHTRAG_COLLECTION}_entities_")
        ]
        qdrant_entities = set()
        for col_name in qdrant_entity_cols:
            cnt = self.qdrant.count(col_name, exact=True).count
            if cnt == 0:
                continue
            pts, _ = self.qdrant.scroll(col_name, limit=min(cnt, 2000), with_payload=True)
            for p in pts:
                eid = str(p.payload.get("entity_name") or p.payload.get("entity_id") or "").strip().lower()
                if eid:
                    qdrant_entities.add(eid)

        our_set = set(our_entities.keys())
        our_in_lr = our_set & lr_entities
        our_missing_lr = our_set - lr_entities
        lr_extra = lr_entities - our_set
        qdrant_in_both = our_set & qdrant_entities
        qdrant_missing_our = qdrant_entities - our_set

        self.report["entities"] = {
            "our_neo4j_total": len(our_set),
            "lightrag_neo4j_total": len(lr_entities),
            "lightrag_qdrant_total": len(qdrant_entities),
            "matched_neo4j": len(our_in_lr),
            "our_missing_from_lightrag_neo4j": len(our_missing_lr),
            "our_missing_from_lightrag_qdrant": len(our_set - qdrant_entities),
            "lightrag_extra_not_in_our_neo4j": len(lr_extra),
            "sample_our_missing_lr": sorted(our_missing_lr)[:20],
            "sample_lr_extra": sorted(lr_extra)[:20],
            "sample_qdrant_missing_our": sorted(qdrant_missing_our)[:20],
        }

        print(f"Our Neo4j entities:             {len(our_set)}")
        print(f"LightRAG Neo4j entities:         {len(lr_entities)}")
        print(f"LightRAG Qdrant entities:        {len(qdrant_entities)}")
        print(f"Matched (in both):               {len(our_in_lr)}")
        print(f"Our entities missing in LR Neo4j: {len(our_missing_lr)}")
        print(f"Our entities missing in LR Qdrant: {len(our_set - qdrant_entities)}")
        print(f"LR entities not in our Neo4j:    {len(lr_extra)}")

        if len(our_missing_lr) > 10:
            self._inc("cross_store", "our_entities_missing_lightrag", "MEDIUM",
                       f"{len(our_missing_lr)} entities exist in our Neo4j but are absent from LightRAG Neo4j. "
                       "LightRAG will return no graph context for these entities.")
        if len(lr_extra) > 10:
            self._inc("cross_store", "lightrag_orphan_entities", "LOW",
                       f"{len(lr_extra)} entities exist in LightRAG Neo4j but have no counterpart in our Neo4j. "
                       "These might be stale/dangling from prior runs.")

    def audit_chunks(self):
        print("\n=== Chunk Cross-Store Audit ===")
        chunk_cols = [
            c.name for c in self.qdrant.get_collections().collections
            if c.name.startswith(f"{LIGHTRAG_COLLECTION}_chunks_")
        ]
        total_chunks = 0
        chunk_count_by_col = {}
        for col_name in chunk_cols:
            cnt = self.qdrant.count(col_name, exact=True).count
            chunk_count_by_col[col_name] = cnt
            total_chunks += cnt

        with self.neo4j.session() as s:
            our_chunks = s.run("MATCH (n:base) WHERE n.entity_type = 'chunk' RETURN count(n) AS c").single()["c"]
            our_docs = s.run("MATCH (n:base) WHERE n.entity_type = 'document' RETURN count(n) AS c").single()["c"]

        self.report["chunks"] = {
            "lightrag_qdrant_chunks": total_chunks,
            "lightrag_qdrant_collections": chunk_count_by_col,
            "our_neo4j_chunks": our_chunks,
            "our_neo4j_documents": our_docs,
        }

        print(f"LightRAG Qdrant chunks (total): {total_chunks}")
        for c, n in sorted(chunk_count_by_col.items()):
            print(f"  {c}: {n}")
        print(f"Our Neo4j chunks:               {our_chunks}")
        print(f"Our Neo4j documents:            {our_docs}")

    def audit_working_dir(self):
        print("\n=== LightRAG Working Directory Audit ===")
        lr_path = Path(LIGHTRAG_DIR)
        if not lr_path.exists():
            print(f"  Working dir {LIGHTRAG_DIR} does not exist")
            return
        kv_json = list(lr_path.glob("*kv_store*.json"))
        doc_status = list(lr_path.glob("*doc_status*.json"))
        graphml = list(lr_path.glob("*.graphml"))
        chunk_files = list(lr_path.glob("chunks_*"))
        rd = self.report["working_dir"]
        rd["path"] = str(lr_path.resolve())
        rd["kv_store_files"] = [str(p.name) for p in kv_json]
        rd["doc_status_files"] = [str(p.name) for p in doc_status]
        rd["graphml_files"] = [str(p.name) for p in graphml]
        rd["chunk_files"] = [str(p.name) for p in chunk_files]
        rd["total_files"] = len(list(lr_path.iterdir()))

        print(f"  Path: {lr_path.resolve()}")
        print(f"  KV store files:     {len(kv_json)}")
        print(f"  Doc status files:   {len(doc_status)}")
        print(f"  GraphML files:      {len(graphml)}")
        print(f"  Chunk files:        {len(chunk_files)}")
        print(f"  Total items:        {rd['total_files']}")

        if kv_json:
            fpath = kv_json[0]
            try:
                data = json.loads(fpath.read_text())
                rd["kv_store_keys"] = list(data.keys())[:100]
                rd["kv_store_key_count"] = len(data)
                print(f"  KV store keys: {len(data)}")
            except Exception as e:
                print(f"  KV store read error: {e}")

    def run_all(self):
        self.audit_entities()
        self.audit_chunks()
        self.audit_working_dir()
        os.makedirs("logs", exist_ok=True)
        rpath = "logs/cross_store_audit_report.json"
        with open(rpath, "w") as f:
            json.dump(self.report, f, indent=2, default=str)
        print(f"\nReport saved to {rpath}")

        if self.report["inconsistencies"]:
            print("\n=== Inconsistencies Found ===")
            rows = []
            for inc in self.report["inconsistencies"]:
                rows.append([inc["database"], inc["type"], inc["severity"], inc["description"][:80]])
            print(format_table(["DB", "Type", "Sev", "Description"], rows))
        else:
            print("\nNo inconsistencies found.")


if __name__ == "__main__":
    auditor = CrossStoreAuditor()
    try:
        auditor.run_all()
    finally:
        auditor.close()
