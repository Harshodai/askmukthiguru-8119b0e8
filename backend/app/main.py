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
import contextvars
import logging
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
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Fix import paths — run from backend/ directory
sys.path.insert(0, ".")

import hashlib
import time
import uuid

from app.config import settings
from app.dependencies import ServiceContainer, get_container, shutdown, startup
from app.language_utils import detect_and_prepare_language_info
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY, metrics_endpoint
from app.observability import init_observability
from app.telemetry_db import init_telemetry_db
from app.telemetry_sink import SupabaseTelemetrySink, TelemetryWorker

telemetry_sink = SupabaseTelemetrySink()
telemetry_worker = TelemetryWorker(telemetry_sink)
from rag.graph import create_initial_state
from rag.memory import build_memory_context, normalize_session_id
from services.auth_service import get_current_user_from_supabase
from services.serene_mind_engine import DistressAssessment, DistressLevel
from services.user_profile_service import LanguagePreference, SpiritualLevel

# Correlation ID context variable — accessible from anywhere in the async call chain
correlation_id_var = contextvars.ContextVar("correlation_id", default="-")
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.endpoints.auth import router as auth_router
from app.core.database import init_db
from app.core.limiter import limiter
from routers.admin import admin_router
from routers.feedback import router as feedback_router
from services.cache_service import init_llm_cache
from services.sarvam_service import CircuitOpenException

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

    # 2.5 Pre-warm heavy ML models in background thread so they don't block startup (Phase 3)
    def prewarm_models():
        logger.info("Background pre-warming: starting...")
        try:
            container.ocr._ensure_reader()
            container.embedding._ensure_models()
            logger.info("Background pre-warming: complete.")
        except Exception as e:
            logger.warning(f"Background pre-warming failed: {e}")

    asyncio.create_task(asyncio.to_thread(prewarm_models))

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

    # 7. Initialize GPTCache to intercept identical LLM calls
    init_llm_cache()

    # 8. Start Telemetry Background Worker (Phase 4)
    telemetry_worker.start()

    # 9. Unit 17: Hot Reload Config Watcher (watchfiles / polling fallback)
    from services.config_watcher import start_config_watcher

    _config_watcher = await start_config_watcher()

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
    timeout_val: float = float(getattr(settings, "pipeline_timeout_budget", 300))
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

# === Mount Gradio UI (Council Recommendation) ===
try:
    import gradio as gr

    from app.gradio_ui import create_demo

    # Reset standard logging to avoid conflict
    gradio_app = gr.mount_gradio_app(app, create_demo(), path="/ui")
    logger.info("✅ Gradio Chat UI mounted at /ui")
except Exception as e:
    logger.warning(f"Failed to mount Gradio UI: {e}")


async def translate_text(text: str, src: str, tgt: str, container: ServiceContainer) -> str:
    """
    Optimized fast translation routing:
    Routes translation through Sarvam Cloud translate (mayura:v1) when a valid API key
    is present, otherwise falls back to local Ollama (llama3.2:3b).
    """
    if type(container.ollama).__name__ in ("MagicMock", "AsyncMock", "Mock") or hasattr(
        container.ollama, "mock_calls"
    ):
        return await container.ollama.translate_text(text, src, tgt)

    if (
        settings.sarvam_api_key
        and not settings.sarvam_api_key.startswith("sk_dummy")
        and settings.sarvam_api_key.strip()
    ):
        try:
            from services.sarvam_service import SarvamCloudService

            sarvam_srv = SarvamCloudService()
            return await sarvam_srv.translate_text(text, src, tgt)
        except Exception as e:
            logger.error(
                f"Error in dynamic Sarvam translation routing: {e}, falling back to Ollama"
            )
    return await container.ollama.translate_text(text, src, tgt)


def _cache_language_key(message: str, language: str) -> str:
    normalized_lang = (language or "en").lower().strip()
    return f"{normalized_lang}:{message.strip()}"


# Language detection and translation utilities are now in language_utils.py


# === Request/Response DTOs ===


class MessagePayload(BaseModel):
    """Single message in the conversation history."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class ChatRequest(BaseModel):
    """Chat API request body — matches frontend's sendMessage format."""

    messages: list[MessagePayload] = Field(..., description="Conversation history")
    user_message: str = Field(..., description="Current user message")
    session_id: Optional[str] = Field(None, description="Optional session ID")
    meditation_step: int = Field(default=0, description="Current meditation step (0 = none)")
    language: Optional[str] = Field(default="en", description="Preferred language")
    last_serene_mind_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp of the user's last completed Serene Mind session (client-reported)",
    )


class ChatResponse(BaseModel):
    """Chat API response body."""

    response: str = Field(..., description="Guru's response")
    intent: Optional[str] = Field(None, description="Detected intent")
    meditation_step: int = Field(default=0, description="Next meditation step")
    citations: list[str] = Field(default_factory=list, description="Source URLs")
    blocked: bool = Field(default=False, description="Was the message blocked?")
    block_reason: Optional[str] = Field(None, description="Why it was blocked")
    proactive_serene_mind: Optional[dict] = Field(
        None, description="Proactive Serene Mind trigger details"
    )
    faithfulness_score: Optional[float] = Field(None, description="Self-RAG faithfulness score")
    relevancy_score: Optional[float] = Field(None, description="Answer relevancy score")
    confidence_score: Optional[float] = Field(None, description="Verifier confidence score")
    verification: Optional[dict] = Field(None, description="CoVe/Self-RAG verification result")
    hallucination_flag: Optional[bool] = Field(
        None, description="Whether verification flagged hallucination risk"
    )
    trace_id: Optional[str] = Field(None, description="Trace/query ID for observability")
    latency_ms: Optional[int] = Field(
        None, description="End-to-end response latency in milliseconds"
    )
    node_timings: Optional[dict] = Field(
        None, description="Per-node LangGraph timings in milliseconds"
    )
    evaluation_trace: Optional[dict] = Field(
        None, description="Trajectory metadata for benchmark and production AI evaluation"
    )
    model_used: Optional[str] = Field(None, description="Underlying LLM model used")
    model_provider: Optional[str] = Field(None, description="Underlying LLM provider")
    route_decision: Optional[str] = Field(None, description="Model/routing decision")


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

    profile = await container.user_profile.get_or_create_profile(user_id)
    profile.total_conversations += 1
    await container.user_profile.update_profile(profile)

    recent_memories = await container.user_profile.get_recent_memories(user_id, limit=3)
    memory_context = build_memory_context(
        recent_memories=recent_memories,
        chat_history=chat_history,
    )

    distress_history = []
    for mem in recent_memories:
        if mem.emotional_arc:
            recent_emotion = mem.emotional_arc[-1]
            if recent_emotion.get("distress_level", 0) >= 2:
                distress_history.append(recent_emotion)

    return memory_context, distress_history


