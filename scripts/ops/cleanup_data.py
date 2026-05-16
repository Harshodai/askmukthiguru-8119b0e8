#!/usr/bin/env python3
import sys
import os
import asyncio
import logging
from qdrant_client import QdrantClient
from qdrant_client.http import models
from neo4j import GraphDatabase

# Setup paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cleanup")

async def cleanup():
    # 1. FULL Clear Qdrant
    logger.info("Connecting to Qdrant...")
    try:
        client = QdrantClient(url="http://qdrant:6333")
        
        # Get all collections
        collections = client.get_collections().collections
        for c in collections:
            logger.info(f"Deleting Qdrant collection: {c.name}")
            client.delete_collection(c.name)
        
        logger.info("✅ Qdrant completely cleared.")
                
    except Exception as e:
        logger.error(f"❌ Qdrant cleanup failed: {e}")

    # 2. FULL Clear Neo4j
    logger.info("Connecting to Neo4j...")
    try:
        # Use proper auth from config/env if possible, but hardcoded for now as per original script
        driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "mukthiguru_neo4j_pass"))
        with driver.session() as session:
            logger.info("Deleting ALL Neo4j data...")
            session.run("MATCH (n) DETACH DELETE n")
        driver.close()
        logger.info("✅ Neo4j completely cleared.")
    except Exception as e:
        logger.error(f"❌ Neo4j cleanup failed: {e}")

    # 3. Clear Redis (Cache)
    logger.info("Connecting to Redis...")
    try:
        import redis
        r = redis.from_url("redis://:mukthiguru_redis_pass@redis:6379/0")
        r.flushall()
        logger.info("✅ Redis cleared.")
    except Exception as e:
        logger.warning(f"⚠️ Redis cleanup failed: {e}")

if __name__ == "__main__":
    asyncio.run(cleanup())
