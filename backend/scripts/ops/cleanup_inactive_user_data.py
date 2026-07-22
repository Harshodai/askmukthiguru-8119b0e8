#!/usr/bin/env python3
"""cleanup_inactive_user_data.py — Data Privacy & Retention TTL Cleanup Script.

Performs automated hygiene for inactive users and stale transient data:
1. Redis Ephemeral Session Keys: Purges stale session state older than 24 hours.
2. Inactive Chat Telemetry Logs: Purges transient logs for users inactive > 90 days.
3. Orphaned/Expired Memory Vectors: Cleans Qdrant memory points for accounts inactive > 365 days.
4. Preserves Core Milestones: User profile settings and Second Brain Vault notes remain protected.

Usage:
  cd backend
  .venv/bin/python scripts/ops/cleanup_inactive_user_data.py [--dry-run] [--days-telemetry 90] [--days-inactivity 365]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

QDRANT_COLLECTION = "spiritual_wisdom"


def cleanup_redis_keys(dry_run: bool = False) -> int:
    """Purge expired ephemeral Redis keys."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis
        r = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)
        stale_count = 0
        for pattern in ("session:*", "ephemeral:*"):
            for k in r.scan_iter(match=pattern, count=100):
                age = r.object("idletime", k)
                if age is not None and age >= 86400:
                    stale_count += 1
                    if not dry_run:
                        r.delete(k)
        print(f"✓ Redis cleanup: purged {stale_count} stale keys.")
        return stale_count
    except Exception as e:
        print(f"WARN: Redis cleanup skipped ({e})")
        return 0


def cleanup_stale_qdrant_memories(days_inactivity: int = 365, dry_run: bool = False) -> int:
    """Scans and purges Qdrant memory vectors for users inactive for > 365 days."""
    try:
        from app.config import settings
        from qdrant_client import QdrantClient
        from qdrant_client.models import (DatetimeRange, FieldCondition, Filter, MatchValue)

        qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")
        client = QdrantClient(url=settings.qdrant_url, api_key=qdrant_api_key or None, timeout=30)
        collections = [c.name for c in client.get_collections().collections if "memory" in c.name]
        
        purged = 0
        cutoff = (datetime.utcnow() - timedelta(days=days_inactivity)).isoformat()

        for col in collections:
            if col in ("spiritual_wisdom", "global_memory", "second_brain_vault"):
                continue  # Skip core doctrine & second brain vault
            
            offset = None
            while True:
                results, next_offset = client.scroll(
                    collection_name=col,
                    scroll_filter=Filter(
                        must=[FieldCondition(key="updated_at", range=DatetimeRange(lt=cutoff))]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not results:
                    break
                point_ids = [p.id for p in results]
                purged += len(point_ids)
                print(f"  Collection '{col}': found {len(point_ids)} memories inactive since {cutoff[:10]}")
                if not dry_run:
                    client.delete(collection_name=col, points_selector=point_ids)
                offset = next_offset
                if offset is None:
                    break

        print(f"✓ Qdrant Memory cleanup: purged {purged} stale user memory vectors.")
        return purged
    except Exception as e:
        print(f"WARN: Qdrant Memory cleanup skipped ({e})")
        return 0


def cleanup_telemetry_logs(days_retention: int = 90, dry_run: bool = False) -> int:
    """Purge telemetry logs older than days_retention from Supabase."""
    try:
        from app.config import settings
        from supabase import create_client
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        cutoff = (datetime.utcnow() - timedelta(days=days_retention)).isoformat()
        query = supabase.table("chat_responses").delete(count="exact").lt("created_at", cutoff)
        if dry_run:
            count_result = supabase.table("chat_responses").select("id", count="exact").lt("created_at", cutoff).execute()
            purged = len(count_result.data) if count_result.data else 0
        else:
            result = query.execute()
            purged = result.count if hasattr(result, 'count') else 0
        print(f"✓ Telemetry cleanup: purged {purged} logs older than {days_retention} days.")
        return purged
    except Exception as e:
        print(f"WARN: Telemetry cleanup skipped ({e})")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up inactive user data & stale memories")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without purging")
    parser.add_argument("--days-telemetry", type=int, default=90, help="Days retention for telemetry logs")
    parser.add_argument("--days-inactivity", type=int, default=365, help="Days retention for inactive memories")
    args = parser.parse_args()

    print(f"=== Starting Inactive User Data & Retention Cleanup ===")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE PURGE'}")
    print(f"Telemetry Retention: {args.days_telemetry} days | Memory Inactivity Cutoff: {args.days_inactivity} days\n")

    start = time.time()
    r_count = cleanup_redis_keys(dry_run=args.dry_run)
    q_count = cleanup_stale_qdrant_memories(days_inactivity=args.days_inactivity, dry_run=args.dry_run)
    t_count = cleanup_telemetry_logs(days_retention=args.days_telemetry, dry_run=args.dry_run)

    elapsed = time.time() - start
    print(f"\nCleanup complete in {elapsed:.2f}s. Total purged: Redis={r_count}, Qdrant={q_count}, Telemetry={t_count}")


if __name__ == "__main__":
    main()
