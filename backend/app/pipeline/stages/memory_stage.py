"""Memory stage — save conversation memory asynchronously.

Body extracted verbatim from PipelineCoordinator._save_memory. Never
short-circuits; fire-and-forget. This stage is the Wave 3 extension point
(episodic + OKF memory will hook in here).
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from app.config import settings
from app.pipeline.result import PipelineResult  # noqa: F401
from app.pipeline.stages.base import Stage
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
# Non-blocking capacity mechanism: only allow the configured number of active
# or queued Celery apply_async calls; defer to Celery Beat when no slot is available.
_DISPATCH_MAX_SLOTS = 2
_DISPATCH_EXECUTOR = ThreadPoolExecutor(
    max_workers=_DISPATCH_MAX_SLOTS, thread_name_prefix="memory-outbox-dispatch"
)
_DISPATCH_SEMAPHORE = asyncio.Semaphore(_DISPATCH_MAX_SLOTS)


def _schedule_memory_task(coro, task_name: str) -> None:
    """Run non-blocking consented memory work with a hard lifetime bound."""

    async def _run() -> None:
        try:
            await asyncio.wait_for(
                coro,
                timeout=settings.memory_background_task_timeout_seconds,
            )
        except TimeoutError:
            logger.warning("%s timed out and was cancelled", task_name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("%s failed (non-fatal): %s", task_name, exc)

    asyncio.create_task(_run(), name=f"memory:{task_name}")


# Strong references to in-flight canonical-memory writes. An asyncio task with
# no reference can be collected before it runs, which loses the write silently.
_CANONICAL_WRITE_TASKS: set = set()


def _vault_write_enabled() -> bool:
    """Single-plane vault-miner switch (owner decision: wire all at one).

    Reads the EXISTING `feature_memory_write` flag via getattr (app/config.py
    is owned elsewhere — never import-mutate it here). Default stays False:
    the owner flips it only after consent proof. No new setting is introduced,
    so the settings-guard baseline does not grow.
    """
    from app.config import settings as _settings

    return bool(getattr(_settings, "feature_memory_write", False))


async def _write_vault_turn(
    *,
    container,
    user_id: str,
    user_msg: str,
    final_answer: str,
) -> int:
    """Write leg of single-plane vault learning: one chat turn → vault miner.

    Called from inside MemoryStage's canonical-write task, AFTER the shared
    consent receipt is verified by the caller — this helper performs NO second
    consent fetch and NO memory read (no personal_context / prepare_user_memory
    / inject_memory_context: the read/injection point stays exactly where it
    is, in the orchestrator). Returns items written; 0 on any skip or failure.
    Never raises: memory failure must never break chat (fail-open).
    """
    try:
        if not _vault_write_enabled():
            return 0
        if not _is_persistable_user_id(user_id):
            return 0
        if not (final_answer or "").strip():
            return 0
        second_brain = getattr(container, "second_brain", None)
        if second_brain is None:
            return 0
        try:
            vault = await second_brain.unlock(user_id)
        except Exception as exc:
            logger.debug("Vault memory write skipped: unlock failed: %s", exc)
            return 0
        try:
            with vault:
                written = await second_brain.extract_and_write(
                    user_id,
                    user_msg or "",
                    final_answer or "",
                    vault=vault,
                )
                return int(written or 0)
        except Exception as exc:
            logger.warning("Vault memory write failed (non-fatal): %s", exc)
            return 0
    except Exception as exc:
        logger.warning("Vault memory write failed (non-fatal): %s", exc)
        return 0


class MemoryStage(Stage):
    """Persist conversation memory (user_profile + memory_service). Never short-circuits."""

    name = "memory_save"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
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
        # --- Canonical memory write path ---
        # Runs BEFORE the legacy `feature_memory_write` gate on purpose: that
        # flag is the kill switch for the legacy outbox, and canonical
        # extraction has its own (`memory_write`). Sharing one switch meant
        # turning canonical writes on did nothing at all, silently — measured
        # 2026-09-13, memory_save returned in 0.01ms.
        #
        # Consent is still required and fails CLOSED: inferring durable facts
        # about a seeker from their words is exactly what consent governs, so no
        # consent receipt (or no outbox to check one against) means no write.
        canonical_integration = getattr(container, "canonical_memory_integration", None)
        # Single-plane vault learning (owner decision: wire all at one): the
        # vault miner rides this SAME task behind the EXISTING
        # `feature_memory_write` flag — no duplicate write path, one consent
        # fetch, one fire-and-forget task. Read/injection stays untouched in
        # the orchestrator's prepare_user_memory (no second fetch from here).
        _want_canonical = bool(settings.memory_write and canonical_integration is not None)
        _want_vault = bool(
            _vault_write_enabled() and getattr(container, "second_brain", None) is not None
        )
        if final_answer and (_want_canonical or _want_vault):
            import asyncio as _asyncio

            from services.tenant_context import TenantContext as _TenantContext

            async def _canonical_write() -> None:
                try:
                    _outbox = getattr(container, "memory_outbox", None)
                    if _outbox is None or not _is_persistable_user_id(user_id):
                        logger.info(
                            "Canonical memory write skipped: no consent store or "
                            "non-persistable user"
                        )
                        return
                    _consent = await _outbox.active_consent(
                        user_id=user_id, tenant_id=_TenantContext.get()
                    )
                    if not _consent:
                        logger.info("Canonical memory write skipped: no active consent receipt")
                        return
                    if _want_canonical:
                        await _asyncio.wait_for(
                            canonical_integration.post_response_memory(
                                user_id=user_id,
                                query=user_msg or "",
                                response=final_answer,
                                session_id=stable_session_id or "",
                                session_messages=chat_body_messages or [],
                            ),
                            timeout=float(
                                getattr(settings, "canonical_memory_write_timeout", 30.0)
                            ),
                        )
                        logger.info("Canonical memory write completed for this turn")
                    if _want_vault:
                        try:
                            _written = await _asyncio.wait_for(
                                _write_vault_turn(
                                    container=container,
                                    user_id=user_id,
                                    user_msg=user_msg or "",
                                    final_answer=final_answer,
                                ),
                                timeout=float(
                                    getattr(settings, "canonical_memory_write_timeout", 30.0)
                                ),
                            )
                            logger.info("Vault memory write completed (%d items)", _written)
                        except TimeoutError:
                            logger.warning("Vault memory write timed out for this turn")
                        except Exception as exc:
                            logger.warning("Vault memory write failed: %s", exc)
                except TimeoutError:
                    logger.warning("Canonical memory write timed out for this turn")
                except Exception as exc:
                    logger.warning("Canonical memory write failed: %s", exc)

            # Strong reference: an asyncio task nobody holds can be collected
            # before it runs, which loses the write with no error anywhere.
            _task = _asyncio.create_task(_canonical_write())
            _CANONICAL_WRITE_TASKS.add(_task)
            _task.add_done_callback(_CANONICAL_WRITE_TASKS.discard)

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
            consent = await outbox.active_consent(user_id=user_id, tenant_id=tenant_id)
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

        if _DISPATCH_SEMAPHORE.locked():
            logger.warning("Memory outbox dispatch capacity reached; deferring to Celery Beat")
            logger.debug("Durable memory outbox row queued: %s", outbox_entry.get("id"))
            return None

        await _DISPATCH_SEMAPHORE.acquire()
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
        finally:
            _DISPATCH_SEMAPHORE.release()
        logger.debug("Durable memory outbox row queued: %s", outbox_entry.get("id"))
        return None
