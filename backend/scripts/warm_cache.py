"""Pre-populate cache with top FAQ questions on deploy."""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.dependencies import ServiceContainer
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.schemas import ChatRequest, ChatMessage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("warm_cache")

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

def create_dummy_chat_body(question: str) -> ChatRequest:
    return ChatRequest(
        messages=[
            ChatMessage(role="user", content=question)
        ],
        assistant_slug=None,
        knowledge_tags=[]
    )

async def main():
    logger.info("Initializing ServiceContainer for cache warming...")
    try:
        container = ServiceContainer()
        coordinator = PipelineCoordinator(container)
    except Exception as e:
        logger.error(f"Failed to initialize container: {e}")
        return

    logger.info(f"Warming cache with {len(TOP_FAQ_QUESTIONS)} top FAQ questions...")
    for question in TOP_FAQ_QUESTIONS:
        try:
            # We call execute. It will perform intent classification, retrieval, etc., and write to cache
            result = await coordinator.execute(
                user_msg=question,
                preferred_lang="en",
                chat_body=create_dummy_chat_body(question),
                user=None,
                is_benchmark=True,  # Bypasses normal user constraints / limits if any
            )
            logger.info(f"Warmed: '{question}' (intent={result.intent}, route={result.route_decision}, cached={result.cache_hit})")
        except Exception as e:
            logger.warning(f"Failed to warm '{question}': {e}")
            
    logger.info("Cache warming complete!")

if __name__ == "__main__":
    asyncio.run(main())
