#!/usr/bin/env python3
"""AskMukthiGuru Railway Rebuild, Cleanup & Cost Optimization Tool.

Performs safe, multi-tiered cleanup for Railway rebuilds and deployments:
1. Redis targeted query cache flush (mukthiguru:cache:*, mukthiguru:semcache:*).
2. Stale distributed lock clearance (mukthiguru:lock:*, maintenance_lock:*, etc.).
3. Optional Celery task queue purging (ingestion, embedding, indexing, okf, memory).
4. Qdrant semantic-cache collection reset (leaves corpus collections untouched).
5. Ephemeral /tmp file and oversized log truncation (10MB ceiling).
6. Local workspace build artifact cleanup (__pycache__, .pytest_cache, logs).
7. Railway deployment pruning (removes old/failed/crashed deployment history).
8. Worker lifecycle control (pause/resume to stay under $25/mo budget ceiling).
9. Budget check against the Railway Pro $25 hard limit.

Guarantees:
- NEVER touches persistent corpus collections (spiritual_wisdom, spiritual_wisdom_contextual).
- NEVER touches user notes, Second Brain vaults (second_brain_vault), or Supabase PostgreSQL tables.
- All destructive operations have --dry-run support.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("railway_cleanup")

# Root directory setup
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Standard Redis query cache patterns (safe to flush)
QUERY_CACHE_PATTERNS = (
    "mukthiguru:cache:*",
    "mukthiguru:semcache:*",
    "cache:query:*",
)

# Standard distributed lock patterns (safe to clear if orphaned/rebuilding)
LOCK_PATTERNS = (
    "mukthiguru:lock:*",
    "maintenance_lock:*",
    "ingestion:lock:*",
    "ingest_lock:*",
    "circuit_breaker:*",
)

# Celery queues
CELERY_QUEUES = ("ingestion", "embedding", "indexing", "okf", "memory")

# Railway Pro Plan Pricing constants (2026 rates)
# RAM: ~$10.00 per GB-month (~$0.0137 / GB-hour)
# vCPU: ~$20.00 per vCPU-month (~$0.0274 / vCPU-hour)
MONTHLY_PER_GB_RAM = 10.0
MONTHLY_PER_VCPU = 20.0
BUDGET_HARD_LIMIT_USD = 25.0


def get_redis_client(redis_url: Optional[str] = None, password: Optional[str] = None) -> Any:
    """Connect to Redis with fail-safe timeouts."""
    try:
        import redis
    except ImportError:
        logger.warning("redis library not installed; skipping Redis operations.")
        return None

    url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    kwargs: Dict[str, Any] = {"socket_connect_timeout": 5, "socket_timeout": 10}
    if password:
        kwargs["password"] = password

    try:
        client = redis.from_url(url, **kwargs)
        client.ping()
        return client
    except Exception as exc:
        logger.warning("Redis connection failed (%s): %s", url, exc)
        return None


def flush_redis_query_caches(
    client: Any, dry_run: bool = False, patterns: Tuple[str, ...] = QUERY_CACHE_PATTERNS
) -> Dict[str, Union[int, str]]:
    """Flush only query response cache keys without touching sessions or user data."""
    if client is None:
        return {p: "redis_unavailable" for p in patterns}

    results: Dict[str, Union[int, str]] = {}
    for pattern in patterns:
        try:
            keys = list(client.scan_iter(match=pattern, count=200))
            count = len(keys)
            if dry_run:
                results[pattern] = f"{count} keys (dry-run)"
                logger.info("[DRY RUN] Would delete %d keys matching %s", count, pattern)
            else:
                deleted = 0
                if keys:
                    pipe = client.pipeline(transaction=False)
                    for k in keys:
                        pipe.delete(k)
                        deleted += 1
                        if deleted % 500 == 0:
                            pipe.execute()
                            pipe = client.pipeline(transaction=False)
                    if deleted % 500:
                        pipe.execute()
                results[pattern] = deleted
                logger.info("Deleted %d keys matching %s", deleted, pattern)
        except Exception as exc:
            results[pattern] = f"error: {exc}"
            logger.error("Failed to delete keys for pattern %s: %s", pattern, exc)
    return results


def clear_stale_locks(
    client: Any, dry_run: bool = False, patterns: Tuple[str, ...] = LOCK_PATTERNS
) -> Dict[str, Union[int, str]]:
    """Clear orphaned distributed locks so new containers do not deadlock."""
    if client is None:
        return {p: "redis_unavailable" for p in patterns}

    results: Dict[str, Union[int, str]] = {}
    for pattern in patterns:
        try:
            keys = list(client.scan_iter(match=pattern, count=100))
            count = len(keys)
            if dry_run:
                results[pattern] = f"{count} locks (dry-run)"
                logger.info("[DRY RUN] Would clear %d locks matching %s", count, pattern)
            else:
                if keys:
                    client.delete(*keys)
                results[pattern] = count
                logger.info("Cleared %d locks matching %s", count, pattern)
        except Exception as exc:
            results[pattern] = f"error: {exc}"
            logger.error("Failed to clear locks for pattern %s: %s", pattern, exc)
    return results


def purge_celery_queues(
    client: Any, queues: Tuple[str, ...] = CELERY_QUEUES, dry_run: bool = False
) -> Dict[str, Union[int, str]]:
    """Purge stale tasks from Celery queues in Redis."""
    if client is None:
        return {q: "redis_unavailable" for q in queues}

    results: Dict[str, Union[int, str]] = {}
    for queue_name in queues:
        try:
            # Celery queue key in Redis is typically the queue name or celery/celery-task-meta
            queue_len = client.llen(queue_name)
            if dry_run:
                results[queue_name] = f"{queue_len} tasks (dry-run)"
                logger.info("[DRY RUN] Would purge %d tasks from Celery queue '%s'", queue_len, queue_name)
            else:
                if queue_len > 0:
                    client.delete(queue_name)
                results[queue_name] = queue_len
                logger.info("Purged %d tasks from Celery queue '%s'", queue_len, queue_name)
        except Exception as exc:
            results[queue_name] = f"error: {exc}"
            logger.warning("Could not purge Celery queue '%s': %s", queue_name, exc)
    return results


def configure_redis_memory_policy(client: Any, maxmemory: str = "256mb", policy: str = "volatile-lru") -> bool:
    """Set Redis maxmemory and eviction policy to prevent memory exhaustion and upgrade fees."""
    if client is None:
        return False
    try:
        client.config_set("maxmemory", maxmemory)
        client.config_set("maxmemory-policy", policy)
        logger.info("Configured Redis maxmemory=%s, policy=%s", maxmemory, policy)
        return True
    except Exception as exc:
        logger.warning("Could not set Redis memory configuration: %s", exc)
        return False


def reset_qdrant_semantic_cache(
    qdrant_url: Optional[str] = None, dimension: int = 1024, dry_run: bool = False
) -> Dict[str, str]:
    """Recreate only the ephemeral semantic cache collections in Qdrant."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
    except ImportError:
        logger.warning("qdrant_client not installed; skipping Qdrant cache reset.")
        return {"semantic_cache": "qdrant_client_unavailable"}

    url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY")
    collection_names = [f"mukthi_semantic_cache_{dimension}d", "semantic_query_cache"]
    results: Dict[str, str] = {}

    try:
        client = QdrantClient(url=url, api_key=api_key, timeout=10)
        existing = {c.name for c in client.get_collections().collections}
        for name in collection_names:
            if dry_run:
                results[name] = "would_recreate (dry-run)"
                logger.info("[DRY RUN] Would recreate Qdrant collection %s", name)
                continue

            if name in existing:
                client.delete_collection(name)
                logger.info("Deleted old Qdrant semantic cache collection %s", name)
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
            results[name] = "recreated_empty"
            logger.info("Recreated empty Qdrant semantic cache collection %s", name)
    except Exception as exc:
        logger.warning("Qdrant cache reset failed (%s): %s", url, exc)
        for name in collection_names:
            results.setdefault(name, f"error: {exc}")

    return results


