#!/usr/bin/env python3
"""
seed_neo4j_okf.py — One-shot seeder for the OKF 5-node Ontology in Neo4j.

Populates the following schema (used by GuruKGService.traverse_guru_ontology):
  (:SeekerDilemma)-[:DRIVEN_BY]->(:RootLimitingBelief)
  (:GuruTeaching)-[:DISMANTLES]->(:RootLimitingBelief)
  (:GuruTeaching)-[:TRANSFORMS_TO]->(:BeautifulState)
  (:GuruTeaching)-[:PRESCRIBES]->(:PracticeStep)
  (:GuruSpeaker)-[:TEACHES]->(:GuruTeaching)

Derived from Sri Krishnaji & Sri Preethaji approved teachings.
Uses MERGE — safe to re-run (idempotent).

Usage:
  cd backend
  .venv/bin/python scripts/seed_neo4j_okf.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]

# Load .env BEFORE importing any app modules so pydantic Settings can validate
env_path = backend_dir / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        pass

sys.path.insert(0, str(backend_dir))

from services.guru_brain.guru_kg_service import GuruKGService


# ── 20 curated OKF Transformation Arcs ────────────────────────────────────────
# Source: UlOt31lBhLY transcript (Marie Forleo interview) + Four Sacred Secrets doctrine
OKF_ARCS = [
    {
        "seeker_dilemma": "Experiencing anxiety, stress, or lack of peace",
        "limiting_belief": "Peace depends on external outcomes or controlling thoughts",
        "teaching": "Present Moment Awareness & Witnessing Consciousness",
        "target_state": "Beautiful State (Serene Mind)",
        "practice_step": "Observe thoughts as cloud formations passing across awareness without judgment",
        "guru": "Sri Preethaji & Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Chasing external success, wealth, or status for happiness",
        "limiting_belief": "Happiness is found in wealth, beauty, relationships, or external achievement",
        "teaching": "Mastering the Inner World before the Outer World",
        "target_state": "Beautiful State (Inner Fulfillment)",
        "practice_step": "First come to a state of joy and calm; from there, build your life, wealth, and success",
        "guru": "Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Carrying past regrets or worrying about the future",
        "limiting_belief": "I must resolve the past or secure the future to be at peace",
        "teaching": "Living in the Present Moment",
        "target_state": "Beautiful State (Present Aliveness)",
        "practice_step": "Drop what you are carrying. Like the monk who set the woman down — you still carry her.",
        "guru": "Sri Preethaji & Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Relationship conflict, feeling unseen or unvalued",
        "limiting_belief": "My peace depends on how others treat me",
        "teaching": "Inner World Independence from Outer World Triggers",
        "target_state": "Beautiful State (Equanimity)",
        "practice_step": "Witness the story your mind creates about the other; it is not the other, it is the story",
        "guru": "Sri Preethaji",
    },
    {
        "seeker_dilemma": "Fear of failure or not being enough",
        "limiting_belief": "I am not worthy unless I succeed, achieve, or am accepted",
        "teaching": "Transcending the Habitual Mind & Ego Identity",
        "target_state": "Beautiful State (Authentic Self)",
        "practice_step": "Observe the ego's fear without feeding it; you are the awareness behind the fear, not the fear itself",
        "guru": "Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Feeling disconnected from meaning or spiritual purpose",
        "limiting_belief": "Spiritual growth requires rituals, credentials, or external teachers",
        "teaching": "Transforming Consciousness from Within",
        "target_state": "Beautiful State (Oneness Consciousness)",
        "practice_step": "Connect to the divine by quieting the habitual mind and entering stillness",
        "guru": "Sri Preethaji & Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Overwhelm from work, responsibilities, and mental exhaustion",
        "limiting_belief": "Being busy and productive is the path to fulfillment",
        "teaching": "Acting from a Beautiful State vs Suffering State",
        "target_state": "Beautiful State (Purposeful Action)",
        "practice_step": "Pause. Ask: am I acting from fear and craving, or from calm and fulfillment? Then act.",
        "guru": "Sri Preethaji",
    },
    {
        "seeker_dilemma": "Grief, loss, or inability to let go",
        "limiting_belief": "Holding on keeps what I love alive; letting go means losing it",
        "teaching": "Witnessing Without Clinging",
        "target_state": "Beautiful State (Open Heart)",
        "practice_step": "Let the grief move through you like weather. You are the sky, not the storm.",
        "guru": "Sri Preethaji",
    },
    {
        "seeker_dilemma": "Anger, resentment, or chronic irritability",
        "limiting_belief": "My anger is justified and the other person must change for me to be at peace",
        "teaching": "Dismantling the Suffering State Reactivity Loop",
        "target_state": "Beautiful State (Inner Calm)",
        "practice_step": "Catch the moment the anger arises. Witness it. Ask: what story am I telling myself right now?",
        "guru": "Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Loneliness or feeling separate from others and the world",
        "limiting_belief": "I am fundamentally separate and must earn connection through performance",
        "teaching": "Oneness — Dissolving the Illusion of Separation",
        "target_state": "Beautiful State (Connectedness)",
        "practice_step": "In stillness, feel the aliveness beneath your thoughts — it is the same aliveness in all beings",
        "guru": "Sri Preethaji & Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Procrastination or inability to take decisive action",
        "limiting_belief": "I must feel ready, certain, or fearless before I can act",
        "teaching": "Action from a Beautiful State",
        "target_state": "Beautiful State (Courageous Presence)",
        "practice_step": "Act from this moment's calm, not from tomorrow's imagined certainty",
        "guru": "Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Anxiety about health, body, or physical wellbeing",
        "limiting_belief": "My body must be perfect for me to feel peace",
        "teaching": "Inner World Mastery Supports Outer World Health",
        "target_state": "Beautiful State (Body-Mind Harmony)",
        "practice_step": "Bring warmth and attention to the body without judgment; the healing state is a beautiful state",
        "guru": "Sri Preethaji",
    },
    {
        "seeker_dilemma": "Struggling to maintain spiritual practice amid daily life",
        "limiting_belief": "Spirituality is separate from ordinary life; I need more time",
        "teaching": "Living Spirituality in Every Moment",
        "target_state": "Beautiful State (Everyday Awakening)",
        "practice_step": "Each conversation, meal, and breath is an opportunity to choose your inner state",
        "guru": "Sri Preethaji & Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Envy or comparison to others' success",
        "limiting_belief": "Others' achievements diminish my worth",
        "teaching": "Inner Abundance vs Outer Comparison",
        "target_state": "Beautiful State (Inner Sufficiency)",
        "practice_step": "Recognize that jealousy is the habitual mind comparing stories; shift to witnessing the emotion",
        "guru": "Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Difficulty in relationships — communication breakdown",
        "limiting_belief": "The other person must change for our relationship to work",
        "teaching": "Beautiful State as the Foundation of Beautiful Relationships",
        "target_state": "Beautiful State (Compassionate Clarity)",
        "practice_step": "Before any difficult conversation, first establish your own inner calm; speak from there",
        "guru": "Sri Preethaji",
    },
    {
        "seeker_dilemma": "Feeling trapped in identity — who am I beyond my roles",
        "limiting_belief": "I am my job title, my family role, my nationality",
        "teaching": "Transcending Ego Identity into Witnessing Consciousness",
        "target_state": "Beautiful State (Pure Awareness)",
        "practice_step": "Ask not 'who am I' but 'what is aware of my thoughts right now'. Rest there.",
        "guru": "Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Chronic dissatisfaction — nothing feels enough",
        "limiting_belief": "Fulfillment exists in a future I haven't reached yet",
        "teaching": "State of Joy Exists Now — Not in Future Outcomes",
        "target_state": "Beautiful State (Present Fulfillment)",
        "practice_step": "This very moment — not the goal achieved — is where the beautiful state lives. Arrive here.",
        "guru": "Sri Preethaji & Sri Krishnaji",
    },
    {
        "seeker_dilemma": "Inability to forgive self or others",
        "limiting_belief": "Withholding forgiveness protects me or holds others accountable",
        "teaching": "Forgiveness as Liberation of the Inner World",
        "target_state": "Beautiful State (Lightness)",
        "practice_step": "Forgiveness is not condoning; it is setting down the weight you have been carrying",
        "guru": "Sri Preethaji",
    },
    {
        "seeker_dilemma": "Desire for deeper love and intimacy",
        "limiting_belief": "I can only receive love if I first give enough or become enough",
        "teaching": "Love Flows from Inner Fullness, Not Need",
        "target_state": "Beautiful State (Unconditional Love)",
        "practice_step": "First become full within. Love then flows naturally outward without grasping.",
        "guru": "Sri Preethaji",
    },
    {
        "seeker_dilemma": "Spiritual doubt or crisis of faith",
        "limiting_belief": "I must understand everything with my mind before I can trust",
        "teaching": "Consciousness Transforms Through Direct Experience, Not Intellectual Understanding",
        "target_state": "Beautiful State (Direct Knowing)",
        "practice_step": "Stop trying to think your way to peace. Be still and notice what is already here.",
        "guru": "Sri Krishnaji",
    },
]


def seed(neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> int:
    """Connect to Neo4j and seed all OKF arcs. Returns number seeded."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("❌ neo4j driver not installed. Run: pip install neo4j")
        return 0

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    kg = GuruKGService(neo4j_driver=driver)
    count = 0
    for arc in OKF_ARCS:
        try:
            kg.populate_ontology_arc(
                seeker_dilemma=arc["seeker_dilemma"],
                limiting_belief=arc["limiting_belief"],
                teaching=arc["teaching"],
                target_state=arc["target_state"],
                practice_step=arc["practice_step"],
                guru_speaker=arc["guru"],
            )
            count += 1
        except Exception as e:
            print(f"  ⚠️  Arc failed: {arc['teaching'][:50]} — {e}")

    driver.close()
    return count


if __name__ == "__main__":
    from app.config import settings

    neo4j_uri = settings.neo4j_uri
    neo4j_user = settings.neo4j_user
    neo4j_password = settings.neo4j_password

    if not neo4j_password:
        raise ValueError("NEO4J_PASSWORD environment variable or settings value is required.")

    print(f"🌱 Seeding OKF ontology into Neo4j at {neo4j_uri}...")
    n = seed(neo4j_uri, neo4j_user, neo4j_password)
    if n > 0:
        print(f"✅ Seeded {n}/{len(OKF_ARCS)} OKF transformation arcs into Neo4j.")
        print("   Labels created: SeekerDilemma, RootLimitingBelief, GuruTeaching, BeautifulState, PracticeStep, GuruSpeaker")
        print("   Relations: DRIVEN_BY, DISMANTLES, TRANSFORMS_TO, PRESCRIBES, TEACHES")
    else:
        print("❌ Seeding failed. Check Neo4j connection and credentials.")
