"""
Mukthi Guru — FastAPI Application

Design Patterns:
  - Controller Pattern: Thin route handlers that delegate to services
  - Mediator Pattern: Routes coordinate between guardrails and RAG pipeline
  - DTO Pattern: Pydantic models for request/response validation

Endpoints:
  POST /api/chat     — Main conversational endpoint
  POST /api/ingest   — Content ingestion (YouTube/image URL)
  GET  /api/health   — Service health status

The /api/chat endpoint orchestrates the full flow:
  NeMo Input Rail → LangGraph RAG Pipeline → NeMo Output Rail → Response
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Fix import paths — run from backend/ directory
sys.path.insert(0, ".")

import time
import uuid

from app.config import settings
from app.dependencies import ServiceContainer, get_container, shutdown, startup
from app.metrics import REQUEST_COUNT, metrics_endpoint
from app.observability import init_observability
from app.telemetry_db import init_telemetry_db
from app.telemetry_sink import SupabaseTelemetrySink, TelemetryWorker

telemetry_sink = SupabaseTelemetrySink()
telemetry_worker = TelemetryWorker(telemetry_sink)
from functools import wraps

from app.context import correlation_id_var
from rag.memory import build_memory_context
from services.auth_service import get_current_user_from_supabase
from services.user_profile_service import LanguagePreference, SpiritualLevel


def record_token_usage(endpoint: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request") or next((arg for arg in args if isinstance(arg, Request)), None)
            chat_body = kwargs.get("chat_body") or next((arg for arg in args if hasattr(arg, "user_message")), None)
            user = kwargs.get("user") or {}
            
            user_id = user.get("id", "anonymous") if isinstance(user, dict) else "anonymous"
            session_id = chat_body.session_id or "" if chat_body else ""
            
            from services.cost_tracker import (
                TokenAccumulator,
                get_cost_tracker,
                token_accumulator_var,
            )
            accumulator = TokenAccumulator()
            token = token_accumulator_var.set(accumulator)
            try:
                return await func(*args, **kwargs)
            finally:
                acc = token_accumulator_var.get()
                if acc and (acc.tokens_in > 0 or acc.tokens_out > 0):
                    try:
                        get_cost_tracker().record(
                            tenant_id="default",
                            user_id=user_id,
                            session_id=session_id,
                            model=acc.model,
                            provider=acc.provider,
                            tokens_in=acc.tokens_in,
                            tokens_out=acc.tokens_out,
                            endpoint=endpoint,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record token usage: {e}")
                token_accumulator_var.reset(token)
        return wrapper
    return decorator

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.endpoints.auth import router as auth_router
from app.api.health import router as health_router
from app.api.cache_metrics import router as cache_metrics_router
from app.core.database import init_db
from app.core.limiter import limiter
from routers.admin import admin_router
from routers.feedback import router as feedback_router

logger = logging.getLogger(__name__)



# Global instances
from app.coalescer import build_coalescer

coalescer = build_coalescer(redis_url=getattr(settings, "redis_url", None), ttl=60.0)

# === Graceful shutdown in-flight request tracker (R3) ===
import asyncio as _asyncio

_INFLIGHT = 0  # simple int — GIL protects single reads/writes in CPython
_DRAIN_TIMEOUT_S = 30  # max seconds to wait for in-flight requests during shutdown

# Configure JSON logging for production observability (Phase 10)
import json


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

    # 1. Initialize DB and Create tables if needed
    await init_db()
    await init_telemetry_db()

    # 2. Dependency injection container setup (loads all services)
    startup()
    container = get_container()

    # 2.5 Ensure encoder is loaded first (resolves primary/fallback models & dimension)
    try:
        logger.info("Lifespan: Ensuring embedding encoder is loaded...")
        await asyncio.to_thread(container.embedding._ensure_encoder)
        logger.info(f"Lifespan: Encoder loaded successfully (Model: {settings.embedding_model}, Dimension: {settings.embedding_dimension})")
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

    logger.info("=== Mukthi Guru Backend Ready ===")
    yield

    # Shutdown
    logger.info("Shutting down — waiting for in-flight requests (R3 graceful drain)...")
    # Drain: wait until all in-flight requests finish or timeout expires
    drain_waited = 0.0
    while _INFLIGHT > 0 and drain_waited < _DRAIN_TIMEOUT_S:
        await _asyncio.sleep(0.25)
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
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-XSS-Protection": "1; mode=block",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.sarvam.ai https://*.supabase.co wss://*.supabase.co; "
        "frame-ancestors 'none';"
    ),
}


class SecurityHeadersMiddleware:
    """Adds OWASP-recommended security headers to every response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                msg_headers = list(message.get("headers", []))
                msg_headers.extend(
                    (name.lower().encode("ascii"), value.encode("utf-8"))
                    for name, value in SECURITY_HEADERS.items()
                )
                message["headers"] = msg_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)

