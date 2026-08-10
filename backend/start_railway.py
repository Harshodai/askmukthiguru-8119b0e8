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

_GRACE_SECONDS = 180
_HEARTBEAT_INTERVAL_S = 5
_HEARTBEAT_STALE_S = 30

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


async def _run_real_lifespan():
    global _real_app, _lifespan_startup_done

    def _import_real_app():
        from app.main import app, lifespan
        return app, lifespan

    try:
        real_app, real_lifespan = await asyncio.to_thread(_import_real_app)
        _real_app = real_app
        logger.info("Real app imported, starting lifespan...")

        # P1-OPS-5: pump the heartbeat while the real lifespan is up. If this
        # task is cancelled (shutdown) or the event loop wedges, the pump
        # stops and healthz eventually reports 503 post-grace.
        pump = asyncio.create_task(_run_heartbeat_pump())

        async with real_lifespan(real_app):
            _lifespan_startup_done = True
            logger.info("Real app lifespan yielded — fully initialized")
            await _shutdown_event.wait()
            logger.info("Real lifespan exiting on shutdown event")
    except asyncio.CancelledError:
        logger.warning("Real lifespan task cancelled during startup")
    except BaseException:
        logger.exception("Fatal error in real lifespan")
        raise
    finally:
        # P1-OPS-5: stop the pump and force the heartbeat stale so post-grace
        # healthz returns 503 once the lifespan is down.
        pump.cancel()
        _last_heartbeat = 0.0


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
        except asyncio.TimeoutError:
            logger.warning("Real lifespan shutdown timed out after 60s")
        except asyncio.CancelledError:
            logger.warning("Real lifespan task was cancelled")

        await send({"type": "lifespan.shutdown.complete"})
        return

    if path == "/api/healthz":
        within_grace = (time.monotonic() - _process_start) < _GRACE_SECONDS
        if within_grace:
            # During the grace window, 200 unconditionally — Railway must not
            # kill the replica while the real app is still initializing.
            healthy = True
        else:
            # Post-grace: healthy only if the real lifespan completed AND its
            # heartbeat pump is fresh. Stale heartbeat means the app degraded
            # (Qdrant/Redis/LLM down, lifespan exited, event loop wedged) —
            # surface 503 so Railway restarts the replica instead of serving
            # dead traffic.
            heartbeat_stale = (time.monotonic() - _last_heartbeat) > _HEARTBEAT_STALE_S
            healthy = _lifespan_startup_done and not heartbeat_stale
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
    # When SERVICE_TYPE=celery, start the Celery worker instead of the ASGI server.
    if os.environ.get("SERVICE_TYPE") == "celery":
        logger.info("Starting Mukthi Guru Celery worker")
        import subprocess
        import sys
        cmd = [
            sys.executable, "-m", "celery",
            "-A", "celery_config",
            "worker",
            "-Q", "ingestion,embedding,indexing,okf",
            "--concurrency=1",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "-l", "info",
        ]
        proc = subprocess.run(cmd)
        sys.exit(proc.returncode)

    logger.info("Starting Mukthi Guru backend on port %s", port)

    import uvicorn

    uvicorn.run(
        "start_railway:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        log_level="info",
    )