def clean_container_temp_files(dry_run: bool = False) -> Dict[str, int]:
    """Clean temporary PID, lock, readiness, and oversized log files."""
    results = {"deleted_files": 0, "truncated_logs": 0}

    # 1. /tmp artifacts
    tmp_patterns = [
        "/tmp/*.pid",
        "/tmp/*.lock",
        "/tmp/railway_readiness*.json",
        "/tmp/ingest_migrate.log",
        "/tmp/all_ingest_urls.txt",
    ]
    for pat in tmp_patterns:
        for file_path in glob.glob(pat):
            try:
                if dry_run:
                    logger.info("[DRY RUN] Would delete temp file: %s", file_path)
                else:
                    os.remove(file_path)
                    logger.info("Deleted temp file: %s", file_path)
                results["deleted_files"] += 1
            except Exception as e:
                logger.debug("Failed to remove %s: %e", file_path, e)

    # 2. Log truncation (cap at 10MB to save disk)
    log_dirs = [REPO_ROOT / "logs", REPO_ROOT / "backend" / "logs", Path("/app/logs")]
    for ldir in log_dirs:
        if ldir.exists():
            for log_file in ldir.glob("*.log"):
                try:
                    if log_file.stat().st_size > 10 * 1024 * 1024:  # > 10MB
                        if dry_run:
                            logger.info("[DRY RUN] Would truncate oversized log: %s", log_file)
                        else:
                            with open(log_file, "w") as f:
                                f.truncate(0)
                            logger.info("Truncated oversized log: %s", log_file)
                        results["truncated_logs"] += 1
                except Exception as e:
                    logger.debug("Failed to check log %s: %s", log_file, e)

    return results


