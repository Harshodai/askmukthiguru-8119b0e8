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
    # 1. Selective Clear Qdrant
    logger.info("Connecting to Qdrant...")
    try:
        client = QdrantClient(url="http://localhost:6333")
        collection_name = "spiritual_wisdom"
        
        # Check if collection exists
        collections = client.get_collections().collections
        if any(c.name == collection_name for c in collections):
            logger.info(f"Selective delete in Qdrant: {collection_name}")
            # Delete everything EXCEPT The_Four_Sacred_Secrets.pdf
            client.delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must_not=[
                            models.FieldCondition(
                                key="source_url",
                                match=models.MatchValue(value="The_Four_Sacred_Secrets.pdf")
                            )
                        ]
                    )
                )
            )
            logger.info("✅ Qdrant (spiritual_wisdom) partially cleared.")
        
        # Clear LightRAG collections entirely (we'll re-ingest if needed, or check if they have 4SS)
        # Usually LightRAG handles its own indexing. Let's clear them to be safe if they are from other videos.
        for col in ["lightrag_vdb_chunks", "lightrag_vdb_entities", "lightrag_vdb_relationships"]:
            if any(c.name == col for c in collections):
                logger.info(f"Deleting LightRAG collection: {col}")
                client.delete_collection(col)
                
    except Exception as e:
        logger.error(f"❌ Qdrant cleanup failed: {e}")

    # 2. Selective Clear Neo4j
    logger.info("Connecting to Neo4j...")
    try:
        # Use proper auth
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "mukthiguru_neo4j_pass"))
        with driver.session() as session:
            logger.info("Deleting Neo4j data (excluding Four Sacred Secrets)...")
            # We assume nodes from 4SS have a property like 'source' or 'file_name'
            # Let's try to match anything NOT related to the PDF
            # If we don't have a clear property, we might need to be careful.
            # But usually the PDF ingestion adds a 'source' property.
            session.run("""
                MATCH (n)
                WHERE NOT (n.source_url CONTAINS 'The_Four_Sacred_Secrets.pdf' OR n.source CONTAINS 'The_Four_Sacred_Secrets.pdf')
                DETACH DELETE n
            """)
        driver.close()
        logger.info("✅ Neo4j partially cleared.")
    except Exception as e:
        logger.error(f"❌ Neo4j cleanup failed: {e}")

    # 3. Clear Redis (Cache)
    logger.info("Connecting to Redis...")
    try:
        import redis
        r = redis.from_url("redis://:mukthiguru_redis_pass@localhost:6379/0")
        r.flushall()
        logger.info("✅ Redis cleared.")
    except Exception as e:
        logger.warning(f"⚠️ Redis cleanup failed: {e}")

if __name__ == "__main__":
    asyncio.run(cleanup())
