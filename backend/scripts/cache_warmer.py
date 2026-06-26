#!/usr/bin/env python3
"""Cache Warmer — Pre-populates SemanticCacheAdapter with doctrine FAQs.

Warms the Qdrant+Redis semantic cache with 60+ canonical doctrine questions.
Uses the full RAG pipeline via TestClient so responses are identical to real
queries — semantic cache then serves them on future similar questions.

Run on startup or via cron:
    python scripts/cache_warmer.py                    # pipeline mode (default)
    python scripts/cache_warmer.py --mode direct      # direct embed+store
    python scripts/cache_warmer.py --mode pipeline --threshold 0.88
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

CACHE_WARMER_QUESTIONS = {
    "Four Sacred Secrets": [
        "What are the Four Sacred Secrets?",
        "Explain the Four Sacred Secrets of Preethaji and Krishnaji",
        "What is Spiritual Vision in the Four Sacred Secrets?",
        "What is Inner Truth in the Four Sacred Secrets?",
        "What is Universal Intelligence in the Four Sacred Secrets?",
        "What is Spiritual Right Action in the Four Sacred Secrets?",
        "How do the Four Sacred Secrets help with manifestation?",
        "Who created the Four Sacred Secrets?",
        "How to practice the Four Sacred Secrets daily?",
        "What is the difference between the Four Sacred Secrets and other teachings?",
    ],
    "Deeksha": [
        "What is Deeksha?",
        "What is Oneness Blessing?",
        "How does Deeksha affect the brain?",
        "What happens during a Deeksha transfer?",
        "Can anyone receive Deeksha?",
    ],
    "Soul Sync": [
        "What is Soul Sync meditation?",
        "How to do Soul Sync meditation?",
        "What are the 6 steps of Soul Sync?",
        "What is Aham in Soul Sync?",
        "How long is a Soul Sync session?",
    ],
    "Ekam": [
        "What is Ekam?",
        "Where is Ekam located?",
        "What happens at Ekam?",
        "Can I visit Ekam?",
    ],
    "Manifest 2026": [
        "What is Manifest 2026?",
        "What are the 12 Powers in Manifest 2026?",
        "How does Manifest 2026 work?",
    ],
    "Beautiful State": [
        "What is a Beautiful State?",
        "How to achieve a Beautiful State?",
        "What are the Beautiful State teachings?",
    ],
    "Founders": [
        "Who is Preethaji?",
        "Who is Krishnaji?",
        "Who are the founders of Ekam?",
        "What is O&O Academy?",
        "What is Lokaa Foundation?",
    ],
    "Meditation": [
        "How to meditate according to Preethaji?",
        "What is the role of breath in meditation?",
        "What is guided meditation in Ekam?",
    ],
}


class CacheWarmer:
    """Warms SemanticCacheAdapter with doctrine FAQs via the full pipeline."""

    def __init__(self, similarity_threshold: float = 0.90):
        self.similarity_threshold = similarity_threshold
        self._adapter = None
        self.stats = {"total": 0, "warmed": 0, "skipped": 0, "errors": 0}

    async def _init_adapter(self):
        """Initialize the SemanticCacheAdapter from the DI container."""
        from app.dependencies import get_container

        container = get_container()
        self._adapter = container.semantic_cache
        if not self._adapter or not self._adapter.is_available:
            logger.warning("Semantic cache adapter unavailable — warming will be skipped")
            self._adapter = None

    async def warm_direct(self) -> dict:
        """Direct mode: embed questions and store via SemanticCacheAdapter.put().

        This does NOT generate answers — it only pre-populates embeddings
        so that future similar queries get faster vector matches. Useful
        when the pipeline is not running.
        """
        if not self._adapter:
            await self._init_adapter()
        if not self._adapter:
            logger.error("No semantic cache adapter — cannot warm")
            return self.stats

        from services.embedding_service import EmbeddingService
        from app.dependencies import get_container

        container = get_container()
        embedder = container.embedding

        total_q = sum(len(v) for v in CACHE_WARMER_QUESTIONS.values())
        print(f"Direct warm: embedding {total_q} questions into semantic cache...")

        for category, questions in CACHE_WARMER_QUESTIONS.items():
            print(f"\n{category} ({len(questions)} questions)")
            for question in questions:
                self.stats["total"] += 1
                try:
                    # Check existing cache
                    cached = self._adapter.get(question)
                    if cached:
                        self.stats["skipped"] += 1
                        print(f"  SKIP (cached): {question[:60]}")
                        continue

                    # Store placeholder — the pipeline will fill the real answer
                    # on first real query. This pre-registers the embedding.
                    self._adapter.put(
                        query=question,
                        response=f"[cache-warmer placeholder for: {question}]",
                        intent="QUERY",
                        citations=[],
                        meditation_step=0,
                    )
                    self.stats["warmed"] += 1
                    print(f"  WARMED: {question[:60]}")
                except Exception as e:
                    self.stats["errors"] += 1
                    print(f"  ERROR: {question[:60]} — {e}")

        return self.stats

    async def warm_with_pipeline(self) -> dict:
        """Pipeline mode: hit /api/chat via TestClient so real RAG responses populate cache.

        This is the preferred mode — responses are identical to production queries
        and the pipeline_coordinator automatically writes to semantic cache on success.
        """
        print("Pipeline warm: hitting /api/chat with doctrine questions...")

        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        for category, questions in CACHE_WARMER_QUESTIONS.items():
            print(f"\n{category}")
            for question in questions:
                self.stats["total"] += 1
                try:
                    response = client.post(
                        "/api/chat",
                        json={"message": question},
                        timeout=120,
                    )
                    if response.status_code == 200:
                        self.stats["warmed"] += 1
                        print(f"  WARMED: {question[:60]}")
                    else:
                        self.stats["errors"] += 1
                        print(f"  ERROR ({response.status_code}): {question[:60]}")
                except Exception as e:
                    self.stats["errors"] += 1
                    print(f"  EXCEPTION: {question[:60]} — {e}")

        return self.stats


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Warm semantic cache with doctrine FAQs")
    parser.add_argument(
        "--mode",
        choices=["direct", "pipeline"],
        default="pipeline",
        help="Warming mode: direct (embed+store) or pipeline (full RAG via /api/chat)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.90,
        help="Similarity threshold for skipping already-cached entries",
    )
    args = parser.parse_args()

    warmer = CacheWarmer(similarity_threshold=args.threshold)

    try:
        if args.mode == "direct":
            stats = await warmer.warm_direct()
        else:
            stats = await warmer.warm_with_pipeline()
    except Exception as e:
        logger.error(f"Cache warming failed: {e}")
        raise

    print(f"\n{'='*50}")
    print("Cache Warming Complete")
    print(f"{'='*50}")
    print(f"Total Questions: {stats['total']}")
    print(f"Warmed: {stats['warmed']}")
    print(f"Skipped (already cached): {stats['skipped']}")
    print(f"Errors: {stats['errors']}")
    print(f"Success Rate: {stats['warmed'] / max(stats['total'], 1) * 100:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
