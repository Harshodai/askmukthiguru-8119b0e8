"""
Railway health-first ASGI wrapper.

Sends lifespan.startup.complete immediately so uvicorn enters its main loop
and accepts connections quickly. The real FastAPI app's lifespan runs as a
background task. Health checks (/api/healthz) respond fast:

  - /api/healthz → 200 within a 180s grace period, then reflects real readiness
    (healthy while the real app's lifespan heartbeat is fresh; 503 when it goes
    stale >30s or the lifespan never completed).
  - All other paths → proxied to the real app once loaded, else 503

CORRECTION (RP-A10/RP-B1, 2026-10-13): the old comment here claimed
"Railway restarts on 503". That is false. Railway healthchecks run ONLY at
deploy start (declared in .railway/railway.ts: healthcheck "/api/healthz",
healthcheckTimeout 330 — NOT /api/health, and the path must not be changed
without owner approval). A 503 served after a successful deploy triggers NO
restart; the platform restarts a service only when its process exits non-zero
(up to 10 restarts). A wedged-but-alive worker answering 503s would therefore
sit dead forever — so when the heartbeat/executor canary below stays stale
past _STALE_EXIT_AFTER_S, this wrapper logs critically and calls os._exit(1)
to let the restart policy fire.

On shutdown, signals the real lifespan to exit, then waits for cleanup.
"""

# BUILD BUSTER: 2026-07-17T12:15 — force new Railway build with ASGI protocol fix

import asyncio
import logging
import os
import signal
import subprocess
import sys
import threading
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

port = int(os.environ.get("PORT", 8000))

_real_app = None
_lifespan_startup_done = False
_shutdown_event = asyncio.Event()
_process_start = time.monotonic()

# P1-OPS-5: heartbeat for post-grace liveness depth. Pumped by a background
# task while the real app's lifespan is running; healthz reads it. If the
# lifespan exits or its event loop wedges, the pump stops, the heartbeat goes
# stale (> _HEARTBEAT_STALE_S), and healthz returns 503 so Railway restarts
# the replica. Driven from the lifespan task (not the healthz handler) so a
# dead lifespan is detectable even while the wrapper loop still serves 200s.
_last_heartbeat = _process_start

# P2-OPS-1 (2026-09-16): executor-starvation canary. The heartbeat above only
# proves the EVENT LOOP is still scheduling coroutines -- asyncio.sleep()
# never touches a worker thread. The container wedged twice under concurrent
# load with the heartbeat still fresh the whole time (event loop running,
# cpu=3.73% i.e. blocked not spinning, pids=266, last log line
# "AUDIT POST /api/chat -> 200 (187.863s)" then a thread-stack-exhaustion
# MemoryError): the shared default ThreadPoolExecutor -- the same one
# app/api/chat.py's asyncio.to_thread() calls queue onto -- was starved while
# the loop itself stayed healthy. This canary submits a trivial no-op to that
# SAME default executor on a timer; if its workers are all blocked, the
# no-op queues behind them, times out, and this timestamp goes stale.
_last_executor_canary = _process_start

# F-PROD-1 (2026-09-16): the grace window below returns 200 UNCONDITIONALLY so
# Railway cannot kill a replica that is still booting. That is also the window
# in which a replica that will NEVER boot looks perfectly healthy -- the same
# defect class as the executor-starvation gap above (a liveness signal that
# reports 200 through a failure it structurally cannot see). Set when the real
# lifespan raises, and checked BEFORE the grace short-circuit, so a crashed
# boot surfaces 503 immediately instead of being masked for _GRACE_SECONDS.
_lifespan_failed = False

# Opt-in readiness gate for /api/healthz (2026-11-27 scaling audit). Off by default so the
# 180 s grace behaviour is unchanged. On: healthz stays 503 until the real app finished
# startup (app.dependencies.startup_complete), in the grace window AND after it. Railway then
# keeps the old container serving until the new one can actually answer /api/chat; a boot that
# never finishes fails the deploy instead of being promoted.
_READY_GATE = os.environ.get("HEALTHZ_REQUIRE_READY", "").strip().lower() in {"1", "true", "yes"}


def _app_ready() -> bool:
    """True once the real app finished startup. Never imports: this runs on the loop while
    the real app is being imported in a thread, so only read the module if already loaded."""
    deps = sys.modules.get("app.dependencies") if _real_app is not None else None
    return _lifespan_startup_done and bool(getattr(deps, "startup_complete", False))


