"""
Railway health-first ASGI wrapper.

Sends lifespan.startup.complete immediately so uvicorn enters its main loop
and accepts connections quickly. The real FastAPI app's lifespan runs as a
background task. Health checks (/api/healthz) respond fast:

  - /api/healthz → 200 within a 180s grace period, then reflects real readiness
    (healthy while the real app's lifespan heartbeat is fresh; 503 when it goes
    stale >30s or the lifespan never completed — Railway restarts on 503)
  - All other paths → proxied to the real app once loaded, else 503

On shutdown, signals the real lifespan to exit, then waits for cleanup.
"""

# BUILD BUSTER: 2026-07-17T12:15 — force new Railway build with ASGI protocol fix

import asyncio
import logging
import os
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

# Must stay <= railway.json's deploy.healthcheckTimeout (330). Railway keeps
# retrying the healthcheck for that whole budget, so the window between this
# grace expiring and the app finishing boot correctly reports 503 ("not ready
# yet") rather than a deploy failure. Raising this to 330 would instead blanket
# the ENTIRE healthcheck budget in unconditional 200s, which is exactly the
# masking this file's _lifespan_failed flag exists to prevent -- do not.
_GRACE_SECONDS = 180
_HEARTBEAT_INTERVAL_S = 5
_HEARTBEAT_STALE_S = 30
# ponytail: plain module constant, matching _HEARTBEAT_STALE_S above, not a
# pydantic setting -- this wrapper deliberately imports nothing from
# app.config at module scope so it keeps answering /api/healthz even if the
# real app's settings fail to load. Promote to a setting if this ever needs
# to be tuned per-environment.
_EXECUTOR_CANARY_TIMEOUT_S = 10
_CELERY_ALLOWED_QUEUES = frozenset({"ingestion", "embedding", "indexing", "okf", "memory"})


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

        async with real_lifespan(real_app):
            _lifespan_startup_done = True
            logger.info("Real app lifespan yielded — fully initialized")
            import gc

            gc.collect()
            logger.info("Post-warmup garbage collection complete (memory freed for steady state)")
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
            healthy = True
        else:
            # Post-grace: healthy only if the real lifespan completed AND both
            # the heartbeat AND the executor canary are fresh. Stale heartbeat
            # means the event loop itself wedged (Qdrant/Redis/LLM down,
            # lifespan exited); stale executor canary means the loop is fine
            # but the shared default thread pool is starved (see P2-OPS-1
            # above) -- the failure mode that left chat hung while healthz
            # kept serving 200s. Either one surfaces 503 so Railway restarts
            # the replica instead of serving dead traffic.
            heartbeat_stale = (time.monotonic() - _last_heartbeat) > _HEARTBEAT_STALE_S
            executor_stale = (time.monotonic() - _last_executor_canary) > _HEARTBEAT_STALE_S
            healthy = _lifespan_startup_done and not heartbeat_stale and not executor_stale
        if healthy:
            await _send_http(send, 200, _OK_HEADERS, _OK_BODY)
        else:
            await _send_http(send, 503, _NOT_READY_HEADERS, _NOT_READY_BODY)
        return

    if _real_app is None:
        await _send_http(send, 503, _NOT_READY_HEADERS, _NOT_READY_BODY)
        return

    await _real_app(scope, receive, send)


if __name__ == "__main__":
    run_preflight_startup_hygiene()

    # A dedicated Beat service schedules durable-memory recovery.
    if os.environ.get("SERVICE_TYPE") == "celery-beat":
        logger.info("Starting Mukthi Guru Celery Beat scheduler")
        import subprocess
        import sys

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "celery_config",
                "beat",
                "--loglevel=INFO",
            ]
        )
        sys.exit(proc.returncode)

    # When SERVICE_TYPE=celery, start the Celery worker instead of the ASGI server.
    if os.environ.get("SERVICE_TYPE") == "celery":
        logger.info("Starting Mukthi Guru Celery worker")
        import subprocess
        import sys
        import threading
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
        worker = subprocess.Popen(cmd)

        class _WorkerHealthHandler(BaseHTTPRequestHandler):
            """Small liveness endpoint for the non-HTTP Celery process."""

            def _respond(self):
                if self.path != "/api/healthz":
                    body = b'{"ok":false,"status":"not-found"}'
                    status = 404
                elif worker.poll() is None:
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
        health_thread = threading.Thread(
            target=health_server.serve_forever,
            name="celery-health-server",
            daemon=True,
        )
        health_thread.start()
        try:
            return_code = worker.wait()
        finally:
            health_server.shutdown()
            health_server.server_close()
            if worker.poll() is None:
                worker.terminate()
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

    uvicorn.run(
        "start_railway:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
    )
