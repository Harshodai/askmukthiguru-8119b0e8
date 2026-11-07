import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Optional

import numpy as np

# Ensure backend root is on sys.path whether executed from root or backend/
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if not os.path.exists(os.path.join(_BACKEND, "app")):
    _BACKEND = os.path.abspath(os.path.join(_HERE, "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.config import settings
from services.canonical_memory.dreamer import (
    DreamingReport,
    MemoryDreamer,
    create_dreamer,
)
from supabase import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dream_memories")

# B4 spec (docs/MEMORY_BACKEND_HANDOFF.md): dedup merge threshold cos > 0.95.
DEDUP_SIM_THRESHOLD = 0.95


def is_duplicate(cosine_sim: float) -> bool:
    """Pure duplicate predicate so the B4 threshold is unit-testable."""
    return cosine_sim > DEDUP_SIM_THRESHOLD


async def legacy_dedup_guru_memories(supabase: Any) -> int:
    """Legacy B4 cosine deduplication for guru_memories table."""
    try:
        res = await asyncio.to_thread(
            supabase.table("guru_memories").select("id, user_id, content, embedding").execute
        )
        memories = res.data if res and hasattr(res, "data") else []
    except Exception as e:
        logger.warning(f"Failed to query legacy guru_memories for dedup: {e}")
        return 0

    if not memories:
        return 0

    user_memories: dict[str, list[dict]] = {}
    for mem in memories:
        user_id = mem.get("user_id")
        if user_id:
            user_memories.setdefault(user_id, []).append(mem)

    deleted_count = 0
    for user_id, mems in user_memories.items():
        if len(mems) < 2:
            continue

        for m in mems:
            emb = m.get("embedding")
            if isinstance(emb, str):
                emb = [float(x) for x in emb.strip("[]").split(",") if x.strip()]
            m["vector"] = np.array(emb) if emb is not None else np.array([])

        to_delete = set()
        for i in range(len(mems)):
            if mems[i]["id"] in to_delete or len(mems[i]["vector"]) == 0:
                continue
            v_i = mems[i]["vector"]
            for j in range(i + 1, len(mems)):
                if mems[j]["id"] in to_delete or len(mems[j]["vector"]) == 0:
                    continue
                v_j = mems[j]["vector"]

                norm_i = np.linalg.norm(v_i)
                norm_j = np.linalg.norm(v_j)
                if norm_i > 0 and norm_j > 0:
                    sim = float(np.dot(v_i, v_j) / (norm_i * norm_j))
                else:
                    sim = 0.0

                if is_duplicate(sim):
                    logger.info(
                        f"Legacy duplicate found for user {user_id}: "
                        f"'{mems[i]['content']}' and '{mems[j]['content']}' (similarity: {sim:.3f})"
                    )
                    to_delete.add(mems[j]["id"])

        for mid in to_delete:
            try:
                await asyncio.to_thread(
                    supabase.table("guru_memories").delete().eq("id", mid).execute
                )
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete duplicate memory {mid}: {e}")

    return deleted_count


async def dream_memories(
    user_id: Optional[str] = None,
    dry_run: bool = False,
    run_all: bool = False,
) -> list[DreamingReport]:
    """Offline Dreaming process for agent memory.

    1. Runs Enterprise MemoryDreamer on canonical_memories:
       - Stage 1: Snapshot creation
       - Stage 2: Transcript Grounding Audit
       - Stage 3: Contradiction & Temporal Evolution
       - Stage 4: Mathematical Decay & Pruning
       - Stage 5: SeekerCoreDashboard Synthesis
    2. Runs legacy cosine deduplication on guru_memories.
    """
    if not settings.supabase_url or not settings.supabase_key:
        logger.error("Supabase credentials not configured.")
        return []

    supabase = create_client(settings.supabase_url, settings.supabase_key)
    logger.info("Starting enterprise memory dreaming (dry_run=%s)...", dry_run)

    dreamer = create_dreamer(supabase_client=supabase)
    reports: list[DreamingReport] = []

    if user_id:
        logger.info("Dreaming for specific user %s", user_id)
        rep = await dreamer.dream(user_id=user_id, dry_run=dry_run)
        reports.append(rep)
    elif run_all or user_id is None:
        logger.info("Dreaming across all active users...")
        reports = await dreamer.dream_all(dry_run=dry_run)

    # Legacy pass if not dry_run
    if not dry_run:
        legacy_deleted = await legacy_dedup_guru_memories(supabase)
        logger.info("Legacy dedup completed: removed %d duplicates.", legacy_deleted)

    logger.info(
        "Offline Dreaming finished. Processed %d users.",
        len(reports),
    )
    return reports


def parse_args():
    parser = argparse.ArgumentParser(
        description="Enterprise Offline Memory Dreamer Worker (Sleep-Time Compute)"
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Run dreaming for a single user UUID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate dreaming audit without persisting mutations",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="run_all",
        help="Run dreaming across all users",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        dream_memories(
            user_id=args.user_id,
            dry_run=args.dry_run,
            run_all=args.run_all,
        )
    )