# Must stay < .railway/railway.ts's deploy healthcheckTimeout (330) — that
# file (healthcheck "/api/healthz", NOT /api/health) is the IaC source since
# railway.json was removed 2026-09-19. Railway keeps retrying the healthcheck
# for that whole budget, so the window between this grace expiring and the app
# finishing boot correctly reports 503 ("not ready yet") rather than a deploy
# failure. Raising this to 330 would instead blanket the ENTIRE healthcheck
# budget in unconditional 200s, which is exactly the masking this file's
# _lifespan_failed flag exists to prevent -- do not.
_GRACE_SECONDS = 180
_HEARTBEAT_INTERVAL_S = 5
_HEARTBEAT_STALE_S = 30
# RP-A10/RP-B1: how long the heartbeat/executor canary may stay continuously
# stale (post-grace, startup done) before the wrapper exits non-zero so the
# platform restart policy fires. Two heartbeat intervals of grace beyond the
# 30s staleness threshold: a transient stall recovers, a wedged worker does
# not. Sustained, not instantaneous — a single stale read only arms the timer.
_STALE_EXIT_AFTER_S = 60
# First monotonic timestamp at which post-grace health was already unhealthy
# (None = currently healthy). Module-global so the ASGI handler can track
# sustained staleness across probes.
_first_unhealthy_at: float | None = None
_watchdog_started = False
# ponytail: plain module constant, matching _HEARTBEAT_STALE_S above, not a
# pydantic setting -- this wrapper deliberately imports nothing from
# app.config at module scope so it keeps answering /api/healthz even if the
# real app's settings fail to load. Promote to a setting if this ever needs
# to be tuned per-environment.
_EXECUTOR_CANARY_TIMEOUT_S = 10
# How long a request that arrives before the real app is loaded waits for it (cold start
# after Railway sleep) before getting a 503. Boot takes ~25 s; keep it under Railway's edge timeout.
_COLD_START_WAIT_S = 45.0
_CELERY_ALLOWED_QUEUES = frozenset({"ingestion", "embedding", "indexing", "okf", "memory"})
# Cost mode: Railway cron starts a `celery-on-demand` run every 5 minutes. It
# exits at once when nothing is queued, otherwise runs a worker until the queues
# stay empty. It also drains `celery`, the default queue that holds unrouted
# tasks (retention, win-back, cache prune); it is kept out of
# _CELERY_ALLOWED_QUEUES because ops_gauges.CELERY_QUEUES must match that set.
_ON_DEMAND_DEFAULT_QUEUES = "ingestion,embedding,indexing,okf,memory"
_ON_DEMAND_EXTRA_QUEUES = ["celery"]
_ON_DEMAND_POLL_S = 15
_ON_DEMAND_IDLE_POLLS = 4  # consecutive empty polls (~1 min) before the worker stops
# Above task_time_limit (2400 s); stops a stale `unacked` entry holding the worker up.
_ON_DEMAND_MAX_RUNTIME_S = 4 * 3600
# What the once-a-day enqueue inside `celery-on-demand` sends: the tasks beat would have scheduled.
_SCHEDULED_TASKS = (
    "tasks.cancel_flow_tasks.dispatch_due_win_back_emails",
    "tasks.layered_memory_tasks.process_batched_memories",
    "tasks.memory_outbox_tasks.drain_memory_outbox",
    "tasks.cache_maintenance_tasks.prune_semantic_cache",
    "tasks.retention_tasks.cleanup_retention_data",
    "tasks.ingest_tasks.sweep_stale_ingest_jobs",
    "tasks.event_media_tasks.purge_ended_event_media",
)


def _parse_celery_queues(value: str) -> list[str]:
    queues = [queue.strip() for queue in value.split(",") if queue.strip()]
    invalid = sorted(set(queues) - _CELERY_ALLOWED_QUEUES)
    if not queues or invalid:
        raise ValueError(
            "CELERY_QUEUES must contain only non-empty values from "
            f"{sorted(_CELERY_ALLOWED_QUEUES)}; invalid={invalid}"
        )
    return queues


def _parse_celery_concurrency(value: str) -> int:
    try:
        concurrency = int(value)
    except ValueError as exc:
        raise ValueError("CELERY_CONCURRENCY must be an integer from 1 to 32") from exc
    if not 1 <= concurrency <= 32:
        raise ValueError("CELERY_CONCURRENCY must be an integer from 1 to 32")
    return concurrency


# RP-A3: uvicorn worker count. Every worker is a separate process with its own
# chat admission semaphore, in-process coalescer, and hot cache — so the
# configured max_concurrent_chat cap is PER WORKER (effective replica cap is
# roughly workers x max_concurrent_chat), and model memory is duplicated per
# worker. Default 1: this service is async single-process by design (lessons
# RULE 11 — BGE-M3-class models duplicate ~550MB+ per worker), matching
# backend/Dockerfile.railway:104 (ENV WEB_CONCURRENCY=1) while backend/Dockerfile:147
# (plain uvicorn CMD, no --workers flag) stays single-process. Note for QO-10:
# root docker-compose.prod.yml:92 sets WEB_CONCURRENCY=2, so the effective cap
# there is 2 x max_concurrent_chat.
_WEB_CONCURRENCY_DEFAULT = 1