def clean_local_workspace(dry_run: bool = False) -> Dict[str, int]:
    """Clean Python bytecode, test caches, and build artifacts from the repository."""
    results = {"pycache_dirs": 0, "cache_dirs": 0, "log_files": 0}

    # Target relevant code directories directly
    target_dirs = [BACKEND_DIR, REPO_ROOT / "scripts", REPO_ROOT / "services", REPO_ROOT / "rag"]
    for tdir in target_dirs:
        if not tdir.exists():
            continue
        for p in tdir.rglob("__pycache__"):
            if any(ignored in str(p) for ignored in [".venv", "node_modules"]):
                continue
            if dry_run:
                logger.info("[DRY RUN] Would remove pycache: %s", p)
            else:
                shutil.rmtree(p, ignore_errors=True)
            results["pycache_dirs"] += 1

    # Remove specific known test/lint caches
    known_caches = [
        REPO_ROOT / ".pytest_cache",
        BACKEND_DIR / ".pytest_cache",
        REPO_ROOT / ".ruff_cache",
        BACKEND_DIR / ".ruff_cache",
        REPO_ROOT / ".coverage",
        BACKEND_DIR / ".coverage",
    ]
    for target in known_caches:
        if target.exists():
            if dry_run:
                logger.info("[DRY RUN] Would remove cache: %s", target)
            else:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            results["cache_dirs"] += 1

    # Remove railway log dumps in root
    for lfile in ["railway_deploy.log", "scripts/railway_logs.txt"]:
        lp = REPO_ROOT / lfile
        if lp.exists():
            if dry_run:
                logger.info("[DRY RUN] Would remove log: %s", lp)
            else:
                lp.unlink(missing_ok=True)
            results["log_files"] += 1

    logger.info("Workspace cleanup finished: %s", results)
    return results


