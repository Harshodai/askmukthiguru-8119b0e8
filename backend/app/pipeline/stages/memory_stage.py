"""Memory stage — save conversation memory asynchronously.

Body extracted verbatim from PipelineCoordinator._save_memory. Never
short-circuits; fire-and-forget. This stage is the Wave 3 extension point
(episodic + OKF memory will hook in here).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.config import settings

from app.pipeline.stages.base import Stage
from app.pipeline.result import PipelineResult  # noqa: F401

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


class MemoryStage(Stage):
    """Persist conversation memory (user_profile + memory_service). Never short-circuits."""

    name = "memory_save"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        # ponytail: body of _save_memory verbatim (self -> ctx.container)
        container = ctx.container
        user_id = ctx.user_id
        stable_session_id = ctx.stable_session_id
        chat_body_messages = ctx.chat_body_messages
        user_msg = ctx.user_msg
        final_answer = ctx.final_answer
        intent = ctx.intent
        med_step = ctx.med_step
        citations = ctx.citations
        distress_level = ctx.assessment.level.value if ctx.assessment else 0

        if not container.user_profile:
            return None
        try:
            from services.user_profile_service import ConversationMemory

            memory = ConversationMemory(
                session_id=stable_session_id,
                user_id=user_id,
                started_at=time.time(),
                messages=[
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": final_answer},
                ],
                key_insights=[c if isinstance(c, str) else c.get("title", "") for c in citations],
                emotional_arc=[
                    {
                        "timestamp": time.time(),
                        "distress_level": distress_level,
                        "provoked": False,
                        "topic": intent,
                    }
                ],
                follow_up_suggestions=[],
            )
            await container.user_profile.save_conversation_memory(memory)
        except Exception as e:
            logger.warning(f"Memory save failed (non-fatal): {e}")

        if settings.feature_memory_write and getattr(container, "memory_service", None):
            full_msgs = chat_body_messages + [
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": final_answer},
            ]

            async def _extract_with_retry():
                max_attempts = 3
                base_delay = 1.0
                for attempt in range(1, max_attempts + 1):
                    try:
                        await container.memory_service.extract_and_write(
                            user_id, stable_session_id, full_msgs
                        )
                        logger.debug(f"Memory extraction succeeded on attempt {attempt}")
                        return
                    except Exception as e:
                        if attempt == max_attempts:
                            logger.error(
                                f"Memory extraction failed after {max_attempts} attempts "
                                f"for user {user_id} session {stable_session_id}: {e}"
                            )
                            return
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"Memory extraction attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)

            asyncio.create_task(_extract_with_retry())

        # Wave 3 — episodic memory: log the raw turn (query + answer + citations).
        # ponytail: fire-and-forget; anonymous users skipped inside log_episode.
        episodic = getattr(container, "episodic_memory_service", None)
        if episodic is not None and final_answer:
            asyncio.create_task(
                episodic.log_episode(
                    user_id=user_id,
                    query=user_msg,
                    answer=final_answer,
                    citations=citations,
                    intent=intent,
                )
            )
        return None