#!/usr/bin/env python3
"""Cache Warmer - Pre-populates GPTCache with doctrine FAQs.

Warms the semantic cache with 60+ canonical doctrine questions across 9 categories.
Run on startup or via cron to ensure fast responses for common queries.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.cache_service import CacheService

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
    """Warms GPTCache with doctrine FAQs."""
    
    def __init__(self, similarity_threshold: float = 0.90):
        self.similarity_threshold = similarity_threshold
        self.cache_service: Optional[CacheService] = None
        self.stats = {"total": 0, "warmed": 0, "skipped": 0, "errors": 0}
    
    async def initialize(self):
        """Initialize cache service."""
        self.cache_service = CacheService()
        await self.cache_service.initialize()
    
    async def warm_cache(self) -> dict:
        """Warm cache with all doctrine questions."""
        if not self.cache_service:
            await self.initialize()
        
        print(f"Starting cache warming with {sum(len(v) for v in CACHE_WARMER_QUESTIONS.values())} questions...")
        
        for category, questions in CACHE_WARMER_QUESTIONS.items():
            print(f"\nWarming category: {category} ({len(questions)} questions)")
            for question in questions:
                self.stats["total"] += 1
                try:
                    await self._warm_question(question, category)
                except Exception as e:
                    self.stats["errors"] += 1
                    print(f"  ERROR: {question} - {e}")
        
        return self.stats
    
    async def _warm_question(self, question: str, category: str):
        """Warm a single question into cache."""
        # Check if already cached with high similarity
        cached = await self.cache_service.get(question)
        if cached and cached.get("similarity", 0) >= self.similarity_threshold:
            self.stats["skipped"] += 1
            print(f"  SKIP (cached): {question[:60]}...")
            return

        # Generate answer using the full pipeline to populate cache
        from services.llm_service import LLMService

        llm = LLMService()
        answer = await llm.generate(question)

        await self.cache_service.set(question, answer)
        self.stats["warmed"] += 1
        print(f"  WARMED: {question[:60]}...")
    
    async def warm_with_real_pipeline(self) -> dict:
        """Warm cache using the actual orchestrator pipeline."""
        if not self.cache_service:
            await self.initialize()
        
        print("Warming cache with real orchestrator pipeline...")
        
        # Import here to avoid circular imports
        from fastapi.testclient import TestClient

        from app.main import app
        
        client = TestClient(app)
        
        for category, questions in CACHE_WARMER_QUESTIONS.items():
            print(f"\nWarming category: {category}")
            for question in questions:
                self.stats["total"] += 1
                try:
                    response = client.post("/api/chat", json={"message": question})
                    if response.status_code == 200:
                        self.stats["warmed"] += 1
                        print(f"  WARMED: {question[:60]}...")
                    else:
                        self.stats["errors"] += 1
                        print(f"  ERROR ({response.status_code}): {question[:60]}...")
                except Exception as e:
                    self.stats["errors"] += 1
                    print(f"  EXCEPTION: {question[:60]}... - {e}")
        
        return self.stats
    
    async def close(self):
        """Close cache service."""
        if self.cache_service:
            await self.cache_service.close()


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Warm GPTCache with doctrine FAQs")
    parser.add_argument("--mode", choices=["direct", "pipeline"], default="pipeline",
                        help="Warming mode: direct (bypass) or pipeline (full)")
    parser.add_argument("--threshold", type=float, default=0.90,
                        help="Similarity threshold for skipping cached entries")
    args = parser.parse_args()
    
    warmer = CacheWarmer(similarity_threshold=args.threshold)
    
    try:
        if args.mode == "direct":
            stats = await warmer.warm_cache()
        else:
            stats = await warmer.warm_with_real_pipeline()
    finally:
        await warmer.close()
    
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