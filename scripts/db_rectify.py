import logging

from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db_rectify")

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
import os
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]  # required


def rectify_isolated_nodes():
    logger.info("Starting rectification of isolated Neo4j nodes...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        with driver.session() as session:
            # Find isolated nodes
            result = session.run("MATCH (n) WHERE NOT (n)-[]-() RETURN count(n) as isolated_count")
            isolated_count = result.single()["isolated_count"]
            logger.info(f"Found {isolated_count} isolated nodes.")

            if isolated_count > 0:
                logger.info("Deleting isolated nodes...")
                session.run("MATCH (n) WHERE NOT (n)-[]-() DELETE n")
                logger.info(f"Successfully deleted {isolated_count} isolated nodes.")
            else:
                logger.info("No isolated nodes found. Nothing to delete.")

            # Find malformed nodes (null or empty entity_id)
            result = session.run(
                "MATCH (n) WHERE n.entity_id IS NULL OR n.entity_id = '' RETURN count(n) as malformed_count"
            )
            malformed_count = result.single()["malformed_count"]
            logger.info(f"Found {malformed_count} malformed nodes (missing entity_id).")

            if malformed_count > 0:
                logger.info("Deleting malformed nodes...")
                session.run(
                    "MATCH (n) WHERE n.entity_id IS NULL OR n.entity_id = '' DETACH DELETE n"
                )
                logger.info(f"Successfully deleted {malformed_count} malformed nodes.")

        driver.close()
    except Exception as e:
        logger.error(f"Error rectifying Neo4j: {e}", exc_info=True)


if __name__ == "__main__":
    rectify_isolated_nodes()
