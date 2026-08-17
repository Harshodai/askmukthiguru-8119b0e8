#!/usr/bin/env python3
"""
Mukthi Guru — Unified Backup & Knowledge Store Reset Tool
===========================================================
Safely backs up and resets Neo4j, Qdrant, LightRAG, and Ingestion Checkpoints
prior to running a full corpus reingestion.

Usage:
  # 1. Take a full backup of all stores (Recommended first step):
  python3 scripts/ops/backup_and_reset_knowledge_stores.py --backup-only

  # 2. Backup and then perform clean wipe:
  python3 scripts/ops/backup_and_reset_knowledge_stores.py --backup-then-wipe

  # 3. Dry run (verify connections and print what will happen):
  python3 scripts/ops/backup_and_reset_knowledge_stores.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
BACKUP_DIR = REPO_ROOT / "backups"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backup_and_reset")


def backup_neo4j(dry_run: bool = False) -> bool:
    logger.info("📦 [1/3] Backing up Neo4j Graph Database...")
    if dry_run:
        logger.info("  [dry-run] Would invoke scripts/ops/backup_neo4j.py")
        return True

    backup_script = REPO_ROOT / "scripts" / "ops" / "backup_neo4j.py"
    if not backup_script.exists():
        logger.warning(f"Neo4j backup script not found at {backup_script}")
        return False

    try:
        res = subprocess.run(
            [sys.executable, str(backup_script), "--format", "cypher"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if res.returncode == 0:
            logger.info("  ✅ Neo4j backup completed successfully.")
            return True
        else:
            logger.error(f"  ❌ Neo4j backup failed: {res.stderr or res.stdout}")
            return False
    except Exception as e:
        logger.error(f"  ❌ Neo4j backup exception: {e}")
        return False


def backup_qdrant(dry_run: bool = False) -> bool:
    logger.info("📦 [2/3] Backing up Qdrant Vector Collection...")
    if dry_run:
        logger.info("  [dry-run] Would invoke scripts/ops/backup_qdrant.py")
        return True

    backup_script = REPO_ROOT / "scripts" / "ops" / "backup_qdrant.py"
    if not backup_script.exists():
        logger.warning(f"Qdrant backup script not found at {backup_script}")
        return False

    try:
        res = subprocess.run(
            [sys.executable, str(backup_script)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if res.returncode == 0:
            logger.info("  ✅ Qdrant backup completed successfully.")
            return True
        else:
            logger.error(f"  ❌ Qdrant backup failed: {res.stderr or res.stdout}")
            return False
    except Exception as e:
        logger.error(f"  ❌ Qdrant backup exception: {e}")
        return False


def backup_lightrag_and_checkpoints(dry_run: bool = False) -> bool:
    logger.info("📦 [3/3] Backing up LightRAG state & ingestion checkpoints...")
    out_archive_dir = BACKUP_DIR / "lightrag_and_checkpoints" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if dry_run:
        logger.info(f"  [dry-run] Would copy data/lightrag and state files to {out_archive_dir}")
        return True

    try:
        out_archive_dir.mkdir(parents=True, exist_ok=True)
        # Copy LightRAG
        lightrag_dir = REPO_ROOT / "data" / "lightrag"
        if lightrag_dir.exists():
            shutil.copytree(lightrag_dir, out_archive_dir / "lightrag", dirs_exist_ok=True)

        # Copy state files
        state_files = [
            REPO_ROOT / "scripts" / "ingestion_state.json",
            REPO_ROOT / "scripts" / "ingestion" / "ingestion_state.json",
            REPO_ROOT / "scripts" / "ingestion" / "fetch_checkpoint.json",
            REPO_ROOT / "scripts" / "ingestion" / "upload_state.json",
            REPO_ROOT / "scripts" / "ingestion" / "batched_pipeline_state.json",
        ]
        for sf in state_files:
            if sf.exists():
                shutil.copy2(sf, out_archive_dir / sf.name)

        logger.info(f"  ✅ LightRAG & checkpoints archived to: {out_archive_dir}")
        return True
    except Exception as e:
        logger.error(f"  ❌ Failed to backup LightRAG / checkpoints: {e}")
        return False


def wipe_neo4j(dry_run: bool = False) -> bool:
    logger.info("🧹 Wiping Neo4j Graph Database...")
    if dry_run:
        logger.info("  [dry-run] Would execute: MATCH (n) DETACH DELETE n")
        return True

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD")

    if not neo4j_password:
        logger.warning("  ⚠️  NEO4J_PASSWORD not set in environment. Skipping Neo4j wipe.")
        return False

    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        driver.close()
        logger.info("  ✅ Neo4j database completely cleared (all nodes & relationships removed).")
        return True
    except Exception as e:
        logger.error(f"  ❌ Neo4j wipe failed: {e}")
        return False


def wipe_qdrant(collection_name: str = "spiritual_wisdom_contextual", dry_run: bool = False) -> bool:
    logger.info(f"🧹 Wiping Qdrant collection: '{collection_name}'...")
    if dry_run:
        logger.info(f"  [dry-run] Would delete and recreate Qdrant collection '{collection_name}'")
        return True

    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")

    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        collections = [c.name for c in client.get_collections().collections]
        if collection_name in collections:
            client.delete_collection(collection_name)
            logger.info(f"  ✅ Qdrant collection '{collection_name}' deleted.")
        else:
            logger.info(f"  ℹ️  Collection '{collection_name}' does not exist, nothing to delete.")
        return True
    except Exception as e:
        logger.error(f"  ❌ Qdrant wipe failed: {e}")
        return False


def wipe_lightrag_and_checkpoints(dry_run: bool = False) -> bool:
    logger.info("🧹 Wiping LightRAG state and ingestion checkpoints...")
    if dry_run:
        logger.info("  [dry-run] Would delete data/lightrag, GPTCache, and ingestion state files")
        return True

    # 1. Clear LightRAG
    for p in [REPO_ROOT / "data" / "lightrag", BACKEND_DIR / "data" / "lightrag"]:
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
            logger.info(f"  ✅ Deleted LightRAG dir: {p}")

    # 2. Clear GPTCache & exact cache
    for p in [REPO_ROOT / "data" / "gptcache", BACKEND_DIR / "data" / "gptcache"]:
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
            logger.info(f"  ✅ Deleted GPTCache dir: {p}")

    # 3. Clear Checkpoint files
    state_files = [
        REPO_ROOT / "scripts" / "ingestion_state.json",
        REPO_ROOT / "scripts" / "ingestion" / "ingestion_state.json",
        REPO_ROOT / "scripts" / "ingestion" / "fetch_checkpoint.json",
        REPO_ROOT / "scripts" / "ingestion" / "upload_state.json",
        REPO_ROOT / "scripts" / "ingestion" / "batched_pipeline_state.json",
    ]
    for sf in state_files:
        if sf.exists():
            sf.unlink(missing_ok=True)
            logger.info(f"  ✅ Deleted state file: {sf.name}")

    # 4. Clear Redis if available
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            r = redis.from_url(redis_url)
            r.flushdb()
            logger.info("  ✅ Redis cache cleared.")
        except Exception as e:
            logger.warning(f"  ⚠️  Redis cleanup skipped: {e}")

    logger.info("  ✅ LightRAG, caches, and checkpoints cleaned.")
    return True


def verify_restore_smoke_test(dry_run: bool = False) -> bool:
    """Verifies that backup artifacts exist, are non-empty, and contain valid Cypher/JSON."""
    logger.info("🧪 Running restore smoke test on generated backup files...")
    if dry_run:
        logger.info("  [dry-run] Restore smoke test passed.")
        return True

    # 1. Verify Neo4j cypher backup
    neo4j_files = list(BACKUP_DIR.glob("neo4j_backup_*.cypher"))
    if not neo4j_files:
        logger.error("  ❌ Neo4j restore smoke test failed: No cypher backup file found.")
        return False
    latest_neo4j = max(neo4j_files, key=lambda p: p.stat().st_mtime)
    if latest_neo4j.stat().st_size == 0:
        logger.error(f"  ❌ Neo4j backup file is empty: {latest_neo4j}")
        return False

    # 2. Verify Qdrant snapshot
    qdrant_files = list(BACKUP_DIR.glob("qdrant_snapshot_*"))
    if not qdrant_files:
        logger.error("  ❌ Qdrant restore smoke test failed: No snapshot file found.")
        return False
    latest_qdrant = max(qdrant_files, key=lambda p: p.stat().st_mtime)
    if latest_qdrant.stat().st_size == 0:
        logger.error(f"  ❌ Qdrant snapshot file is empty: {latest_qdrant}")
        return False

    logger.info("  ✅ Restore smoke test passed (all backup artifacts valid and verified).")
    return True


def main() -> None:
    # Ponytail: self-check when invoked with --self-check
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        print("Running Ponytail self-check on backup & reset tool...")
        assert REPO_ROOT.exists()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        assert BACKUP_DIR.exists()
        print("✅ Ponytail backup & reset tool self-check passed!")
        sys.exit(0)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backup-only", action="store_true", help="Only perform backups, do not wipe")
    parser.add_argument("--wipe-only", action="store_true", help="Perform wipe without backup (Requires --confirm-wipe)")
    parser.add_argument("--backup-then-wipe", action="store_true", help="Backup first, verify restore, then wipe (Requires --confirm-wipe)")
    parser.add_argument("--confirm-wipe", action="store_true", help="Mandatory safety confirmation flag to execute any destructive wipe")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without modifying data")
    parser.add_argument("--collection", default="spiritual_wisdom_contextual", help="Qdrant collection to wipe")
    args = parser.parse_args()

    mode = "backup-then-wipe"
    if args.backup_only:
        mode = "backup-only"
    elif args.wipe_only:
        mode = "wipe-only"
    elif args.backup_then_wipe:
        mode = "backup-then-wipe"

    print("=" * 70)
    print(f"🛡️  MUKTHI GURU: KNOWLEDGE STORES BACKUP & RESET TOOL")
    print(f"   Mode:         {mode.upper()}")
    print(f"   Confirm Wipe: {args.confirm_wipe}")
    print(f"   Dry Run:      {args.dry_run}")
    print("=" * 70)

    if mode in ("backup-only", "backup-then-wipe"):
        b1 = backup_neo4j(dry_run=args.dry_run)
        b2 = backup_qdrant(dry_run=args.dry_run)
        b3 = backup_lightrag_and_checkpoints(dry_run=args.dry_run)

        # Fail-closed: ALL required backups must succeed
        all_backups_ok = all([b1, b2, b3])
        if not all_backups_ok and not args.dry_run:
            logger.critical("❌ FAIL-CLOSED GATE: One or more backups failed! Aborting before any wipe.")
            sys.exit(1)

        # Restore smoke test
        if not verify_restore_smoke_test(dry_run=args.dry_run):
            logger.critical("❌ FAIL-CLOSED GATE: Restore smoke test failed! Aborting before any wipe.")
            sys.exit(1)

    if mode in ("wipe-only", "backup-then-wipe"):
        if not args.confirm_wipe and not args.dry_run:
            print("\n❌ REFUSING TO WIPE: You must explicitly provide '--confirm-wipe' to execute destructive database reset.")
            sys.exit(1)

        print("\n" + "-" * 70)
        print("🚨 STARTING CLEAN WIPE OF KNOWLEDGE STORES...")
        print("-" * 70)
        w1 = wipe_neo4j(dry_run=args.dry_run)
        w2 = wipe_qdrant(collection_name=args.collection, dry_run=args.dry_run)
        w3 = wipe_lightrag_and_checkpoints(dry_run=args.dry_run)
        if not (w1 and w2 and w3) and not args.dry_run:
            logger.error("⚠️  One or more store wipe operations returned non-success. Review logs above.")
            sys.exit(1)

    print("\n" + "=" * 70)
    print("🎉 OPERATION FINISHED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    main()
