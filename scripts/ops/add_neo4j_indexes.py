#!/usr/bin/env python3
"""Add missing Neo4j indexes for query performance.

Run: source .venv/bin/activate && python scripts/ops/add_neo4j_indexes.py
"""
import logging
import os
import sys

from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("add_neo4j_indexes")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from app.config import settings

NEO4J_URI = os.getenv("NEO4J_URI") or settings.neo4j_uri
NEO4J_USER = os.getenv("NEO4J_USER") or settings.neo4j_user
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or settings.neo4j_password

INDEXES = [
    ("entity_type_index", "CREATE INDEX entity_type_index IF NOT EXISTS FOR (n:base) ON (n.entity_type)"),
    ("source_id_index", "CREATE INDEX source_id_index IF NOT EXISTS FOR (n:base) ON (n.source_id)"),
    ("entity_id_index", "CREATE INDEX entity_id_index IF NOT EXISTS FOR (n:base) ON (n.entity_id)"),
    ("tenant_id_index", "CREATE INDEX tenant_id_index IF NOT EXISTS FOR (n:base) ON (n.tenant_id)"),
]


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        logger.info("Neo4j reachable")
    except Exception as e:
        logger.error(f"Neo4j unreachable: {e}")
        return 1

    for name, cypher in INDEXES:
        try:
            with driver.session() as session:
                session.run(cypher)
            logger.info(f"Index created: {name}")
        except Exception as e:
            logger.warning(f"Index {name} failed: {e}")

    # Verify
    with driver.session() as session:
        result = session.run("SHOW INDEXES")
        for r in result:
            logger.info(f"  Existing index: {r['name']} on {r['labelsOrTypes']}({r['properties']})")

    driver.close()
    logger.info("Done")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
