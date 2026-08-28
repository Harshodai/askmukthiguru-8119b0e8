from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from celery_config import REDIS_URL, celery_app

app = celery_app
logger = logging.getLogger(__name__)

TURN_THRESHOLD = 5
IDLE_TIMEOUT = 600
TURN_REDIS_PREFIX = "turn_counter:"


@app.task(
    bind=True,
    name="tasks.layered_memory_tasks.process_batched_memories",
    max_retries=2,
    soft_time_limit=120,
)
def process_batched_memories(self) -> dict:
    """Scan users with accumulated turns, trigger L3 persona + skill refresh."""
    try:
        import redis as sync_redis

        r = sync_redis.from_url(REDIS_URL, decode_responses=True)
        keys = r.keys(f"{TURN_REDIS_PREFIX}*")
        now = time.time()
        processed = 0
        for key in keys or []:
            try:
                data = json.loads(r.get(key) or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            user_id = key.replace(TURN_REDIS_PREFIX, "")
            count = data.get("count", 0)
            last_ts = data.get("last_ts", 0)
            idle = now - last_ts
            if count >= TURN_THRESHOLD or (count > 0 and idle > IDLE_TIMEOUT):
                try:
                    asyncio.run(_refresh_persona_and_skills(user_id))
                    r.set(key, json.dumps({"count": 0, "last_ts": now}))
                    processed += 1
                except Exception as e:
                    logger.warning(f"Batched refresh failed for {user_id}: {e}")
        return {"processed": processed}
    except Exception as e:
        logger.error(f"process_batched_memories failed: {e}")
        return {"processed": 0, "error": str(e)}


async def _refresh_persona_and_skills(user_id: str):
    from app.telemetry_db import _get_client
    from services.layered_memory.l1_extractor import get_recent_atoms
    from services.layered_memory.l3_persona_generator import generate_persona
    from services.layered_memory.persona_store import get_persona, save_persona
    from services.layered_memory.skill_generator import generate_skills, get_skills, save_skills
    from services.memory_service_v2 import get_service
    from services.tenant_context import TenantContext

    svc = get_service()
    if not svc:
        return
    client = _get_client()
    if not client:
        return
    tenant_id = TenantContext.get()
    atoms = await get_recent_atoms(svc, user_id, limit=30)
    if not atoms:
        return

    atoms_text = "\n".join(a.content for a in atoms)
    existing_persona, _ = await get_persona(client, user_id)
    persona = await generate_persona(atoms, existing_persona)
    if persona:
        await save_persona(client, user_id, persona)

    existing_skills = await get_skills(client, user_id, tenant_id)
    new_skills = await generate_skills(atoms_text, existing_skills)
    if new_skills:
        await save_skills(client, user_id, tenant_id, new_skills)


if __name__ == "__main__":
    print("Layered memory tasks loaded")
