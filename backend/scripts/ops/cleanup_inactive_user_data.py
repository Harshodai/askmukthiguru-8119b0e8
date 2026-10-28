#!/usr/bin/env python3
"""cleanup_inactive_user_data.py — Data Privacy & Retention TTL Cleanup Script.

Performs automated hygiene for inactive users and stale transient data:
1. Redis Ephemeral Session Keys: Purges stale session state older than 24 hours.
2. Inactive Chat Telemetry Logs: Purges transient logs for users inactive > 90 days.
3. Orphaned/Expired Memory Vectors: Cleans Qdrant memory points for accounts inactive > 365 days.
4. Preserves Core Milestones: User profile settings and Second Brain Vault notes remain protected.

Usage (run from the repository root):
  backend/.venv/bin/python scripts/ops/cleanup_inactive_user_data.py [--dry-run] [--days-telemetry 90] [--days-inactivity 365]

Exit status: 0 only when every cleanup step succeeded (a step with zero
deletions is a success); 1 when any step raised — exceptions propagate out of
the cleanup_* functions instead of being reported as "purged 0".
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

# Ensure backend/ is on path (this copy lives at <repo>/scripts/ops/)
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..", "backend")))

# Module-level imports kept re-patchable for tests.
from postgrest import ReturnMethod
from qdrant_client import QdrantClient

from app.config import settings
from supabase import create_client

QDRANT_COLLECTION = "spiritual_wisdom"

#: Default retention window for transient telemetry tables (days).
TELEMETRY_RETENTION_DAYS = 90

#: Postgres telemetry tables purged on each run when rows exceed retention days.
TELEMETRY_TABLES = (
    "chat_queries",
    "chat_responses",
    "retrieval_events",
    "trace_spans",
    "trigger_events",
    "safety_events",
    "app_logs",
    "token_usage",
    "router_decisions",
)


def cleanup_redis_keys(dry_run: bool = False) -> int:
    """Purge expired ephemeral Redis keys."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        r = redis.Redis.from_url(
            redis_url, decode_responses=True, socket_timeout=5, socket_connect_timeout=5
        )
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
        # Distinct failure signal: a real exception must not look like a
        # successful run that simply found 0 keys to purge.
        print(f"ERROR: Redis cleanup failed ({e})")
        raise