def get_web_concurrency(env=None) -> int:
    """Read the uvicorn worker count from WEB_CONCURRENCY (RP-A3).

    Unset or blank → 1 (the default). Anything else must be an integer >= 1;
    garbage fails closed with SystemExit (fail-fast at boot, never a silent
    default that hides a misconfigured environment).
    """
    source = env if env is not None else os.environ
    raw = source.get("WEB_CONCURRENCY", "")
    if raw is None or str(raw).strip() == "":
        return _WEB_CONCURRENCY_DEFAULT
    try:
        workers = int(str(raw).strip())
    except ValueError as exc:
        raise SystemExit(
            f"WEB_CONCURRENCY must be an integer >= 1, got {raw!r}; "
            "refusing to start rather than guessing a worker count."
        ) from exc
    if workers < 1:
        raise SystemExit(
            f"WEB_CONCURRENCY must be an integer >= 1, got {raw!r}; "
            "refusing to start rather than guessing a worker count."
        )
    return workers


# 2026-11-27: one live process (WEB_CONCURRENCY=1) read ~2.6 GB RSS in the container and
# averaged 2.7 GB on Railway; with 2 workers the 7-day average was 4.8 GB (~2.4 GB each).
# The 0.5 GB libraries + 0.9 GB BGE-M3 INT8 session + reranker split is an estimate, not a
# per-component measurement. Railway bills memory, so extra workers duplicate it. Loading the
# ONNX session before fork is NOT adopted: one early test hung forked children, but a controlled
# re-test could not reproduce a deadlock, so the cause is unproven (see
# docs/operations/model-memory-sharing-research-2026-11-27.md). Creating the session after fork
# is the safe pattern.
_WORKER_MODEL_MEMORY_GB = 2.5


def model_duplication_warning(workers: int, model_server_url: str) -> str | None:
    """Warning text when WEB_CONCURRENCY > 1 would duplicate the models, else None.

    Not fatal: the owner may choose the cost. The shared model server
    (SERVICE_TYPE=model-server + MODEL_SERVER_URL) is the way around it.
    """
    if workers <= 1 or model_server_url:
        return None
    return (
        f"WEB_CONCURRENCY={workers} with MODEL_SERVER_URL empty: every worker loads its own "
        f"BGE-M3 + reranker, measured ~{_WORKER_MODEL_MEMORY_GB} GB per worker process, so "
        f"~{workers * _WORKER_MODEL_MEMORY_GB:.1f} GB total for the API service. Run the models "
        "once in a separate service (SERVICE_TYPE=model-server) and set MODEL_SERVER_URL + "
        "MODEL_SERVER_TOKEN to avoid this; see docs/operations/shared-model-server.md."
    )


def _run_model_server() -> int:
    """SERVICE_TYPE=model-server: one process that loads the models for the API workers."""
    import uvicorn

    from app.config import settings
    from services.model_server.app import create_app

    if not settings.model_server_token:
        logger.error("MODEL_SERVER_TOKEN must be set; refusing to start the model server")
        return 1
    logger.info("Starting Mukthi Guru model server on port %s (single process)", port)
    # "::" is dual-stack on Linux (IPv4 too); Railway legacy environments
    # resolve *.railway.internal to IPv6 only.
    uvicorn.run(create_app(), host="::", port=port, workers=1, log_level="info")
    return 0


# NEW-RW-3 (RW-04, 2026-11-06): graceful shutdown of the Celery child.
# This wrapper is PID 1 in the container. Linux ignores SIGTERM for a PID 1
# process that installed no handler, so before this change Railway's SIGTERM
# never reached the Celery child and the later SIGKILL ended it mid-task
# (runbook section 8, G-4). The supervisor below installs a handler, forwards
# the first SIGTERM to the child (Celery warm shutdown for a worker, a normal
# stop for beat), and waits for it to exit.
#
# The grace period must stay BELOW Railway's RAILWAY_DEPLOYMENT_DRAINING_SECONDS
# for that service (worker 60, beat 30 in .railway/railway.ts), or Railway
# SIGKILLs this wrapper before it can SIGKILL a stuck child itself. A task
# that is killed is redelivered because task_acks_late=True (celery_config.py).
_CELERY_SHUTDOWN_GRACE_DEFAULT_S = 25.0
_CELERY_SHUTDOWN_GRACE_MAX_S = 3600.0


def get_celery_shutdown_grace_s(env=None) -> float:
    """Seconds the wrapper waits for the Celery child after SIGTERM.

    Unset or blank uses the default. Garbage fails closed with SystemExit,
    like WEB_CONCURRENCY above.
    """
    source = env if env is not None else os.environ
    raw = source.get("CELERY_SHUTDOWN_GRACE_SECONDS", "")
    if raw is None or str(raw).strip() == "":
        return _CELERY_SHUTDOWN_GRACE_DEFAULT_S
    try:
        value = float(str(raw).strip())
    except ValueError as exc:
        raise SystemExit(
            f"CELERY_SHUTDOWN_GRACE_SECONDS must be a number > 0 and <= "
            f"{_CELERY_SHUTDOWN_GRACE_MAX_S:g}, got {raw!r}"
        ) from exc
    if not 0 < value <= _CELERY_SHUTDOWN_GRACE_MAX_S:
        raise SystemExit(
            f"CELERY_SHUTDOWN_GRACE_SECONDS must be a number > 0 and <= "
            f"{_CELERY_SHUTDOWN_GRACE_MAX_S:g}, got {raw!r}"
        )
    return value


