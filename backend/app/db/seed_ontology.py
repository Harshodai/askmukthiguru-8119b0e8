import asyncio
import logging
import os
from app.config import settings
from app.dependencies import get_container

logger = logging.getLogger(__name__)

def seed_spiritual_ontology():
    """
    Ensure Neo4j contains the default spiritual ontology (Teachers, Concepts, Practices, and Relationships).
    This function executes synchronously via executor or run_in_executor to avoid blocking event loops.
    Maps to both:
      - The custom ontology schema (e.g. :Teacher {name: 'Sadhguru'})
      - The LightRAG base schema (e.g. :base {entity_id: 'Sadhguru'})
    """
    if not settings.neo4j_uri:
        logger.info("seed_spiritual_ontology: Neo4j URI not configured; skipping.")
        return

    logger.info(f"seed_spiritual_ontology: Checking Neo4j connection at {settings.neo4j_uri}...")
    try:
        driver = get_container().neo4j_driver
        if driver is None:
            raise RuntimeError("Neo4j driver unavailable")

        # Verify connection
        driver.verify_connectivity()
        
        # 1. Run Schema Migrations (constraints) in a separate session
        def _migrations(tx):
            logger.info("seed_spiritual_ontology: Running Cypher schema migrations...")
            tx.run("CREATE CONSTRAINT UNIQUE_TEACHER_NAME IF NOT EXISTS FOR (t:Teacher) REQUIRE t.name IS UNIQUE")
            tx.run("CREATE CONSTRAINT UNIQUE_CONCEPT_NAME IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE")
            tx.run("CREATE CONSTRAINT UNIQUE_PRACTICE_NAME IF NOT EXISTS FOR (p:Practice) REQUIRE p.name IS UNIQUE")
            
        with driver.session() as session:
            session.execute_write(_migrations)

        def _seed(tx):
            logger.info("seed_spiritual_ontology: Seeding data...")
            # 2. Seed Teachers (with stable teacher_id for payload partitioning)
            tx.run("""
                MERGE (t:base {entity_id: 'Sadhguru'})
                SET t:Teacher:person, t.name = 'Sadhguru',
                    t.bio = 'Jaggi Vasudev, commonly known as Sadhguru, is an Indian yogi, mystic, and author.',
                    t.entity_type = 'person',
                    t.teacher_id = 'sadhguru'
            """)
            tx.run("""
                MERGE (t:base {entity_id: 'Sri Amma Bhagavan'})
                SET t:Teacher:organization, t.name = 'Sri Amma Bhagavan',
                    t.bio = 'Founders of the Oneness Movement, focusing on shifting consciousness from division to oneness.',
                    t.entity_type = 'organization',
                    t.teacher_id = 'amma_bhagavan'
            """)
            tx.run("""
                MERGE (t:base {entity_id: 'ISKCON'})
                SET t:Teacher:organization, t.name = 'ISKCON',
                    t.bio = 'International Society for Krishna Consciousness, teaching Bhakti Yoga and devotion to Lord Krishna.',
                    t.entity_type = 'organization',
                    t.teacher_id = 'iskcon'
            """)
            tx.run("""
                MERGE (t:base {entity_id: 'Sri Preethaji'})
                SET t:Teacher:person, t.name = 'Sri Preethaji',
                    t.bio = 'Co-founder of Ekam, teacher of the Beautiful State and dissolving suffering.',
                    t.entity_type = 'person',
                    t.teacher_id = 'preethaji'
            """)
            tx.run("""
                MERGE (t:base {entity_id: 'Sri Krishnaji'})
                SET t:Teacher:person, t.name = 'Sri Krishnaji',
                    t.bio = 'Co-founder of Ekam, teacher of the Beautiful State and ego observation.',
                    t.entity_type = 'person',
                    t.teacher_id = 'krishnaji'
            """)

            # 3. Seed Concepts
            tx.run("""
                MERGE (c:base {entity_id: 'Karma'})
                SET c:Concept, c.name = 'Karma',
                    c.description = 'Action, work, or deed; also refers to the spiritual principle of cause and effect.',
                    c.entity_type = 'concept'
            """)
            tx.run("""
                MERGE (c:base {entity_id: 'Dharma'})
                SET c:Concept, c.name = 'Dharma',
                    c.description = 'Righteous conduct, moral duty, or the natural order of life.',
                    c.entity_type = 'concept'
            """)
            tx.run("""
                MERGE (c:base {entity_id: 'Consciousness'})
                SET c:Concept, c.name = 'Consciousness',
                    c.description = 'The fundamental state of awareness and being.',
                    c.entity_type = 'concept'
            """)
            tx.run("""
                MERGE (c:base {entity_id: 'Beautiful State'})
                SET c:Concept, c.name = 'Beautiful State',
                    c.description = 'A state of connection, peace, and inner joy, free from suffering.',
                    c.entity_type = 'concept'
            """)
            tx.run("""
                MERGE (c:base {entity_id: 'Suffering'})
                SET c:Concept, c.name = 'Suffering',
                    c.description = 'A contracted state of division, fear, and ego-centric existence.',
                    c.entity_type = 'concept'
            """)
            tx.run("""
                MERGE (c:base {entity_id: 'Suffering State'})
                SET c:Concept, c.name = 'Suffering State',
                    c.description = 'A contracted state of division, fear, and ego-centric existence.',
                    c.entity_type = 'concept'
            """)
            tx.run("""
                MERGE (c:base {entity_id: 'Shrinking Self'})
                SET c:Concept, c.name = 'Shrinking Self',
                    c.description = 'An expression of the warring self characterized by comparison, inadequacy, and low self-esteem.',
                    c.entity_type = 'concept'
            """)
            tx.run("""
                MERGE (c:base {entity_id: 'Destructive Self'})
                SET c:Concept, c.name = 'Destructive Self',
                    c.description = 'An expression of the warring self characterized by anger, blame, aggression, and perfectionism.',
                    c.entity_type = 'concept'
            """)
            tx.run("""
                MERGE (c:base {entity_id: 'Inert Self'})
                SET c:Concept, c.name = 'Inert Self',
                    c.description = 'An expression of the warring self characterized by laziness, procrastination, and giving up.',
                    c.entity_type = 'concept'
            """)


            # 4. Seed Practices
            tx.run("""
                MERGE (p:base {entity_id: 'Meditation'})
                SET p:Practice, p.name = 'Meditation',
                    p.description = 'General practice of quiet observation and mindfulness.',
                    p.entity_type = 'practice'
            """)
            tx.run("""
                MERGE (p:base {entity_id: 'Yoga'})
                SET p:Practice, p.name = 'Yoga',
                    p.description = 'Physical and mental disciplines aligning body and mind.',
                    p.entity_type = 'practice'
            """)
            tx.run("""
                MERGE (p:base {entity_id: 'Serene Mind'})
                SET p:Practice, p.name = 'Serene Mind',
                    p.description = 'A 3-minute guided breathwork and meditation practice to calm the mind.',
                    p.entity_type = 'practice'
            """)
            tx.run("""
                MERGE (p:base {entity_id: 'Soul Sync'})
                SET p:Practice, p.name = 'Soul Sync',
                    p.description = 'A practice designed to shift the seeker into a state of oneness.',
                    p.entity_type = 'practice'
            """)

            # 5. Seed Relationships (Weaving the Teaching Graph)
            tx.run("""
                MATCH (t:base {entity_id: 'Sri Preethaji'}), (c:base {entity_id: 'Beautiful State'})
                MERGE (t)-[:EXPOUNDS]->(c)
            """)
            tx.run("""
                MATCH (t:base {entity_id: 'Sri Krishnaji'}), (c:base {entity_id: 'Beautiful State'})
                MERGE (t)-[:EXPOUNDS]->(c)
            """)
            tx.run("""
                MATCH (t:base {entity_id: 'Sadhguru'}), (c:base {entity_id: 'Karma'})
                MERGE (t)-[:EXPOUNDS]->(c)
            """)
            tx.run("""
                MATCH (t:base {entity_id: 'Sadhguru'}), (c:base {entity_id: 'Dharma'})
                MERGE (t)-[:EXPOUNDS]->(c)
            """)
            tx.run("""
                MATCH (t:base {entity_id: 'Sri Amma Bhagavan'}), (c:base {entity_id: 'Consciousness'})
                MERGE (t)-[:EXPOUNDS]->(c)
            """)
            tx.run("""
                MATCH (p:base {entity_id: 'Serene Mind'}), (c:base {entity_id: 'Beautiful State'})
                MERGE (p)-[:PRACTICE_FOR]->(c)
            """)
            tx.run("""
                MATCH (p:base {entity_id: 'Soul Sync'}), (c:base {entity_id: 'Beautiful State'})
                MERGE (p)-[:PRACTICE_FOR]->(c)
            """)
            tx.run("""
                MATCH (c1:base {entity_id: 'Suffering'}), (c2:base {entity_id: 'Beautiful State'})
                MERGE (c1)-[:CONTRASTS_WITH]->(c2)
            """)
            logger.info("seed_spiritual_ontology: Seeding completed successfully.")

        with driver.session() as session:
            session.execute_write(_seed)

        # Post-seeding: Run ontology alignment to link any existing extracted nodes
        align_extracted_ontology()
    except Exception as e:
        logger.error(f"seed_spiritual_ontology: Database seeding failed: {e}", exc_info=True)
        if getattr(settings, "is_production", False) or os.environ.get("ENV") == "production":
            raise RuntimeError(f"Neo4j ontology seeding failed in production: {e}")

