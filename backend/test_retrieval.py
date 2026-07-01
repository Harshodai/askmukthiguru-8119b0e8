import asyncio
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.dependencies import get_container
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.schemas import ChatRequest, MessagePayload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_retrieval")

async def main():
    container = get_container()
    coordinator = PipelineCoordinator(container)

    question = "What is the Serene Mind practice and what are the detailed steps to practice it?"
    logger.info(f"Executing: {question}")
    
    # We want to trace what's in the state / context during pipeline execution
    result = await coordinator.execute(
        user_msg=question,
        preferred_lang="en",
        chat_body=ChatRequest(
            messages=[MessagePayload(role="user", content=question)],
            user_message=question,
        ),
        user=None,
        is_benchmark=True,
    )
    
    print("\n" + "="*80)
    print("RESULTS:")
    print("="*80)
    print(f"Intent          : {result.intent}")
    print(f"Route Decision  : {result.route_decision}")
    print(f"Cache Hit       : {result.cache_hit}")
    print(f"Citations       : {result.citations}")
    print(f"Response        :\n{result.final_answer}")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