def build_celery_beat_command() -> list[str]:
    """Command for the dedicated Beat service.

    The image runs as `appuser`, but `/app` is created root-owned by WORKDIR,
    and Beat's default schedule file (`celerybeat-schedule`) is written to the
    working directory. `/app/data` is chowned to appuser in Dockerfile.railway,
    so the schedule file goes there. [INF]: not yet proven on a live Railway
    run; the change is safe either way because the directory exists.
    """
    return [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "celery_config",
        "beat",
        "--loglevel=INFO",
        "--schedule",
        "/app/data/celerybeat-schedule",
    ]


def _exit_code_for(returncode: int) -> int:
    """Map a subprocess return code to a process exit code (never negative)."""
    return 128 - returncode if returncode < 0 else returncode


def _supervise_celery_child(cmd, *, label: str, grace_s: float, on_started=None) -> int:
    """Run `cmd` as a child, forward SIGTERM/SIGINT to it, and return its exit code.

    - First SIGTERM or SIGINT: forwarded once as SIGTERM. A running Celery task
      finishes (warm shutdown); the wrapper waits up to `grace_s`.
    - Later signals during the drain are logged and ignored. They are not
      forwarded again and do not shorten the grace period.
    - If the child is still alive after `grace_s`, it gets SIGKILL and the
      wrapper exits non-zero, so the platform does not read a forced kill as a
      clean stop.
    - The handler is installed BEFORE the child starts, so a signal that
      arrives during start-up is not lost.

    Must run on the main thread (Python only allows signal handlers there).
    """
    state: dict = {"child": None, "terminating": False, "term_at": None}

    def _forward() -> None:
        child = state["child"]
        if child is None or child.poll() is not None:
            return
        try:
            child.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass

    def _handler(signum, _frame) -> None:
        if state["terminating"]:
            logger.warning(
                "%s: signal %s received while already draining; ignoring (not forwarded again)",
                label,
                signum,
            )
            return
        state["terminating"] = True
        state["term_at"] = time.monotonic()
        logger.info("%s: signal %s received; forwarding SIGTERM to the child", label, signum)
        _forward()

    previous = {sig: signal.signal(sig, _handler) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        child = subprocess.Popen(cmd)
        state["child"] = child
        if state["terminating"]:
            # The signal arrived between handler install and Popen returning.
            _forward()
        if on_started is not None:
            on_started(child)
        while True:
            try:
                returncode = child.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                term_at = state["term_at"]
                if term_at is not None and (time.monotonic() - term_at) >= grace_s:
                    logger.error(
                        "%s: child still running %.0fs after SIGTERM; sending SIGKILL "
                        "(an unacknowledged task is redelivered, task_acks_late=True)",
                        label,
                        grace_s,
                    )
                    child.kill()
                    child.wait()
                    return 1
        return _exit_code_for(returncode)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _stale_exit_due(now: float, first_unhealthy_at: float | None) -> tuple[bool, float]:
    """Decide whether a stale canary must now exit the process (RP-A10/RP-B1).

    Returns ``(should_exit, first_unhealthy_at)``. The first stale
    observation only arms the timer (returns False with now as the new
    baseline); the process exits only once staleness has been CONTINUOUS for
    _STALE_EXIT_AFTER_S. Callers reset the baseline to None on any healthy
    probe so a recovered worker never exits on old staleness.
    """
    if first_unhealthy_at is None:
        return False, now
    return (now - first_unhealthy_at) >= _STALE_EXIT_AFTER_S, first_unhealthy_at


def _exit_if_canary_stays_stale() -> None:
    """One watchdog tick: exit non-zero when a canary stays stale (RP-A10/RP-B1).

    Called ONLY by the watchdog thread below — never by the /api/healthz
    handler. The handler reports status (200/503); exiting is the thread's
    job, on its own clock, because Railway probes health at deploy start and
    never again, and a wedged event loop cannot run a request handler at all.
    `_first_unhealthy_at` therefore has a single writer. No-op until the real
    lifespan finished starting, inside the boot grace window, and during
    graceful shutdown (the lifespan zeroes both canaries on its way out; that
    is not a wedge). A healthy tick clears the timer, so the exit fires only
    after staleness that was continuous for _STALE_EXIT_AFTER_S.
    """
    global _first_unhealthy_at
    if not _lifespan_startup_done or _shutdown_event.is_set():
        return
    now = time.monotonic()
    if (now - _process_start) < _GRACE_SECONDS:
        return
    stale = (now - _last_heartbeat) > _HEARTBEAT_STALE_S or (
        now - _last_executor_canary
    ) > _HEARTBEAT_STALE_S
    if not stale:
        _first_unhealthy_at = None
        return
    should_exit, _first_unhealthy_at = _stale_exit_due(now, _first_unhealthy_at)
    if should_exit:
        logger.critical(
            "Heartbeat/executor canary stale for >%ss — exiting "
            "non-zero so the platform restart policy fires "
            "(a 503 alone never restarts a live replica).",
            _STALE_EXIT_AFTER_S,
        )
        os._exit(1)


def _stale_exit_watchdog() -> None:
    """Daemon thread driving the stale-exit check on a fixed cadence.

    The check cannot live only in the /api/healthz handler: Railway probes
    health at deploy start and never again, so nothing would call it on a
    live replica, and a wedged event loop cannot run a request handler at
    all. A thread needs neither a probe nor the loop.
    """
    while not _shutdown_event.is_set():
        time.sleep(_HEARTBEAT_INTERVAL_S)
        _exit_if_canary_stays_stale()


def run_preflight_startup_hygiene() -> dict[str, int]:
    """Purge stale temporary files and release dead distributed locks on container boot."""
    import glob

    cleaned = {"temp_files": 0, "stale_locks": 0}
    for pattern in ["/tmp/*.pid", "/tmp/*.lock", "/tmp/railway_readiness*.json"]:
        for p in glob.glob(pattern):
            try:
                os.remove(p)
                cleaned["temp_files"] += 1
            except Exception:
                pass

    # If CLEANUP_ON_STARTUP or REBUILD_CLEANUP is requested, clear stale locks in Redis
    if os.environ.get("CLEANUP_ON_STARTUP", "").lower() in ("1", "true", "yes") or os.environ.get(
        "REBUILD_CLEANUP", ""
    ).lower() in ("1", "true", "yes"):
        try:
            redis_url = os.environ.get("REDIS_URL")
            if redis_url:
                import redis

                r = redis.from_url(redis_url, socket_timeout=3, socket_connect_timeout=3)
                for lock_pat in ["mukthiguru:lock:*", "maintenance_lock:*", "ingest_lock:*"]:
                    keys = list(r.scan_iter(match=lock_pat, count=50))
                    if keys:
                        r.delete(*keys)
                        cleaned["stale_locks"] += len(keys)
                        logger.info(
                            "Startup hygiene: cleared %d stale locks matching %s",
                            len(keys),
                            lock_pat,
                        )
        except Exception as exc:
            logger.warning("Startup hygiene lock clearance non-fatal warning: %s", exc)

    if cleaned["temp_files"] > 0 or cleaned["stale_locks"] > 0:
        logger.info("Pre-flight startup hygiene complete: %s", cleaned)
    return cleaned


_OK_BODY = b'{"ok":true,"status":"alive"}'
_OK_HEADERS = [
    (b"content-type", b"application/json"),
    (b"content-length", str(len(_OK_BODY)).encode()),
]
_NOT_READY_BODY = b'{"ok":false,"status":"starting"}'
_NOT_READY_HEADERS = [
    (b"content-type", b"application/json"),
    (b"content-length", str(len(_NOT_READY_BODY)).encode()),
]


async def _run_heartbeat_pump():
    global _last_heartbeat
    try:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
            _last_heartbeat = time.monotonic()
    except asyncio.CancelledError:
        pass


async def _run_executor_canary_pump():
    """Probe the shared default thread-pool executor for starvation.

    See the P2-OPS-1 comment on `_last_executor_canary` above for why the
    heartbeat pump alone cannot see this failure mode.
    """
    global _last_executor_canary
    try:
        while True:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(lambda: None), timeout=_EXECUTOR_CANARY_TIMEOUT_S
                )
                _last_executor_canary = time.monotonic()
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                logger.warning(
                    "Executor canary timed out after %ss -- default thread pool "
                    "may be starved (stuck synchronous calls holding all workers)",
                    _EXECUTOR_CANARY_TIMEOUT_S,
                )
            except Exception:
                logger.exception("Executor canary probe failed")
            await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
    except asyncio.CancelledError:
        pass