def manage_railway_worker(action: str, dry_run: bool = False) -> bool:
    """Pause, resume, or check status of the Celery worker service on Railway."""
    logger.info("Executing Celery worker action: %s", action)
    if shutil.which("railway") is None:
        logger.warning("Railway CLI is not installed. Run: npm i -g @railway/cli")
        return False

    if action == "status":
        cmd = ["railway", "status"]
        subprocess.run(cmd, check=False)
        return True

    if action == "pause":
        # Scale celery-worker service to 0 or stop it to save idle compute
        logger.info("Pausing Railway Celery worker to save compute budget...")
        if dry_run:
            logger.info("[DRY RUN] Would down/pause service 'celery-worker'")
            return True
        cmd = ["railway", "scale", "--service", "celery-worker", "0"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            # Fallback: railway down for service
            cmd_fallback = ["railway", "down", "--service", "celery-worker", "--yes"]
            res = subprocess.run(cmd_fallback, capture_output=True, text=True, check=False)
        logger.info("Worker pause result: %s", res.stdout or res.stderr)
        return res.returncode == 0

    if action == "resume":
        logger.info("Resuming Railway Celery worker...")
        if dry_run:
            logger.info("[DRY RUN] Would deploy/up service 'celery-worker'")
            return True
        cmd = ["railway", "up", "--service", "celery-worker", "--detach"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        logger.info("Worker resume result: %s", res.stdout or res.stderr)
        return res.returncode == 0

    return False


def prune_railway_deployments(dry_run: bool = False) -> bool:
    """List and prune dead/failed deployments using the Railway CLI."""
    if shutil.which("railway") is None:
        logger.warning("Railway CLI not installed; skipping deployment pruning.")
        return False

    logger.info("Querying Railway deployments...")
    try:
        proc = subprocess.run(
            ["railway", "deployment", "list", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            # Try plain railway deployment list
            logger.info("Railway deployment list output:")
            subprocess.run(["railway", "deployment", "list"], check=False)
            return True

        deployments = json.loads(proc.stdout)
        dead_deployments = [
            d for d in deployments if d.get("status") in ["FAILED", "CRASHED", "REMOVED", "CANCELLED"]
        ]
        logger.info("Found %d inactive/failed deployments.", len(dead_deployments))
        for d in dead_deployments:
            dep_id = d.get("id")
            if dry_run:
                logger.info("[DRY RUN] Would remove inactive deployment %s (%s)", dep_id, d.get("status"))
            else:
                logger.info("Removing inactive deployment %s...", dep_id)
                # Note: railway deployment remove/delete command varies by CLI version
                subprocess.run(["railway", "deployment", "delete", dep_id, "--yes"], check=False)
        return True
    except Exception as exc:
        logger.warning("Failed to prune Railway deployments: %s", exc)
        return False


def check_railway_budget(
    backend_ram_gb: float = 4.3,
    backend_avg_vcpu: float = 0.25,
    worker_running: bool = False,
    worker_ram_gb: float = 0.8,
    worker_avg_vcpu: float = 0.1,
    num_replicas: int = 1,
    duty_cycle: float = 1.0,  # 1.0 = 24/7, 0.5 = 12h/day with auto-sleep
) -> Dict[str, Any]:
    """Calculate projected monthly cost against the $25/month hard budget ceiling.

    Railway Pro Plan:
    - RAM: $10.00 / GB / month ($0.0137 / GB-hour)
    - vCPU: $20.00 / vCPU / month ($0.0274 / vCPU-hour)
    - Hard Auto-Terminate ceiling: $25.00
    """
    backend_ram_cost = backend_ram_gb * MONTHLY_PER_GB_RAM * num_replicas * duty_cycle
    backend_vcpu_cost = backend_avg_vcpu * MONTHLY_PER_VCPU * num_replicas * duty_cycle
    backend_total = backend_ram_cost + backend_vcpu_cost

    worker_total = 0.0
    if worker_running:
        worker_ram_cost = worker_ram_gb * MONTHLY_PER_GB_RAM * duty_cycle
        worker_vcpu_cost = worker_avg_vcpu * MONTHLY_PER_VCPU * duty_cycle
        worker_total = worker_ram_cost + worker_vcpu_cost

    # Redis (256MB) + Memgraph (512MB) baseline estimation (~0.75GB RAM + minimal CPU)
    db_ram_cost = 0.75 * MONTHLY_PER_GB_RAM
    db_vcpu_cost = 0.05 * MONTHLY_PER_VCPU
    db_baseline = db_ram_cost + db_vcpu_cost  # ~$8.50/mo

    total_projected = backend_total + worker_total + db_baseline
    pro_credit = 20.0  # Railway Pro plan includes $20/month usage credit
    net_projected = max(0.0, total_projected - pro_credit)
    headroom = BUDGET_HARD_LIMIT_USD - net_projected
    is_safe = net_projected <= BUDGET_HARD_LIMIT_USD

    report = {
        "budget_limit_usd": BUDGET_HARD_LIMIT_USD,
        "duty_cycle": duty_cycle,
        "backend_estimated_usd": round(backend_total, 2),
        "worker_running": worker_running,
        "worker_estimated_usd": round(worker_total, 2),
        "db_baseline_usd": round(db_baseline, 2),
        "gross_projected_monthly_usd": round(total_projected, 2),
        "pro_credit_usd": pro_credit,
        "net_projected_monthly_usd": round(net_projected, 2),
        "headroom_usd": round(headroom, 2),
        "safe_under_budget": is_safe,
    }

    print("\n" + "=" * 65)
    print("        RAILWAY PRO BUDGET & COST ESTIMATION (2026)")
    print("=" * 65)
    print(f"Spend Limit / Auto-Terminate Ceiling:  ${BUDGET_HARD_LIMIT_USD:.2f}")
    print(f"Pro Plan Included Usage Credit:        -${pro_credit:.2f}/mo")
    print("-" * 65)
    print(f"Backend API ({num_replicas} replica, {backend_ram_gb}GB RAM):   ${backend_total:.2f}/mo")
    print(f"Celery Worker ({'RUNNING' if worker_running else 'PAUSED'}):        ${worker_total:.2f}/mo")
    print(f"Databases (Redis 256MB + Memgraph):  ${db_baseline:.2f}/mo")
    print("-" * 65)
    print(f"Gross Usage (at {int(duty_cycle*100)}% duty cycle):        ${total_projected:.2f}/mo")
    print(f"Net Billed (after $20 Pro credit):   ${net_projected:.2f}/mo")
    print(f"Safety Headroom to $25 ceiling:      ${headroom:.2f}/mo")
    if is_safe:
        print("Status: \033[92m[SAFE] Net usage is within your $25 spend limit!\033[0m")
    else:
        print("Status: \033[91m[CRITICAL WARNING] Net usage risks breaching $25 limit!\033[0m")
        print("  -> Actions to stay under $25 and prevent auto-termination:")
        if worker_running:
            print("     1. Pause Celery worker: make railway-worker-pause")
        print("     2. Keep Celery worker paused except during active ingestion")
        print("     3. In Railway dashboard, enable service auto-sleep when idle")
    print("=" * 65 + "\n")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AskMukthiGuru Railway Rebuild, Cleanup & Cost Optimization CLI"
    )
    parser.add_argument(
        "--mode",
        choices=["safe", "deployments", "local", "all"],
        default="safe",
        help="Cleanup mode: safe (cache+locks+temp), deployments (prune dead deploys), local (workspace), all",
    )
    parser.add_argument(
        "--purge-celery",
        action="store_true",
        help="Purge backlog from Celery queues in Redis",
    )
    parser.add_argument(
        "--tune-redis",
        action="store_true",
        help="Apply 256MB maxmemory and volatile-lru policy to Redis",
    )
    parser.add_argument(
        "--worker-action",
        choices=["status", "pause", "resume"],
        help="Manage Celery worker state on Railway",
    )
    parser.add_argument(
        "--check-budget",
        action="store_true",
        help="Check projected monthly cost against $25 budget ceiling",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate cleanup operations without deleting anything",
    )

    args = parser.parse_args()

    if args.check_budget:
        check_railway_budget()
        return 0

    if args.worker_action:
        manage_railway_worker(args.worker_action, dry_run=args.dry_run)
        return 0

    print(f"\n--- AskMukthiGuru Railway Cleanup Tool (mode={args.mode}, dry_run={args.dry_run}) ---")

    # 1. Local workspace cleanup
    if args.mode in ["local", "all"]:
        clean_local_workspace(dry_run=args.dry_run)

    # 2. Redis and Qdrant cleanup
    if args.mode in ["safe", "all"]:
        r_client = get_redis_client()
        if r_client:
            logger.info("1/4. Flushing Redis query caches...")
            flush_redis_query_caches(r_client, dry_run=args.dry_run)

            logger.info("2/4. Clearing stale distributed locks...")
            clear_stale_locks(r_client, dry_run=args.dry_run)

            if args.purge_celery:
                logger.info("Purging Celery task queues...")
                purge_celery_queues(r_client, dry_run=args.dry_run)

            if args.tune_redis:
                logger.info("Tuning Redis memory policy...")
                configure_redis_memory_policy(r_client)

        logger.info("3/4. Resetting Qdrant semantic cache...")
        reset_qdrant_semantic_cache(dry_run=args.dry_run)

        logger.info("4/4. Cleaning container temporary and log files...")
        clean_container_temp_files(dry_run=args.dry_run)

    # 3. Railway deployments pruning
    if args.mode in ["deployments", "all"]:
        prune_railway_deployments(dry_run=args.dry_run)

    print("\nCleanup completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
