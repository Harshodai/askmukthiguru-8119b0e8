import asyncio
import logging
import os
import sys

import numpy as np

# Add backend to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from supabase import create_client

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dream_memories")

async def dream_memories():
    """
    Nightly consolidation script for seeker memories.
    1. Retrieves all episodic memories for each user.
    2. Deduplicates semantic memories using cosine similarity of embeddings.
    3. Prunes or consolidates old session summaries/memories if necessary.
    """
    if not settings.supabase_url or not settings.supabase_key:
        logger.error("Supabase credentials not configured.")
        return
        
    supabase = create_client(settings.supabase_url, settings.supabase_key)
    logger.info("Starting memory consolidation (dreaming)...")
    
    # 1. Fetch all memories
    try:
        res = await asyncio.to_thread(
            supabase.table("guru_memories")
            .select("id, user_id, content, embedding")
            .execute
        )
        memories = res.data if res and hasattr(res, 'data') else []
    except Exception as e:
        logger.error(f"Failed to query memories: {e}")
        return
        
    if not memories:
        logger.info("No memories found to consolidate.")
        return
        
    logger.info(f"Loaded {len(memories)} memories for consolidation.")
    
    # Group memories by user_id
    user_memories = {}
    for mem in memories:
        user_id = mem["user_id"]
        user_memories.setdefault(user_id, []).append(mem)
        
    deleted_count = 0
    
    # 2. Deduplicate per user
    for user_id, mems in user_memories.items():
        if len(mems) < 2:
            continue
            
        # Parse embeddings as numpy arrays
        for m in mems:
            emb = m["embedding"]
            if isinstance(emb, str):
                # strip brackets and parse floats
                emb = [float(x) for x in emb.strip("[]").split(",")]
            m["vector"] = np.array(emb)
            
        to_delete = set()
        for i in range(len(mems)):
            if mems[i]["id"] in to_delete:
                continue
            v_i = mems[i]["vector"]
            for j in range(i + 1, len(mems)):
                if mems[j]["id"] in to_delete:
                    continue
                v_j = mems[j]["vector"]
                
                # Calculate cosine similarity
                norm_i = np.linalg.norm(v_i)
                norm_j = np.linalg.norm(v_j)
                if norm_i > 0 and norm_j > 0:
                    sim = np.dot(v_i, v_j) / (norm_i * norm_j)
                else:
                    sim = 0.0
                    
                # If similarity is very high (> 0.90), mark the newer/older one for deletion
                if sim > 0.90:
                    logger.info(
                        f"Duplicate found for user {user_id}: "
                        f"'{mems[i]['content']}' and '{mems[j]['content']}' (similarity: {sim:.3f})"
                    )
                    # Keep the first one, delete the second one
                    to_delete.add(mems[j]["id"])
                    
        for mid in to_delete:
            try:
                await asyncio.to_thread(
                    supabase.table("guru_memories")
                    .delete()
                    .eq("id", mid)
                    .execute
                )
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete duplicate memory {mid}: {e}")
                
    logger.info(f"Dreaming complete. Deduplicated/deleted {deleted_count} memories.")

if __name__ == "__main__":
    asyncio.run(dream_memories())