async def _run_memory_trimmer_pump():
    """Periodically trim process memory (malloc_trim) on Linux to release idle heap pages back to OS.

    Python's glibc allocator retains freed memory pages in its arena bins; without
    malloc_trim(0), process RSS stays pegged at peak allocation even after gc.collect().
    """
    import gc

    try:
        import ctypes

        _libc = ctypes.CDLL("libc.so.6")
        _has_trim = hasattr(_libc, "malloc_trim")
    except Exception:
        _has_trim = False

    try:
        while True:
            await asyncio.sleep(120)
            gc.collect()
            if _has_trim:
                try:
                    _libc.malloc_trim(0)
                except Exception:
                    pass
    except asyncio.CancelledError:
        pass


async def _run_real_lifespan():
    global _real_app, _lifespan_startup_done, _last_heartbeat, _last_executor_canary
    global _lifespan_failed

    def _import_real_app():
        from app.main import app, lifespan

        return app, lifespan

    # Initialized BEFORE any await/task creation so the cleanup path can never
    # hit an unbound pump (e.g. when the import above raises).
    pump = None
    executor_pump = None
    memory_pump = None
    try:
        real_app, real_lifespan = await asyncio.to_thread(_import_real_app)
        _real_app = real_app
        logger.info("Real app imported, starting lifespan...")

        # P1-OPS-5: pump the heartbeat while the real lifespan is up. If this
        # task is cancelled (shutdown) or the event loop wedges, the pump
        # stops and healthz eventually reports 503 post-grace.
        pump = asyncio.create_task(_run_heartbeat_pump())
        # P2-OPS-1: pump the executor canary alongside it -- catches thread-pool
        # starvation the event-loop-only heartbeat above cannot see.
        executor_pump = asyncio.create_task(_run_executor_canary_pump())
        # Memory pump: periodically trim idle glibc heap pages back to the kernel
        memory_pump = asyncio.create_task(_run_memory_trimmer_pump())

        async with real_lifespan(real_app):
            _lifespan_startup_done = True
            logger.info("Real app lifespan yielded — fully initialized")
            global _watchdog_started
            if not _watchdog_started:
                _watchdog_started = True
                threading.Thread(
                    target=_stale_exit_watchdog, name="stale-exit-watchdog", daemon=True
                ).start()
            import gc

            gc.collect()
            try:
                import ctypes

                _libc = ctypes.CDLL("libc.so.6")
                if hasattr(_libc, "malloc_trim"):
                    _libc.malloc_trim(0)
            except Exception:
                pass
            logger.info(
                "Post-warmup garbage collection & malloc_trim complete (memory freed for steady state)"
            )
            await _shutdown_event.wait()
            logger.info("Real lifespan exiting on shutdown event")
    except asyncio.CancelledError:
        logger.warning("Real lifespan task cancelled during startup")
    except BaseException:
        # F-PROD-1: mark the boot as failed so /api/healthz reports 503 even
        # inside the grace window. Without this a replica whose lifespan raised
        # on startup (bad env var, unreachable Qdrant, import error) served 200
        # for the full _GRACE_SECONDS and Railway marked the deploy healthy.
        _lifespan_failed = True
        logger.exception("Fatal error in real lifespan")
        raise
    finally:
        # P1-OPS-5/P2-OPS-1: stop both pumps and force their timestamps stale
        # so post-grace healthz returns 503 once the lifespan is down.
        if pump is not None:
            pump.cancel()
        if executor_pump is not None:
            executor_pump.cancel()
        if memory_pump is not None:
            memory_pump.cancel()
        _last_heartbeat = 0.0
        _last_executor_canary = 0.0


