"""
Usage:
    python scripts/db_rectify.py            # dry-run (default): reports counts, deletes nothing
    python scripts/db_rectify.py --apply     # actually delete isolated/malformed nodes
"""

import argparse
import logging
import os

from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db_rectify")

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]  # required


def rectify_isolated_nodes(apply: bool = False):
    mode = "APPLY" if apply else "DRY RUN"
    logger.info(f"Starting rectification of isolated Neo4j nodes... (mode={mode})")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        with driver.session() as session:
            # Find isolated nodes
            result = session.run("MATCH (n) WHERE NOT (n)-[]-() RETURN count(n) as isolated_count")
            isolated_count = result.single()["isolated_count"]
            logger.info(f"Found {isolated_count} isolated nodes.")

            if isolated_count > 0:
                if apply:
                    logger.info("Deleting isolated nodes...")
                    session.run("MATCH (n) WHERE NOT (n)-[]-() DELETE n")
                    logger.info(f"Successfully deleted {isolated_count} isolated nodes.")
                else:
                    logger.info(f"[dry-run] Would delete {isolated_count} isolated nodes. Re-run with --apply.")
            else:
                logger.info("No isolated nodes found. Nothing to delete.")

            # Find malformed nodes (null or empty entity_id)
            result = session.run(
                "MATCH (n) WHERE n.entity_id IS NULL OR n.entity_id = '' RETURN count(n) as malformed_count"
            )
            malformed_count = result.single()["malformed_count"]
            logger.info(f"Found {malformed_count} malformed nodes (missing entity_id).")

            if malformed_count > 0:
                if apply:
                    logger.info("Deleting malformed nodes...")
                    session.run(
                        "MATCH (n) WHERE n.entity_id IS NULL OR n.entity_id = '' DETACH DELETE n"
                    )
                    logger.info(f"Successfully deleted {malformed_count} malformed nodes.")
                else:
                    logger.info(f"[dry-run] Would delete {malformed_count} malformed nodes. Re-run with --apply.")

        driver.close()
    except Exception as e:
        logger.error(f"Error rectifying Neo4j: {e}", exc_info=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rectify isolated/malformed Neo4j nodes")
    parser.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    args = parser.parse_args()
    rectify_isolated_nodes(apply=args.apply)