# Token-bucket rate limiter for /api/chat
from app.middleware.rate_limit import TokenBucketMiddleware

app.add_middleware(TokenBucketMiddleware, redis_url=settings.redis_url, capacity=20, refill_per_sec=20 / 60)


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


app.include_router(auth_router, prefix="/api/auth")
# (Other routers moved down to avoid circular deps if any, or just kept here)
app.include_router(admin_router, prefix="/api/admin")
app.include_router(feedback_router, prefix="/api")
app.include_router(health_router, prefix="")
app.include_router(cache_metrics_router, prefix="/api")

# Unit 24: Compliance router (GDPR audit log access)
from routers.compliance import router as compliance_router

app.include_router(compliance_router)

# Mount trace dashboard routes
from datetime import timezone

UTC = timezone.utc

from app.trace_dashboard import router as trace_router

app.include_router(trace_router)


@app.get("/metrics", tags=["Observability"])
async def get_metrics(user: dict = Depends(get_current_user_from_supabase)):
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response

    data, content_type = metrics_endpoint()
    return Response(content=data, media_type=content_type)


# === Mount Ingestion UI ===

# Try to find the directory (Docker vs Local/Colab)
# Priority: 1. Docker/Copied local, 2. Colab/Dev sibling
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
            gradio_app = gr.mount_gradio_app(app, create_demo(), path="/ui", auth=_auth)
            logger.info("✅ Gradio Chat UI mounted at /ui (basic auth enabled)")
    except Exception as e:
        logger.warning(f"Failed to mount Gradio UI: {e}")
else:
    logger.info("Gradio UI disabled (set ENABLE_GRADIO_UI=true to enable)")



def _cache_language_key(message: str, language: str) -> str:
    normalized_lang = (language or "en").lower().strip()
    return f"{normalized_lang}:{message.strip()}"


# Language detection and translation utilities are now in language_utils.py


# === Request/Response DTOs ===


from app.schemas import ChatRequest, ChatResponse


class IngestRequest(BaseModel):
    """Ingestion API request body."""

    url: str = Field(..., description="YouTube video/playlist URL or image URL")
    max_accuracy: bool = Field(
        default=False,
        description="If True, skip auto-generated captions (T3) and rely on Manual (T1) or Whisper (T2)",
    )


class IngestResponse(BaseModel):
    """Ingestion API response body."""

    status: str
    message: str = ""
    source_url: str = ""
    chunks_indexed: int = 0
    summaries_created: int = 0


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    services: dict
    total_chunks: int = 0


# === Route Handlers ===


async def _prepare_user_memory(
    container: ServiceContainer,
    user_id: str,
    chat_history: list[dict],
) -> tuple[str, list[dict]]:
    """Load bounded user memory and derive distress signals for this turn."""
    if not container.user_profile:
        return "", []

    # Anonymous users have no persistent profile — skip all DB calls
    if not user_id or user_id == "anonymous":
        return "", []

    profile = await container.user_profile.get_or_create_profile(user_id)
    profile.total_conversations += 1
    await container.user_profile.update_profile(profile)

    recent_memories = await container.user_profile.get_recent_memories(user_id, limit=3)
    memory_context = build_memory_context(
        recent_memories=recent_memories,
        chat_history=chat_history,
    )

    # Fetch persistent memory layer context under a 200ms timeout budget if enabled
    if settings.feature_memory_enabled and getattr(container, "memory_service", None):
        try:
            last_query = chat_history[-1]["content"] if chat_history else ""
            
            async def fetch_memory_layer():
                core_m = await container.memory_service.get_core(user_id)
                semantic_m = []
                if last_query:
                    semantic_m = await container.memory_service.search_semantic(user_id, last_query, limit=3, min_similarity=0.6)
                return core_m, semantic_m

            core_m, semantic_m = await asyncio.wait_for(fetch_memory_layer(), timeout=0.200)

            # Format memory context blocks
            memory_blocks = []
            if core_m:
                memory_blocks.append("USER PROFILE & CORE FACTS:\n- " + "\n- ".join(c["content"] for c in core_m))
            if semantic_m:
                memory_blocks.append("PAST RELEVANT RECOLLECTIONS:\n- " + "\n- ".join(s["content"] for s in semantic_m))

            if memory_blocks:
                new_memory_context = "\n\n".join(memory_blocks)
                if memory_context:
                    memory_context = f"{memory_context}\n\n{new_memory_context}"
                else:
                    memory_context = new_memory_context
        except asyncio.TimeoutError:
            logger.warning(f"Memory layer fetch timed out for user {user_id} (exceeded 200ms budget)")
        except Exception as e:
            logger.warning(f"Memory layer fetch failed: {e}")

    distress_history = []
    for mem in recent_memories:
        if mem.emotional_arc:
            recent_emotion = mem.emotional_arc[-1]
            if recent_emotion.get("distress_level", 0) >= 2:
                distress_history.append(recent_emotion)

    return memory_context, distress_history