async def _send_http(send, status, headers, body):
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def app(scope, receive, send):
    path = scope.get("path", "")

    if scope["type"] == "lifespan":
        # ASGI lifespan protocol: consume startup message BEFORE responding.
        # Older code omitted this receive(), leaving a stale lifespan.startup in
        # the queue — the next receive() got startup instead of shutdown,
        # immediately setting _shutdown_event and killing the real lifespan
        # the instant it yielded.  Fixes the "starts then instantly shuts down"
        # cycle on Railway.  See start_railway.py::_REWRITE_RATIONALE
        msg = await receive()
        assert msg["type"] == "lifespan.startup", f"expected startup, got {msg['type']}"

        await send({"type": "lifespan.startup.complete"})

        lifespan_task = asyncio.create_task(_run_real_lifespan())

        msg = await receive()
        assert msg["type"] == "lifespan.shutdown", f"expected shutdown, got {msg['type']}"
        logger.info("Wrapper received shutdown signal — notifying real lifespan")

        _shutdown_event.set()

        try:
            await asyncio.wait_for(lifespan_task, timeout=60)
        except TimeoutError:
            logger.warning("Real lifespan shutdown timed out after 60s")
        except asyncio.CancelledError:
            logger.warning("Real lifespan task was cancelled")

        await send({"type": "lifespan.shutdown.complete"})
        return

    if path == "/api/healthz":
        within_grace = (time.monotonic() - _process_start) < _GRACE_SECONDS
        if _lifespan_failed:
            # F-PROD-1: checked FIRST, ahead of the grace short-circuit below.
            # A boot that has already raised is never "still starting", and a
            # grace window that outlives the crash is a healthcheck reporting
            # 200 through a dead app.
            healthy = False
        elif within_grace:
            # During the grace window, 200 unconditionally — Railway must not
            # kill the replica while the real app is still initializing.
            # With HEALTHZ_REQUIRE_READY the same readiness test as post-grace applies.
            healthy = _app_ready() if _READY_GATE else True
        else:
            # Post-grace: healthy only if the real lifespan completed AND both
            # the heartbeat AND the executor canary are fresh. Stale heartbeat
            # means the event loop itself wedged (Qdrant/Redis/LLM down,
            # lifespan exited); stale executor canary means the loop is fine
            # but the shared default thread pool is starved (see P2-OPS-1
            # above) -- the failure mode that left chat hung while healthz
            # kept serving 200s.
            #
            # RP-A10/RP-B1: EITHER stale canary surfaces 503 here. The process
            # exit on CONTINUOUS staleness is the watchdog thread's job alone
            # (it runs _exit_if_canary_stays_stale on its own clock): a
            # post-deploy 503 restarts nothing (Railway probes health at
            # deploy start only; restarts fire on non-zero process exit), and
            # a wedged loop cannot run this handler at all. This handler only
            # reports; it never exits. Boot failures (_lifespan_failed)
            # intentionally do NOT exit here: they are already fatal to the
            # lifespan task, and changing that is a separate owner decision.
            heartbeat_stale = (time.monotonic() - _last_heartbeat) > _HEARTBEAT_STALE_S
            executor_stale = (time.monotonic() - _last_executor_canary) > _HEARTBEAT_STALE_S
            healthy = _lifespan_startup_done and not heartbeat_stale and not executor_stale
            if _READY_GATE:
                healthy = healthy and _app_ready()
        if healthy:
            await _send_http(send, 200, _OK_HEADERS, _OK_BODY)
        else:
            await _send_http(send, 503, _NOT_READY_HEADERS, _NOT_READY_BODY)
        return

    if _real_app is None:
        # Cold start: Railway wakes a sleeping service on the first request. Hold it
        # until the real app is loaded (~25 s) instead of answering 503, which carries
        # no CORS headers and so shows up in the browser as an opaque "failed (—)".
        deadline = time.monotonic() + _COLD_START_WAIT_S
        while _real_app is None and not _lifespan_failed and time.monotonic() < deadline:
            await asyncio.sleep(0.25)
    if _real_app is None:
        await _send_http(send, 503, _NOT_READY_HEADERS, _NOT_READY_BODY)
        return

    await _real_app(scope, receive, send)


