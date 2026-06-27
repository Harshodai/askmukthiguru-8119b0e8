"""
Mukthi Guru — FastAPI Application Bootstrap

This module is intentionally thin: route groups live in app.api.* modules,
lifespan and middleware wiring live here, and the app is exported as `app`.
"""

import asyncio
import json
import logging
import os
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Fix import paths — run from backend/ directory
sys.path.insert(0, ".")

# Configure threading limits before importing any heavy numerical libraries.
from app.core.threading_config import configure_threading

configure_threading()

# Set Python process memory limit early to prevent runaway OOM crashes.
# Controlled by PYTHON_MEMORY_LIMIT_MB env var (default 2048 = 2GB).
# Only effective on Linux (RLIMIT_AS); silently skipped on macOS/Windows.
try:
    import resource as _resource
    _mb = int(os.environ.get("PYTHON_MEMORY_LIMIT_MB", "8192"))
    _limit_bytes = _mb * 1024 * 1024
    if hasattr(_resource, "RLIMIT_AS"):  # Linux only
        _resource.setrlimit(_resource.RLIMIT_AS, (_limit_bytes, _limit_bytes))
        logger_tmp = logging.getLogger(__name__)
        logger_tmp.info(f"Python memory limit set to {_mb}MB via RLIMIT_AS")
    elif hasattr(_resource, "RLIMIT_DATA"):  # fallback
        _resource.setrlimit(_resource.RLIMIT_DATA, (_limit_bytes, _limit_bytes))
except Exception:
    pass  # Non-fatal: Docker itself provides hard memory limits



from app.config import settings
from app.context import correlation_id_var
from app.dependencies import ServiceContainer, get_container, shutdown, startup
from app.metrics import REQUEST_COUNT
from app.observability import init_observability
from app.security_utils import TTLRateLimiter, build_csp
from app.telemetry_db import init_telemetry_db
from app.telemetry_sink import SupabaseTelemetrySink, TelemetryWorker
from services.auth_service import get_current_user_from_supabase

# Initialize tenant context from request
from services.tenant_context import TenantContext, get_tenant_collection, set_tenant_from_request

# Backward-compatible module-level coalescer (tests patch app.main.coalescer).
from app.coalescer import build_coalescer as _build_coalescer

coalescer = _build_coalescer(redis_url=getattr(settings, "redis_url", None), ttl=60.0)

# Existing routers
from app.api.admin import admin_router
from app.api.cache_metrics import router as cache_metrics_router
from app.api.compliance import router as compliance_router
from app.api.endpoints.auth import router as auth_router
from app.api.feedback import router as feedback_router
from app.api.health import router as health_router
from app.core.limiter import limiter

# Newly-extracted route groups
from app.api.chat import router as chat_router
from app.api.ingest import router as ingest_router
from app.api.memory import router as memory_router
from app.api.profile import router as profile_router
from app.api.speech import router as speech_router

# Job and trace routers are imported where needed below to avoid
# heavy imports during module load.

telemetry_sink = SupabaseTelemetrySink()
telemetry_worker = TelemetryWorker(telemetry_sink)

logger = logging.getLogger(__name__)


# === Graceful shutdown in-flight request tracker (R3) ===
_INFLIGHT = 0  # simple int — GIL protects single reads/writes in CPython
_DRAIN_TIMEOUT_S = 30  # max seconds to wait for in-flight requests during shutdown


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include correlation ID if available
        try:
            cid = correlation_id_var.get()
            if cid != "-":
                log_obj["correlation_id"] = cid
        except Exception:
            pass
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"))
logging.basicConfig(level=logging.INFO, handlers=[handler])


# === NodeObserver wiring (called during startup) ===

def _register_node_observers() -> None:
    """
    Wire NodeObserver instances for the RAG pipeline.

    MetricsObserver and LoggingObserver are registered globally so that
    any NodeCommand execution emits telemetry automatically.
    This is a no-op if NodeRegistry has not been populated yet.
    """
    try:
        from rag.telemetry_observer import LoggingObserver, MetricsObserver, SelfCorrectionObserver

        # Register observers globally (used at node-execution time)
        global _node_observers
        _node_observers = [
            MetricsObserver(),
            LoggingObserver(),
            SelfCorrectionObserver(max_retries=3),
        ]
        logger.info(f"Registered {len(_node_observers)} NodeObserver(s) for pipeline telemetry")
    except Exception as exc:
        logger.warning(f"NodeObserver wiring skipped: {exc}")


