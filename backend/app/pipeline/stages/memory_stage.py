"""Memory stage — save conversation memory asynchronously.

Body extracted verbatim from PipelineCoordinator._save_memory. Never
short-circuits; fire-and-forget. This stage is the Wave 3 extension point
(episodic + OKF memory will hook in here).
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from app.config import settings

from app.pipeline.stages.base import Stage
from app.pipeline.result import PipelineResult  # noqa: F401
from services.user_profile_service import _is_persistable_user_id

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# Dedicated bounded pool for the Celery apply_async dispatch below (matches
# the pattern in app/telemetry_sink.py's _invalidation_executor). The default
# asyncio.to_thread executor is shared process-wide -- a slow/hanging broker
# repeatedly consuming its threads on timeout starves unrelated to_thread
# callers elsewhere in the app. asyncio.wait_for's timeout does not cancel the
# underlying thread (there is no way to interrupt a blocking Celery call), so
# bounding the pool caps how many such stuck threads can accumulate.
_DISPATCH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="memory-outbox-dispatch")


def _schedule_memory_task(coro, task_name: str) -> None:
    """Run non-blocking consented memory work with a hard lifetime bound."""

    async def _run() -> None:
        try:
            await asyncio.wait_for(
                coro,
                timeout=settings.memory_background_task_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("%s timed out and was cancelled", task_name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("%s failed (non-fatal): %s", task_name, exc)

    asyncio.create_task(_run(), name=f"memory:{task_name}")


class MemoryStage(Stage):
    """Persist conversation memory (user_profile + memory_service). Never short-circuits."""

    name = "memory_save"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        if ctx.incognito:
            logger.debug("Memory persistence skipped for incognito request")
            return None
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
        if not settings.feature_memory_write:
            logger.debug("Memory persistence disabled by feature_memory_write")
            return None

        from services.tenant_context import TenantContext

        outbox = getattr(container, "memory_outbox", None)
        if outbox is None or not _is_persistable_user_id(user_id):
            logger.warning("Memory persistence requires durable outbox and authenticated user")
            return None
        tenant_id = TenantContext.get()
        try:
            consent = await outbox.active_consent(
                user_id=user_id, tenant_id=tenant_id
            )
            if not consent:
                logger.debug("Memory persistence skipped: no active consent receipt")
                return None
            outbox_entry = await outbox.enqueue(
                user_id=user_id,
                tenant_id=tenant_id,
                session_id=stable_session_id,
                consent_receipt_id=consent.get("id"),
                payload={
                    "user_message": user_msg,
                    "assistant_answer": final_answer,
                    "prior_messages": chat_body_messages,
                    "citations": citations,
                    "intent": intent or "GENERAL",
                    "med_step": med_step,
                    "distress_level": distress_level,
                },
            )
        except Exception as exc:
            logger.error("Durable memory enqueue failed; persistence skipped: %s", exc)
            return None


        try:
            import asyncio
            import functools

            from tasks.memory_outbox_tasks import drain_memory_outbox

            publish_timeout = max(1.0, settings.memory_background_task_timeout_seconds - 2.0)
            request_deadline = max(2.0, settings.memory_background_task_timeout_seconds + 2.0)
            loop = asyncio.get_running_loop()
            dispatch_call = functools.partial(
                drain_memory_outbox.apply_async,
                kwargs={},
                countdown=0,
                time_limit=request_deadline,
            )
            await asyncio.wait_for(
                loop.run_in_executor(_DISPATCH_EXECUTOR, dispatch_call),
                timeout=publish_timeout,
            )
        except Exception as exc:
            # The periodic Celery Beat task will recover this pending row.
            logger.warning("Memory outbox dispatch deferred to scheduled worker: %s", exc)
        logger.debug("Durable memory outbox row queued: %s", outbox_entry.get("id"))
        return None
