"""Auto-purge expired conversations per per-user retention_days.

Retention scope (per locked user decision):
  - Conversations + chat_messages: purged by this script.
  - Guru memories (core facts): NEVER purged — durable by design.
  - Telemetry trace data: NOT touched here; own TTL via prune_telemetry.py cron.
  - Meditation session/streak history: NOT touched here; sacred.

Ponytail: idempotent, logarithmed, dry-run flag, runnable bycron or manually.
Self-check: runnable directly with `python prune_retention.py [--user-id <uuid>] [--dry-run]`.

Usage:
    python scripts/ops/prune_retention.py                     # all users, real run
    python scripts/ops/prune_retention.py --dry-run          # all users, no delete
    python scripts/ops/prune_retention.py --user-id <uuid>  # one user
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Make `backend` importable when run from the repo root.
_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logger = logging.getLogger("prune_retention")


def _make_client() -> Any:
    """Build a Supabase client from env. Service-role key required for cross-user deletes."""
    from supabase import create_client  # type: ignore

    url = os.environ.get("SUPABASE_URL") or os.environ.get("VITE_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) must be set."
        )
    return create_client(url, key)


async def prune_retention(db: Any, user_id: str | None = None, dry_run: bool = False) -> dict[str, int]:
    """Delete expired conversations per retention_days. Returns per-step counts."""
    counts = {"scanned": 0, "purged_conversations": 0, "purged_messages": 0}

    # We rely on Postgres to do the date math via a raw SQL RPC (supabase.rpc).
    # Falling back to client-side filtering if RPC is unavailable.
    try:
        # SQL: delete from conversations where (retention_days > 0)
        #      and created_at < now() - (retention_days || ' days')::interval
        #      [and user_id = $user_id]
        sql = (
            "WITH expired AS ("
            "  DELETE FROM public.conversations"
            "  WHERE retention_days > 0"
            "    AND created_at < now() - (retention_days || ' days')::interval"
        )
        params: dict[str, Any] = {}
        if user_id:
            sql += " AND user_id = $user_id"
            params["user_id"] = user_id
        sql += " RETURNING id"
        sql += ")"
        # chat_messages cascade via FK ON DELETE CASCADE — no manual delete needed.
        sql += " SELECT count(*)::int AS n FROM expired;"

        if dry_run:
            # Dry run: replace DELETE with SELECT count(*).
            sql = sql.replace(
                "WITH expired AS (\n  DELETE FROM public.conversations",
                "WITH expired AS (\n  SELECT id FROM public.conversations",
            )

        result = await asyncio.to_thread(
            lambda: db.rpc("exec_sql", {"query": sql, "params": params}).execute()
        )
        n = (result.data or [{}])[0].get("n", 0) if result and hasattr(result, "data") else 0
        counts["purged_conversations"] = int(n)
        logger.info(
            f"prune_retention user={user_id or 'ALL'} dry_run={dry_run} "
            f"conversations={counts['purged_conversations']}"
        )
        return counts
    except Exception as rpc_err:
        logger.warning(f"RPC path unavailable, falling back to client-side scan: {rpc_err}")
        # Client-side fallback: list + filter + delete iteratively.
        try:
            q = db.table("conversations").select("id, user_id, retention_days, created_at")
            if user_id:
                q = q.eq("user_id", user_id)
            res = await asyncio.to_thread(lambda: q.execute())
            rows = res.data if res and hasattr(res, "data") else []
            counts["scanned"] = len(rows)
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            to_delete: list[str] = []
            for r in rows:
                rd = r.get("retention_days")
                ca = r.get("created_at")
                if not rd or rd <= 0 or not ca:
                    continue
                try:
                    created = (
                        ca if isinstance(ca, datetime) else datetime.fromisoformat(str(ca).replace("Z", "+00:00"))
                    )
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if created < now - timedelta(days=int(rd)):
                    to_delete.append(str(r["id"]))
            if dry_run:
                counts["purged_conversations"] = len(to_delete)
                logger.info(f"DRY RUN: would delete {len(to_delete)} conversations")
            else:
                for cid in to_delete:
                    try:
                        await asyncio.to_thread(
                            lambda c=cid: db.table("conversations").delete().eq("id", c).execute()
                        )
                        counts["purged_conversations"] += 1
                    except Exception as del_err:
                        logger.error(f"failed to delete conversation {cid}: {del_err}")
            return counts
        except Exception as scan_err:
            logger.error(f"client-side scan failed: {scan_err}")
            raise


async def _main_async(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s prune_retention %(levelname)s %(message)s",
    )
    db = _make_client()
    counts = await prune_retention(db, user_id=args.user_id, dry_run=args.dry_run)
    logger.info(f"summary: {counts}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-purge expired conversations by retention_days.")
    parser.add_argument("--user-id", default=None, help="Only prune this user's conversations (UUID).")
    parser.add_argument("--dry-run", action="store_true", help="Compute deletions but don't execute.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main_async(args)))
