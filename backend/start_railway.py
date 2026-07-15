import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

port = int(os.environ.get("PORT", 8000))

_real_app = None
_lifespan_startup_done = False
_lifespan_task: asyncio.Task | None = None
_shutdown_event = asyncio.Event()

_health_body = b'{"ok":true,"status":"alive"}'
_health_headers = [
    (b"content-type", b"application/json"),
    (b"content-length", str(len(_health_body)).encode()),
]


async def _run_real_lifespan(app):
    global _lifespan_startup_done
    try:
        async with app.router.lifespan_context(app):
            _lifespan_startup_done = True
            await _shutdown_event.wait()
    except Exception as e:
        logger.error("Real app lifespan failed: %s", e)
        raise


async def _get_real_app():
    global _real_app, _lifespan_task
    if _real_app is None:
        logger.info("Loading real FastAPI app...")
        from app.main import app as real_app
        _real_app = real_app
        _lifespan_task = asyncio.create_task(_run_real_lifespan(real_app))
        logger.info("Real FastAPI app loaded, lifespan scheduled")
    return _real_app


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                _shutdown_event.set()
                if _lifespan_task is not None:
                    try:
                        await asyncio.wait_for(_lifespan_task, timeout=30)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
                await send({"type": "lifespan.shutdown.complete"})
                break
        return

    path = scope.get("path", "")

    if path in ("/api/healthz", "/api/health"):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": _health_headers,
        })
        await send({"type": "http.response.body", "body": _health_body})
        return

    real_app = await _get_real_app()
    await real_app(scope, receive, send)


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Railway health-first ASGI wrapper on port %s", port)
    uvicorn.run(
        "start_railway:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        log_level="info",
    )
