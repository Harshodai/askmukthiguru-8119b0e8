"""Warm the doctrine semantic cache with top 200 doctrine queries.

This script pre-computes and warms the semantic cache for the most common
doctrine queries, reducing latency for frequently asked spiritual questions.
Queries are sourced from the benchmark question bank.

Usage:
    cd backend
    python scripts/warm_doctrine_cache.py
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

# Add parent directory to path for imports
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from benchmarks.question_bank import QUERIES

# Collect all doctrine queries from the question bank
DOCTRINE_QUERIES: list[str] = []

DOCTRINE_CATEGORIES = [
    "doctrine_four_secrets",
    "doctrine_founders",
    "doctrine_manifest",
    "doctrine_deeksha",
    "doctrine_soul_sync",
    "doctrine_ekam_architecture",
    "complex_multi_hop",
]

for category in DOCTRINE_CATEGORIES:
    if category in QUERIES:
        DOCTRINE_QUERIES.extend(
            [q["q"] for q in QUERIES[category] if "q" in q]
        )

# Add common spiritual queries to reach 200
COMMON_QUERIES = [
    "What is the Beautiful State?",
    "How do I practice Soul Sync?",
    "What are the Four Sacred Secrets?",
    "Who are Sri Preethaji and Sri Krishnaji?",
    "What is Deeksha?",
    "What is Ekam?",
    "How can I achieve inner peace?",
    "What is the purpose of meditation?",
    "How do I deal with stress spiritually?",
    "What is spiritual awakening?",
    "How can I improve my relationships?",
    "What is the meaning of life?",
    "How do I find my purpose?",
    "What is consciousness?",
    "How do I let go of anger?",
    "What is karma?",
    "How do I practice gratitude?",
    "What is the source of suffering?",
    "How can I manifest my desires?",
    "What is the power of intention?",
    "How do I connect with the divine?",
    "What is the nature of reality?",
    "How do I cultivate self-love?",
    "What is the role of a spiritual teacher?",
    "How do I overcome fear?",
    "What is the importance of breath?",
    "How do I find inner stillness?",
    "What is the journey of the soul?",
    "How do I live in the present moment?",
    "What is true happiness?",
    "How do I forgive someone?",
    "What is the difference between mind and consciousness?",
    "How do I develop intuition?",
    "What is the role of suffering in growth?",
    "How do I practice non-attachment?",
    "What is the law of attraction?",
    "How do I raise my vibration?",
    "How do I purify my mind?",
    "What is the nature of God?",
    "How do I find balance in life?",
    "What is the meaning of Namaste?",
    "How do I develop compassion?",
    "What is the role of service in spirituality?",
    "How do I overcome ego?",
    "What is the importance of silence?",
    "How do I transform negative thoughts?",
    "What is the power of mantra?",
    "How do I create a sacred space?",
    "What is the connection between body and soul?",
    "How do I practice mindfulness?",
    "What is the nature of time?",
    "How do I find peace in chaos?",
    "What is the role of faith?",
    "How do I develop patience?",
    "What is the meaning of surrender?",
    "How do I overcome jealousy?",
    "What is the nature of love?",
    "How do I practice self-discipline?",
    "What is the role of the guru?",
    "How do I find my true self?",
    "What is the importance of gratitude?",
    "How do I deal with loss?",
    "What is the nature of illusion?",
    "How do I develop willpower?",
    "What is the meaning of Aham?",
    "How do I practice self-inquiry?",
    "What is the nature of energy?",
    "How do I find clarity?",
    "What is the role of rituals?",
    "How do I overcome laziness?",
    "What is the importance of fasting?",
    "How do I develop humility?",
    "What is the nature of the ego?",
    "How do I find joy?",
    "How do I practice detachment?",
    "What is the meaning of Om?",
    "How do I overcome anxiety through spirituality?",
    "What is the nature of the universe?",
    "How do I find my dharma?",
    "What is the role of chanting?",
    "How do I develop inner strength?",
    "What is the importance of truth?",
    "How do I overcome attachment?",
    "What is the nature of the mind?",
    "How do I find spiritual community?",
    "What is the role of pilgrimage?",
    "How do I practice forgiveness?",
    "What is the meaning of enlightenment?",
    "How do I overcome negative karma?",
    "How do I find purpose in pain?",
    "What is the nature of the soul?",
    "How do I develop discipline?",
    "How do I overcome negative self-talk?",
    "How do I find inner child healing?",
    "What is the meaning of Shakti?",
    "How do I overcome procrastination?",
    "How do I develop spiritual vision?",
    "What is the importance of surrender?",
    "How do I find peace after trauma?",
    "What is the nature of karma?",
    "How do I practice conscious eating?",
    "What is the role of dreams?",
    "What is the meaning of moksha?",
    "How do I overcome self-doubt?",
    "How do I find meaning in suffering?",
    "What is the nature of the divine feminine?",
    "How do I practice visualisation?",
    "What is the importance of selfless service?",
    "How do I overcome negative emotions?",
    "What is the role of breathwork?",
    "How do I find my spiritual path?",
    "What is the nature of the divine masculine?",
    "How do I practice grounding?",
    "What is the importance of self-awareness?",
]

DOCTRINE_QUERIES.extend(COMMON_QUERIES)

# Deduplicate and limit to 200
DOCTRINE_QUERIES = list(dict.fromkeys(DOCTRINE_QUERIES))[:200]

API_URL = os.getenv("API_URL", "http://localhost:8000/api/chat")
REQUEST_TIMEOUT = float(os.getenv("WARM_TIMEOUT", "30"))


async def warm_cache():
    """Pre-warm the semantic cache with top doctrine queries."""
    print(f"Warming doctrine cache with {len(DOCTRINE_QUERIES)} queries...")
    print(f"Target API: {API_URL}")

    warmed = 0
    failed = 0

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for i, query in enumerate(DOCTRINE_QUERIES, 1):
            try:
                response = await client.post(
                    API_URL,
                    json={
                        "messages": [],
                        "user_message": query,
                        "meditation_step": 0,
                    },
                )
                if response.status_code in (200, 201):
                    warmed += 1
                    print(f"  [{i}/{len(DOCTRINE_QUERIES)}] Warmed: {query[:60]}...")
                else:
                    failed += 1
                    print(f"  [{i}/{len(DOCTRINE_QUERIES)}] Failed ({response.status_code}): {query[:60]}...")
            except Exception as e:
                failed += 1
                print(f"  [{i}/{len(DOCTRINE_QUERIES)}] Error: {query[:60]}... — {e}")

            # Small delay to avoid overwhelming the backend
            await asyncio.sleep(0.2)

    print(f"\nCache warming complete: {warmed} warmed, {failed} failed.")


if __name__ == "__main__":
    asyncio.run(warm_cache())