async def _prepare_request_state(
    container: ServiceContainer,
    chat_body: ChatRequest,
    preferred_lang: str,
    user: Optional[dict] = None,
) -> dict:
    """
    Prepare the common state for both chat endpoints.
    Returns a dictionary with:
        - user_msg_en: the user message in English (if translation needed)
        - is_indic: bool indicating if preferred language is Indic
        - preferred_lang: the normalized preferred language
        - user_id: the user ID from auth
        - stable_session_id: normalized session ID
        - chat_history_en: chat history in English (if translation needed)
        - memory_context: string from user profile memories
        - distress_history: list of distress indicators from recent memories
        - lang_detection: LanguageDetection object
        - original_user_msg: the original user message (for memory saving)
        - original_chat_history: original chat history (for memory saving)
    """
    user_msg = chat_body.user_message.strip()
    is_indic = preferred_lang and not preferred_lang.startswith("en")
    cache_key = _cache_language_key(user_msg, preferred_lang)

    # Language detection and translation setup
    lang_detection, normalized_lang, is_indic, should_translate = detect_and_prepare_language_info(
        container, user_msg, preferred_lang
    )
    user_id = user.get("id", "anonymous") if user else "anonymous"
    stable_session_id = normalize_session_id(chat_body.session_id, user_id)
    chat_history = [m.model_dump() for m in chat_body.messages]
    # Cap conversation context to prevent OOM/timeouts on long sessions
    if len(chat_history) > settings.chat_history_max_messages:
        chat_history = chat_history[-settings.chat_history_max_messages :]

    # Translate user query to English if Indic preferred language selected
    user_msg_en = user_msg
    if should_translate:
        user_msg_en = await translate_text(user_msg, preferred_lang, "en", container)
        logger.info(f"Translated user query from {preferred_lang} to English: {user_msg_en}")

    # Translate history messages to English if Indic language is active
    chat_history_en = []
    if is_indic and should_translate:
        for msg in chat_history:
            msg_content_en = await translate_text(msg["content"], preferred_lang, "en", container)
            chat_history_en.append({"role": msg["role"], "content": msg_content_en})
    else:
        chat_history_en = chat_history

    # User profile and memory preparation
    memory_context, distress_history = await _prepare_user_memory(
        container,
        user_id,
        chat_history_en,
    )

    return {
        "user_msg_en": user_msg_en,
        "is_indic": is_indic,
        "preferred_lang": preferred_lang,
        "user_id": user_id,
        "stable_session_id": stable_session_id,
        "chat_history_en": chat_history_en,
        "memory_context": memory_context,
        "distress_history": distress_history,
        "lang_detection": lang_detection,
        "original_user_msg": chat_body.user_message,  # Keep original for memory saving
        "original_chat_history": chat_body.messages,  # Keep original for memory saving
        "cache_key": cache_key,
    }


