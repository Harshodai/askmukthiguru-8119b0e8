"""Pre-populate cache with top FAQ questions on deploy."""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.config import settings
from app.dependencies import get_container
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.schemas import ChatRequest, MessagePayload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("warm_cache")

# Increase LLM timeout for batch warming to reduce transient Ollama timeouts
os.environ["LLM_TIMEOUT"] = "120"
os.environ["PIPELINE_TIMEOUT"] = "240"
settings.llm_timeout = 120
settings.pipeline_timeout = 240

TOP_FAQ_QUESTIONS = [
    "What is the Beautiful State?",
    "What are the Four Sacred Secrets?",
    "How do I practice Soul Sync?",
    "What is Deeksha?",
    "What is Serene Mind meditation?",
    "How can I find inner peace?",
    "What is the teaching of Oneness?",
    "Who are Sri Preethaji and Sri Krishnaji?",
    "What is Ekam?",
    "How do I receive Deeksha?",
    "What is the cause of suffering?",
    "How does meditation help in daily life?",
    "What are the different stages of consciousness?",
    "How can I practice mindfulness?",
    "What is the meaning of life?",
    "How do I overcome anxiety?",
    "What is the role of a spiritual teacher?",
    "How can I cultivate compassion?",
    "What is the goal of spiritual awakening?",
    "How do I meditate for beginners?",
]

# Concurrency limit to avoid choking Ollama
_WARM_CACHE_CONCURRENCY = 4


def create_dummy_chat_body(question: str) -> ChatRequest:
    return ChatRequest(
        messages=[
            MessagePayload(role="user", content=question)
        ],
        user_message=question,
        assistant_slug=None,
        knowledge_tags=[]
    )


async def _warm_single_question(
    coordinator: PipelineCoordinator, question: str, sem: asyncio.Semaphore
) -> tuple[str, bool, str]:
    """Warm a single question, respecting the concurrency semaphore."""
    async with sem:
        logger.info(f"[WARM START] '{question}'")
        try:
            result = await coordinator.execute(
                user_msg=question,
                preferred_lang="en",
                chat_body=create_dummy_chat_body(question),
                user=None,
                is_benchmark=True,
            )
            logger.info(
                f"[WARM DONE] '{question}' (intent={result.intent}, "
                f"route={result.route_decision}, cached={result.cache_hit})"
            )
            return question, True, ""
        except Exception as e:
            logger.warning(f"[WARM FAIL] '{question}': {e}")
            return question, False, str(e)


async def main():
    logger.info("Initializing ServiceContainer for cache warming...")
    try:
        container = get_container()
        coordinator = PipelineCoordinator(container)
    except Exception as e:
        logger.error(f"Failed to initialize container: {e}")
        return

    logger.info(f"Warming cache with {len(TOP_FAQ_QUESTIONS)} top FAQ questions...")

    # Batch-embed all questions upfront to prime the embedding cache
    try:
        embed_service = container.embedding
        all_texts = TOP_FAQ_QUESTIONS
        logger.info(f"Batch-embedding all {len(all_texts)} questions upfront...")
        embed_service.encode_batch(all_texts)
        logger.info("Batch embedding complete — subsequent pipeline calls will hit cache.")
    except Exception as e:
        logger.warning(f"Batch upfront embedding failed (non-critical): {e}")

    sem = asyncio.Semaphore(_WARM_CACHE_CONCURRENCY)
    tasks = [
        _warm_single_question(coordinator, q, sem)
        for q in TOP_FAQ_QUESTIONS
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = 0
    fail_count = 0
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"[WARM EXCEPTION] {r}")
            fail_count += 1
            continue
        _question, ok, _err = r
        if ok:
            success_count += 1
        else:
            fail_count += 1

    logger.info(
        f"Cache warming complete! Success: {success_count}/{len(TOP_FAQ_QUESTIONS)}, "
        f"Failed: {fail_count}/{len(TOP_FAQ_QUESTIONS)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
