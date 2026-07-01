import asyncio
import logging
import sys
from pathlib import Path
import redis
import json

sys.path.append(str(Path(__file__).parent.parent))

from app.dependencies import get_container
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import PipelineContext, StageRunner, build_default_pipeline
from app.schemas import ChatRequest, MessagePayload
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_retrieval")

async def main():
    # Disable cache to force retrieval and generation
    settings.cache_mode = "none"
    settings.semantic_cache_enabled = False
    settings.rag_okf_injection_enabled = True
    
    container = get_container()
    
    # Flush Redis cache
    redis_client = redis.from_url(settings.redis_url)
    redis_client.flushall()
    logger.info("Redis cache flushed successfully")

    coordinator = PipelineCoordinator(container)

    question = "What is the Serene Mind practice and what are the detailed steps to practice it?"
    logger.info(f"Executing: {question}")
    
    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=ChatRequest(
            messages=[MessagePayload(role="user", content=question)],
            user_message=question,
        ),
        user_msg=question,
        preferred_lang="en",
        is_benchmark=True,
    )
    
    await StageRunner.run(build_default_pipeline(), ctx, coordinator=coordinator)
    
    print("\n" + "="*80)
    print("RESULTS:")
    print("="*80)
    print(f"Intent          : {ctx.intent}")
    print(f"Citations       : {ctx.citations}")
    print(f"Response        :\n{ctx.final_answer}")
    
    print("\n" + "="*80)
    print("GRAPH RESULT KEYS:")
    print("="*80)
    if ctx.graph_result:
        for k, v in ctx.graph_result.items():
            if k == "documents":
                print(f"Documents count: {len(v)}")
                for idx, doc in enumerate(v):
                    print(f"\nDocument {idx+1}:")
                    # Try to print document attributes or dict
                    if hasattr(doc, "page_content"):
                        print(f"Source: {getattr(doc, 'metadata', {}).get('source')}")
                        print(f"Content: {doc.page_content[:300]}...")
                    else:
                        print(doc)
            else:
                # print other key types/lengths
                print(f"{k}: {type(v)}")
    else:
        print("No graph_result in context")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
