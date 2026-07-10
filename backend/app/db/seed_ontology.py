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
            teachers = [
                ("Sadhguru", "person", "sadhguru",
                 "Jaggi Vasudev, commonly known as Sadhguru, is an Indian yogi, mystic, and author. Founder of Isha Foundation."),
                ("Sri Amma Bhagavan", "organization", "amma_bhagavan",
                 "Founders of the Oneness Movement, focusing on shifting consciousness from division to oneness. Key teachers of Deeksha."),
                ("ISKCON", "organization", "iskcon",
                 "International Society for Krishna Consciousness, teaching Bhakti Yoga and devotion to Lord Krishna."),
                ("Sri Preethaji", "person", "preethaji",
                 "Co-founder of Ekam World Centre for Enlightenment. Teacher of the Beautiful State, dissolving suffering, and the Four Sacred Secrets."),
                ("Sri Krishnaji", "person", "krishnaji",
                 "Co-founder of Ekam World Centre for Enlightenment. Teacher of the Beautiful State, ego observation, and the science of inner transformation."),
                ("Ekam", "organization", "ekam",
                 "The World Centre for Enlightenment, co-founded by Sri Preethaji and Sri Krishnaji. Dedicated to shifting human consciousness from suffering to the beautiful state."),
                ("O&O Academy", "organization", "oo_academy",
                 "The O&O Academy co-founded by Sri Preethaji and Sri Krishnaji. Teaches the science of inner transformation and the beautiful state."),
                ("Mukthi Guru", "organization", "mukthi_guru",
                 "The platform and teaching lineage of Mukthi Guru, guided by Sri Preethaji and Sri Krishnaji. Focused on liberation (moksha) through the beautiful state."),
            ]

            for entity_id, entity_type, teacher_id, bio in teachers:
                label_type = "person" if entity_type == "person" else "organization"
                tx.run("""
                    MERGE (t:base {entity_id: $entity_id})
                    SET t:Teacher:$label_type, t.name = $entity_id,
                        t.bio = $bio,
                        t.entity_type = $entity_type,
                        t.teacher_id = $teacher_id
                """, entity_id=entity_id, label_type=label_type,
                     bio=bio, entity_type=entity_type, teacher_id=teacher_id)

            # 3. Seed Concepts — Core Teachings
            concepts = [
                # Vedantic / universal spiritual concepts
                ("Karma", "Action, work, or deed; the spiritual principle of cause and effect where every action creates consequences."),
                ("Dharma", "Righteous conduct, moral duty, or the natural order of life that upholds cosmic harmony."),
                ("Consciousness", "The fundamental state of awareness and being that underlies all existence."),
                ("Moksha", "Liberation from the cycle of suffering; the state of oneness with universal intelligence."),

                # Mukthi Guru core framework
                ("Beautiful State", "A state of connection, peace, and inner joy, free from suffering. Sri Preethaji teaches this is the only alternative to the stress state."),
                ("Suffering State", "A contracted state of division, fear, and obsessive self-centric thinking. The default human condition when not in the beautiful state."),
                ("Suffering", "A contracted state of division, fear, and ego-centric existence arising from obsessive self-centric thinking."),
                ("Universal Intelligence", "The divine field or cosmic consciousness that becomes accessible when one approaches with passion, stillness, and dedication."),
                ("Inner Stillness", "The foundational state of calm and presence that allows universal intelligence to flow. Prerequisite for spiritual awakening."),
                ("Self-Centric Thinking", "Obsessive, incessant preoccupation with oneself — the root cause of all emotional suffering, war, conflict, and division."),

                # The Warring Self — three expressions
                ("Warring Self", "The divided self that perpetually creates suffering through three expressions: shrinking, destructive, and inert."),
                ("Shrinking Self", "An expression of the warring self characterized by comparison, inadequacy, and low self-esteem."),
                ("Destructive Self", "An expression of the warring self characterized by anger, blame, aggression, and perfectionism."),
                ("Inert Self", "An expression of the warring self characterized by laziness, procrastination, and giving up."),

                # Deeksha / Oneness Blessing
                ("Deeksha", "The Oneness Blessing — a sacred energy transmission from guru to seeker that facilitates spiritual awakening and clears karmic blocks."),
                ("Ekam", "The World Centre for Enlightenment founded by Sri Preethaji and Sri Krishnaji, dedicated to shifting human consciousness from division to oneness."),
                ("Oneness", "The state of unity consciousness where the sense of separation dissolves. Also called non-duality or advaita."),

                # The Four Sacred Secrets
                ("Four Sacred Secrets", "Four transformative teachings revealed by Sri Preethaji and Sri Krishnaji: Live with a Spiritual Vision, The Science of Purification, See the Truth of Suffering, Dissolve into the Beautiful State."),
                ("Spiritual Vision", "The first sacred secret — living with a vision beyond material life, seeing the divine purpose in all experiences."),
                ("Science of Purification", "The second sacred secret — the process of purifying the mind and heart through awareness and practice."),
                ("Truth of Suffering", "The third sacred secret — seeing clearly that all suffering arises from self-centric thinking and the warring self."),
                ("Dissolving into the Beautiful State", "The fourth sacred secret — complete surrender into the state of connection, peace, and inner joy."),

                # Heart / Awakening
                ("Heart Awakening", "The shift from living in the mind (thought, analysis, self-centric thinking) to living in the heart (feeling, connection, intuition)."),
                ("Heart Explosion", "A sudden, profound opening of the heart center experienced in deep meditation or through the grace of the guru. Gateway to manifesting divine blessings."),
                ("Compassion", "The natural state of the awakened heart — feeling deeply connected to others, transcending the sense of separation."),
                ("Intuition", "Heart-based knowing that transcends intellectual analysis. Awakened when one enters the beautiful state."),

                # Spiritual Processes
                ("Awakening", "The shift from the suffering state to the beautiful state. A gradual or sudden realization of one's true nature beyond the warring self."),
                ("Grace", "Divine assistance that flows when one surrenders the ego and opens to universal intelligence."),
                ("Surrender", "The conscious letting go of control, resistance, and self-centric thinking. The gateway to grace and transformation."),
                ("Presence", "Being fully in the present moment, free from regrets about the past and anxiety about the future."),
                ("Inner Truth", "The truth that reveals itself through inner stillness and presence, beyond what the mind can conceptualize."),
                ("Collective Meditation", "Group spiritual practice in which the shared intention and consciousness amplify individual practice, creating a powerful field of transformation."),

                # Manifestation & Life
                ("Divine Manifest", "The aspect of the divine that takes form — the universe, nature, and all creation as an expression of universal intelligence."),
                ("Divine Unmanifest", "The formless, transcendent aspect of the divine — pure consciousness beyond all attributes and forms."),
                ("Synchronicity", "Meaningful coincidences that arise when one is aligned with universal intelligence. A sign of being in the beautiful state."),
                ("Prosperity", "Natural flow of abundance that arises when one lives from the beautiful state. Includes material, emotional, and spiritual well-being."),
                ("Karmic Clearing", "The process of releasing accumulated karmic debt through awakening, awareness, and breaking free from the thinking that created the karma in the first place."),

                # Practices & Tools
                ("Soul Sync", "A practice designed to shift the seeker into a state of oneness through synchronized breath and awareness."),
                ("Serene Mind", "A 3-minute guided breathwork and meditation practice to calm the mind and return to the beautiful state."),
                ("Three Questions", "A framework for self-inquiry: What is my state? What time is it (past/present/future)? Who am I beyond the warring self?"),
                ("Serene Mind Flame", "A flame visualized at the eyebrow center during the Serene Mind practice, representing the light of consciousness."),
            ]

            for entity_id, description in concepts:
                tx.run("""
                    MERGE (c:base {entity_id: $entity_id})
                    SET c:Concept, c.name = $entity_id,
                        c.description = $description,
                        c.entity_type = 'concept'
                """, entity_id=entity_id, description=description)


            # 4. Seed Practices
            practices = [
                ("Meditation", "General practice of quiet observation and mindfulness. The foundation of all spiritual practice."),
                ("Yoga", "Physical and mental disciplines aligning body and mind, preparing the practitioner for deeper spiritual experience."),
                ("Serene Mind", "A 3-minute guided breathwork and meditation practice to calm the mind. Involves breath awareness, emotional release, and visualizing a flame at the eyebrow center."),
                ("Soul Sync", "A practice designed to shift the seeker into a state of oneness through synchronized breath and heart-centered awareness."),
                ("Three Question Meditation", "A self-inquiry meditation asking: What is my state? What time is it? Who am I? Designed to return the practitioner to the beautiful state."),
                ("Inner Stillness Practice", "The foundational practice of sitting in quiet presence, allowing universal intelligence to flow through the still mind."),
                ("Collective Meditation Practice", "Group meditation where shared intention and collective consciousness amplify the transformative power of individual practice."),
                ("Kriya Practice", "Sacred spiritual actions and purificatory practices that accelerate inner transformation and karmic clearing."),
                ("Heart Awakening Practice", "A practice focused on opening the heart center, moving awareness from the thinking mind to the feeling heart."),
                ("Four Sacred Secrets Practice", "Working systematically with the four sacred secrets as a complete spiritual framework for transformation."),
            ]

            for entity_id, description in practices:
                tx.run("""
                    MERGE (p:base {entity_id: $entity_id})
                    SET p:Practice, p.name = $entity_id,
                        p.description = $description,
                        p.entity_type = 'practice'
                """, entity_id=entity_id, description=description)

            # 5. Seed Relationships (Weaving the Teaching Graph)
            # Teacher → Concept (EXPOUNDS)
            expounds = [
                ("Sri Preethaji", "Beautiful State"),
                ("Sri Preethaji", "Four Sacred Secrets"),
                ("Sri Preethaji", "Heart Awakening"),
                ("Sri Preethaji", "Compassion"),
                ("Sri Preethaji", "Oneness"),
                ("Sri Preethaji", "Deeksha"),
                ("Sri Krishnaji", "Beautiful State"),
                ("Sri Krishnaji", "Self-Centric Thinking"),
                ("Sri Krishnaji", "Warring Self"),
                ("Sri Krishnaji", "Inner Stillness"),
                ("Sri Krishnaji", "Dissolving into the Beautiful State"),
                ("Ekam", "Beautiful State"),
                ("Ekam", "Oneness"),
                ("Ekam", "Deeksha"),
                ("Ekam", "Awakening"),
                ("Sadhguru", "Karma"),
                ("Sadhguru", "Dharma"),
                ("Sadhguru", "Consciousness"),
                ("Sadhguru", "Meditation"),
                ("Sadhguru", "Yoga"),
                ("Sri Amma Bhagavan", "Consciousness"),
                ("Sri Amma Bhagavan", "Deeksha"),
                ("Sri Amma Bhagavan", "Oneness"),
                ("Sri Amma Bhagavan", "Awakening"),
                ("O&O Academy", "Beautiful State"),
                ("O&O Academy", "Four Sacred Secrets"),
                ("O&O Academy", "Heart Awakening"),
                ("Mukthi Guru", "Moksha"),
                ("Mukthi Guru", "Awakening"),
                ("Mukthi Guru", "Beautiful State"),
            ]
            for t_name, c_name in expounds:
                tx.run("""
                    MATCH (t:base {entity_id: $t_name})
                    MATCH (c:base {entity_id: $c_name})
                    MERGE (t)-[:EXPOUNDS]->(c)
                """, t_name=t_name, c_name=c_name)

            # Practice → Concept (PRACTICE_FOR)
            practices_for = [
                ("Serene Mind", "Beautiful State"),
                ("Serene Mind", "Inner Stillness"),
                ("Soul Sync", "Oneness"),
                ("Soul Sync", "Beautiful State"),
                ("Three Question Meditation", "Beautiful State"),
                ("Three Question Meditation", "Self-Centric Thinking"),
                ("Three Question Meditation", "Awakening"),
                ("Inner Stillness Practice", "Inner Stillness"),
                ("Inner Stillness Practice", "Beautiful State"),
                ("Collective Meditation Practice", "Collective Meditation"),
                ("Collective Meditation Practice", "Oneness"),
                ("Kriya Practice", "Karmic Clearing"),
                ("Kriya Practice", "Beautiful State"),
                ("Heart Awakening Practice", "Heart Awakening"),
                ("Heart Awakening Practice", "Compassion"),
                ("Four Sacred Secrets Practice", "Four Sacred Secrets"),
                ("Four Sacred Secrets Practice", "Beautiful State"),
                ("Meditation", "Awakening"),
                ("Meditation", "Consciousness"),
                ("Meditation", "Inner Stillness"),
                ("Yoga", "Dharma"),
                ("Yoga", "Consciousness"),
            ]
            for p_name, c_name in practices_for:
                tx.run("""
                    MATCH (p:base {entity_id: $p_name})
                    MATCH (c:base {entity_id: $c_name})
                    MERGE (p)-[:PRACTICE_FOR]->(c)
                """, p_name=p_name, c_name=c_name)

            # Concept → Concept relationships
            concept_rels = [
                ("Suffering State", "Beautiful State", "CONTRASTS_WITH"),
                ("Suffering", "Beautiful State", "CONTRASTS_WITH"),
                ("Self-Centric Thinking", "Suffering State", "CAUSES"),
                ("Self-Centric Thinking", "Suffering", "CAUSES"),
                ("Warring Self", "Self-Centric Thinking", "MANIFESTS_AS"),
                ("Shrinking Self", "Warring Self", "EXPRESSION_OF"),
                ("Destructive Self", "Warring Self", "EXPRESSION_OF"),
                ("Inert Self", "Warring Self", "EXPRESSION_OF"),
                ("Inner Stillness", "Beautiful State", "PREREQUISITE_FOR"),
                ("Inner Stillness", "Awakening", "PREREQUISITE_FOR"),
                ("Beautiful State", "Awakening", "LEADS_TO"),
                ("Beautiful State", "Compassion", "LEADS_TO"),
                ("Beautiful State", "Synchronicity", "LEADS_TO"),
                ("Beautiful State", "Prosperity", "LEADS_TO"),
                ("Heart Awakening", "Compassion", "LEADS_TO"),
                ("Heart Awakening", "Intuition", "LEADS_TO"),
                ("Surrender", "Grace", "LEADS_TO"),
                ("Grace", "Awakening", "LEADS_TO"),
                ("Deeksha", "Awakening", "LEADS_TO"),
                ("Deeksha", "Karmic Clearing", "LEADS_TO"),
                ("Awakening", "Moksha", "LEADS_TO"),
                ("Oneness", "Moksha", "LEADS_TO"),
                ("Universal Intelligence", "Oneness", "REVEALS"),
                ("Universal Intelligence", "Divine Manifest", "EXPRESSES_AS"),
                ("Universal Intelligence", "Divine Unmanifest", "EXPRESSES_AS"),
                ("Karmic Clearing", "Moksha", "PREREQUISITE_FOR"),
                ("Spiritual Vision", "Four Sacred Secrets", "COMPONENT_OF"),
                ("Science of Purification", "Four Sacred Secrets", "COMPONENT_OF"),
                ("Truth of Suffering", "Four Sacred Secrets", "COMPONENT_OF"),
                ("Dissolving into the Beautiful State", "Four Sacred Secrets", "COMPONENT_OF"),
                ("Collective Meditation", "Oneness", "AMPLIFIES"),
                ("Presence", "Inner Stillness", "REINFORCES"),
                ("Inner Truth", "Beautiful State", "REVEALS"),
            ]
            for c1_name, c2_name, rel_type in concept_rels:
                tx.run(f"""
                    MATCH (c1:base {{entity_id: $c1_name}})
                    MATCH (c2:base {{entity_id: $c2_name}})
                    MERGE (c1)-[:{rel_type}]->(c2)
                """, c1_name=c1_name, c2_name=c2_name)
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
                "Sadhguru": ["sadhguru", "jaggi", "vasudev", "isha foundation", "yogi mystic"],
                "Sri Amma Bhagavan": ["amma", "bhagavan", "amma bhagavan", "amma_bhagavan", "oneness movement", "kalki bhagavan"],
                "ISKCON": ["iskcon", "prabhupada", "krishna consciousness", "hare krishna", "swami prabhupada"],
                "Sri Preethaji": ["preethaji", "preetha", "sri preethaji", "preetha ji", "sreepreethaji"],
                "Sri Krishnaji": ["krishnaji", "sri krishnaji", "krishna ji", "sreekrishnaji", "krishnaji mukthi"],
                "Ekam": ["ekam", "ekam world", "world centre for enlightenment", "world center for enlightenment", "ekam foundation"],
                "O&O Academy": ["o and o academy", "oo academy", "oando academy", "o & o academy"],
                "Mukthi Guru": ["mukthi guru", "mukthiguru", "mukti guru", "mukti"],
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