def align_extracted_ontology():
    """
    Scans LightRAG-extracted generic nodes (:base) and aligns them with the seeded
    spiritual ontology (:Teacher, :Concept, :Practice) using DOCTRINE_SYNONYMS and aliases.
    """
    if not settings.neo4j_uri:
        logger.info("align_extracted_ontology: Neo4j not configured; skipping.")
        return

    logger.info("align_extracted_ontology: Aligning extracted graph nodes to spiritual ontology...")
    try:
        driver = get_container().neo4j_driver
        if driver is None:
            raise RuntimeError("Neo4j driver unavailable")

        def _align(tx):
            # 1. Map extracted person/organization nodes to Teacher nodes using synonyms
            teachers_synonyms = {
                "Sadhguru": ["sadhguru", "jaggi", "vasudev", "isha"],
                "Sri Amma Bhagavan": ["amma", "bhagavan", "amma bhagavan", "amma_bhagavan", "oneness", "kalki"],
                "ISKCON": ["iskcon", "prabhupada", "krishna consciousness", "hare krishna"],
                "Sri Preethaji": ["preethaji", "preetha", "sri preethaji"],
                "Sri Krishnaji": ["krishnaji", "sri krishnaji"]
            }
            
            for canonical, aliases in teachers_synonyms.items():
                # Establish/configure canonical node properties & labels
                tx.run("""
                    MERGE (n:base {entity_id: $canonical})
                    SET n:Teacher, n.name = $canonical
                """, canonical=canonical)
                
                # Relate other matching aliases to the canonical node
                tx.run("""
                    MATCH (n:base), (canonical:base {entity_id: $canonical})
                    WHERE n.entity_id IN $aliases AND n.entity_id <> $canonical
                    MERGE (n)-[:SYNONYMOUS_WITH]->(canonical)
                """, canonical=canonical, aliases=aliases)
                
            # 2. Map extracted nodes to Concepts using DOCTRINE_SYNONYMS
            from rag.nodes.utils import DOCTRINE_SYNONYMS
            for canonical, alternates in DOCTRINE_SYNONYMS.items():
                # Avoid mapping teachers as concepts
                if canonical in ["sri preethaji", "sri krishnaji", "sadhguru", "iskcon"]:
                    continue
                canonical_cap = canonical.title()
                
                # Establish/configure canonical node properties & labels
                tx.run("""
                    MERGE (n:base {entity_id: $canonical_cap})
                    SET n:Concept, n.name = $canonical_cap
                """, canonical_cap=canonical_cap)
                
                # Relate other matching aliases to the canonical node
                tx.run("""
                    MATCH (n:base), (canonical:base {entity_id: $canonical_cap})
                    WHERE (n.entity_id IN $alternates OR toLower(n.entity_id) = toLower($canonical))
                      AND n.entity_id <> $canonical_cap
                    MERGE (n)-[:SYNONYMOUS_WITH]->(canonical)
                """, canonical_cap=canonical_cap, alternates=alternates, canonical=canonical)
            
        with driver.session() as session:
            session.execute_write(_align)
        logger.info("align_extracted_ontology: Alignment completed successfully.")
    except Exception as e:
        logger.error(f"align_extracted_ontology: Alignment failed: {e}", exc_info=True)