def celery_backlog(client, queues) -> int:
    """Queued plus in-flight Celery messages. With task_acks_late=True a running
    task stays in the Redis `unacked` hash until it finishes."""
    return sum(int(client.llen(q)) for q in queues) + int(client.hlen("unacked"))


def _run_on_demand_worker() -> int:
    import redis

    from celery_config import CELERY_BROKER_URL

    queues = (
        _parse_celery_queues(os.environ.get("CELERY_QUEUES", _ON_DEMAND_DEFAULT_QUEUES))
        + _ON_DEMAND_EXTRA_QUEUES
    )
    concurrency = _parse_celery_concurrency(os.environ.get("CELERY_CONCURRENCY", "1"))
    client = redis.Redis.from_url(CELERY_BROKER_URL)
    # Once per 24 h (Redis SET NX): send the tasks beat used to schedule, so
    # no always-on beat service is needed. They land in the queues checked below.
    if client.set("celery:daily-enqueue", "1", nx=True, ex=86400):
        _enqueue_scheduled_tasks()
    if celery_backlog(client, queues) == 0:
        logger.info("celery-on-demand: no queued work, exiting")
        return 0

    cmd = [
        sys.executable, "-m", "celery", "-A", "celery_config", "worker",
        "-Q", ",".join(queues), f"--concurrency={concurrency}",
        "--without-gossip", "--without-mingle", "--without-heartbeat", "-l", "info",
    ]  # fmt: skip

    def _stop_when_drained(child) -> None:
        idle, started = 0, time.monotonic()
        while child.poll() is None:
            time.sleep(_ON_DEMAND_POLL_S)
            try:
                idle = idle + 1 if celery_backlog(client, queues) == 0 else 0
            except redis.RedisError:
                logger.warning("celery-on-demand: backlog check failed", exc_info=True)
                idle = 0
            if (
                idle >= _ON_DEMAND_IDLE_POLLS
                or time.monotonic() - started > _ON_DEMAND_MAX_RUNTIME_S
            ):
                logger.info("celery-on-demand: queues drained (or runtime cap hit), stopping")
                os.kill(os.getpid(), signal.SIGTERM)  # _supervise_celery_child forwards it
                return

    return _supervise_celery_child(
        cmd,
        label="celery-on-demand",
        grace_s=get_celery_shutdown_grace_s(),
        on_started=lambda child: threading.Thread(
            target=_stop_when_drained, args=(child,), daemon=True
        ).start(),
    )


def _enqueue_scheduled_tasks() -> int:
    from celery_config import celery_app

    for name in _SCHEDULED_TASKS:
        celery_app.send_task(name)
        logger.info("celery-enqueue: sent %s", name)
    return 0


