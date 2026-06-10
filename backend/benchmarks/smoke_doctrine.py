#!/usr/bin/env python3
"""
smoke_doctrine.py — Micro-benchmark to verify that E5 queries retrieve 
the core doctrine documents ("Deeksha", "Sri Preethaji and Sri Krishnaji", "Ekam")
using dense search fallback (with Issue B fix applied).
"""

import asyncio
import sys
import time
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.config import settings
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService


async def main():
    print("\n" + "=" * 60)
    print("MUKTHI GURU: SMOKE DOCTRINE RETRIEVAL BENCHMARK")
    print("=" * 60 + "\n")

    try:
        embedder = EmbeddingService()
        qdrant = QdrantService()
    except Exception as e:
        print(f"❌ Could not initialize services: {e}")
        print("Please make sure Qdrant is running.")
        sys.exit(1)

    queries = [
        {
            "q": "What is Deeksha?",
            "keywords": ["deeksha", "diksha", "initiation", "spiritual", "consciousness", "divine"],
        },
        {
            "q": "Who are Sri Preethaji and Sri Krishnaji?",
            "keywords": ["preethaji", "krishnaji", "founders", "one world academy", "ekam", "teachers"],
        },
        {
            "q": "Where is Ekam?",
            "keywords": ["ekam", "temple", "oneness", "tirupati", "mountains", "chennai"],
        }
    ]

    success = True
    for item in queries:
        query = item["q"]
        keywords = item["keywords"]
        print(f"Querying: \"{query}\"")
        start = time.perf_counter()

        # Generate embeddings (E5 will generate dense vector, and empty sparse dict)
        enc = await asyncio.to_thread(embedder.encode_single_full, query)
        
        # Verify Issue B: sparse dict should be empty when using non-BGE model
        is_bge = settings.embedding_model == "BAAI/bge-m3"
        if not is_bge:
            if enc["sparse"] != {}:
                print(f"❌ Issue B Regressed: Sparse vector is not empty! Got: {enc['sparse']}")
                success = False
            else:
                print("✅ Issue B Verified: Sparse vector is empty (bypassed random sparse weights).")

        # Perform Search
        docs = await asyncio.to_thread(
            qdrant.search,
            query_vector=enc["dense"],
            limit=5,
            sparse_vector=enc["sparse"],
            query=query
        )

        duration = time.perf_counter() - start
        print(f"Search completed in {duration:.4f}s. Retrieved {len(docs)} documents.")

        if not docs:
            print("❌ Failure: No documents retrieved!")
            success = False
            continue

        # Check for keyword matches in top retrieved documents to verify accuracy
        matched_keywords = []
        combined_text = "\n".join([d["text"].lower() for d in docs])
        for kw in keywords:
            if kw.lower() in combined_text:
                matched_keywords.append(kw)

        kw_ratio = len(matched_keywords) / len(keywords)
        print(f"Keyword matches: {matched_keywords} ({len(matched_keywords)}/{len(keywords)})")
        
        if kw_ratio >= 0.5:
            print(f"✅ Success: Query retrieved relevant spiritual context (score={docs[0]['score']:.4f})")
        else:
            print(f"❌ Failure: Retrieved documents do not seem relevant (score={docs[0]['score']:.4f})")
            print("Retrieved texts:")
            for i, d in enumerate(docs):
                print(f"  [{i}] Level {d.get('raptor_level')} (Score {d['score']:.4f}): {d['text'][:300]}...")
            success = False
        print("-" * 60)

    if success:
        print("\n🎉 SMOKE DOCTRINE RETRIEVAL PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print("\n❌ SMOKE DOCTRINE RETRIEVAL FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
