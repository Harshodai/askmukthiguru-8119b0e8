import asyncio
import functools
import logging
import os

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


def _import_real_app():
    from app.main import app
    return app


async def _run_real_lifespan(app):
    global _lifespan_startup_done
    try:
        async with app.router.lifespan_context(app):
            _lifespan_startup_done = True
            logger.info("Real app lifespan yielded — fully initialized")
            await _shutdown_event.wait()
    except Exception as e:
        logger.error("Real app lifespan failed: %s", e)
        raise


async def _load_real_app_background():
    global _real_app, _lifespan_task
    logger.info("Background: loading real FastAPI app in thread...")
    try:
        real_app = await asyncio.to_thread(_import_real_app)
        _real_app = real_app
        logger.info("Background: real app imported, starting lifespan...")
        _lifespan_task = asyncio.create_task(_run_real_lifespan(real_app))
        logger.info("Background: lifespan task scheduled")
    except Exception as e:
        logger.error("Background: failed to load real app: %s", e)


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await send({"type": "lifespan.startup.complete"})
        asyncio.create_task(_load_real_app_background())
        await receive()
        _shutdown_event.set()
        if _lifespan_task is not None:
            try:
                await asyncio.wait_for(_lifespan_task, timeout=30)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        await send({"type": "lifespan.shutdown.complete"})
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

    if _real_app is None:
        body = b'{"status":"starting","message":"Server still loading"}'
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        await send({"type": "http.response.start", "status": 503, "headers": headers})
        await send({"type": "http.response.body", "body": body})
        return

    await _real_app(scope, receive, send)


if __name__ == "__main__":
    logger.info("Starting Railway health-first wrapper on port %s", port)
    import uvicorn
    uvicorn.run(
        "start_railway:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        log_level="info",
    )