# Initialize tenant context from request
from services.tenant_context import TenantContext, get_tenant_collection
def _init_tenant_context_from_request(request: Request) -> None:
    """
    Initialize TenantContext from the FastAPI request.

    Must be called before any tenant-aware operations like Qdrant indexing or search.
    """
    try:
        from services.auth_service import get_current_user_from_supabase
        user = get_current_user_from_supabase(request)
        tenant_id = user.get("tenant_id", user.get("id", "default"))
        email = user.get("email", "")
        TenantContext.set(tenant_id, email)
        logger.debug(f"Initialized TenantContext: tenant_id={tenant_id}, email={email}")
    except Exception as e:
        logger.warning(f"Failed to initialize TenantContext: {e}")
        TenantContext.set("default", "")


def _wire_graph_observers() -> None:
    """
    Attach registered observers to compiled LangGraph nodes.

    This is a best-effort wiring that maps the GraphState keys back to
    NodeCommand wrappers so observers can fire for each graph step.
    Observers are stored in the module-level _node_observers list from
    _register_node_observers() and consumed by Command wrappers at runtime.
    """
    try:
        from rag.node_registry import registry

        node_names = registry.list()
        # Wiring is lazy — see rag.node_command for observer dispatch
        logger.info(f"Graph observers wired for {len(node_names)} registered node(s)")
    except Exception as exc:
        logger.warning(f"Graph observer wiring skipped: {exc}")


# === Lifespan (startup/shutdown) ===


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=== Starting Mukthi Guru Backend ===")

    # 1. Initialize telemetry DB (Supabase — single operational DB)
    await init_telemetry_db()

    # 2. Dependency injection container setup (loads all services)
    startup()
    container = get_container()

    # 2.5 Ensure encoder is loaded first (resolves primary/fallback models & dimension)
    try:
        logger.info("Lifespan: Ensuring embedding encoder is loaded...")
        await asyncio.to_thread(container.embedding._ensure_encoder)
        logger.info(
            f"Lifespan: Encoder loaded successfully (Model: {settings.embedding_model}, "
            f"Dimension: {settings.embedding_dimension})"
        )
    except Exception as e:
        logger.error(f"Lifespan: Failed to load embedding encoder: {e}", exc_info=True)

    # Pre-warm remaining models (reranker, colbert) in a background thread
    def prewarm_remaining():
        logger.info("Background pre-warming (reranker/colbert): starting...")
        try:
            container.embedding._ensure_reranker()
            container.embedding._ensure_colbert()
            logger.info("Background pre-warming (reranker/colbert): complete.")
        except Exception as ex:
            logger.warning(f"Background pre-warming (reranker/colbert) failed: {ex}")

    asyncio.create_task(asyncio.to_thread(prewarm_remaining))

    # 3. Async services initialization (LightRAG)
    try:
        await container.lightrag.initialize()
    except Exception as e:
        logger.warning(f"LightRAG initialization failed (GraphRAG unavailable): {e}")

    # 4. (Deprecated) Depression detector is now merged into Serene Mind Engine

    # 5. Observability tracing (OpenTelemetry + Jaeger)
    init_observability(app)

    # 6. Schedule recurring jobs (BE-5)
    def shutdown_scheduler():
        return None

    try:
        from infrastructure.scheduler import shutdown_scheduler as _sd
        from infrastructure.scheduler import start_scheduler

        start_scheduler()
        shutdown_scheduler = _sd
    except Exception as e:
        logger.warning(f"Failed to initialize APScheduler: {e}")

    # 7. Start Telemetry Background Worker (Phase 4)
    telemetry_worker.start()

    # 8. Unit 17: Hot Reload Config Watcher (watchfiles / polling fallback)
    from services.config_watcher import start_config_watcher

    _config_watcher = await start_config_watcher()

    # 9. Wire NodeObservers (Metrics + Logging) for the RAG pipeline
    _register_node_observers()

    # 10. Start Job Queue workers (if queue enabled)
    if getattr(container, "job_queue", None):
        try:
            from app.orchestrator import queue_worker_factory

            await container.job_queue.start(queue_worker_factory)
            logger.info("JobQueue workers started")
        except Exception as e:
            logger.warning(f"Failed to start JobQueue workers: {e}")

    # 11. Start LLM Queue (if enabled)
    if getattr(container, "llm_queue", None):
        try:
            await container.llm_queue.start()
            logger.info("LLMQueue started")
        except Exception as e:
            logger.warning(f"Failed to start LLMQueue: {e}")

    logger.info("=== Mukthi Guru Backend Ready ===")
    yield

    # Shutdown
    logger.info("Shutting down — waiting for in-flight requests (R3 graceful drain)...")
    # Drain: wait until all in-flight requests finish or timeout expires
    drain_waited = 0.0
    while _INFLIGHT > 0 and drain_waited < _DRAIN_TIMEOUT_S:
        await asyncio.sleep(0.25)
        drain_waited += 0.25
    if _INFLIGHT > 0:
        logger.warning(
            f"Graceful drain timeout after {_DRAIN_TIMEOUT_S}s — {_INFLIGHT} request(s) still active"
        )
    else:
        logger.info(f"Graceful drain complete in {drain_waited:.1f}s")
    try:
        if callable(shutdown_scheduler):
            shutdown_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler shutdown error: {e}")

    # Stop Telemetry Background Worker
    telemetry_worker.stop()

    # Stop Config Watcher (Unit 17)
    from services.config_watcher import stop_config_watcher

    await stop_config_watcher()

    # Stop Job Queue workers
    if getattr(container, "job_queue", None) and getattr(container.job_queue, "_running", False):
        try:
            await container.job_queue.stop()
            logger.info("JobQueue workers stopped")
        except Exception as e:
            logger.warning(f"JobQueue shutdown error: {e}")

    # Stop LLM Queue
    if getattr(container, "llm_queue", None):
        try:
            await container.llm_queue.stop()
            logger.info("LLMQueue stopped")
        except Exception as e:
            logger.warning(f"LLMQueue shutdown error: {e}")

    shutdown()


