"""
Export / Import utility for migrating Neo4j graph data to Memgraph.
Supports:
  1. python3 -m scripts.ops.migrate_neo4j_to_memgraph export --output data/neo4j_graph_dump.json
  2. python3 -m scripts.ops.migrate_neo4j_to_memgraph import --input data/neo4j_graph_dump.json --uri bolt://localhost:7687
  3. python3 -m scripts.ops.migrate_neo4j_to_memgraph verify --uri bolt://localhost:7687
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate_neo4j_to_memgraph")


def _sanitize_val(val: Any) -> Any:
    """Convert Neo4j temporal/spatial or non-JSON types to JSON-serializable types."""
    if hasattr(val, "iso_format"):
        return val.iso_format()
    if hasattr(val, "to_native"):
        return str(val.to_native())
    if isinstance(val, (int, float, str, bool)) or val is None:
        return val
    if isinstance(val, list):
        return [_sanitize_val(x) for x in val]
    if isinstance(val, dict):
        return {k: _sanitize_val(v) for k, v in val.items()}
    return str(val)


def export_neo4j(uri: str, user: str, password: str, output_path: Path) -> dict[str, Any]:
    """Export all nodes and relationships from Neo4j to a JSON dump."""
    logger.info(f"Connecting to source Neo4j at {uri}...")
    auth = (user, password) if user or password else None
    driver = GraphDatabase.driver(uri, auth=auth)
    driver.verify_connectivity()

    nodes_data: list[dict[str, Any]] = []
    rels_data: list[dict[str, Any]] = []

    start_time = time.time()

    with driver.session() as session:
        logger.info("Fetching nodes from Neo4j...")
        node_result = session.run(
            "MATCH (n) RETURN elementId(n) AS elem_id, id(n) AS legacy_id, labels(n) AS labels, properties(n) AS props"
        )
        for record in node_result:
            nodes_data.append(
                {
                    "elem_id": record["elem_id"],
                    "legacy_id": record["legacy_id"],
                    "labels": record["labels"],
                    "props": _sanitize_val(record["props"]),
                }
            )
        logger.info(f"Fetched {len(nodes_data)} nodes.")

        logger.info("Fetching relationships from Neo4j...")
        rel_result = session.run(
            "MATCH (a)-[r]->(b) "
            "RETURN elementId(a) AS start_elem_id, id(a) AS start_legacy_id, "
            "elementId(b) AS end_elem_id, id(b) AS end_legacy_id, "
            "type(r) AS rel_type, properties(r) AS props"
        )
        for record in rel_result:
            rels_data.append(
                {
                    "start_elem_id": record["start_elem_id"],
                    "start_legacy_id": record["start_legacy_id"],
                    "end_elem_id": record["end_elem_id"],
                    "end_legacy_id": record["end_legacy_id"],
                    "rel_type": record["rel_type"],
                    "props": _sanitize_val(record["props"]),
                }
            )
        logger.info(f"Fetched {len(rels_data)} relationships.")

    driver.close()

    dump_payload = {
        "timestamp": time.time(),
        "node_count": len(nodes_data),
        "relationship_count": len(rels_data),
        "nodes": nodes_data,
        "relationships": rels_data,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dump_payload, f, indent=2)

    elapsed = time.time() - start_time
    logger.info(
        f"✅ Exported {len(nodes_data)} nodes and {len(rels_data)} relationships to {output_path} in {elapsed:.2f}s"
    )
    return dump_payload


def import_memgraph(
    uri: str, user: str, password: str, input_path: Path, batch_size: int = 500
) -> None:
    """Import nodes and relationships from JSON dump into Memgraph."""
    logger.info(f"Loading dump from {input_path}...")
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    rels = data.get("relationships", [])
    logger.info(f"Dump contains {len(nodes)} nodes and {len(rels)} relationships.")

    logger.info(f"Connecting to target Memgraph at {uri}...")
    auth = (user, password) if user or password else None
    driver = GraphDatabase.driver(uri, auth=auth)
    driver.verify_connectivity()

    start_time = time.time()

    with driver.session() as session:
        # 1. Create index on _migration_id for fast relationship wiring
        logger.info("Setting up indices in Memgraph...")
        try:
            session.run("CREATE INDEX ON :_MigrationNode(migration_id);").consume()
        except Exception as e:
            logger.warning(f"Index creation notice: {e}")

        # 2. Insert nodes in batches
        logger.info(f"Importing {len(nodes)} nodes in batches of {batch_size}...")
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            for item in batch:
                elem_id = item["elem_id"]
                labels = item["labels"] or []
                # Include helper label _MigrationNode
                label_str = (
                    ":" + ":".join(labels + ["_MigrationNode"]) if labels else ":_MigrationNode"
                )
                props = item["props"]
                props["_migration_id"] = elem_id

                cypher = f"CREATE (n{label_str}) SET n = $props"
                session.run(cypher, props=props)
            logger.info(f"Inserted nodes {min(i + batch_size, len(nodes))}/{len(nodes)}")

        # 3. Create indices on standard labels
        for common_label, prop in [
            ("Teacher", "name"),
            ("Concept", "name"),
            ("Practice", "name"),
            ("base", "entity_id"),
        ]:
            try:
                session.run(f"CREATE INDEX ON :{common_label}({prop});").consume()
            except Exception as e:
                logger.debug(f"Index for {common_label}({prop}): {e}")

        # 4. Insert relationships in batches
        logger.info(f"Importing {len(rels)} relationships in batches of {batch_size}...")
        for i in range(0, len(rels), batch_size):
            batch = rels[i : i + batch_size]
            for item in batch:
                start_id = item["start_elem_id"]
                end_id = item["end_elem_id"]
                rel_type = item["rel_type"]
                props = item["props"]

                cypher = f"""
                MATCH (a:_MigrationNode {{_migration_id: $start_id}})
                MATCH (b:_MigrationNode {{_migration_id: $end_id}})
                CREATE (a)-[r:{rel_type}]->(b)
                SET r = $props
                """
                session.run(cypher, start_id=start_id, end_id=end_id, props=props)
            logger.info(f"Inserted relationships {min(i + batch_size, len(rels))}/{len(rels)}")

        # 5. Clean up helper label and migration_id property
        logger.info("Cleaning up temporary migration metadata...")
        try:
            session.run(
                "MATCH (n:_MigrationNode) REMOVE n:_MigrationNode, n._migration_id"
            ).consume()
            session.run("DROP INDEX ON :_MigrationNode(migration_id);").consume()
        except Exception as e:
            logger.warning(f"Cleanup notice: {e}")

        # 6. Verify counts
        m_nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        m_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

    driver.close()
    elapsed = time.time() - start_time
    logger.info(
        f"✅ Migration complete in {elapsed:.2f}s! Memgraph has {m_nodes} nodes and {m_rels} relationships."
    )


def verify_counts(uri: str, user: str, password: str) -> None:
    auth = (user, password) if user or password else None
    driver = GraphDatabase.driver(uri, auth=auth)
    with driver.session() as s:
        n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        r = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        logger.info(f"Graph Database at {uri}: {n} nodes, {r} relationships")
    driver.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate Neo4j to Memgraph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Export
    exp = subparsers.add_parser("export")
    exp.add_argument("--uri", default="bolt://localhost:7687")
    exp.add_argument("--user", default="neo4j")
    exp.add_argument("--password", default="mukthiguru_neo4j_pass")
    exp.add_argument("--output", default="data/neo4j_graph_dump.json")

    # Import
    imp = subparsers.add_parser("import")
    imp.add_argument("--uri", default="bolt://localhost:7687")
    imp.add_argument("--user", default="")
    imp.add_argument("--password", default="")
    imp.add_argument("--input", default="data/neo4j_graph_dump.json")
    imp.add_argument("--batch-size", type=int, default=200)

    # Verify
    ver = subparsers.add_parser("verify")
    ver.add_argument("--uri", default="bolt://localhost:7687")
    ver.add_argument("--user", default="")
    ver.add_argument("--password", default="")

    args = parser.parse_args()

    if args.command == "export":
        export_neo4j(args.uri, args.user, args.password, Path(args.output))
    elif args.command == "import":
        import_memgraph(
            args.uri, args.user, args.password, Path(args.input), batch_size=args.batch_size
        )
    elif args.command == "verify":
        verify_counts(args.uri, args.user, args.password)


if __name__ == "__main__":
    main()
