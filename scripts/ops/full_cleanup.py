#!/usr/bin/env python3
import os
import shutil
import sys
import logging
from pathlib import Path

# Setup paths to backend
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("full_cleanup")

def main():
    logger.info("🧹 Starting complete clean up of all local cache, state, and databases...")

    # 1. Clear GPTCache
    gptcache_paths = [Path(BASE_DIR) / "data" / "gptcache", Path(BACKEND_DIR) / "data" / "gptcache"]
    for path in gptcache_paths:
        if path.exists():
            try:
                shutil.rmtree(path)
                logger.info(f"✅ GPTCache directory '{path}' deleted.")
            except Exception as e:
                logger.error(f"❌ Failed to delete GPTCache directory {path}: {e}")

    # 2. Clear LightRAG State
    lightrag_path = Path(BASE_DIR) / "data" / "lightrag"
    if lightrag_path.exists():
        try:
            shutil.rmtree(lightrag_path)
            logger.info(f"✅ LightRAG state directory '{lightrag_path}' deleted.")
        except Exception as e:
            logger.error(f"❌ Failed to delete LightRAG directory: {e}")

    # 3. Clear Ingestion state files (excluding logs)
    ingestion_files = [
        Path(BASE_DIR) / "scripts" / "ingestion_state.json"
    ]
    for file_path in ingestion_files:
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"✅ Ingestion file '{file_path}' deleted.")
            except Exception as e:
                logger.error(f"❌ Failed to delete ingestion file {file_path}: {e}")

    # 4. Clear Qdrant collections on localhost
    logger.info("Connecting to Qdrant on localhost...")
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url="http://localhost:6333")
        collections = client.get_collections().collections
        for c in collections:
            logger.info(f"Deleting Qdrant collection: {c.name}")
            client.delete_collection(c.name)
        logger.info("✅ Qdrant database completely cleared.")
    except Exception as e:
        logger.error(f"❌ Qdrant cleanup failed (is Qdrant running on localhost:6333?): {e}")

    # 5. Clear Neo4j on localhost
    logger.info("Connecting to Neo4j on localhost...")
    try:
        from neo4j import GraphDatabase
        password = os.environ.get("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
        with driver.session() as session:
            logger.info("Deleting ALL Neo4j data (nodes + relationships)...")
            session.run("MATCH (n) DETACH DELETE n")
        driver.close()
        logger.info("✅ Neo4j database completely cleared.")
    except Exception as e:
        logger.error(f"❌ Neo4j cleanup failed (is Neo4j running on localhost:7687?): {e}")

    # 6. Clear Redis on localhost
    logger.info("Connecting to Redis on localhost...")
    try:
        import redis
        password = os.environ.get("REDIS_PASSWORD", "mukthiguru_redis_pass")
        r = redis.from_url(f"redis://:{password}@localhost:6379/0")
        r.flushall()
        logger.info("✅ Redis cache completely cleared.")
    except Exception as e:
        logger.warning(f"⚠️ Redis cleanup failed: {e}")

    logger.info("🎉 Complete cleanup finished successfully!")

if __name__ == "__main__":
    main()
