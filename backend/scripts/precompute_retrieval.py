"""Pre-compute retrieval results for hot doctrine topics.

Usage:
    cd backend && python scripts/precompute_retrieval.py

Stores topic -> top doc IDs in Redis so that `retrieve_documents`
can short-circuit for common spiritual queries.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime

# Add backend/ to the path so imports work when run as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger(__name__)

# Default hot topics — highly repetitive spiritual queries
DEFAULT_HOT_TOPICS = [
    "Beautiful State",
    "Soul Sync",
    "Sri Preethaji",
    "Sri Krishnaji",
    "Four Sacred Secrets",
    "Ekam",
    "Oneness",
    "Moksha",
    "Deeksha",
    "meditation",
    "spiritual awakening",
    "inner peace",
    "compassion",
    "consciousness",
    "suffering",
]


def _load_service_container():
    """Load the ServiceContainer (assumes dependencies.py is importable)."""
    try:
        from app.dependencies import ServiceContainer
        return ServiceContainer()
    except Exception as e:
        logger.error("Failed to initialize ServiceContainer: %s", e)
        raise


def _get_redis_client():
    """Try to get a Redis client for storing precomputed results."""
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        logger.warning("Redis unavailable, precomputed results will not be stored: %s", e)
        return None


async def precompute_topic(container, topic: str, redis_client, limit: int = 5) -> dict:
    """Precompute Qdrant search results for a single topic.

    Returns a dict with doc IDs and scores, stores in Redis.
    """
    try:
        # Use the embedding service to get a query vector
        query_vector = container.embedding.encode(topic)

        # Run Qdrant search
        results = container.qdrant.search(
            query_vector=query_vector,
            limit=limit,
            query=topic,
        )

        # Extract doc IDs and scores
        docs = [
            {
                "id": str(result.get("id", "")),
                "score": float(result.get("score", 0.0)),
                "title": str(result.get("payload", {}).get("title", "")),
            }
            for result in results
        ]

        payload = {
            "topic": topic,
            "timestamp": datetime.utcnow().isoformat(),
            "count": len(docs),
            "docs": docs,
        }

        # Store in Redis with 24-hour TTL
        if redis_client:
            key = f"precompute:{topic.lower().replace(' ', '_')}"
            redis_client.setex(key, 86400, json.dumps(payload))
            logger.info("Precomputed and cached '%s' (%d docs) -> %s", topic, len(docs), key)
        else:
            logger.info("Precomputed '%s' (%d docs) — Redis unavailable", topic, len(docs))

        return payload

    except Exception as e:
        logger.warning("Precompute failed for '%s': %s", topic, e)
        return {"topic": topic, "error": str(e)}


async def main(topics: list[str] | None = None) -> None:
    """Run precomputation for all hot topics."""
    logging.basicConfig(level=logging.INFO)

    topics = topics or DEFAULT_HOT_TOPICS
    logger.info("Starting precompute for %d topics", len(topics))

    container = _load_service_container()
    redis_client = _get_redis_client()

    results = {}
    for topic in topics:
        results[topic] = await precompute_topic(container, topic, redis_client)

    total_docs = sum(r.get("count", 0) for r in results.values() if "error" not in r)
    logger.info("Precompute complete: %d topics, %d total docs cached", len(topics), total_docs)

    return results


if __name__ == "__main__":
    asyncio.run(main())