# === App Creation ===

app = FastAPI(
    title="Mukthi Guru API",
    description="AI Spiritual Guide — Sri Preethaji & Sri Krishnaji's teachings",
    version="1.0.0",
    lifespan=lifespan,
)

# Trusted Host — validate Host header (only in production)
if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[h.strip() for h in settings.allowed_hosts.split(",") if h.strip()] or ["localhost", "127.0.0.1"],
    )

# CORS — allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Correlation ID middleware — generates UUID per request
class CorrelationIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        cid = None
        for k, v in headers:
            if k.lower() == b"x-correlation-id":
                cid = v.decode("utf-8")
                break
        if not cid:
            cid = str(uuid.uuid4())[:8]

        correlation_id_var.set(cid)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                msg_headers = list(message.get("headers", []))
                msg_headers.append((b"x-correlation-id", cid.encode("utf-8")))
                message["headers"] = msg_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


if settings.enable_correlation_ids:
    app.add_middleware(CorrelationIDMiddleware)

# ── Security Headers Middleware (auto-added by security_audit.py) ──
# CSP is generated per-request with a fresh nonce so 'unsafe-inline' is not needed.
_SECURITY_HEADERS_STATIC = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-XSS-Protection": "1; mode=block",
}


class SecurityHeadersMiddleware:
    """Adds OWASP-recommended security headers to every response.
    Generates a per-request nonce for the Content-Security-Policy."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        nonce = secrets.token_urlsafe(16)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                msg_headers = list(message.get("headers", []))
                msg_headers.extend(
                    (name.lower().encode("ascii"), value.encode("utf-8"))
                    for name, value in _SECURITY_HEADERS_STATIC.items()
                )
                csp = build_csp(nonce)
                msg_headers.append((b"content-security-policy", csp.encode("utf-8")))
                message["headers"] = msg_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)

# ── TTL-based in-memory rate limiter ──
_AUTH_RATE_LIMITER = TTLRateLimiter(ttl=60.0, max_requests=5)


# Auth endpoint rate limiter middleware — tight limits on login/reset/register
_AUTH_LIMIT_PATHS: frozenset[str] = frozenset({
    "/api/auth/jwt/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
})


@app.middleware("http")
async def auth_rate_limit_middleware(request: Request, call_next):
    if request.method == "POST" and request.url.path in _AUTH_LIMIT_PATHS:
        client_ip = request.client.host if request.client else "unknown"
        key = f"auth_rl:{request.url.path}:{client_ip}"
        if not _AUTH_RATE_LIMITER.is_allowed(key):
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "message": "Auth rate limit exceeded. Try again later."},
            )
    return await call_next(request)


# Token-bucket rate limiter for /api/chat (only when Redis is configured)
from app.middleware.rate_limit import TokenBucketMiddleware

if settings.redis_url and settings.redis_url.startswith(("redis://", "rediss://", "unix://")):
    app.add_middleware(TokenBucketMiddleware, redis_url=settings.redis_url, capacity=20, refill_per_sec=20 / 60)

# Idempotency middleware for mutating endpoints (Phase 3.3)
from app.middleware.idempotency import IdempotencyMiddleware

if settings.redis_url and settings.redis_url.startswith(("redis://", "rediss://", "unix://")):
    app.add_middleware(IdempotencyMiddleware, redis_url=settings.redis_url)


# In-flight tracker middleware for graceful drain (R3)
@app.middleware("http")
async def inflight_tracker(request: Request, call_next):
    """Increment/decrement global in-flight counter for graceful shutdown drain."""
    global _INFLIGHT
    _INFLIGHT += 1
    try:
        return await call_next(request)
    finally:
        _INFLIGHT -= 1


# ── Global request-level timeout middleware ──
# Caps every HTTP request at pipeline_timeout_budget (default 300s).
# Streaming (SSE) paths are excluded — they intentionally hold the connection open.
_STREAMING_PATHS: frozenset[str] = frozenset({"/api/chat/stream"})


@app.middleware("http")
async def request_timeout_middleware(request: Request, call_next):
    """Global request timeout — belt-and-suspenders safety net for all routes."""
    if request.url.path in _STREAMING_PATHS:
        return await call_next(request)
    timeout_val: float = float(getattr(settings, "pipeline_timeout", 180))
    try:
        return await asyncio.wait_for(call_next(request), timeout=timeout_val)
    except asyncio.TimeoutError:
        logger.error(
            f"Global request timeout ({timeout_val:.0f}s) on {request.method} {request.url.path}"
        )
        REQUEST_COUNT.labels(status="timeout").inc()
        return JSONResponse(
            status_code=504,
            content={
                "error": "Gateway Timeout",
                "message": "The request took too long to process. Please try again.",
            },
        )


# SlowAPI limiter wiring
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global error boundary catching all unhandled exceptions."""
    error_id = f"err_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    logger.error(
        f"Unhandled server error on {request.url.path} (error_id: {error_id}): {exc}", exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "An internal error occurred",
            "message": "We encountered an issue processing your request. Please try again.",
            "error_id": error_id,
        },
    )


