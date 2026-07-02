#!/usr/bin/env python3
"""
Mukthi Guru — Consolidated Data Dump & Export Script

Fetches, merges, and exports all ingested content across:
  1. Qdrant (points, payload metadata, quality scores)
  2. Neo4j (nodes, labels, relationships)
  3. LightRAG (entities, relations)
  4. OKF entries (yaml frontmatter + body)

Outputs a consolidated backup folder under ./data/dump/<date>/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add backend directory to python path
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("dump_all_stores")


# ── Data fetchers ────────────────────────────────────────────────────────────

async def get_qdrant_data(quality_threshold: int) -> list[dict[str, Any]]:
    """Fetch all points from the main Qdrant collection with payload."""
    try:
        from services.qdrant_service import QdrantService
        svc = QdrantService()
        raw = await asyncio.to_thread(svc.get_all_texts)
        if not raw:
            return []

        # Filter by quality threshold if available
        filtered = []
        for point in raw:
            score = point.get("quality_score")
            if score is not None and int(score) < quality_threshold:
                continue
            filtered.append(point)

        logger.info(f"Fetched {len(filtered)} chunks from Qdrant (filtered from {len(raw)} under threshold={quality_threshold})")
        return filtered
    except Exception as e:
        logger.error(f"Failed to fetch Qdrant data: {e}")
        return []


async def get_neo4j_data() -> dict[str, list[dict[str, Any]]]:
    """Fetch all nodes and relationships from Neo4j."""
    from app.config import settings

    if not getattr(settings, "neo4j_uri", None):
        logger.warning("Neo4j not configured — skipping export")
        return {"nodes": [], "relationships": []}

    try:
        from neo4j import GraphDatabase

        def _fetch():
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            nodes = []
            rels = []
            with driver.session() as session:
                # Nodes query
                res_nodes = session.run("MATCH (n) RETURN id(n) as id, labels(n) as labels, properties(n) as props")
                for r in res_nodes:
                    nodes.append({
                        "id": r["id"],
                        "labels": list(r["labels"]),
                        "properties": dict(r["props"]),
                    })

                # Relationships query
                res_rels = session.run("MATCH (n)-[r]->(m) RETURN id(r) as id, type(r) as type, id(n) as start, id(m) as end, properties(r) as props")
                for r in res_rels:
                    rels.append({
                        "id": r["id"],
                        "type": r["type"],
                        "start_node_id": r["start"],
                        "end_node_id": r["end"],
                        "properties": dict(r["props"]),
                    })
            driver.close()
            return {"nodes": nodes, "relationships": rels}

        data = await asyncio.to_thread(_fetch)
        logger.info(f"Fetched {len(data['nodes'])} nodes and {len(data['relationships'])} relationships from Neo4j")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch Neo4j data: {e}")
        return {"nodes": [], "relationships": []}


def get_lightrag_data() -> dict[str, Any]:
    """Load entities and relationships from LightRAG local KV stores."""
    entities_path = Path("data/lightrag/kv_store_full_entities.json")
    relations_path = Path("data/lightrag/kv_store_full_relations.json")

    entities = {}
    relations = {}

    try:
        if entities_path.exists():
            entities = json.loads(entities_path.read_text(encoding="utf-8"))
        if relations_path.exists():
            relations = json.loads(relations_path.read_text(encoding="utf-8"))
        logger.info(f"Loaded {len(entities)} entities and {len(relations)} relations from LightRAG KV")
    except Exception as e:
        logger.warning(f"Could not load LightRAG KV stores: {e}")

    return {"entities": entities, "relations": relations}


def get_okf_entries() -> list[dict[str, Any]]:
    """Gather all staging and production OKF markdown files."""
    okf_dir = _BACKEND.parent / "memory" / "okf"
    entries = []

    if not okf_dir.exists():
        return entries

    # Scan for markdown files recursively
    for path in okf_dir.glob("**/*.md"):
        try:
            content = path.read_text(encoding="utf-8")
            # Parse simple YAML frontmatter manually
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    fm_text = parts[1]
                    body = parts[2].strip()

                    frontmatter = {}
                    for line in fm_text.split("\n"):
                        if ":" in line:
                            k, _, v = line.partition(":")
                            frontmatter[k.strip()] = v.strip().strip('"').strip("'")

                    entries.append({
                        "file_path": str(path.relative_to(okf_dir.parent)),
                        "frontmatter": frontmatter,
                        "body_length": len(body),
                        "preview": body[:200]
                    })
        except Exception as e:
            logger.warning(f"Failed to parse OKF file {path}: {e}")

    logger.info(f"Found {len(entries)} OKF entries under memory/okf/")
    return entries


# ── CLI & Main Orchestrator ──────────────────────────────────────────────────

async def run_dump(output_dir: str, quality_threshold: int) -> int:
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target_dir = Path(output_dir) / date_str
    target_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting consolidated data dump to: {target_dir}")

    # Gather in parallel
    qdrant_task = get_qdrant_data(quality_threshold)
    neo4j_task = get_neo4j_data()

    qdrant_chunks, neo4j_graph = await asyncio.gather(qdrant_task, neo4j_task)

    lightrag_data = get_lightrag_data()
    okf_entries = get_okf_entries()

    # Write files
    (target_dir / "qdrant_chunks.json").write_text(json.dumps(qdrant_chunks, indent=2, ensure_ascii=False), encoding="utf-8")
    (target_dir / "neo4j_graph.json").write_text(json.dumps(neo4j_graph, indent=2, ensure_ascii=False), encoding="utf-8")
    (target_dir / "lightrag_store.json").write_text(json.dumps(lightrag_data, indent=2, ensure_ascii=False), encoding="utf-8")
    (target_dir / "okf_entries.json").write_text(json.dumps(okf_entries, indent=2, ensure_ascii=False), encoding="utf-8")

    # Compute summary/statistics
    valid_scores = [c["quality_score"] for c in qdrant_chunks if c.get("quality_score") is not None]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

    summary = {
        "timestamp": datetime.now().isoformat(),
        "quality_threshold": quality_threshold,
        "counts": {
            "qdrant_chunks": len(qdrant_chunks),
            "neo4j_nodes": len(neo4j_graph["nodes"]),
            "neo4j_relationships": len(neo4j_graph["relationships"]),
            "lightrag_entities": len(lightrag_data["entities"]),
            "lightrag_relations": len(lightrag_data["relations"]),
            "okf_entries": len(okf_entries)
        },
        "average_quality_score": round(avg_score, 2),
    }

    (target_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(f"Consolidated dump complete! Summary statistics: {summary}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidated Mukthi Guru data dump")
    parser.add_argument("--output-dir", default="./data/dump", help="Base directory to write dump folders")
    parser.add_argument("--quality-threshold", type=int, default=65, help="Only export chunks meeting this threshold (default: 65)")
    args = parser.parse_args()

    return asyncio.run(run_dump(args.output_dir, args.quality_threshold))


if __name__ == "__main__":
    sys.exit(main())