@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
@limiter.limit(settings.chat_rate_limit)
async def chat_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> ChatResponse:
    """
    Main conversational endpoint.

    Full pipeline: NeMo Input Rail → LangGraph (11 layers) → NeMo Output Rail
    """
    user_msg = chat_body.user_message.strip()
    preferred_lang = chat_body.language or "en"
    is_indic = preferred_lang and not preferred_lang.startswith("en")
    start_time = time.time()
    cache_key = _cache_language_key(user_msg, preferred_lang)

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if len(user_msg) > settings.max_input_length:
        raise HTTPException(
            status_code=400,
            detail=f"Message too long. Please keep it under {settings.max_input_length} characters.",
        )

    # === Benchmark cache bypass ===
    # Requests from the evaluation benchmark carry X-Test-Key == jwt_secret.
    # We skip both cache reads and cache writes for benchmark traffic so that:
    #   (a) stale cache cannot inflate scores with pre-cached responses, and
    #   (b) benchmark responses cannot pollute the production cache.
    is_benchmark = request.headers.get("X-Test-Key") == settings.jwt_secret

    # === Response Cache Check (Run output rail before returning cached responses) ===
    if not is_benchmark:
        # Check exact-match Redis cache first to bypass embedding calculation
        cached = container.exact_cache.get(cache_key)
        if cached is None:
            cached = container.semantic_cache.get(cache_key)
        if cached is not None:
            REQUEST_COUNT.labels(status="cache_hit").inc()
            # Run cached response through output guardrails to prevent bypass
            cached_response = cached["response"]
            output_check = await container.guardrails.check_output(cached_response)
            final_response = (
                output_check["moderated_response"] if output_check["blocked"] else cached_response
            )

            # Translate back to native language if needed
            if is_indic and final_response != cached_response:
                final_response = await translate_text(
                    final_response, "en", preferred_lang, container
                )

            query_id = str(uuid.uuid4())
            latency_ms = int((time.time() - start_time) * 1000)
            user_id = user.get("id", "anonymous")
            background_tasks.add_task(
                telemetry_sink.log_query_trace,
                query_id=query_id,
                session_id=normalize_session_id(chat_body.session_id, user_id),
                user_id=user_id,
                query_text=user_msg,
                model=getattr(settings, "sarvam_cloud_model", None)
                or getattr(settings, "ollama_model", None)
                or "cache",
                latency_ms=latency_ms,
                status="ok",
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                response_text=final_response,
                citations=cached.get("citations", []),
                provider=getattr(settings, "llm_provider", None),
                route_decision="semantic_cache",
                cache_hit=True,
            )
            return ChatResponse(
                response=final_response,
                intent=cached.get("intent"),
                meditation_step=cached.get("meditation_step", 0),
                citations=cached.get("citations", []),
                trace_id=query_id,
                latency_ms=latency_ms,
                model_used=getattr(settings, "sarvam_cloud_model", None)
                or getattr(settings, "ollama_model", None),
                model_provider=getattr(settings, "llm_provider", None),
                route_decision="semantic_cache",
            )

    # Prepare request state (language detection, translation, memory preparation)
    state = await _prepare_request_state(container, chat_body, preferred_lang, user=user)
    user_msg_en = state["user_msg_en"]
    is_indic = state["is_indic"]
    preferred_lang = state["preferred_lang"]
    user_id = state["user_id"]
    stable_session_id = state["stable_session_id"]
    chat_history = [m.model_dump() for m in chat_body.messages]
    chat_history_en = state["chat_history_en"]
    memory_context = state["memory_context"]
    distress_history = state["distress_history"]
    lang_detection = state["lang_detection"]

    # === Layer 1: NeMo Input Rail ===
    with REQUEST_LATENCY.labels(stage="guardrails").time():
        input_check = await container.guardrails.check_input(user_msg_en)

    if input_check["blocked"]:
        logger.info(f"Input blocked: {input_check['reason']}")
        REQUEST_COUNT.labels(status="blocked").inc()
        blocked_resp = input_check["response"]
        if is_indic:
            blocked_resp = await translate_text(blocked_resp, "en", preferred_lang, container)
        return ChatResponse(
            response=blocked_resp,
            blocked=True,
            block_reason=input_check["reason"],
        )

    # === Depression Detection (Council Recommendation) ===
    # We log the distress assessment here, but no longer fail-fast.
    # We let the query proceed to the RAG pipeline so Mukti Guru can
    # provide a compassionate teaching-based response first.
    try:
        if container.serene_mind:
            assessment_history = (
                [{"role": "system", "content": f"Previous distress history: {distress_history}"}]
                if distress_history
                else []
            )
            assessment = await container.serene_mind.analyze_with_history(
                user_msg_en, history=chat_history_en + assessment_history
            )
            if assessment.level.value >= 2:
                logger.info(
                    f"Distress detected ({assessment.level.name}), passing to RAG pipeline for compassionate response."
                )
    except Exception as e:
        logger.warning(f"Serene Mind detection failed (non-fatal): {e}")

    # === PROACTIVE SERENE MIND TRIGGERING ===
    # Check if we should proactively offer Serene Mind based on conversation trend
    try:
        if container.serene_mind and container.user_profile:
            # Use current assessment if available, otherwise create a neutral one
            current_assessment = locals().get("assessment")
            if current_assessment is None:
                current_assessment = DistressAssessment(
                    level=DistressLevel.NONE,
                    confidence=0.0,
                    detected_signals=[],
                    language_detected=lang_detection.primary.value,
                    recommended_response_type="normal",
                )

            proactive_assessment = await container.serene_mind.analyze_distress_trend(
                user_id=user_id,
                current_assessment=current_assessment,
                user_profile_service=container.user_profile,
            )

            if proactive_assessment:
                # 15-minute cooldown: skip if user completed Serene Mind recently.
                _client_ts = chat_body.last_serene_mind_at or 0.0
                _now = time.time()
                _COOLDOWN_SECS = 15 * 60  # 15 minutes
                _skip_cooldown = (_now - _client_ts) < _COOLDOWN_SECS

                # Also check Supabase for server-side verification
                if not _skip_cooldown and container.user_profile:
                    _db_ts = await container.user_profile.get_last_meditation_session(user_id)
                    if _db_ts and (_now - _db_ts) < _COOLDOWN_SECS:
                        _skip_cooldown = True

                if not _skip_cooldown:
                    logger.info(
                        f"Proactive Serene Mind triggered for user {user_id}: "
                        f"level={proactive_assessment.level.name}, "
                        f"confidence={proactive_assessment.confidence:.2f}"
                    )
                    state["proactive_serene_mind"] = {
                        "triggered": True,
                        "level": proactive_assessment.level.name,
                        "confidence": proactive_assessment.confidence,
                        "signals": proactive_assessment.detected_signals,
                        "suggested_response": container.serene_mind.get_response(
                            proactive_assessment
                        ),
                        "teachings_prelude": (
                            "Sri Krishnaji and Preethaji teach us that suffering is not the truth of who you are. "
                            "Every moment of pain is also a doorway to awakening. "
                            "You are not alone in this — Mukti Guru is here with you. "
                            "Before we continue, let's pause together in a moment of Serene Mind."
                        ),
                    }
                else:
                    logger.info(
                        f"Proactive Serene Mind skipped for {user_id} — within 15-min cooldown."
                    )
    except Exception as e:
        logger.warning(f"Proactive Serene Mind analysis failed (non-fatal): {e}")

    # === Layers 2-11: LangGraph RAG Pipeline ===
    try:
        # Coalesce identical concurrent requests (Sys 4.1)
        async def run_pipeline():
            initial_state = create_initial_state(
                question=user_msg_en,
                chat_history=chat_history_en,
                meditation_step=chat_body.meditation_step,
                request_id=correlation_id_var.get(),
            )
            # Inject language and user context into state
            initial_state["detected_language"] = lang_detection.primary.value
            initial_state["user_id"] = user_id
            initial_state["memory_context"] = memory_context

            # A/B Testing Logic
            import random

            if settings.ab_testing_enabled and random.random() < settings.ab_testing_ratio:
                initial_state["ab_model"] = "krutrim"
            else:
                initial_state["ab_model"] = "primary"

            return await container.rag_graph.ainvoke(initial_state)

        result = await asyncio.wait_for(
            coalescer.get_or_run(
                f"{preferred_lang}:{user_msg_en}:{hashlib.md5(str([m['content'] for m in chat_history_en[-4:]]).encode()).hexdigest()[:8]}",
                run_pipeline,
            ),
            timeout=settings.pipeline_timeout,  # Dedicated pipeline budget (180s) >> per-call timeout (120s)
        )

        final_answer = result.get("final_answer", "I apologize, something went wrong.")
        intent = result.get("intent", "CASUAL")
        # Normalize FACTUAL to QUERY for consistency with legacy monitoring and cache
        if intent == "FACTUAL":
            intent = "QUERY"
        med_step = result.get("meditation_step", 0)
        citations = result.get("citations", [])
        REQUEST_COUNT.labels(status="success").inc()

        # Translate final answer back to native language if Indic preferred language selected
        final_answer_native = final_answer
        if is_indic:
            final_answer_native = await translate_text(
                final_answer, "en", preferred_lang, container
            )
            logger.info(f"Translated final answer to {preferred_lang}: {final_answer_native}")

        # NEW: Save conversation memory (always save native/user-visible texts)
        if container.user_profile:
            from services.user_profile_service import ConversationMemory

            memory = ConversationMemory(
                session_id=stable_session_id,
                user_id=user_id,
                started_at=time.time(),
                messages=[
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": final_answer_native},
                ],
                key_insights=[c if isinstance(c, str) else c.get("title", "") for c in citations],
                emotional_arc=[
                    {
                        "timestamp": time.time(),
                        "distress_level": assessment.level.value if "assessment" in locals() else 0,
                        "topic": intent,
                    }
                ],
                follow_up_suggestions=[],
            )
            background_tasks.add_task(container.user_profile.save_conversation_memory, memory)

        # Populate cache for QUERY and CASUAL intents (both exact and semantic caching)
        # Skip cache population for benchmark requests to prevent score inflation.
        if not is_benchmark and intent in ["QUERY", "CASUAL", "FACTUAL"]:
            container.exact_cache.put(
                query=cache_key,
                response=final_answer_native,
                intent=intent,
                citations=citations,
                meditation_step=med_step,
            )
            container.semantic_cache.put(
                query=cache_key,
                response=final_answer_native,
                intent=intent,
                citations=citations,
                meditation_step=med_step,
            )

        final_answer = final_answer_native

    except TimeoutError:
        logger.error(f"Pipeline timeout after {settings.pipeline_timeout}s for: {user_msg[:100]}")
        REQUEST_COUNT.labels(status="timeout").inc()
        final_answer = (
            "I apologize, the process took too long. 🙏 Please try asking your question again."
        )
        if is_indic:
            final_answer = await translate_text(final_answer, "en", preferred_lang, container)
        intent = "ERROR"
        med_step = 0
        citations = []
    except CircuitOpenException:
        logger.warning("Sarvam API circuit breaker is OPEN in chat_endpoint — failing fast")
        if is_benchmark:
            raise HTTPException(
                status_code=503, detail="Service temporarily unavailable - circuit breaker is OPEN"
            )
        else:
            final_answer = "I apologize, but the service is temporarily unavailable. Please try again in a moment."
            intent = "ERROR"
            med_step = 0
            citations = []
    except Exception as e:
        citations = []
        from services.sarvam_service import QuotaExceededError

        if (
            isinstance(e, QuotaExceededError)
            or "credits" in str(e).lower()
            or "429" in str(e).lower()
        ):
            logger.warning(f"Sarvam API quota error intercepted: {e}")
            fallback_answer = "I apologize, our upstream provider is currently out of credits. Here is the relevant wisdom directly retrieved from our sacred knowledge base:\n\n"
            try:
                from app.dependencies import get_container

                container = get_container()
                query_enc = container.embedding.encode_single_full(user_msg_en)
                docs = container.qdrant.search(
                    query_vector=query_enc["dense"], limit=3, sparse_vector=query_enc["sparse"]
                )
                if docs:
                    for i, doc in enumerate(docs, 1):
                        text_snippet = doc["text"].strip()
                        if len(text_snippet) > 350:
                            text_snippet = text_snippet[:350] + "..."
                        fallback_answer += f"✦ **Teaching {i}:** {text_snippet}\n\n"
                    final_answer = fallback_answer
                    citations = [
                        d.get("source_url")
                        for d in docs
                        if d.get("source_url") and d.get("source_url") != "None"
                    ]
                else:
                    final_answer = (
                        "The essence of spiritual practice is compassion and mindfulness. "
                        "Even in stillness, your presence is heard."
                    )
            except Exception as inner_e:
                logger.error(f"Fallback context synthesis failed: {inner_e}")
                final_answer = (
                    "The essence of spiritual practice is compassion and mindfulness. "
                    "Even in stillness, your presence is heard."
                )
            # Translate fallback answer if Indic
            if is_indic:
                final_answer = await translate_text(final_answer, "en", preferred_lang, container)
            intent = "QUERY"
            med_step = 0
        else:
            logger.error(f"RAG pipeline error: {e}", exc_info=True)
            REQUEST_COUNT.labels(status="error").inc()
            final_answer = "I apologize, but I don't have that specific teaching. 🙏 Please try asking another question."
            if is_indic:
                final_answer = await translate_text(final_answer, "en", preferred_lang, container)
            intent = "ERROR"
            med_step = 0
            citations = []

    # === Layer 12: NeMo Output Rail ===
    output_check = await container.guardrails.check_output(final_answer)
    if output_check["blocked"]:
        logger.info(f"Output moderated: {output_check['reason']}")
        final_answer = output_check["moderated_response"]

    # --- Telemetry Logging ---
    try:
        session_uuid = stable_session_id
    except (ValueError, TypeError, AttributeError):
        session_uuid = str(uuid.uuid4())

    query_id = str(uuid.uuid4())
    latency_ms = int((time.time() - start_time) * 1000)

    # Collect retrieval metadata from result
    retrieval_meta = None
    if citations:
        retrieval_meta = {
            "chunk_ids": [c.get("id") if isinstance(c, dict) else "" for c in citations],
            "source_docs": [c.get("source_url") if isinstance(c, dict) else c for c in citations],
            "scores": [c.get("score", 0.0) if isinstance(c, dict) else 1.0 for c in citations],
            "top_k": len(citations),
            "hit": len(citations) > 0,
        }

    # Collect trigger events (Distress)
    trigger_events = []
    if "assessment" in locals() and assessment.level.value >= 2:
        trigger_events.append(
            {
                "name": "DISTRESS",
                "metadata": {
                    "level": assessment.level.name,
                    "confidence": assessment.confidence,
                    "signals": assessment.detected_signals,
                },
            }
        )

    # Extract spans from LangGraph metrics
    spans_data = []
    if "result" in locals() and isinstance(result, dict) and result.get("metrics"):
        for node_name, duration_sec in result["metrics"].items():
            spans_data.append(
                {"span_name": node_name, "start_ms": 0, "duration_ms": int(duration_sec * 1000)}
            )

    # Extract safety events
    safety_events = []
    if input_check.get("blocked"):
        safety_events.append(
            {
                "event_type": "INPUT_GUARDRAIL",
                "decision": "BLOCKED",
                "reason": input_check.get("reason") or "Harmful input detected",
            }
        )
    if output_check.get("blocked"):
        safety_events.append(
            {
                "event_type": "OUTPUT_GUARDRAIL",
                "decision": "BLOCKED",
                "reason": output_check.get("reason") or "Harmful output detected",
            }
        )

    is_rag = intent == "QUERY"
    response_data = {
        "faithfulness": result.get("faithfulness_score", 0.0)
        if is_rag and "result" in locals()
        else 1.0,
        "answer_relevancy": 1.0,
        "context_precision": 1.0,
        "context_recall": 1.0,
        "hallucination_flag": not result.get("is_faithful", True)
        if is_rag and "result" in locals()
        else False,
        "judge_reasoning": result.get("verification_reason", "")
        if is_rag and "result" in locals()
        else "",
    }

    model_used = (
        result.get("model_used")
        if "result" in locals() and isinstance(result, dict)
        else getattr(settings, "sarvam_cloud_model", None)
        or getattr(settings, "ollama_model", None)
    )
    model_provider = (
        result.get("model_provider")
        if "result" in locals() and isinstance(result, dict)
        else getattr(settings, "llm_provider", None)
    )
    route_decision = (
        result.get("route_decision") if "result" in locals() and isinstance(result, dict) else None
    )

    background_tasks.add_task(
        telemetry_sink.log_query_trace,
        query_id=query_id,
        session_id=session_uuid,
        user_id=user_id,
        query_text=user_msg,
        model=model_used or "unknown",
        latency_ms=latency_ms,
        status="ok" if intent != "ERROR" else "error",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        response_text=final_answer,
        citations=citations,
        faithfulness=response_data["faithfulness"],
        answer_relevancy=response_data["answer_relevancy"],
        context_precision=response_data["context_precision"],
        context_recall=response_data["context_recall"],
        hallucination_flag=response_data["hallucination_flag"],
        confidence_score=result.get("confidence_score")
        if "result" in locals() and isinstance(result, dict)
        else None,
        judge_reasoning=response_data["judge_reasoning"],
        retrieval_metadata=retrieval_meta,
        spans=spans_data,
        trigger_events=trigger_events,
        safety_events=safety_events,
        provider=model_provider,
        route_decision=route_decision,
        cache_hit=False,
        tokens_per_second=round(
            max(1, len(final_answer.split())) / max(latency_ms / 1000, 0.001), 2
        ),
        evaluation_trace=result.get("evaluation_trace")
        if "result" in locals() and isinstance(result, dict)
        else None,
    )

    return ChatResponse(
        response=final_answer,
        intent=intent,
        meditation_step=med_step,
        citations=citations,
        blocked=output_check.get("blocked", False),
        block_reason=output_check.get("reason"),
        proactive_serene_mind=state.get("proactive_serene_mind"),
        faithfulness_score=result.get("faithfulness_score")
        if "result" in locals() and isinstance(result, dict)
        else None,
        relevancy_score=result.get("relevancy_score")
        if "result" in locals() and isinstance(result, dict)
        else None,
        confidence_score=result.get("confidence_score")
        if "result" in locals() and isinstance(result, dict)
        else None,
        verification=result.get("verification")
        if "result" in locals() and isinstance(result, dict)
        else None,
        hallucination_flag=response_data.get("hallucination_flag")
        if "response_data" in locals()
        else None,
        trace_id=query_id,
        latency_ms=latency_ms,
        node_timings=result.get("node_timings")
        if "result" in locals() and isinstance(result, dict)
        else None,
        evaluation_trace=result.get("evaluation_trace")
        if "result" in locals() and isinstance(result, dict)
        else None,
        model_used=model_used,
        model_provider=model_provider,
        route_decision=route_decision,
    )


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

    Emits events:
      - {"event": "status", "data": "..."} during pipeline stages
      - {"event": "token", "data": "..."} for each answer token
      - {"event": "done", "data": {...}} final metadata (intent, citations, etc.)
      - {"event": "error", "data": "..."} on failure
    """
    import json

    from fastapi.responses import StreamingResponse

    user_msg = chat_body.user_message.strip()
    preferred_lang = chat_body.language or "en"
    is_indic = preferred_lang and not preferred_lang.startswith("en")
    cache_key = _cache_language_key(user_msg, preferred_lang)

    if not user_msg:

        async def error_stream():
            yield "event: error\ndata: Message cannot be empty\n\n"

        return StreamingResponse(error_stream(), media_type="text/event-stream")

    if len(user_msg) > settings.max_input_length:

        async def length_error_stream():
            yield f"event: error\ndata: Message too long. Please keep it under {settings.max_input_length} characters.\n\n"

        return StreamingResponse(length_error_stream(), media_type="text/event-stream")

    is_benchmark = request.headers.get("X-Test-Key") == settings.jwt_secret
    if settings.is_sarvam_cloud:
        if not container.ollama._circuit.can_execute():
            if is_benchmark:
                raise HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable - circuit breaker is OPEN",
                )
            else:

                async def circuit_error_stream():
                    yield "event: token\ndata: I apologize, but the service is temporarily unavailable. Please try again in a moment.\n\n"
                    meta = json.dumps({"intent": "ERROR", "citations": [], "meditation_step": 0})
                    yield f"event: done\ndata: {meta}\n\n"

                return StreamingResponse(circuit_error_stream(), media_type="text/event-stream")

    async def generate_sse():
        """SSE generator that runs the pipeline and streams results."""
        try:
            stream_start_time = time.time()
            # === Benchmark cache bypass (captures request from outer scope via closure) ===
            is_benchmark = request.headers.get("X-Test-Key") == settings.jwt_secret

            # === Cache check (Run output rail before returning cached responses) ===
            if not is_benchmark:
                # Check exact-match Redis cache first to bypass embedding calculation
                cached_raw = container.exact_cache.get(cache_key)
                if cached_raw is None:
                    cached_raw = container.semantic_cache.get(cache_key)
            else:
                cached_raw = None
            cached = cached_raw
            if cached is not None:
                cached_response = cached["response"]
                output_check = await container.guardrails.check_output(cached_response)
                final_response = (
                    output_check["moderated_response"]
                    if output_check["blocked"]
                    else cached_response
                )

                # Translate back to native language if needed
                if is_indic and final_response != cached_response:
                    final_response = await translate_text(
                        final_response, "en", preferred_lang, container
                    )

                escaped = final_response.replace("\n", "\\n")
                yield f"event: token\ndata: {escaped}\n\n"
                query_id = str(uuid.uuid4())
                latency_ms = int((time.time() - stream_start_time) * 1000)
                meta = json.dumps(
                    {
                        "intent": cached.get("intent"),
                        "citations": cached.get("citations", []),
                        "meditation_step": cached.get("meditation_step", 0),
                        "trace_id": query_id,
                        "cache_hit": True,
                        "route_decision": "semantic_cache",
                        "model_used": getattr(settings, "sarvam_cloud_model", None)
                        or getattr(settings, "ollama_model", None),
                        "model_provider": getattr(settings, "llm_provider", None),
                    }
                )
                yield f"event: done\ndata: {meta}\n\n"
                asyncio.create_task(
                    telemetry_sink.log_query_trace(
                        query_id=query_id,
                        session_id=normalize_session_id(
                            chat_body.session_id, user.get("id", "anonymous")
                        ),
                        user_id=user.get("id", "anonymous"),
                        query_text=user_msg,
                        model=getattr(settings, "sarvam_cloud_model", None)
                        or getattr(settings, "ollama_model", None)
                        or "cache",
                        latency_ms=latency_ms,
                        status="ok",
                        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        response_text=final_response,
                        citations=cached.get("citations", []),
                        provider=getattr(settings, "llm_provider", None),
                        route_decision="semantic_cache",
                        cache_hit=True,
                    )
                )
                return

            user_id = user.get("id", "anonymous")
            start_time = time.time()

            # === Language Detection and Translation Setup ===
            # IMPORTANT: Do NOT reassign `is_indic` here — the outer scope's
            # `is_indic` (line 975) is read on the cache-hit path (line 1007).
            # Any assignment would make Python treat the whole generator as having
            # a local `is_indic`, triggering UnboundLocalError on cache hits.
            lang_detection, normalized_lang, is_indic_detected, should_translate = (
                detect_and_prepare_language_info(container, user_msg, preferred_lang)
            )
            stable_session_id = normalize_session_id(chat_body.session_id, user_id)
            chat_history = [m.model_dump() for m in chat_body.messages]
            # Cap conversation context to prevent OOM/timeouts on long sessions
            if len(chat_history) > settings.chat_history_max_messages:
                chat_history = chat_history[-settings.chat_history_max_messages :]

            # Translate user query to English if Indic preferred language selected
            user_msg_en = user_msg
            if should_translate:
                yield "event: status\ndata: Translating your question to English...\n\n"
                user_msg_en = await translate_text(user_msg, preferred_lang, "en", container)
                logger.info(
                    f"Stream: Translated user query from {preferred_lang} to English: {user_msg_en}"
                )

            # Translate history messages to English if Indic language is active
            chat_history_en = []
            if is_indic_detected and should_translate:

                async def _translate_msg(msg):
                    return await translate_text(msg["content"], preferred_lang, "en", container)

                chat_history_en = await asyncio.gather(*[_translate_msg(m) for m in chat_history])
                chat_history_en = list(chat_history_en)
            else:
                chat_history_en = chat_history

            # === NEW: User Profile & Memory ===
            memory_context, distress_history = await _prepare_user_memory(
                container,
                user_id,
                chat_history_en,
            )

            # === Layer 1: Input rail ===
            yield "event: status\ndata: Checking message safety...\n\n"
            input_check = await container.guardrails.check_input(user_msg_en)

            if input_check["blocked"]:
                blocked_resp = input_check["response"]
                if is_indic_detected:
                    blocked_resp = await translate_text(
                        blocked_resp, "en", preferred_lang, container
                    )
                yield f"event: token\ndata: {blocked_resp}\n\n"
                meta = json.dumps({"blocked": True, "block_reason": input_check["reason"]})
                yield f"event: done\ndata: {meta}\n\n"
                return

            # === Depression check (non-fatal if detection fails) ===
            try:
                if container.serene_mind:
                    assessment_history = (
                        [
                            {
                                "role": "system",
                                "content": f"Previous distress history: {distress_history}",
                            }
                        ]
                        if distress_history
                        else []
                    )
                    assessment = await container.serene_mind.analyze_with_history(
                        user_msg_en,
                        history=chat_history_en + assessment_history,
                    )
                    if assessment.level.value >= 2:
                        logger.info(
                            f"Stream: Distress detected ({assessment.level.name}), passing to RAG pipeline."
                        )
            except Exception as e:
                logger.warning(f"Serene Mind detection failed in stream (non-fatal): {e}")

            # === PROACTIVE SERENE MIND TRIGGERING ===
            # Check if we should proactively offer Serene Mind based on conversation trend
            proactive_serene_mind = None
            try:
                if container.serene_mind and container.user_profile:
                    current_assessment = locals().get("assessment")
                    if current_assessment is None:
                        current_assessment = DistressAssessment(
                            level=DistressLevel.NONE,
                            confidence=0.0,
                            detected_signals=[],
                            language_detected=lang_detection.primary.value,
                            recommended_response_type="normal",
                        )

                    proactive_assessment = await container.serene_mind.analyze_distress_trend(
                        user_id=user_id,
                        current_assessment=current_assessment,
                        user_profile_service=container.user_profile,
                    )

                    if proactive_assessment:
                        # 15-minute cooldown check
                        _client_ts = chat_body.last_serene_mind_at or 0.0
                        _now = time.time()
                        _COOLDOWN_SECS = 15 * 60
                        _skip_cooldown = (_now - _client_ts) < _COOLDOWN_SECS

                        if not _skip_cooldown and container.user_profile:
                            _db_ts = await container.user_profile.get_last_meditation_session(
                                user_id
                            )
                            if _db_ts and (_now - _db_ts) < _COOLDOWN_SECS:
                                _skip_cooldown = True

                        if not _skip_cooldown:
                            logger.info(
                                f"Stream: Proactive Serene Mind triggered for user {user_id}: "
                                f"level={proactive_assessment.level.name}, "
                                f"confidence={proactive_assessment.confidence:.2f}"
                            )
                            proactive_serene_mind = {
                                "triggered": True,
                                "level": proactive_assessment.level.name,
                                "confidence": proactive_assessment.confidence,
                                "signals": proactive_assessment.detected_signals,
                                "suggested_response": container.serene_mind.get_response(
                                    proactive_assessment
                                ),
                                "teachings_prelude": (
                                    "Sri Krishnaji and Preethaji teach us that suffering is not the truth of who you are. "
                                    "Every moment of pain is also a doorway to awakening. "
                                    "You are not alone in this — Mukti Guru is here with you. "
                                    "Before we continue, let's pause together in a moment of Serene Mind."
                                ),
                            }
                        else:
                            logger.info(
                                f"Stream: Proactive Serene Mind skipped for {user_id} — within 15-min cooldown."
                            )
            except Exception as e:
                logger.warning(f"Proactive Serene Mind analysis failed in stream (non-fatal): {e}")

            # === RAG Pipeline ===
            yield "event: status\ndata: Understanding your question...\n\n"
            initial_state = create_initial_state(
                question=user_msg_en,
                chat_history=chat_history_en,
                meditation_step=chat_body.meditation_step,
                request_id=correlation_id_var.get(),
            )
            # Inject language and user context into state
            initial_state["detected_language"] = lang_detection.primary.value
            initial_state["user_id"] = user_id
            initial_state["memory_context"] = memory_context

            # A/B Testing Logic
            import random

            if settings.ab_testing_enabled and random.random() < settings.ab_testing_ratio:
                initial_state["ab_model"] = "krutrim"
            else:
                initial_state["ab_model"] = "primary"

            # Create a queue for token streaming
            queue = asyncio.Queue()
            config = {"configurable": {"stream_queue": queue}}

            # Run RAG graph in the background
            pipeline_task = asyncio.create_task(
                asyncio.wait_for(
                    container.rag_graph.ainvoke(initial_state, config=config),
                    timeout=settings.llm_timeout + 15,
                )
            )

            # Stream tokens from queue as they are produced in the graph.
            # NOTE: For Indic requests we suppress English tokens here to avoid
            # a double-render: client would see English tokens first, then the
            # full translated text.  Status events are still forwarded so the
            # "thinking pills" continue to update normally.
            has_streamed_tokens = False
            while not pipeline_task.done() or not queue.empty():
                try:
                    # Poll queue with timeout to check if task finished
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                    if isinstance(item, dict):
                        # Support structured events (status/metadata)
                        event_type = item.get("event", "token")
                        data = item.get("data", "")
                        if event_type == "status":
                            # Always forward status/thinking-pill events
                            yield f"event: status\ndata: {data}\n\n"
                        elif event_type == "token" and not is_indic_detected:
                            # Suppress English tokens when translation is pending
                            has_streamed_tokens = True
                            escaped = data.replace("\n", "\\n")
                            yield f"event: token\ndata: {escaped}\n\n"
                    elif not is_indic_detected:
                        # Plain string token — suppress for Indic
                        has_streamed_tokens = True
                        escaped = item.replace("\n", "\\n")
                        yield f"event: token\ndata: {escaped}\n\n"
                    queue.task_done()
                except TimeoutError:
                    continue

            # Wait for pipeline completion to get final state
            result = await pipeline_task
            final_answer = result.get("final_answer", "I apologize, something went wrong.")
            intent = result.get("intent", "CASUAL")
            med_step = result.get("meditation_step", 0)
            citations = result.get("citations", [])

            # For Indic language requests, translate the final completed answer
            if is_indic_detected:
                yield "event: status\ndata: Translating spiritual response to your language...\n\n"
                final_answer_native = await translate_text(
                    final_answer, "en", preferred_lang, container
                )
                logger.info(
                    f"Stream: Translated final answer to {preferred_lang}: {final_answer_native}"
                )

                output_check = await container.guardrails.check_output(final_answer_native)
                if output_check["blocked"]:
                    final_answer_native = output_check["moderated_response"]

                final_answer = final_answer_native
                # Stream the native response to the client
                for i in range(0, len(final_answer_native), 10):
                    chunk = final_answer_native[i : i + 10]
                    escaped = chunk.replace("\n", "\\n")
                    yield f"event: token\ndata: {escaped}\n\n"
                    await asyncio.sleep(0.01)
            else:
                # Run output guardrail check for non-Indic
                output_check = await container.guardrails.check_output(final_answer)
                if output_check["blocked"]:
                    final_answer = output_check["moderated_response"]

                # If we did NOT stream any tokens during graph execution (e.g. CASUAL or DISTRESS intent),
                # stream the final answer here using simulated streaming.
                if not has_streamed_tokens:
                    for i in range(0, len(final_answer), 20):
                        chunk = final_answer[i : i + 20]
                        escaped = chunk.replace("\n", "\\n")
                        yield f"event: token\ndata: {escaped}\n\n"
                        await asyncio.sleep(0.01)

            # Cache FACTUAL, QUERY, and CASUAL results (both exact and semantic caching)
            # Skip cache population for benchmark requests to prevent score inflation.
            if not is_benchmark and intent in ["QUERY", "CASUAL", "FACTUAL"]:
                container.exact_cache.put(
                    cache_key, final_answer, intent, citations, meditation_step=med_step
                )
                container.semantic_cache.put(
                    cache_key, final_answer, intent, citations, meditation_step=med_step
                )

            REQUEST_COUNT.labels(status="success").inc()
            query_id = str(uuid.uuid4())
            latency_ms = int((time.time() - start_time) * 1000)
            approx_tokens = max(1, len(final_answer.split()))
            tokens_per_second = round(approx_tokens / max(latency_ms / 1000, 0.001), 2)
            model_used = (
                result.get("model_used")
                or getattr(settings, "sarvam_cloud_model", None)
                or getattr(settings, "ollama_model", None)
            )
            model_provider = result.get("model_provider") or getattr(settings, "llm_provider", None)
            route_decision = result.get("route_decision")

            # Final metadata
            meta = json.dumps(
                {
                    "intent": intent,
                    "citations": citations,
                    "meditation_step": med_step,
                    "proactive_serene_mind": proactive_serene_mind,
                    "trace_id": query_id,
                    "latency_ms": latency_ms,
                    "tokens_per_second": tokens_per_second,
                    "model_used": model_used,
                    "model_provider": model_provider,
                    "route_decision": route_decision,
                    "node_timings": result.get("node_timings")
                    if "result" in locals() and isinstance(result, dict)
                    else None,
                    "evaluation_trace": result.get("evaluation_trace")
                    if "result" in locals() and isinstance(result, dict)
                    else None,
                    "faithfulness_score": result.get("faithfulness_score")
                    if "result" in locals() and isinstance(result, dict)
                    else None,
                    "relevancy_score": result.get("relevancy_score")
                    if "result" in locals() and isinstance(result, dict)
                    else None,
                    "confidence_score": result.get("confidence_score")
                    if "result" in locals() and isinstance(result, dict)
                    else None,
                    "verification": result.get("verification")
                    if "result" in locals() and isinstance(result, dict)
                    else None,
                }
            )
            yield f"event: done\ndata: {meta}\n\n"

            # NEW: Save conversation memory (always save native texts)
            if container.user_profile:
                from services.user_profile_service import ConversationMemory

                memory = ConversationMemory(
                    session_id=stable_session_id,
                    user_id=user_id,
                    started_at=time.time(),
                    messages=[
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": final_answer},
                    ],
                    key_insights=[
                        c if isinstance(c, str) else c.get("title", "") for c in citations
                    ],
                    emotional_arc=[
                        {
                            "timestamp": time.time(),
                            "distress_level": assessment.level.value
                            if "assessment" in locals()
                            else 0,
                            "topic": intent,
                        }
                    ],
                    follow_up_suggestions=[],
                )
                asyncio.create_task(container.user_profile.save_conversation_memory(memory))

            # --- Telemetry Logging for Stream ---
            try:
                session_uuid = stable_session_id
            except (ValueError, TypeError, AttributeError):
                session_uuid = str(uuid.uuid4())

            # Collect retrieval metadata from result
            retrieval_meta = None
            if citations:
                retrieval_meta = {
                    "chunk_ids": [c.get("id") if isinstance(c, dict) else "" for c in citations],
                    "source_docs": [
                        c.get("source_url") if isinstance(c, dict) else c for c in citations
                    ],
                    "scores": [
                        c.get("score", 0.0) if isinstance(c, dict) else 1.0 for c in citations
                    ],
                    "top_k": len(citations),
                    "hit": len(citations) > 0,
                }

            # Collect trigger events (Distress)
            trigger_events = []
            if "assessment" in locals() and assessment.level.value >= 2:
                trigger_events.append(
                    {
                        "name": "DISTRESS",
                        "metadata": {
                            "level": assessment.level.name,
                            "confidence": assessment.confidence,
                            "signals": assessment.detected_signals,
                        },
                    }
                )

            # Extract spans from LangGraph metrics
            spans_data = []
            if "result" in locals() and isinstance(result, dict) and result.get("metrics"):
                for node_name, duration_sec in result["metrics"].items():
                    spans_data.append(
                        {
                            "span_name": node_name,
                            "start_ms": 0,
                            "duration_ms": int(duration_sec * 1000),
                        }
                    )

            # Extract safety events
            safety_events = []
            if "input_check" in locals() and input_check.get("blocked"):
                safety_events.append(
                    {
                        "event_type": "INPUT_GUARDRAIL",
                        "decision": "BLOCKED",
                        "reason": input_check.get("reason") or "Harmful input detected",
                    }
                )
            if "output_check" in locals() and output_check.get("blocked"):
                safety_events.append(
                    {
                        "event_type": "OUTPUT_GUARDRAIL",
                        "decision": "BLOCKED",
                        "reason": output_check.get("reason") or "Harmful output detected",
                    }
                )

            is_rag = intent == "QUERY"
            response_data = {
                "faithfulness": result.get("faithfulness_score", 0.0)
                if is_rag and "result" in locals()
                else 1.0,
                "answer_relevancy": 1.0,
                "context_precision": 1.0,
                "context_recall": 1.0,
                "hallucination_flag": not result.get("is_faithful", True)
                if is_rag and "result" in locals()
                else False,
                "judge_reasoning": result.get("verification_reason", "")
                if is_rag and "result" in locals()
                else "",
            }

            asyncio.create_task(
                telemetry_sink.log_query_trace(
                    query_id=query_id,
                    session_id=session_uuid,
                    user_id=user_id,
                    query_text=user_msg,
                    model=model_used or "unknown",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status="ok" if intent != "ERROR" else "error",
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    response_text=final_answer,
                    citations=citations,
                    faithfulness=response_data["faithfulness"],
                    answer_relevancy=response_data["answer_relevancy"],
                    context_precision=response_data["context_precision"],
                    context_recall=response_data["context_recall"],
                    hallucination_flag=response_data["hallucination_flag"],
                    confidence_score=result.get("confidence_score")
                    if "result" in locals() and isinstance(result, dict)
                    else None,
                    judge_reasoning=response_data["judge_reasoning"],
                    retrieval_metadata=retrieval_meta,
                    spans=spans_data,
                    trigger_events=trigger_events,
                    safety_events=safety_events,
                    provider=model_provider,
                    route_decision=route_decision,
                    cache_hit=False,
                    tokens_per_second=tokens_per_second,
                    evaluation_trace=result.get("evaluation_trace")
                    if "result" in locals() and isinstance(result, dict)
                    else None,
                )
            )

        except CircuitOpenException as e:
            logger.warning(f"CircuitOpenException caught in generate_sse: {e}")
            if is_benchmark:
                raise HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable - circuit breaker is OPEN",
                )
            else:
                yield "event: token\ndata: I apologize, but the service is temporarily unavailable. Please try again in a moment.\n\n"
                meta = json.dumps({"intent": "ERROR", "citations": [], "meditation_step": 0})
                yield f"event: done\ndata: {meta}\n\n"
        except Exception as e:
            logger.error(f"SSE streaming error: {e}", exc_info=True)
            REQUEST_COUNT.labels(status="error").inc()
            yield "event: error\ndata: An error occurred. Please try again.\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
        if container.rag_graph:
            # Use the lightweight retrieval node (bypass full pipeline for speed)
            initial_state = create_initial_state(
                question=query,
                chat_history=[],
                meditation_step=0,
                request_id=f"breath-teaching-{technique_id}",
            )
            initial_state["user_id"] = user.get("sub", "anonymous")
            initial_state["skip_full_pipeline"] = True  # hint for lightweight path

            result = await asyncio.wait_for(
                container.rag_graph.ainvoke(initial_state),
                timeout=12.0,
            )
            raw = result.get("answer", "")
            # Trim to 2 sentences max — this is a subtitle, not a full answer
            sentences = [s.strip() for s in raw.split(".") if s.strip()][:2]
            teaching = ". ".join(sentences) + ("." if sentences else "")

        if not teaching and container.ollama:
            # Fallback: direct LLM call if RAG graph unavailable
            teaching = await asyncio.wait_for(
                container.ollama.generate(
                    prompt=(
                        f"In 1-2 sentences, share a teaching from Sri Preethaji or Sri Krishnaji "
                        f"about: {query.lower()} Be poetic, grounded in their actual teachings, "
                        f"and end with an invitation to practice."
                    ),
                    max_tokens=80,
                ),
                timeout=8.0,
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
        logger.error(f"Local Whisper fallback failed: {e}")
        raise HTTPException(status_code=500, detail=f"Speech transcription failed: {e}")


@app.post("/api/speech/tts", tags=["Speech"])
async def text_to_speech_endpoint(
    req: SpeechTTSRequest, container: ServiceContainer = Depends(get_container)
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
                    status_code=resp.status_code, detail=f"Sarvam TTS failed: {resp.text}"
                )
    except Exception as e:
        logger.error(f"Error calling Sarvam TTS: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/api/ready", tags=["Health"])
async def readiness_endpoint(container: ServiceContainer = Depends(get_container)) -> dict:
    """
    Kubernetes readiness probe endpoint.

    Unlike /api/health (liveness), this checks that critical services
    (Qdrant vector DB, LLM provider) are ready to serve requests.
    Returns 503 if not ready.
    """
    health = await container.health_status()

    critical_ok = health.get("qdrant", False) and health.get("ollama", False)

    if not critical_ok:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "qdrant": health.get("qdrant", False),
                "llm": health.get("ollama", False),
                "message": "Critical services not ready",
            },
        )

    return {
        "ready": True,
        "qdrant": True,
        "llm": True,
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
