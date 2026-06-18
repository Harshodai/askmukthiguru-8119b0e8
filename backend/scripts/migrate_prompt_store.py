"""
Migrate existing SQLite prompt_store.db to Supabase prompt_versions table.

Idempotent: skips prompts already present in Supabase (matched by name + version).
Safe to run multiple times.

Usage:
    python3 scripts/migrate_prompt_store.py
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SQLITE_PATH = Path("data/prompt_store.db")


def migrate():
    if not SQLITE_PATH.exists():
        logger.info(f"No SQLite prompt_store.db found at {SQLITE_PATH} — nothing to migrate")
        return

    settings = get_settings()
    if not settings.supabase_key:
        logger.error("SUPABASE_KEY not set — cannot migrate")
        return

    client = create_client(settings.supabase_url, settings.supabase_key)

    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM prompts ORDER BY name, created_at ASC").fetchall()
    conn.close()

    if not rows:
        logger.info("SQLite prompt_store.db has 0 rows — nothing to migrate")
        return

    logger.info(f"Found {len(rows)} prompt versions in SQLite to migrate")

    migrated = 0
    skipped = 0

    for row in rows:
        name = row["name"]
        version = row["version"]

        existing = (
            client.table("prompt_versions")
            .select("id")
            .eq("name", name)
            .eq("version", version)
            .execute()
        )
        if existing.data:
            logger.debug(f"Skipping {name} v{version} — already in Supabase")
            skipped += 1
            continue

        created_ts = row["created_at"]
        try:
            from datetime import datetime, timezone
            created_iso = datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()
        except Exception:
            created_iso = datetime.now(timezone.utc).isoformat()

        payload = {
            "name": name,
            "version": version,
            "content": row["content"],
            "description": row.get("description", ""),
            "author": row.get("author", "system"),
            "active": bool(row["is_active"]),
            "created_at": created_iso,
        }

        try:
            client.table("prompt_versions").insert(payload).execute()
            migrated += 1
            logger.info(f"  Migrated {name} v{version} ({'active' if payload['active'] else 'inactive'})")
        except Exception as e:
            logger.error(f"  Failed to migrate {name} v{version}: {e}")

    logger.info(f"Migration complete: {migrated} migrated, {skipped} skipped")
    return migrated


if __name__ == "__main__":
    migrate()
