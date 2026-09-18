"""Celery consumer for durable, consented memory outbox rows."""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from celery_config import celery_app

app = celery_app
logger = logging.getLogger(__name__)


# AMK-C-005: each enrichment write below is a side effect on a different store,
# and none of them is idempotent. `mark_processed` only runs after all of them
# succeed, so a worker that DIES mid-loop (not one that raises — that path is
# handled) leaves the row to be reclaimed by claim_memory_outbox's 10-minute
# staleness rule and re-run from the top, writing the user's episodic memory,
# L1 atoms and L2 scene block a second time.
#
# Recording each step as it commits makes a reclaimed row resume instead of
# restart. This narrows the duplicate window from "all five writes, including
# two LLM calls" to "the single step that was in flight at the instant of the
# crash". It does not close it: a crash between a side effect and its marker
# still replays that one step. Closing it fully needs the destination stores to
# accept an idempotency key, which they do not today.
STEP_PROFILE = "profile_conversation"
STEP_EXTRACT = "extract_and_write"
STEP_EPISODIC = "episodic_log"
STEP_L1 = "l1_atoms"
STEP_L2 = "l2_scene"


class _StepTracker:
    """Tracks which enrichment sub-steps have committed for one outbox row."""

    def __init__(self, outbox, outbox_id: str, already_done) -> None:
        self._outbox = outbox
        self._outbox_id = outbox_id
        self._done = {str(step) for step in (already_done or [])}

    def done(self, step: str) -> bool:
        return step in self._done

    async def record(self, step: str) -> None:
        """Persist that `step` committed. Never fails the row.

        A failed marker write only costs us the resume optimisation for that
        step — the enrichment itself already succeeded, and losing the marker
        degrades to the old at-least-once behaviour rather than to data loss.
        """
        self._done.add(step)
        recorder = getattr(self._outbox, "mark_step_done", None)
        if recorder is None:
            return
        try:
            await recorder(self._outbox_id, sorted(self._done))
        except Exception as exc:
            logger.warning(
                "Outbox %s: could not record completed step %s (%s). A reclaim will re-run it.",
                self._outbox_id,
                step,
                exc,
            )


async def _drain_once(limit: int = 50) -> dict[str, int]:
    from app.dependencies import get_container
    from services.tenant_context import TenantContext

    container = get_container()
    outbox = getattr(container, "memory_outbox", None)
    memory_service = getattr(container, "memory_service", None)
    episodic = getattr(container, "episodic_memory_service", None)
    if not settings.feature_memory_write or outbox is None or memory_service is None:
        return {"claimed": 0, "processed": 0, "failed": 0}

    rows = await outbox.get_pending(limit=limit)
    processed = 0
    failed = 0
    for row in rows:
        outbox_id = str(row["id"])
        tenant_id = str(row["tenant_id"])
        user_id = str(row["user_id"])
        payload = row.get("payload") or {}
        TenantContext.set(tenant_id, user_id=user_id)
        try:
            consent = await outbox.active_consent(user_id=user_id, tenant_id=tenant_id)
            if not consent:
                await outbox.mark_failed(outbox_id, "consent revoked before processing")
                failed += 1
                continue
            steps = _StepTracker(outbox, outbox_id, row.get("completed_steps"))
            profile = getattr(container, "user_profile", None)
            if profile is not None and not steps.done(STEP_PROFILE):
                try:
                    import time

                    from services.user_profile_service import ConversationMemory

                    insights = [
                        item if isinstance(item, str) else item.get("title", "")
                        for item in (payload.get("citations") or [])
                    ]
                    record = ConversationMemory(
                        session_id=row["session_id"],
                        user_id=user_id,
                        started_at=time.time(),
                        messages=[
                            {"role": "user", "content": payload["user_message"]},
                            {"role": "assistant", "content": payload["assistant_answer"]},
                        ],
                        key_insights=insights,
                        emotional_arc=[
                            {
                                "timestamp": time.time(),
                                "distress_level": payload.get("distress_level", 0),
                                "provoked": False,
                                "topic": payload.get("intent"),
                                "signal": "general",
                            }
                        ],
                        follow_up_suggestions=[],
                    )
                    await profile.save_conversation_memory(record)
                    await steps.record(STEP_PROFILE)
                except Exception as exc:
                    logger.warning("Outbox profile persistence failed: %s", exc)
            prior = list(payload.get("prior_messages") or [])
            prior.extend(
                [
                    {"role": "user", "content": payload["user_message"]},
                    {"role": "assistant", "content": payload["assistant_answer"]},
                ]
            )
            if not steps.done(STEP_EXTRACT):
                await memory_service.extract_and_write(user_id, row["session_id"], prior)
                await steps.record(STEP_EXTRACT)
            if episodic is not None and not steps.done(STEP_EPISODIC):
                await episodic.log_episode(
                    user_id=user_id,
                    query=payload["user_message"],
                    answer=payload["assistant_answer"],
                    citations=payload.get("citations") or [],
                    intent=payload.get("intent"),
                )
                await steps.record(STEP_EPISODIC)
            if not steps.done(STEP_L1):
                try:
                    from services.layered_memory.l1_extractor import extract_atoms

                    atoms = await extract_atoms(
                        user_msg=payload["user_message"],
                        assistant_msg=payload["assistant_answer"],
                        prior_messages=payload.get("prior_messages") or [],
                        previous_scene_name=payload.get("intent") or "General",
                    )
                    if atoms:
                        await memory_service.add_atoms(user_id, row["session_id"], atoms)
                    await steps.record(STEP_L1)
                except Exception as exc:
                    logger.warning("Outbox L1 enrichment failed: %s", exc)
            if not steps.done(STEP_L2):
                try:
                    from services.layered_memory.l2_scene_compressor import (
                        compress_turns_to_scene,
                        save_scene_block,
                    )

                    block = await compress_turns_to_scene(
                        [
                            {"role": "user", "content": payload["user_message"]},
                            {"role": "assistant", "content": payload["assistant_answer"]},
                        ]
                    )
                    if block and getattr(container, "supabase_client", None):
                        await save_scene_block(
                            container.supabase_client,
                            user_id,
                            tenant_id,
                            row["session_id"],
                            block,
                        )
                    await steps.record(STEP_L2)
                except Exception as exc:
                    logger.warning("Outbox L2 enrichment failed: %s", exc)
            await outbox.mark_processed(outbox_id)
            processed += 1
        except Exception as exc:
            logger.exception("Memory outbox row %s failed", outbox_id)
            await outbox.mark_failed(outbox_id, str(exc))
            failed += 1
    return {"claimed": len(rows), "processed": processed, "failed": failed}


@app.task(
    bind=True,
    name="tasks.memory_outbox_tasks.drain_memory_outbox",
    max_retries=0,
    soft_time_limit=120,
)
def drain_memory_outbox(self) -> dict[str, int]:
    """Process at most 50 durable memory writes. Safe across worker replicas."""
    return asyncio.run(_drain_once())