# === Routers ===

app.include_router(auth_router, prefix="/api/auth")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(feedback_router, prefix="/api")
app.include_router(health_router, prefix="")
app.include_router(cache_metrics_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")
app.include_router(speech_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(memory_router, prefix="/api")

from app.api.job_routes import router as job_router

app.include_router(job_router)

# Mount trace dashboard routes
from app.trace_dashboard import router as trace_router

app.include_router(trace_router)


# === Mount Ingestion UI ===

# Try to find the directory (Docker vs Local/Colab)
ui_possible_paths = [
    Path("/app/ingest-ui"),  # Docker (absolute)
    Path("ingest-ui"),  # Local (relative to CWD)
    Path("../ingest-ui"),  # Colab/Dev (relative to CWD backend/)
]

ui_path = None
for p in ui_possible_paths:
    if p.exists():
        ui_path = p
        break

if ui_path:
    app.mount("/static-ingest", StaticFiles(directory=str(ui_path), html=True), name="ingest")
    logger.info(f"✅ Ingestion UI mounted at /static-ingest (from {ui_path})")
else:
    logger.warning("⚠️ Ingestion UI directory not found. UI will not be available.")

# === Mount Chat UI ===
chat_ui_possible_paths = [
    Path("/app/chat-ui"),
    Path("chat-ui"),
    Path("../chat-ui"),
]

chat_ui_path = None
for p in chat_ui_possible_paths:
    if p.exists():
        chat_ui_path = p
        break

if chat_ui_path:
    app.mount("/static-chat", StaticFiles(directory=str(chat_ui_path), html=True), name="chat")
    logger.info(f"✅ Premium Chat UI mounted at /static-chat (from {chat_ui_path})")
else:
    logger.warning("⚠️ Chat UI directory not found.")

# === Mount Gradio UI (gated; disabled by default in production) ===
if os.getenv("ENABLE_GRADIO_UI", "false").lower() in ("1", "true", "yes"):
    try:
        import gradio as gr

        from app.gradio_ui import create_demo

        _gradio_user = os.getenv("GRADIO_USER")
        _gradio_pass = os.getenv("GRADIO_PASS")
        _auth = (_gradio_user, _gradio_pass) if _gradio_user and _gradio_pass else None
        if _auth is None:
            logger.warning(
                "Gradio UI enabled without GRADIO_USER/GRADIO_PASS — refusing to mount unauthenticated UI."
            )
        else:
            gr.mount_gradio_app(app, create_demo(), path="/ui", auth=_auth)
            logger.info("✅ Gradio Chat UI mounted at /ui (basic auth enabled)")
    except Exception as e:
        logger.warning(f"Failed to mount Gradio UI: {e}")
else:
    logger.info("Gradio UI disabled (set ENABLE_GRADIO_UI=true to enable)")


@app.get("/")
async def root():
    """Redirect root to Ingestion UI."""
    return RedirectResponse(url="/ingest/")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
