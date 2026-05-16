import asyncio
import logging
from app.config import settings
from services.embedding_service import EmbeddingService
from services.cache_service import SemanticCacheAdapter

logging.basicConfig(level=logging.INFO)

async def test_semantic_cache():
    print("Initializing services for test...")
    embedder = EmbeddingService()
    cache = SemanticCacheAdapter(
        embedding_service=embedder,
        qdrant_url=settings.qdrant_url if not settings.qdrant_local_path else None,
        qdrant_path=settings.qdrant_local_path if settings.qdrant_local_path else None,
        redis_url=settings.redis_url
    )
    
    print("\n--- Testing Semantic Cache ---")
    query1 = "How do I find peace?"
    query2 = "What is the path to inner peace?"
    
    # Optional: Clear cache before test
    # cache.invalidate_all()
    
    print(f"\n1. First Query: '{query1}'")
    result = cache.get(query1)
    if result:
        print(f"FAILED: Expected Cache MISS, but got HIT!")
    else:
        print(f"SUCCESS: Cache MISS as expected.")
        print(f"Putting dummy response into cache for '{query1}'...")
        cache.put(
            query=query1,
            response="Inner peace is found through meditation and detachment.",
            intent="QUERY",
            citations=["dummy_source.pdf"],
            meditation_step=0
        )
        print("Done.")

    print(f"\n2. Second (Similar) Query: '{query2}'")
    print("Looking up cache...")
    result2 = cache.get(query2)
    if result2:
        print(f"SUCCESS: Cache HIT for similar query! Response: {result2['response']}")
    else:
        print(f"FAILED: Expected Cache HIT, but got MISS.")
        
    print(f"\nStats: {cache.stats}")

if __name__ == "__main__":
    asyncio.run(test_semantic_cache())