def main() -> None:
    run_preflight_startup_hygiene()

    # A dedicated Beat service schedules durable-memory recovery.
    if os.environ.get("SERVICE_TYPE") == "celery-beat":
        logger.info("Starting Mukthi Guru Celery Beat scheduler")
        sys.exit(
            _supervise_celery_child(
                build_celery_beat_command(),
                label="celery-beat",
                grace_s=get_celery_shutdown_grace_s(),
            )
        )

    # Opt-in shared model server (default OFF): one copy of BGE-M3 + reranker
    # for several API workers; see docs/operations/shared-model-server.md.
    if os.environ.get("SERVICE_TYPE") == "model-server":
        sys.exit(_run_model_server())

    # Railway cron modes (cost): no always-on worker or beat.
    if os.environ.get("SERVICE_TYPE") == "celery-on-demand":
        sys.exit(_run_on_demand_worker())

    # When SERVICE_TYPE=celery, start the Celery worker instead of the ASGI server.
    if os.environ.get("SERVICE_TYPE") == "celery":
        logger.info("Starting Mukthi Guru Celery worker")
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        try:
            queues = _parse_celery_queues(
                os.environ.get("CELERY_QUEUES", "ingestion,embedding,indexing,okf,memory")
            )
            celery_concurrency = _parse_celery_concurrency(
                os.environ.get("CELERY_CONCURRENCY", "2")
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        cmd = [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "celery_config",
            "worker",
            "-Q",
            ",".join(queues),
            f"--concurrency={celery_concurrency}",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "-l",
            "info",
        ]
        worker_holder: dict = {}

        class _WorkerHealthHandler(BaseHTTPRequestHandler):
            """Small liveness endpoint for the non-HTTP Celery process."""

            def _respond(self):
                if self.path != "/api/healthz":
                    body = b'{"ok":false,"status":"not-found"}'
                    status = 404
                elif worker_holder["child"].poll() is None:
                    body = b'{"ok":true,"status":"alive"}'
                    status = 200
                else:
                    body = b'{"ok":false,"status":"stopped"}'
                    status = 503
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            do_GET = _respond
            do_HEAD = _respond

            def log_message(self, _format, *_args):
                return

        health_server = ThreadingHTTPServer(("0.0.0.0", port), _WorkerHealthHandler)
        health_server.daemon_threads = True

        def _start_health(child) -> None:
            worker_holder["child"] = child
            threading.Thread(
                target=health_server.serve_forever,
                name="celery-health-server",
                daemon=True,
            ).start()

        # NEW-RW-3: SIGTERM is forwarded to the Celery child (warm shutdown).
        # Health stays "alive" while the child drains, then turns 503.
        return_code = 1
        try:
            return_code = _supervise_celery_child(
                cmd,
                label="celery-worker",
                grace_s=get_celery_shutdown_grace_s(),
                on_started=_start_health,
            )
        finally:
            if worker_holder:
                health_server.shutdown()
            health_server.server_close()
        sys.exit(return_code)

    logger.info("Starting Mukthi Guru backend on port %s", port)

    import uvicorn

    # Trust the platform edge's X-Forwarded-For so rate-limit client IPs are the
    # real seeker, not Railway's single edge IP (otherwise every user shares one
    # bucket and five failed logins lock out everyone). This entrypoint only runs
    # behind Railway's proxy, so trusting the forwarded header here is the gate —
    # local dev runs `uvicorn app.main:app` directly and keeps the socket peer.
    # The allowlist comes from app.config (FORWARDED_ALLOW_IPS) and must be an
    # explicit non-wildcard value: "*" would let any peer spoof a client IP past
    # rate limiting, so startup fails instead of running with a wildcard.
    from app.config import settings

    forwarded_allow_ips = settings.forwarded_allow_ips
    if not forwarded_allow_ips or forwarded_allow_ips.strip() == "*":
        logger.error(
            "FORWARDED_ALLOW_IPS must be set to an explicit non-wildcard proxy "
            "allowlist (e.g. '10.0.0.0/8' on Railway); refusing to start with "
            "forwarded-header trust missing or set to '*'. Set FORWARDED_ALLOW_IPS "
            "in the service environment and redeploy."
        )
        raise SystemExit(1)

    uvicorn_workers = get_web_concurrency()
    duplication_warning = model_duplication_warning(uvicorn_workers, settings.model_server_url)
    if duplication_warning:
        logger.warning("MEMORY WARNING: %s", duplication_warning)
    # RP-A3: the chat admission cap (max_concurrent_chat) is enforced per
    # worker process, so log both numbers together — the replica-wide ceiling
    # is roughly uvicorn_workers x max_concurrent_chat. /api/health reports
    # the same pair (chat_backpressure.workers + max_concurrent, per_worker).
    logger.info(
        "Starting Mukthi Guru backend on port %s with %d uvicorn worker(s); "
        "chat admission cap %d per worker",
        port,
        uvicorn_workers,
        settings.max_concurrent_chat,
    )
    uvicorn.run(
        "start_railway:app",
        host="0.0.0.0",
        port=port,
        workers=uvicorn_workers,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