def cleanup_stale_qdrant_memories(days_inactivity: int = 365, dry_run: bool = False) -> int:
    try:
        qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")
        client = QdrantClient(url=settings.qdrant_url, api_key=qdrant_api_key or None, timeout=30)
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        collections = [c.name for c in client.get_collections().collections if "memory" in c.name]

        purged = 0
        cutoff = (datetime.utcnow() - timedelta(days=days_inactivity)).isoformat()

        # Resolve inactive user IDs from Supabase profiles (paginated to handle large user tables).
        # A memory point is purged only when BOTH the user is inactive AND the point itself
        # has not been updated within the retention window.
        try:
            inactive_user_ids = set()
            page_size = 1000
            start = 0
            while True:
                user_res = (
                    supabase.table("profiles")
                    .select("id")
                    .lt("last_active_at", cutoff)
                    .order("id")
                    .range(start, start + page_size - 1)
                    .execute()
                )
                if not user_res.data:
                    break
                for row in user_res.data:
                    uid = row.get("id")
                    if uid:
                        inactive_user_ids.add(uid)
                if len(user_res.data) < page_size:
                    break
                start += page_size
            print(
                f"  Found {len(inactive_user_ids)} inactive users (profiles.last_active_at before {cutoff[:10]})"
            )
        except Exception as ue:
            # Finding cleanup-inactive-fallback: without the inactive-user set
            # the filter below cannot be applied, and the old fallback purged
            # EVERY point older than the cutoff — including active users'
            # memories. Skip the Qdrant memory cleanup entirely instead.
            raise RuntimeError(
                "Could not query inactive users from Supabase; skipping Qdrant "
                f"memory cleanup rather than deleting unfiltered points: {ue}"
            ) from ue

        for col in collections:
            if col in ("spiritual_wisdom", "global_memory", "second_brain_vault"):
                continue

            offset = None
            while True:
                from qdrant_client.models import DatetimeRange, FieldCondition, Filter

                stale_results, next_offset = client.scroll(
                    collection_name=col,
                    scroll_filter=Filter(
                        must=[FieldCondition(key="updated_at", range=DatetimeRange(lt=cutoff))]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                stale_results = stale_results or []
                if not stale_results:
                    break

                filtered = [
                    p for p in stale_results if p.payload.get("user_id") in inactive_user_ids
                ]

                if not filtered:
                    offset = next_offset
                    if offset is None:
                        break
                    continue

                point_ids = [p.id for p in filtered]
                purged += len(point_ids)
                print(f"  Collection '{col}': found {len(point_ids)} memories from inactive users")
                if not dry_run:
                    client.delete(collection_name=col, points_selector=point_ids)
                offset = next_offset
                if offset is None:
                    break

        print(f"✓ Qdrant Memory cleanup: purged {purged} stale user memory vectors.")
        return purged
    except Exception as e:
        # Distinct failure signal: raise instead of reporting "purged 0".
        print(f"ERROR: Qdrant Memory cleanup failed ({e})")
        raise


def cleanup_telemetry_logs(
    days_retention: int = TELEMETRY_RETENTION_DAYS, dry_run: bool = False
) -> int:
    """Purge telemetry logs older than days_retention from Supabase."""
    try:
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        cutoff = (datetime.utcnow() - timedelta(days=days_retention)).isoformat()
        total = 0
        failed_tables: list[str] = []
        for table in TELEMETRY_TABLES:
            try:
                if dry_run:
                    count_result = (
                        supabase.table(table)
                        .select("id", count="exact")
                        .lt("created_at", cutoff)
                        .execute()
                    )
                    purged = getattr(count_result, "count", 0) or (
                        len(count_result.data) if count_result.data else 0
                    )
                else:
                    result = (
                        supabase.table(table)
                        .delete(count="exact", returning=ReturnMethod.minimal)
                        .lt("created_at", cutoff)
                        .execute()
                    )
                    purged = result.count if hasattr(result, "count") else 0
                total += purged
                print(f"  Table '{table}': purged {purged} rows older than {days_retention} days.")
            except Exception as te:
                failed_tables.append(table)
                print(f"  WARN: Telemetry cleanup failed for table {table}: {te}")
        if failed_tables:
            # A partially-cleaned telemetry step is a failed step: report it
            # distinctly instead of printing a success line and returning a
            # total that makes main() exit 0.
            raise RuntimeError(
                f"Telemetry cleanup failed for {len(failed_tables)}/{len(TELEMETRY_TABLES)} "
                f"tables: {', '.join(failed_tables)} ({total} rows purged from the rest)"
            )
        print(f"✓ Telemetry cleanup: purged {total} rows across {len(TELEMETRY_TABLES)} tables.")
        return total
    except Exception as e:
        # Distinct failure signal: raise instead of reporting "purged 0".
        print(f"ERROR: Telemetry cleanup failed ({e})")
        raise


def cleanup_anonymous_session_summaries(days_retention: int = 30, dry_run: bool = False) -> int:
    """Purge anonymous guru_session_summaries rows older than days_retention days."""
    try:
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        cutoff = (datetime.utcnow() - timedelta(days=days_retention)).isoformat()
        if dry_run:
            count_result = (
                supabase.table("guru_session_summaries")
                .select("id", count="exact")
                .is_("user_id", "null")
                .lt("created_at", cutoff)
                .execute()
            )
            purged = getattr(count_result, "count", 0) or (
                len(count_result.data) if count_result.data else 0
            )
        else:
            result = (
                supabase.table("guru_session_summaries")
                .delete(count="exact", returning=ReturnMethod.minimal)
                .is_("user_id", "null")
                .lt("created_at", cutoff)
                .execute()
            )
            purged = result.count if hasattr(result, "count") else 0
        print(
            f"✓ Anonymous session summaries: purged {purged} orphan rows older than {days_retention} days."
        )
        return purged
    except Exception as e:
        # Distinct failure signal: raise instead of reporting "purged 0".
        print(f"ERROR: Anonymous session summary cleanup failed ({e})")
        raise


def cleanup_staging_quality_queue(days_retention: int = 90, dry_run: bool = False) -> int:
    """Purge staging_quality_queue rows older than days_retention days."""
    try:
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        cutoff = (datetime.utcnow() - timedelta(days=days_retention)).isoformat()
        if dry_run:
            count_result = (
                supabase.table("staging_quality_queue")
                .select("id", count="exact")
                .lt("created_at", cutoff)
                .execute()
            )
            purged = getattr(count_result, "count", 0) or (
                len(count_result.data) if count_result.data else 0
            )
        else:
            result = (
                supabase.table("staging_quality_queue")
                .delete(count="exact", returning=ReturnMethod.minimal)
                .lt("created_at", cutoff)
                .execute()
            )
            purged = result.count if hasattr(result, "count") else 0
        print(
            f"✓ Staging quality queue: purged {purged} rows older than {days_retention} days."
        )
        return purged
    except Exception as e:
        print(f"ERROR: Staging quality queue cleanup failed ({e})")
        raise


def cleanup_corpus_gate_rejections(days_retention: int = 90, dry_run: bool = False) -> int:
    """Purge corpus_gate_rejections rows older than days_retention days."""
    try:
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        cutoff = (datetime.utcnow() - timedelta(days=days_retention)).isoformat()
        if dry_run:
            count_result = (
                supabase.table("corpus_gate_rejections")
                .select("id", count="exact")
                .lt("created_at", cutoff)
                .execute()
            )
            purged = getattr(count_result, "count", 0) or (
                len(count_result.data) if count_result.data else 0
            )
        else:
            result = (
                supabase.table("corpus_gate_rejections")
                .delete(count="exact", returning=ReturnMethod.minimal)
                .lt("created_at", cutoff)
                .execute()
            )
            purged = result.count if hasattr(result, "count") else 0
        print(
            f"✓ Corpus gate rejections: purged {purged} rows older than {days_retention} days."
        )
        return purged
    except Exception as e:
        print(f"ERROR: Corpus gate rejections cleanup failed ({e})")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up inactive user data & stale memories")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without purging")
    parser.add_argument(
        "--days-telemetry", type=int, default=90, help="Days retention for telemetry logs"
    )
    parser.add_argument(
        "--days-inactivity", type=int, default=365, help="Days retention for inactive memories"
    )
    args = parser.parse_args()

    print("=== Starting Inactive User Data & Retention Cleanup ===")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE PURGE'}")
    print(
        f"Telemetry Retention: {args.days_telemetry} days | Memory Inactivity Cutoff: {args.days_inactivity} days\n"
    )

    start = time.time()
    # Each cleanup_* function now RAISES on failure (distinct from a
    # successful run with zero deletions), so main() must catch per step,
    # keep going, and exit non-zero if any step failed.
    steps = (
        ("Redis", lambda: cleanup_redis_keys(dry_run=args.dry_run)),
        (
            "QdrantMemory",
            lambda: cleanup_stale_qdrant_memories(
                days_inactivity=args.days_inactivity, dry_run=args.dry_run
            ),
        ),
        (
            "Telemetry",
            lambda: cleanup_telemetry_logs(
                days_retention=args.days_telemetry, dry_run=args.dry_run
            ),
        ),
        ("AnonymousSummaries", lambda: cleanup_anonymous_session_summaries(dry_run=args.dry_run)),
        (
            "StagingQualityQueue",
            lambda: cleanup_staging_quality_queue(
                days_retention=args.days_telemetry, dry_run=args.dry_run
            ),
        ),
        (
            "CorpusGateRejections",
            lambda: cleanup_corpus_gate_rejections(
                days_retention=args.days_telemetry, dry_run=args.dry_run
            ),
        ),
    )
    counts: dict[str, int] = {}
    failed_steps: list[str] = []
    for name, call in steps:
        try:
            counts[name] = call()
        except Exception:
            counts[name] = 0
            failed_steps.append(name)
            # The cleanup_* function already printed the ERROR line.

    elapsed = time.time() - start
    print(
        f"\nCleanup {'FAILED' if failed_steps else 'complete'} in {elapsed:.2f}s. Total purged: "
        f"Redis={counts['Redis']}, Qdrant={counts['QdrantMemory']}, "
        f"Telemetry={counts['Telemetry']}, AnonymousSummaries={counts['AnonymousSummaries']}, "
        f"StagingQualityQueue={counts['StagingQualityQueue']}, "
        f"CorpusGateRejections={counts['CorpusGateRejections']}"
    )
    if failed_steps:
        print(f"ERROR: {len(failed_steps)} cleanup step(s) failed: {', '.join(failed_steps)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