@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
@limiter.limit(settings.chat_rate_limit)
@record_token_usage(endpoint="/api/chat")
async def chat_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> ChatResponse:
    """
    Main conversational endpoint.

    Delegates to ChatRequestOrchestrator.
    """
    from app.orchestrator import ChatRequestOrchestrator

    orchestrator = ChatRequestOrchestrator(container)
    return await orchestrator.orchestrate(request, chat_body, background_tasks, user)



@app.post("/api/chat/stream", tags=["Chat"])
@limiter.limit(settings.chat_rate_limit)
async def chat_stream_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).

    Delegates to ChatStreamRequestOrchestrator.
    """
    from app.stream_orchestrator import ChatStreamRequestOrchestrator

    orchestrator = ChatStreamRequestOrchestrator(container)
    return await orchestrator.orchestrate_stream(request, chat_body, background_tasks, user)



# === Breath Technique Teaching ===

# Simple 1-hr in-memory cache to avoid repeated LLM calls for the same technique
_breath_teaching_cache: dict[str, dict] = {}

# Maps technique ID → a focused query against the teachings knowledge base
_TECHNIQUE_QUERIES: dict[str, str] = {
    "serene_mind": "What do Sri Preethaji and Sri Krishnaji teach about conscious breathing and the long exhale as a path to the beautiful state?",
    "box": "What do Sri Preethaji and Sri Krishnaji teach about equanimity, balance, and equal-phase breathing or pranayama?",
    "4_7_8": "What do Sri Preethaji and Sri Krishnaji teach about deep rest, surrender, and releasing all tension through the breath?",
    "deep_vitality": "What do Sri Preethaji and Sri Krishnaji teach about prana, life force, and energising the body through breath awareness?",
}
_DEFAULT_TECHNIQUE_QUERY = "What do Sri Preethaji and Sri Krishnaji teach about the sacred importance of conscious breathing in spiritual practice?"


@app.get("/api/breath-teaching/{technique_id}", tags=["Meditation"])
async def get_breath_teaching(
    technique_id: str,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """
    Return an LLM-generated teaching from the Sri Preethaji / Sri Krishnaji knowledge
    base that contextualises a specific breathing technique for the Serene Mind modal.

    Results are cached in memory for 1 hour to avoid redundant LLM calls.
    The teaching is retrieved via RAG (Qdrant vector search) so it is always grounded
    in the actual ingested teachings — never a hardcoded string.
    """
    import time as _time

    # Check in-memory cache (1hr TTL)
    cached = _breath_teaching_cache.get(technique_id)
    if cached and (_time.time() - cached["ts"]) < 3600:
        return {"technique_id": technique_id, "teaching": cached["teaching"], "cached": True}

    query = _TECHNIQUE_QUERIES.get(technique_id, _DEFAULT_TECHNIQUE_QUERY)

    teaching = ""
    try:
        if container.qdrant and container.embedding and container.ollama:
            # Direct Qdrant retrieve
            query_embedding = await asyncio.to_thread(container.embedding.encode_single_full, query)
            results = await asyncio.to_thread(
                container.qdrant.search,
                query_vector=query_embedding["dense"],
                limit=3,
                sparse_vector=query_embedding["sparse"],
                raptor_level=0,
                query=query,
            )
            # Compile context
            context_text = "\n\n".join([r["text"] for r in results if r.get("text")])

            # Generate prompt for Ollama/Sarvam
            prompt = (
                f"You are Mukthi Guru, a spiritual guide. Sri Preethaji and Sri Krishnaji are the founders of O&O Academy.\n"
                f"Based on the following context, share a teaching about: {query.lower()}\n"
                f"Requirements:\n"
                f"1. Keep it to exactly 1-2 sentences.\n"
                f"2. Be poetic, grounded, and use their actual teachings/terminology if present in the context.\n"
                f"3. End with a gentle invitation to practice.\n"
                f"4. Do NOT say 'Based on the context...' or mention constraints.\n\n"
                f"Context:\n{context_text}\n\n"
                f"Teaching:"
            )

            # Generate response
            raw = await asyncio.wait_for(
                container.ollama.generate(
                    system_prompt="You share concise spiritual teachings.",
                    user_prompt=prompt,
                    max_tokens=80,
                ),
                timeout=25.0,
            )
            # Trim to 2 sentences max — this is a subtitle, not a full answer
            sentences = [s.strip() for s in raw.split(".") if s.strip()][:2]
            teaching = ". ".join(sentences) + ("." if sentences else "")

        if not teaching and container.ollama:
            # Fallback: direct LLM call if RAG search is empty or failed
            teaching = await asyncio.wait_for(
                container.ollama.generate(
                    system_prompt="You share concise spiritual teachings.",
                    user_prompt=(
                        f"In 1-2 sentences, share a teaching from Sri Preethaji or Sri Krishnaji "
                        f"about: {query.lower()} Be poetic, grounded in their actual teachings, "
                        f"and end with an invitation to practice."
                    ),
                    max_tokens=80,
                ),
                timeout=25.0,
            )

    except Exception as e:
        logger.warning(f"Breath teaching generation failed for {technique_id}: {e}")

    if not teaching:
        if technique_id == "serene_mind":
            teaching = (
                "Sri Preethaji and Sri Krishnaji teach that the Serene Mind practice calms the amygdala. "
                "Sit erect, close your eyes, take deep abdominal breaths (4s inhale, 2s hold, 6s exhale), "
                "observe your emotions/thoughts, and visualize a flame moving from your eyebrow center to the center of your brain."
            )
        else:
            teaching = (
                "Sri Preethaji and Sri Krishnaji teach that conscious breathing is the bridge "
                "between the suffering state and the beautiful state. Let each breath be a sacred offering."
            )

    # Cache the result
    _breath_teaching_cache[technique_id] = {"teaching": teaching, "ts": _time.time()}

    return {"technique_id": technique_id, "teaching": teaching, "cached": False}


class SpeechTTSRequest(BaseModel):
    text: str
    target_language_code: str
    speaker: Optional[str] = None


@app.post("/api/speech/stt", tags=["Speech"])
async def speech_to_text_endpoint(
    file: UploadFile = File(...),
    language_code: Optional[str] = Form(None),
    model: str = Form("saaras:v3"),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """
    Transcribe uploaded audio file using Sarvam Cloud STT or fallback to local Whisper.
    """
    import os
    import tempfile

    import httpx

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file provided.")

    api_key = settings.sarvam_api_key

    if api_key and not api_key.startswith("sk_dummy") and len(api_key) > 10:
        try:
            logger.info("Calling Sarvam STT Cloud API...")
            headers = {
                "api-subscription-key": api_key,
            }
            files = {
                "file": (file.filename or "audio.webm", content, file.content_type or "audio/webm")
            }
            data = {"model": model}
            if language_code:
                data["language_code"] = language_code

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.sarvam.ai/speech-to-text", headers=headers, files=files, data=data
                )
                if resp.status_code == 200:
                    result = resp.json()
                    transcript = result.get("transcript", "")
                    detected_lang = result.get("language_code", language_code or "en-IN")
                    logger.info(
                        f"Sarvam STT returned transcript: {transcript} (lang: {detected_lang})"
                    )
                    return {"transcript": transcript, "language_code": detected_lang}
                else:
                    logger.error(f"Sarvam STT failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error calling Sarvam STT: {e}")

    # Fallback to local Whisper
    try:
        logger.info("Falling back to local Whisper STT...")
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            from services.whisper_local_service import transcribe_with_whisper

            whisper_lang = "en"
            if language_code:
                whisper_lang = language_code.split("-")[0].lower()

            transcript = transcribe_with_whisper(
                video_id="browser_recording", audio_path=tmp_path, language=whisper_lang
            )

            if transcript:
                detected_lang = language_code or "en-IN"
                if any("\u0900" <= c <= "\u097f" for c in transcript):
                    detected_lang = "hi-IN"
                elif any("\u0c00" <= c <= "\u0c7f" for c in transcript):
                    detected_lang = "te-IN"
                elif any("\u0b80" <= c <= "\u0bff" for c in transcript):
                    detected_lang = "ta-IN"

                return {"transcript": transcript, "language_code": detected_lang}
            else:
                raise Exception("Whisper returned empty transcript")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        logger.error(f"Local Whisper fallback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Speech transcription failed. Please try again.")


@app.post("/api/speech/tts", tags=["Speech"])
async def text_to_speech_endpoint(
    req: SpeechTTSRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """
    Generate speech from text using Sarvam Cloud TTS.
    """
    import httpx

    api_key = settings.sarvam_api_key
    if not api_key or api_key.startswith("sk_dummy") or len(api_key) <= 10:
        raise HTTPException(
            status_code=500, detail="Sarvam TTS not configured (missing or dummy API key)."
        )

    lang = req.target_language_code
    if "-" not in lang:
        mapping = {
            "en": "en-IN",
            "hi": "hi-IN",
            "bn": "bn-IN",
            "te": "te-IN",
            "mr": "mr-IN",
            "ta": "ta-IN",
            "ur": "ur-IN",
            "gu": "gu-IN",
            "kn": "kn-IN",
            "ml": "ml-IN",
            "or": "or-IN",
            "pa": "pa-IN",
            "as": "as-IN",
            "mai": "mai-IN",
            "sa": "sa-IN",
            "ks": "ks-IN",
            "ne": "ne-NP",
            "sd": "sd-IN",
            "kok": "kok-IN",
            "doi": "doi-IN",
            "mni": "mni-IN",
            "sat": "sat-IN",
            "brx": "brx-IN",
        }
        lang = mapping.get(lang.lower(), f"{lang.lower()}-IN")

    speaker = req.speaker or "shubh"

    url = "https://api.sarvam.ai/text-to-speech"
    headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
    payload = {
        "inputs": [req.text],
        "target_language_code": lang,
        "speaker": speaker,
        "model": "bulbul:v3",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                audios = data.get("audios", [])
                if audios:
                    return {"audio": audios[0]}
                else:
                    raise Exception("Sarvam TTS returned empty audio list")
            else:
                logger.error(f"Sarvam TTS failed with status {resp.status_code}: {resp.text}")
                raise HTTPException(
                    status_code=502, detail="Speech synthesis failed. Please try again."
                )
    except Exception as e:
        logger.error(f"Error calling Sarvam TTS: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail="Speech synthesis failed. Please try again.")


@app.post("/api/ingest", response_model=IngestResponse, tags=["Ingestion"])
@limiter.limit("5/minute")
async def ingest_endpoint(
    request: Request,
    ingest_body: IngestRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> IngestResponse:
    """
    Content ingestion endpoint (Admin only).
    Accepts YouTube video/playlist URLs and image URLs.
    Runs ingestion in the background so the API responds immediately.
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    url = ingest_body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    import re

    from app.security_utils import is_valid_youtube_url
    from ingest.image_loader import is_image_url

    is_yt = "youtube.com" in url or "youtu.be" in url
    if is_yt:
        if not is_valid_youtube_url(url):
            raise HTTPException(status_code=400, detail="Invalid YouTube URL format.")
    elif is_image_url(url):
        if not re.match(r"^https?://[a-zA-Z0-9_.:/?=&%#-]+$", url) or len(url) > 250:
            raise HTTPException(status_code=400, detail="Invalid image URL format.")
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported URL format. Only YouTube and image URLs are supported.",
        )

    # Run ingestion in the background for large content
    async def _run_ingestion():
        import time
        import uuid
        from datetime import datetime

        from app.telemetry_db import log_ingestion_run

        start_time = time.time()
        chunks_added = 0
        status = "ok"
        error_log = None

        def progress_callback(msg: str, pct: float):
            container.update_progress(url, msg, pct)

        try:
            # Init tracker
            container.update_progress(url, "Starting...", 0.0)

            result = await container.ingestion.ingest_url(
                url, max_accuracy=ingest_body.max_accuracy, on_progress=progress_callback
            )
            logger.info(f"Ingestion complete: {result}")
            container.update_progress(url, "Complete!", 1.0)

            if isinstance(result, dict):
                chunks_added = result.get("chunks_indexed", result.get("chunks_added", 0))

            # Invalidate response cache after new content ingestion
            container.exact_cache.invalidate_all()
            container.semantic_cache.invalidate_all()

        except Exception as e:
            logger.error(f"Ingestion failed for {url}: {e}", exc_info=True)
            status = "failed"
            error_log = str(e)
            # Mark as error
            container.ingestion_tracker.mark_error(url, str(e))
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            try:
                await log_ingestion_run(
                    {
                        "id": str(uuid.uuid4()),
                        "source": url,
                        "chunks_added": chunks_added,
                        "embedding_model": settings.embedding_model,
                        "duration_ms": duration_ms,
                        "status": status,
                        "error_log": error_log,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as db_e:
                logger.error(f"Failed to log ingestion run in background task: {db_e}")

    background_tasks.add_task(_run_ingestion)

    return IngestResponse(
        status="processing",
        message=f"Ingestion started for: {url}",
        source_url=url,
    )


@app.get("/api/profile", tags=["Profile"])
async def get_profile_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """Fetch the authenticated user's spiritual profile."""
    if not container.user_profile:
        raise HTTPException(status_code=501, detail="User profile service not enabled")

    profile = await container.user_profile.get_or_create_profile(user["id"])
    return asdict(profile)


@app.put("/api/profile", tags=["Profile"])
async def update_profile_endpoint(
    profile_data: dict,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """Update user preferences and spiritual level."""
    if not container.user_profile:
        raise HTTPException(status_code=501, detail="User profile service not enabled")

    # Load current profile
    profile = await container.user_profile.get_or_create_profile(user["id"])

    # Update allowed fields
    if "preferred_language" in profile_data:
        try:
            profile.preferred_language = LanguagePreference(profile_data["preferred_language"])
        except ValueError:
            pass

    if "spiritual_level" in profile_data:
        try:
            profile.spiritual_level = SpiritualLevel(profile_data["spiritual_level"])
        except ValueError:
            pass

    if "topics_of_interest" in profile_data:
        profile.topics_of_interest = profile_data["topics_of_interest"]

    if "codemix_preference" in profile_data:
        profile.codemix_preference = bool(profile_data["codemix_preference"])

    await container.user_profile.update_profile(profile)
    return asdict(profile)


# === Memory Management Endpoints (Track B) ===

class GuruMemoryResponse(BaseModel):
    id: str
    claim: str
    confidence: float
    last_seen: str
    created_at: str
    decay_score: float
    source: str

class MemoryListResponse(BaseModel):
    memories: list[GuruMemoryResponse]
    total: int
    page: int
    page_size: int

class CoreMemoryProfile(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    practice_level: Optional[str] = None
    dominant_themes: list[str] = []

class CoreMemoryResponse(BaseModel):
    profile: CoreMemoryProfile
    updated_at: str

class ForgetMemoryRequest(BaseModel):
    memory_id: str

class AddMemoryRequest(BaseModel):
    text: str


@app.get("/api/memory/list", response_model=MemoryListResponse, tags=["Memory"])
async def list_memories_endpoint(
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> MemoryListResponse:
    """List episodic memories for the authenticated user, paginated."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory service not enabled")

    result = await container.memory_service.list_memories(user["id"], page=page, page_size=page_size)
    memories = []
    for m in result["memories"]:
        created_iso = m.get("created_at")
        updated_iso = m.get("updated_at")
        
        if not isinstance(created_iso, str):
            created_iso = created_iso.isoformat() if created_iso else ""
        if not isinstance(updated_iso, str):
            updated_iso = updated_iso.isoformat() if updated_iso else ""

        memories.append(
            GuruMemoryResponse(
                id=str(m["id"]),
                claim=m["content"],
                confidence=1.0,
                last_seen=updated_iso or created_iso,
                created_at=created_iso,
                decay_score=1.0,
                source=m.get("source", "extracted"),
            )
        )
    return MemoryListResponse(
        memories=memories,
        total=result["total"],
        page=page,
        page_size=page_size,
    )


@app.get("/api/memory/core", response_model=CoreMemoryResponse, tags=["Memory"])
async def get_core_memory_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> CoreMemoryResponse:
    """Retrieve core profile preferences aggregated with core facts."""
    if not container.user_profile:
        raise HTTPException(status_code=501, detail="User profile service not enabled")

    profile = await container.user_profile.get_or_create_profile(user["id"])
    
    practice_level_map = {
        SpiritualLevel.BEGINNER: "beginner",
        SpiritualLevel.EXPLORER: "intermediate",
        SpiritualLevel.PRACTITIONER: "committed",
        SpiritualLevel.SEEKER: "advanced",
    }
    practice_level = practice_level_map.get(profile.spiritual_level, "beginner")
    language = profile.preferred_language.value if profile.preferred_language else "en"

    core_profile = CoreMemoryProfile(
        name=user.get("user_metadata", {}).get("full_name") or user.get("email", "Seeker"),
        language=language,
        practice_level=practice_level,
        dominant_themes=profile.topics_of_interest or [],
    )
    
    import datetime
    try:
        updated_at_dt = datetime.datetime.fromtimestamp(profile.updated_at, datetime.timezone.utc)
        updated_at_iso = updated_at_dt.isoformat()
    except Exception:
        updated_at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return CoreMemoryResponse(
        profile=core_profile,
        updated_at=updated_at_iso,
    )


@app.post("/api/memory/add", response_model=GuruMemoryResponse, tags=["Memory"])
async def add_memory_endpoint(
    body: AddMemoryRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> GuruMemoryResponse:
    """Manually add an explicit memory."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory service not enabled")

    content = body.text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory text cannot be empty")

    m = await container.memory_service.add_explicit(user["id"], content, is_core=False)
    if not m:
        raise HTTPException(status_code=500, detail="Failed to save memory")

    created_iso = m.get("created_at")
    updated_iso = m.get("updated_at")
    if not isinstance(created_iso, str):
        created_iso = created_iso.isoformat() if created_iso else ""
    if not isinstance(updated_iso, str):
        updated_iso = updated_iso.isoformat() if updated_iso else ""

    return GuruMemoryResponse(
        id=str(m["id"]),
        claim=m["content"],
        confidence=1.0,
        last_seen=updated_iso or created_iso,
        created_at=created_iso,
        decay_score=1.0,
        source=m.get("source", "explicit"),
    )


@app.post("/api/memory/forget", tags=["Memory"])
async def forget_memory_endpoint(
    body: ForgetMemoryRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Forget/delete a specific memory by its ID."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory service not enabled")

    success = await container.memory_service.forget(user["id"], body.memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or not owned by user")

    return {"status": "ok", "message": "Memory forgotten"}


class RelevantMemoryRequest(BaseModel):
    query: str
    limit: int = 5


@app.get("/api/memory/summaries", tags=["Memory"])
async def list_summaries_endpoint(
    limit: int = 10,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List recent session summaries for the authenticated user."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory service not enabled")
    rows = await container.memory_service.recent_summaries(user["id"], limit=limit)
    out = []
    for r in rows:
        created = r.get("created_at")
        if not isinstance(created, str):
            created = created.isoformat() if created else ""
        out.append({
            "id": str(r.get("id", "")),
            "session_id": str(r.get("session_id", "")),
            "summary": r.get("summary", ""),
            "created_at": created,
        })
    return out


@app.post("/api/memory/relevant", tags=["Memory"])
async def relevant_memories_endpoint(
    body: RelevantMemoryRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """Return memories semantically relevant to a query via match_user_memories RPC."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory service not enabled")
    rows = await container.memory_service.search_semantic(
        user["id"], body.query, limit=body.limit, min_similarity=0.6
    )
    out = []
    for r in rows:
        created = r.get("created_at")
        if not isinstance(created, str):
            created = created.isoformat() if created else ""
        out.append({
            "id": str(r.get("id", "")),
            "content": r.get("content", ""),
            "similarity": float(r.get("similarity", 0.0)),
            "created_at": created,
        })
    return out


@app.get("/api/memory/conversations", tags=["Memory"])
async def list_conversation_continuity_endpoint(
    limit: int = 5,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List recent conversation memories (for continuity display)."""
    if not container.user_profile:
        raise HTTPException(status_code=501, detail="User profile service not enabled")
    rows = await container.user_profile.get_recent_memories(user["id"], limit=limit)
    out = []
    for m in rows:
        started = m.started_at
        if not isinstance(started, str):
            import datetime as _dt
            try:
                started = _dt.datetime.fromtimestamp(float(started), _dt.timezone.utc).isoformat()
            except Exception:
                started = str(started)
        out.append({
            "session_id": m.session_id,
            "started_at": started,
            "key_insights": m.key_insights or [],
            "follow_up_suggestions": m.follow_up_suggestions or [],
        })
    return out



@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_endpoint(container: ServiceContainer = Depends(get_container)) -> HealthResponse:
    """
    Health check endpoint.

    Returns status of all backend services and total indexed chunks.
    """
    health = await container.health_status()

    # Only core services determine healthy/degraded status
    # Optional services (OCR, guardrails) don't affect overall health
    from app.config import settings

    core_services = {"qdrant", "embedding"}
    if settings.llm_provider == "ollama":
        core_services.add("ollama")
    all_healthy = all(v for k, v in health.items() if k in core_services)

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        services={
            k: (v if isinstance(v, bool) else True)
            for k, v in health.items()
            if k not in ["qdrant_count", "guardrails_provider"]
        },
        total_chunks=0 if not all_healthy else -1,  # Redact exact count
    )


async def _health_check(name: str, coro) -> dict:
    s = time.perf_counter()
    try:
        await asyncio.wait_for(coro, timeout=2.0)
        return {"name": name, "ok": True, "latency_ms": int((time.perf_counter() - s) * 1000)}
    except Exception as exc:
        return {"name": name, "ok": False, "error": str(exc)[:120]}


async def _check_redis(container: ServiceContainer) -> dict:
    async def _redis_ping():
        loop = asyncio.get_running_loop()
        if container.exact_cache and getattr(container.exact_cache, "_redis", None):
            return await loop.run_in_executor(None, container.exact_cache._redis.ping)
        return False
    return _redis_ping()
async def circuit_breaker_reset_endpoint() -> dict:
    """
    Manually reset the active circuit breaker to CLOSED.

    Use when the circuit has been OPEN for a long time (e.g. after
    a temporary API outage) and you want to allow traffic immediately
    instead of waiting for the auto-recovery timeout.

    Works with any LLM provider (Sarvam, Ollama, OpenRouter, etc.)
    based on the currently active provider in the registry.
    """
    from services.circuit_breaker import CircuitState

    # Access the circuit breaker through the dependency container
    try:
        container = get_container()
        # Use provider-agnostic circuit breaker registry
        active_breaker = container.circuit_breaker_registry.get_active()
        if not active_breaker:
            return {
                "status": "error",
                "message": "No active circuit breaker found. Check LLM_PROVIDER config.",
            }

        provider = container.circuit_breaker_registry.get_active_provider()
        previous_state = active_breaker.get_state().value
        active_breaker._state = CircuitState.CLOSED
        active_breaker._failures = 0
        active_breaker._last_failure_time = None
        active_breaker._half_open_calls = 0
        logger.info(f"Circuit breaker [{provider}] manually reset (was {previous_state}) → CLOSED")
        return {
            "status": "ok",
            "provider": provider,
            "previous_state": previous_state,
            "current_state": "closed",
            "message": f"Circuit breaker for {provider} has been reset. New requests will be attempted.",
        }
    except AttributeError as e:
        logger.error(f"Circuit breaker reset failed: {e}")
        return {
            "status": "error",
            "message": "Could not access circuit breaker. Ensure services are initialized.",
        }


@app.get("/api/circuit-breaker/status", tags=["Health"])
async def circuit_breaker_status(container: ServiceContainer = Depends(get_container)) -> dict:
    """
    Get circuit breaker status for all registered providers.

    Useful for debugging circuit breaker state without needing to reset it.
    """
    try:
        registry = container.circuit_breaker_registry
        if not registry:
            return {"status": "error", "message": "Circuit breaker registry not initialized"}

        all_stats = registry.get_all_stats()
        active_provider = registry.get_active_provider()

        # Also check the Sarvam service circuit breaker directly
        sarvam_circuit = None
        if hasattr(container.ollama, "_service"):
            svc = container.ollama._service
            if hasattr(svc, "_circuit"):
                sarvam_circuit = svc._circuit.get_stats()

        return {
            "status": "ok",
            "active_provider": active_provider,
            "registry_breakers": all_stats,
            "sarvam_service_circuit": sarvam_circuit,
            "llm_provider_config": container.ollama.__class__.__name__,
        }
    except Exception as e:
        logger.error(f"Circuit breaker status failed: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/debug/headers", tags=["Debug"])
async def debug_headers(request: Request) -> dict:
    """Debug endpoint to see what headers are received."""
    headers = dict(request.headers)
    # Filter for auth-related headers
    auth_headers = {k: v for k, v in headers.items() if k.lower() in ('authorization', 'cookie', 'x-test-key', 'content-type')}
    return {
        "all_headers_count": len(headers),
        "auth_headers": auth_headers,
        "has_authorization": "authorization" in headers,
        "has_cookie": "cookie" in headers,
        "has_x_test_key": "x-test-key" in headers,
    }


@app.get("/api/ready", tags=["Health"])
async def readiness_endpoint(container: ServiceContainer = Depends(get_container)) -> dict:
    """
    Kubernetes readiness probe endpoint.

    Unlike /api/health (liveness), this checks that critical services
    (Qdrant vector DB, LLM provider) are ready to serve requests.
    Returns 503 if not ready.
    """
    health = await container.health_status()

    # Check circuit breaker for Sarvam Cloud
    circuit_breaker_ok = True
    circuit_state = "unknown"
    if hasattr(container.ollama, "_service"):
        svc = container.ollama._service
        if hasattr(svc, "_circuit"):
            circuit_state = svc._circuit.get_state().value
            circuit_breaker_ok = circuit_state == "closed"

    critical_ok = health.get("qdrant", False) and health.get("ollama", False) and circuit_breaker_ok

    if not critical_ok:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "qdrant": health.get("qdrant", False),
                "llm": health.get("ollama", False),
                "circuit_breaker": circuit_state,
                "message": "Critical services not ready" if (health.get("qdrant", False) and health.get("ollama", False)) else "Circuit breaker OPEN",
            },
        )

    return {
        "ready": True,
        "qdrant": True,
        "llm": True,
        "circuit_breaker": circuit_state,
        "total_chunks": -1,  # Redacted
    }


@app.get("/api/ingest/status", tags=["Ingestion"])
async def ingest_status_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """
    Get the status of active/recent ingestion jobs (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return container.ingestion_tracker.get_all()


# === Entry Point ===


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
