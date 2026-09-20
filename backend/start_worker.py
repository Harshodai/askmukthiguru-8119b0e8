#!/usr/bin/env python3
"""On-demand Celery worker for Mukthi Guru ingestion pipeline.

Design: This worker checks the Redis ingestion queue before launching Celery.
If the queue is empty, it polls until a job appears (configurable idle sleep).
Once all queues drain to zero, it exits gracefully.

This eliminates the cost of a permanently-running Celery worker on Railway.
The backend API enqueues jobs to Redis; this script (running as a separate Railway
service) polls Redis and starts Celery only when there is work.

Railway on-demand pattern:
  - Deploy this as a separate Railway service with start command: python start_worker.py
  - Set WORKER_POLL_INTERVAL=30 (seconds to poll when idle)
  - Set WORKER_IDLE_EXIT_AFTER=300 (exit after N seconds of empty queues post-drain)
  - Railway will restart it if it exits while jobs are queued (via restart policy)

Queues watched: ingestion, okf, memory (all Celery task queues)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

import redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] CELERY_WORKER %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Seconds to sleep between queue polls when idle (no jobs yet)
WORKER_POLL_INTERVAL = int(os.environ.get("WORKER_POLL_INTERVAL", "30"))

# After draining all queues, wait this many seconds before exiting.
# Allows Beat tasks (memory drain etc.) to be fully processed before shutdown.
WORKER_IDLE_EXIT_AFTER = int(os.environ.get("WORKER_IDLE_EXIT_AFTER", "300"))

# Max seconds to wait for work before giving up (0 = wait forever)
WORKER_MAX_WAIT_SECONDS = int(os.environ.get("WORKER_MAX_WAIT_SECONDS", "0"))

# Celery queues to poll
CELERY_QUEUES = ["ingestion", "okf", "memory", "celery"]

# Celery worker concurrency (set low for Railway free tier)
WORKER_CONCURRENCY = int(os.environ.get("WORKER_CONCURRENCY", "2"))


def _get_redis_client() -> redis.Redis:
    """Connect to Redis broker from environment."""
    redis_url = os.environ.get("CELERY_BROKER_URL") or os.environ.get(
        "REDIS_URL", "redis://localhost:6379/1"
    )
    return redis.from_url(redis_url, decode_responses=True, socket_timeout=5)


def _queue_depth(r: redis.Redis, queue: str) -> int:
    """Return the number of tasks in a Celery queue."""
    try:
        return r.llen(queue) or 0
    except Exception:
        return 0


def _total_pending(r: redis.Redis) -> int:
    """Total tasks pending across all watched queues."""
    return sum(_queue_depth(r, q) for q in CELERY_QUEUES)


def _wait_for_work(r: redis.Redis) -> bool:
    """Block until at least one task is queued. Returns True when work found, False on timeout."""
    waited = 0
    logger.info(
        "No jobs queued. Polling every %ds (max_wait=%ds, 0=forever)...",
        WORKER_POLL_INTERVAL,
        WORKER_MAX_WAIT_SECONDS,
    )
    while True:
        total = _total_pending(r)
        if total > 0:
            logger.info("Found %d pending task(s) across queues. Starting Celery worker.", total)
            return True

        if WORKER_MAX_WAIT_SECONDS > 0 and waited >= WORKER_MAX_WAIT_SECONDS:
            logger.info(
                "Max wait time (%ds) reached with no jobs. Exiting.", WORKER_MAX_WAIT_SECONDS
            )
            return False

        depths = {q: _queue_depth(r, q) for q in CELERY_QUEUES if _queue_depth(r, q) > 0}
        if depths:
            logger.info("Queue depths: %s", depths)

        time.sleep(WORKER_POLL_INTERVAL)
        waited += WORKER_POLL_INTERVAL


def _launch_celery() -> subprocess.Popen:
    """Launch the Celery worker process."""
    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "celery_config.celery_app",
        "worker",
        "--loglevel=info",
        f"--concurrency={WORKER_CONCURRENCY}",
        "--queues=ingestion,okf,memory,celery",
        "--without-gossip",
        "--without-mingle",
        "--without-heartbeat",
        # Graceful shutdown: wait up to 120s for running tasks to complete
        "--max-tasks-per-child=10",
    ]
    logger.info("Launching: %s", " ".join(cmd))
    return subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))


def _wait_for_drain(r: redis.Redis, proc: subprocess.Popen) -> None:
    """Monitor queues and shut worker down when queues drain."""
    idle_since: float | None = None

    while True:
        # Check if worker process died unexpectedly
        retcode = proc.poll()
        if retcode is not None:
            logger.warning("Celery worker exited unexpectedly with code %d", retcode)
            return

        total = _total_pending(r)
        depths = {q: _queue_depth(r, q) for q in CELERY_QUEUES if _queue_depth(r, q) > 0}

        if total > 0:
            idle_since = None
            logger.info("Queue depths: %s", depths)
        else:
            if idle_since is None:
                idle_since = time.time()
                logger.info(
                    "All queues empty. Will exit in %ds if no new jobs arrive.",
                    WORKER_IDLE_EXIT_AFTER,
                )
            elif time.time() - idle_since >= WORKER_IDLE_EXIT_AFTER:
                logger.info(
                    "Queues idle for %ds. Sending graceful shutdown to Celery worker.",
                    WORKER_IDLE_EXIT_AFTER,
                )
                # Send SIGTERM for graceful shutdown (Celery honours this)
                proc.terminate()
                try:
                    proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    logger.warning("Worker did not exit in 60s; sending SIGKILL.")
                    proc.kill()
                    proc.wait()
                logger.info("Celery worker exited. Shutting down on-demand worker.")
                return

        time.sleep(WORKER_POLL_INTERVAL)


def main() -> None:
    logger.info(
        "On-demand Celery worker starting. poll_interval=%ds, idle_exit_after=%ds, queues=%s",
        WORKER_POLL_INTERVAL,
        WORKER_IDLE_EXIT_AFTER,
        CELERY_QUEUES,
    )

    try:
        r = _get_redis_client()
        r.ping()
        logger.info("Redis connection OK.")
    except Exception as exc:
        logger.error("Cannot connect to Redis: %s. Exiting.", exc)
        sys.exit(1)

    # Phase 1: wait until there is work
    has_work = _wait_for_work(r)
    if not has_work:
        logger.info("No work found. Exiting (Railway will restart if needed).")
        sys.exit(0)

    # Phase 2: run worker until queues drain
    proc = _launch_celery()
    _wait_for_drain(r, proc)

    logger.info("On-demand worker cycle complete. Exiting (Railway will restart if jobs appear).")
    sys.exit(0)


if __name__ == "__main__":
    main()
