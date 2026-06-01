import logging
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("neo4j_inspect")

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "mukthiguru_neo4j_pass"

def inspect_poisoned_nodes():
    logger.info("Connecting to Neo4j to find poisoned nodes...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            # Query nodes containing prompt markers in their description or other text properties
            query = """
            MATCH (n)
            WHERE n.description CONTAINS "---Role---" 
               OR n.description CONTAINS "Knowledge Graph Specialist"
               OR n.description CONTAINS "synthesize"
            RETURN n.id as id, labels(n) as labels, n.description as description, keys(n) as properties
            """
            result = session.run(query)
            records = list(result)
            logger.info(f"Found {len(records)} poisoned nodes in Neo4j:")
            print("=" * 100)
            for r in records:
                desc_snippet = r["description"][:150].replace('\n', ' ') if r["description"] else "None"
                print(f"Node ID: {r['id']}")
                print(f"Labels: {r['labels']}")
                print(f"Properties: {r['properties']}")
                print(f"Description Snippet: {desc_snippet}...")
                print("-" * 100)
        driver.close()
    except Exception as e:
        logger.error(f"Error connecting to Neo4j: {e}", exc_info=True)

if __name__ == "__main__":
    inspect_poisoned_nodes()
