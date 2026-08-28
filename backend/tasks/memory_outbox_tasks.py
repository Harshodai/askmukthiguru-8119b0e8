"""Celery consumer for durable, consented memory outbox rows."""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from celery_config import REDIS_URL, celery_app

app = celery_app
logger = logging.getLogger(__name__)


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
            profile = getattr(container, "user_profile", None)
            if profile is not None:
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
                except Exception as exc:
                    logger.warning("Outbox profile persistence failed: %s", exc)
            prior = list(payload.get("prior_messages") or [])
            prior.extend(
                [
                    {"role": "user", "content": payload["user_message"]},
                    {"role": "assistant", "content": payload["assistant_answer"]},
                ]
            )
            await memory_service.extract_and_write(user_id, row["session_id"], prior)
            if episodic is not None:
                await episodic.log_episode(
                    user_id=user_id,
                    query=payload["user_message"],
                    answer=payload["assistant_answer"],
                    citations=payload.get("citations") or [],
                    intent=payload.get("intent"),
                )
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
            except Exception as exc:
                logger.warning("Outbox L1 enrichment failed: %s", exc)
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
