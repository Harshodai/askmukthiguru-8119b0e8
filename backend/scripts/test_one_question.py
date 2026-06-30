"""Quick test: warm cache for first FAQ question to verify fix."""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.dependencies import get_container
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.schemas import ChatRequest, MessagePayload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_one")

async def main():
    logger.info("Init container...")
    container = get_container()
    coordinator = PipelineCoordinator(container)

    question = "What is the Beautiful State?"
    logger.info(f"Executing: {question}")
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
    ans = result.final_answer[:300] if result.final_answer else "(empty)"
    logger.info(f"Result: intent={result.intent}, route={result.route_decision}, cached={result.cache_hit}")
    logger.info(f"Answer ({len(result.final_answer or '')} chars): {ans}...")

if __name__ == "__main__":
    asyncio.run(main())
