"""
Seed personal knowledge graph data for the test user.
Creates User + GlobalMemory nodes in Neo4j with content that links to ontology concepts.
"""
from __future__ import annotations

import logging
import os

from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_personal_kg")

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# Test user ID that X-Test-Key auth resolves to
TEST_USER_ID = "00000000-0000-0000-0000-000000000000"

MEMORIES = [
    {
        "content": "I have been practicing Meditation daily for 3 years. It helps me find inner peace and connect with my true Self.",
        "keywords": ["meditation", "peace", "self"],
    },
    {
        "content": "The concept of Karma reminds me that every action has consequences. I strive to act with awareness and compassion.",
        "keywords": ["karma", "compassion", "awareness"],
    },
    {
        "content": "I am exploring what a Beautiful State means. Sri Preethaji teaches that it is a state of inner peace and connection with the divine.",
        "keywords": ["beautiful state", "preethaji", "inner peace"],
    },
    {
        "content": "Suffering arises from attachment to the ego. Through letting go and meditation, I am learning to transcend suffering.",
        "keywords": ["suffering", "ego", "meditation"],
    },
    {
        "content": "Dharma is my righteous duty. By following my dharma, I align my actions with the cosmic order.",
        "keywords": ["dharma", "duty"],
    },
    {
        "content": "Yoga helps me unite body, mind, and spirit. The physical postures prepare the body for deeper meditation.",
        "keywords": ["yoga", "meditation", "body"],
    },
    {
        "content": "Consciousness is the fundamental ground of all existence. Through awareness practices, I touch the timeless.",
        "keywords": ["consciousness", "awareness"],
    },
    {
        "content": "Sadhguru's teachings on inner engineering have transformed my understanding of life and well-being.",
        "keywords": ["sadhguru", "inner engineering"],
    },
    {
        "content": "The Serene Mind meditation practice helps me remain calm and centered even in difficult situations.",
        "keywords": ["serene mind", "meditation", "calm"],
    },
    {
        "content": "I feel overwhelmed by stress at work sometimes, but my spiritual practice gives me strength and perspective.",
        "keywords": ["stress", "overwhelmed", "meditation"],
    },
]


def seed():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        # Create User node
        session.run(
            """
            MERGE (u:User {id: $user_id})
            SET u.tenant_id = 'default', u.name = 'Test Seeker'
            """,
            user_id=TEST_USER_ID,
        )
        logger.info("Created/merged User node: %s", TEST_USER_ID)

        # Remove existing GlobalMemory nodes for this user (clean slate)
        session.run(
            "MATCH (u:User {id: $user_id})-[:HAS_MEMORY]->(m:GlobalMemory) DETACH DELETE m",
            user_id=TEST_USER_ID,
        )
        logger.info("Cleared existing memories for test user")

        # Create GlobalMemory nodes
        for i, mem in enumerate(MEMORIES):
            mem_id = f"seed:{TEST_USER_ID}:{i}"
            session.run(
                """
                MERGE (u:User {id: $user_id})
                CREATE (m:GlobalMemory {id: $mem_id, content: $content, created_at: timestamp(), tenant_id: 'default'})
                MERGE (u)-[:HAS_MEMORY]->(m)
                """,
                user_id=TEST_USER_ID,
                mem_id=mem_id,
                content=mem["content"],
            )
            logger.info("  Created memory %d: %s…", i, mem["content"][:50])

        # Verify
        result = session.run(
            "MATCH (u:User {id: $user_id})-[:HAS_MEMORY]->(m:GlobalMemory) RETURN count(m) AS cnt",
            user_id=TEST_USER_ID,
        )
        cnt = result.single()["cnt"]
        logger.info("Total memories for user: %d", cnt)

        # Show ontology concepts available for cross-reference
        result = session.run(
            "MATCH (c) WHERE c:Concept OR c:Teacher OR c:Practice RETURN c.entity_id AS eid LIMIT 20"
        )
        concepts = [r["eid"] for r in result]
        logger.info("Ontology concepts available: %s", concepts)

    driver.close()
    logger.info("Seed complete!")


if __name__ == "__main__":
    seed()
