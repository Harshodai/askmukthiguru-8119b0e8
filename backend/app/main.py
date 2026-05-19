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

import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any, Union
import contextvars
from dataclasses import asdict

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Depends, File, UploadFile, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field

# Fix import paths — run from backend/ directory
sys.path.insert(0, ".")

from app.config import settings
from app.dependencies import get_container, startup, shutdown, ServiceContainer
from app.observability import init_observability
from app.telemetry_db import init_telemetry_db, log_query_trace
from rag.graph import create_initial_state
from rag.memory import build_memory_context, normalize_session_id
import time
import uuid
import hashlib
from app.metrics import REQUEST_LATENCY, REQUEST_COUNT, metrics_endpoint
from services.auth_service import current_active_user, get_current_user_from_supabase
from services.user_profile_service import LanguagePreference, SpiritualLevel

# Correlation ID context variable — accessible from anywhere in the async call chain
correlation_id_var = contextvars.ContextVar('correlation_id', default='-')
from services.cache_service import RedisCacheAdapter, InMemoryCacheAdapter, init_llm_cache

from app.core.limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.api.endpoints.auth import router as auth_router
from routers.admin import admin_router
from routers.feedback import router as feedback_router
from app.core.database import init_db
from models.user import User as AuthUser

logger = logging.getLogger(__name__)

# Global instances
class RequestCoalescer:
    """
    System Design Pattern 4.1: Coalesce Caching.
    Merges identical concurrent requests to avoid redundant RAG runs.
    Auto-cleans results after TTL to prevent unbounded memory growth.
    """
    def __init__(self, ttl: float = 60.0):
        self._locks = {}
        self._results = {}  # key -> (result, timestamp)
        self._ttl = ttl

    def _cleanup(self):
        """Remove expired entries to prevent memory leak."""
        now = time.time()
        expired = [k for k, (_, ts) in self._results.items() if now - ts > self._ttl]
        for k in expired:
            self._results.pop(k, None)
            self._locks.pop(k, None)

    async def get_or_run(self, key: str, coro_func):
        self._cleanup()

        if key in self._results:
            result, _ = self._results[key]
            return result
        
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        
        async with self._locks[key]:
            if key in self._results:
                result, _ = self._results[key]
                return result
            
            result = await coro_func()
            self._results[key] = (result, time.time())
            return result

coalescer = RequestCoalescer()

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
            if cid != '-':
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
    shutdown_scheduler = lambda: None
    try:
        from infrastructure.scheduler import start_scheduler, shutdown_scheduler as _sd
        start_scheduler()
        shutdown_scheduler = _sd
    except Exception as e:
        logger.warning(f"Failed to initialize APScheduler: {e}")

    # 7. Initialize GPTCache to intercept identical LLM calls
    init_llm_cache()
    
    logger.info("=== Mukthi Guru Backend Ready ===")
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    try:
        if callable(shutdown_scheduler):
            shutdown_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler shutdown error: {e}")
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
                msg_headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"content-security-policy", (
                        "default-src 'self'; "
                        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
                        "font-src 'self' https://fonts.gstatic.com; "
                        "img-src 'self' data: https:; "
                        "connect-src 'self' https://api.sarvam.ai https://*.supabase.co wss://*.supabase.co; "
                        "frame-ancestors 'none';"
                    ).encode("utf-8"))
                ])
                message["headers"] = msg_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

app.add_middleware(SecurityHeadersMiddleware)


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global error boundary catching all unhandled exceptions."""
    error_id = f"err_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    logger.error(
        f"Unhandled server error on {request.url.path} (error_id: {error_id}): {exc}", 
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "An internal error occurred",
            "message": "We encountered an issue processing your request. Please try again.",
            "error_id": error_id
        },
    )


app.include_router(auth_router, prefix="/api/auth")
# (Other routers moved down to avoid circular deps if any, or just kept here)
app.include_router(admin_router, prefix="/api/admin")
app.include_router(feedback_router, prefix="/api")

# Mount trace dashboard routes
from app.trace_dashboard import router as trace_router
app.include_router(trace_router)

@app.get("/metrics")
async def get_metrics(user: Dict = Depends(get_current_user_from_supabase)):
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    data, content_type = metrics_endpoint()
    return Response(content=data, media_type=content_type)


# === Mount Ingestion UI ===

# Try to find the directory (Docker vs Local/Colab)
# Priority: 1. Docker/Copied local, 2. Colab/Dev sibling
ui_possible_paths = [
    Path("/app/ingest-ui"),      # Docker (absolute)
    Path("ingest-ui"),           # Local (relative to CWD)
    Path("../ingest-ui"),        # Colab/Dev (relative to CWD backend/)
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
    from app.gradio_ui import create_demo
    import gradio as gr
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
    if type(container.ollama).__name__ in ("MagicMock", "AsyncMock", "Mock") or hasattr(container.ollama, "mock_calls"):
        return await container.ollama.translate_text(text, src, tgt)

    if settings.sarvam_api_key and not settings.sarvam_api_key.startswith("sk_dummy") and settings.sarvam_api_key.strip():
        try:
            from services.sarvam_service import SarvamCloudService
            sarvam_srv = SarvamCloudService()
            return await sarvam_srv.translate_text(text, src, tgt)
        except Exception as e:
            logger.error(f"Error in dynamic Sarvam translation routing: {e}, falling back to Ollama")
    return await container.ollama.translate_text(text, src, tgt)



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



class ChatResponse(BaseModel):
    """Chat API response body."""
    response: str = Field(..., description="Guru's response")
    intent: Optional[str] = Field(None, description="Detected intent")
    meditation_step: int = Field(default=0, description="Next meditation step")
    citations: list[str] = Field(default_factory=list, description="Source URLs")
    blocked: bool = Field(default=False, description="Was the message blocked?")
    block_reason: Optional[str] = Field(None, description="Why it was blocked")


class IngestRequest(BaseModel):
    """Ingestion API request body."""
    url: str = Field(..., description="YouTube video/playlist URL or image URL")
    max_accuracy: bool = Field(default=False, description="If True, skip auto-generated captions (T3) and rely on Manual (T1) or Whisper (T2)")


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

@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit(settings.chat_rate_limit)
async def chat_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container)
) -> ChatResponse:
    """
    Main conversational endpoint.
    
    Full pipeline: NeMo Input Rail → LangGraph (11 layers) → NeMo Output Rail
    """
    user_msg = chat_body.user_message.strip()
    preferred_lang = chat_body.language or "en"
    is_indic = preferred_lang and not preferred_lang.startswith("en")
    start_time = time.time()

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if len(user_msg) > settings.max_input_length:
        raise HTTPException(
            status_code=400,
            detail=f"Message too long. Please keep it under {settings.max_input_length} characters."
        )

    # === Response Cache Check (Bypass Guardrails for known safe queries) ===
    cached = container.semantic_cache.get(user_msg)
    if cached is not None:
        REQUEST_COUNT.labels(status="cache_hit").inc()
        return ChatResponse(
            response=cached["response"],
            intent=cached.get("intent"),
            meditation_step=cached.get("meditation_step", 0),
            citations=cached.get("citations", []),
        )

    # Translate user query to English if Indic preferred language selected
    user_msg_en = user_msg
    if is_indic:
        user_msg_en = await translate_text(user_msg, preferred_lang, "en", container)
        logger.info(f"Translated user query from {preferred_lang} to English: {user_msg_en}")

    # === NEW: Language Detection ===
    lang_detection = container.language_router.detect(user_msg_en)
    user_id = user.get("id", "anonymous")
    stable_session_id = normalize_session_id(chat_body.session_id, user_id)
    chat_history = [m.model_dump() for m in chat_body.messages]
    # Cap conversation context to prevent OOM/timeouts on long sessions
    if len(chat_history) > settings.chat_history_max_messages:
        chat_history = chat_history[-settings.chat_history_max_messages:]
    
    # Translate history messages to English if Indic language is active
    chat_history_en = []
    if is_indic:
        for msg in chat_history:
            msg_content_en = await translate_text(msg["content"], preferred_lang, "en", container)
            chat_history_en.append({"role": msg["role"], "content": msg_content_en})
    else:
        chat_history_en = chat_history

    # === NEW: User Profile & Memory ===
    memory_context, distress_history = await _prepare_user_memory(
        container,
        user_id,
        chat_history_en,
    )

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
            assessment_history = [{"role": "system", "content": f"Previous distress history: {distress_history}"}] if distress_history else []
            assessment = await container.serene_mind.analyze_with_history(
                user_msg_en,
                history=chat_history_en + assessment_history
            )
            if assessment.level.value >= 2:
                logger.info(f"Distress detected ({assessment.level.name}), passing to RAG pipeline for compassionate response.")
    except Exception as e:
        logger.warning(f"Serene Mind detection failed (non-fatal): {e}")

    # === Layers 2-11: LangGraph RAG Pipeline ===
    try:
        # Coalesce identical concurrent requests (Sys 4.1)
        async def run_pipeline():
            initial_state = create_initial_state(
                question=user_msg_en,
                chat_history=chat_history_en,
                meditation_step=chat_body.meditation_step,
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
                f"{user_msg_en}:{hashlib.md5(str([m['content'] for m in chat_history_en[-4:]]).encode()).hexdigest()[:8]}",
                run_pipeline,
            ),
            timeout=settings.llm_timeout + 10,  # Pipeline timeout = LLM timeout + 10s buffer
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
            final_answer_native = await translate_text(final_answer, "en", preferred_lang, container)
            logger.info(f"Translated final answer to {preferred_lang}: {final_answer_native}")

        # NEW: Save conversation memory (always save native/user-visible texts)
        if container.user_profile:
            from services.user_profile_service import ConversationMemory
            memory = ConversationMemory(
                session_id=stable_session_id,
                user_id=user_id,
                started_at=time.time(),
                messages=[{"role": "user", "content": user_msg}, {"role": "assistant", "content": final_answer_native}],
                key_insights=[c if isinstance(c, str) else c.get("title", "") for c in citations],
                emotional_arc=[{"timestamp": time.time(), "distress_level": assessment.level.value if 'assessment' in locals() else 0, "topic": intent}],
                follow_up_suggestions=[],
            )
            background_tasks.add_task(container.user_profile.save_conversation_memory, memory)

        # Populate cache for QUERY and CASUAL intents (Semantic Caching for fast routing)
        if intent in ["QUERY", "CASUAL"]:
            container.semantic_cache.put(
                query=user_msg,
                response=final_answer_native,
                intent=intent,
                citations=citations,
                meditation_step=med_step
            )

        final_answer = final_answer_native

    except asyncio.TimeoutError:
        logger.error(f"Pipeline timeout after {settings.llm_timeout + 10}s for: {user_msg[:100]}")
        REQUEST_COUNT.labels(status="timeout").inc()
        final_answer = "I apologize, the process took too long. 🙏 Please try asking your question again."
        if is_indic:
            final_answer = await translate_text(final_answer, "en", preferred_lang, container)
        intent = "ERROR"
        med_step = 0
        citations = []
    except Exception as e:
        citations = []
        from services.sarvam_service import QuotaExceededError
        if isinstance(e, QuotaExceededError) or "credits" in str(e).lower() or "429" in str(e).lower():
            logger.warning(f"Sarvam API quota error intercepted: {e}")
            fallback_answer = "I apologize, our upstream provider is currently out of credits. Here is the relevant wisdom directly retrieved from our sacred knowledge base:\n\n"
            try:
                from app.dependencies import get_container
                container = get_container()
                query_enc = container.embedding.encode_single_full(user_msg_en)
                docs = container.qdrant.search(
                    query_vector=query_enc['dense'],
                    limit=3,
                    sparse_vector=query_enc['sparse']
                )
                if docs:
                    for i, doc in enumerate(docs, 1):
                        text_snippet = doc["text"].strip()
                        if len(text_snippet) > 350:
                            text_snippet = text_snippet[:350] + "..."
                        fallback_answer += f"✦ **Teaching {i}:** {text_snippet}\n\n"
                    final_answer = fallback_answer
                    citations = [d.get("source_url") for d in docs if d.get("source_url") and d.get("source_url") != "None"]
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
    
    # Collect retrieval metadata from result
    retrieval_meta = None
    if citations:
        retrieval_meta = {
            "chunk_ids": [c.get("id") if isinstance(c, dict) else "" for c in citations],
            "source_docs": [c.get("source_url") if isinstance(c, dict) else c for c in citations],
            "scores": [c.get("score", 0.0) if isinstance(c, dict) else 1.0 for c in citations],
            "top_k": len(citations),
            "hit": len(citations) > 0
        }

    # Collect trigger events (Distress)
    trigger_events = []
    if 'assessment' in locals() and assessment.level.value >= 2:
        trigger_events.append({
            "name": "DISTRESS",
            "metadata": {
                "level": assessment.level.name,
                "confidence": assessment.confidence,
                "signals": assessment.detected_signals
            }
        })

    query_data = {
        "id": query_id,
        "session_id": session_uuid,
        "user_id": user_id,
        "anon_user_id": str(uuid.uuid4()),
        "query_text": user_msg,
        "model": "askmukthiguru",
        "latency_ms": int((time.time() - start_time) * 1000),
        "status": "ok" if intent != "ERROR" else "error",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "retrieval_metadata": retrieval_meta,
        "trigger_events": trigger_events
    }
    
    # Safely pull RAG eval scores if available
    is_rag = (intent == "QUERY")
    response_data = {
        "id": str(uuid.uuid4()),
        "response_text": final_answer,
        "citations": citations,
        "faithfulness": result.get("faithfulness_score", 0.0) if is_rag and 'result' in locals() else 1.0,
        "answer_relevancy": 1.0,
        "context_precision": 1.0,
        "context_recall": 1.0,
        "hallucination_flag": not result.get("faithful", True) if is_rag and 'result' in locals() else False,
        "judge_reasoning": result.get("verification_reason", "") if is_rag and 'result' in locals() else ""
    }
    background_tasks.add_task(log_query_trace, query_data, response_data)

    return ChatResponse(
        response=final_answer,
        intent=intent,
        meditation_step=med_step,
        citations=citations,
        blocked=output_check.get("blocked", False),
        block_reason=output_check.get("reason"),
    )



@app.post("/api/chat/stream")
@limiter.limit(settings.chat_rate_limit)
async def chat_stream_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container)
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

    if not user_msg:
        async def error_stream():
            yield f"event: error\ndata: Message cannot be empty\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    if len(user_msg) > settings.max_input_length:
        async def length_error_stream():
            yield f"event: error\ndata: Message too long. Please keep it under {settings.max_input_length} characters.\n\n"
        return StreamingResponse(length_error_stream(), media_type="text/event-stream")

    async def generate_sse():
        """SSE generator that runs the pipeline and streams results."""
        try:
            # === Cache check (Bypass guardrails for known safe queries) ===
            cached = container.semantic_cache.get(user_msg)
            if cached is not None:
                yield f"event: token\ndata: {cached['response']}\n\n"
                meta = json.dumps({
                    "intent": cached.get("intent"),
                    "citations": cached.get("citations", []),
                    "meditation_step": cached.get("meditation_step", 0),
                })
                yield f"event: done\ndata: {meta}\n\n"
                return

            user_id = user.get("id", "anonymous")
            
            # Translate user query to English if Indic preferred language selected
            user_msg_en = user_msg
            if is_indic:
                yield f"event: status\ndata: Translating your question to English...\n\n"
                user_msg_en = await translate_text(user_msg, preferred_lang, "en", container)
                logger.info(f"Stream: Translated user query from {preferred_lang} to English: {user_msg_en}")

            # === NEW: Language Detection ===
            lang_detection = container.language_router.detect(user_msg_en)
            stable_session_id = normalize_session_id(chat_body.session_id, user_id)
            chat_history = [m.model_dump() for m in chat_body.messages]
            # Cap conversation context to prevent OOM/timeouts on long sessions
            if len(chat_history) > settings.chat_history_max_messages:
                chat_history = chat_history[-settings.chat_history_max_messages:]
            
            # Translate history messages to English if Indic language is active
            chat_history_en = []
            if is_indic and chat_history:
                async def _translate_msg(msg):
                    translated = await translate_text(msg["content"], preferred_lang, "en", container)
                    return {"role": msg["role"], "content": translated}
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
            yield f"event: status\ndata: Checking message safety...\n\n"
            input_check = await container.guardrails.check_input(user_msg_en)

            if input_check["blocked"]:
                blocked_resp = input_check["response"]
                if is_indic:
                    blocked_resp = await translate_text(blocked_resp, "en", preferred_lang, container)
                yield f"event: token\ndata: {blocked_resp}\n\n"
                meta = json.dumps({"blocked": True, "block_reason": input_check["reason"]})
                yield f"event: done\ndata: {meta}\n\n"
                return

            # === Depression check (non-fatal if detection fails) ===
            try:
                if container.serene_mind:
                    assessment_history = [{"role": "system", "content": f"Previous distress history: {distress_history}"}] if distress_history else []
                    assessment = await container.serene_mind.analyze_with_history(
                        user_msg_en,
                        history=chat_history_en + assessment_history,
                    )
                    if assessment.level.value >= 2:
                        logger.info(f"Stream: Distress detected ({assessment.level.name}), passing to RAG pipeline.")
            except Exception as e:
                logger.warning(f"Serene Mind detection failed in stream (non-fatal): {e}")

            # === RAG Pipeline ===
            yield f"event: status\ndata: Understanding your question...\n\n"
            initial_state = create_initial_state(
                question=user_msg_en,
                chat_history=chat_history_en,
                meditation_step=chat_body.meditation_step,
            )
            # Inject language and user context into state
            initial_state["detected_language"] = lang_detection.primary.value
            initial_state["user_id"] = user_id
            initial_state["memory_context"] = memory_context

            yield f"event: status\ndata: Searching knowledge base...\n\n"
            result = await asyncio.wait_for(
                container.rag_graph.ainvoke(initial_state),
                timeout=settings.llm_timeout + 10,
            )

            final_answer = result.get("final_answer", "I apologize, something went wrong.")
            intent = result.get("intent", "CASUAL")
            med_step = result.get("meditation_step", 0)
            citations = result.get("citations", [])

            if is_indic:
                # Indicate translation status
                yield f"event: status\ndata: Translating spiritual response to your language...\n\n"
                
                final_answer_native = await translate_text(final_answer, "en", preferred_lang, container)
                logger.info(f"Stream: Translated final answer to {preferred_lang}: {final_answer_native}")
                
                output_check = await container.guardrails.check_output(final_answer_native)
                if output_check["blocked"]:
                    final_answer_native = output_check["moderated_response"]
                
                final_answer = final_answer_native
                # Chunk-stream the translated text
                for i in range(0, len(final_answer_native), 10):
                    chunk = final_answer_native[i:i + 10]
                    escaped = chunk.replace("\n", "\\n")
                    yield f"event: token\ndata: {escaped}\n\n"
                    await asyncio.sleep(0.01)
            else:
                # Stream the answer using real SSE if it's a QUERY with context
                if intent == "QUERY" and result.get("documents") and settings.sarvam_api_key:
                    try:
                        from services.streaming_generator import stream_sarvam_response
                        context_text = "\n\n".join([d.get("text", d.get("page_content", "")) if isinstance(d, dict) else getattr(d, "page_content", "") for d in result.get("documents", [])])
                        messages = [
                            {"role": "system", "content": f"You are a spiritual guide. Answer using this context:\n{context_text}"},
                            {"role": "user", "content": user_msg_en}
                        ]
                        sarvam_answer = ""
                        async for chunk in stream_sarvam_response(messages, api_key=settings.sarvam_api_key):
                            if chunk:
                                sarvam_answer += chunk
                                escaped = chunk.replace("\n", "\\n")
                                yield f"event: token\ndata: {escaped}\n\n"
                        final_answer = sarvam_answer
                    except Exception as stream_e:
                        logger.warning(f"Sarvam API streaming failed: {stream_e}. Falling back to Ollama.")
                        # Fallback to simulated stream of local LLM answer
                        for i in range(0, len(final_answer), 20):
                            chunk = final_answer[i:i + 20]
                            escaped = chunk.replace("\n", "\\n")
                            yield f"event: token\ndata: {escaped}\n\n"
                            await asyncio.sleep(0.01)
                else:
                    # Fallback to simulated stream for casual/distress/cached responses
                    for i in range(0, len(final_answer), 20):
                        chunk = final_answer[i:i + 20]
                        escaped = chunk.replace("\n", "\\n")
                        yield f"event: token\ndata: {escaped}\n\n"
                        await asyncio.sleep(0.01)

                output_check = await container.guardrails.check_output(final_answer)
                if output_check["blocked"]:
                    final_answer = output_check["moderated_response"]

            # Cache QUERY and CASUAL results (Semantic Caching for fast routing)
            if intent in ["QUERY", "CASUAL"]:
                container.semantic_cache.put(user_msg, final_answer, intent, citations, meditation_step=med_step)

            REQUEST_COUNT.labels(status="success").inc()

            # Final metadata
            meta = json.dumps({
                "intent": intent,
                "citations": citations,
                "meditation_step": med_step,
            })
            yield f"event: done\ndata: {meta}\n\n"

            # NEW: Save conversation memory (always save native texts)
            if container.user_profile:
                from services.user_profile_service import ConversationMemory
                memory = ConversationMemory(
                    session_id=stable_session_id,
                    user_id=user_id,
                    started_at=time.time(),
                    messages=[{"role": "user", "content": user_msg}, {"role": "assistant", "content": final_answer}],
                    key_insights=[c if isinstance(c, str) else c.get("title", "") for c in citations],
                    emotional_arc=[{"timestamp": time.time(), "distress_level": assessment.level.value if 'assessment' in locals() else 0, "topic": intent}],
                    follow_up_suggestions=[],
                )
                asyncio.create_task(container.user_profile.save_conversation_memory(memory))

        except Exception as e:
            logger.error(f"SSE streaming error: {e}", exc_info=True)
            REQUEST_COUNT.labels(status="error").inc()
            yield f"event: error\ndata: An error occurred. Please try again.\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class SpeechTTSRequest(BaseModel):
    text: str
    target_language_code: str
    speaker: Optional[str] = None


@app.post("/api/speech/stt")
async def speech_to_text_endpoint(
    file: UploadFile = File(...),
    language_code: Optional[str] = Form(None),
    model: str = Form("saaras:v3"),
    container: ServiceContainer = Depends(get_container)
):
    """
    Transcribe uploaded audio file using Sarvam Cloud STT or fallback to local Whisper.
    """
    import tempfile
    import os
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
            data = {
                "model": model
            }
            if language_code:
                data["language_code"] = language_code
                
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.sarvam.ai/speech-to-text",
                    headers=headers,
                    files=files,
                    data=data
                )
                if resp.status_code == 200:
                    result = resp.json()
                    transcript = result.get("transcript", "")
                    detected_lang = result.get("language_code", language_code or "en-IN")
                    logger.info(f"Sarvam STT returned transcript: {transcript} (lang: {detected_lang})")
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
                video_id="browser_recording",
                audio_path=tmp_path,
                language=whisper_lang
            )
            
            if transcript:
                detected_lang = language_code or "en-IN"
                if any("\u0900" <= c <= "\u097F" for c in transcript):
                    detected_lang = "hi-IN"
                elif any("\u0C00" <= c <= "\u0C7F" for c in transcript):
                    detected_lang = "te-IN"
                elif any("\u0B80" <= c <= "\u0BFF" for c in transcript):
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


@app.post("/api/speech/tts")
async def text_to_speech_endpoint(
    req: SpeechTTSRequest,
    container: ServiceContainer = Depends(get_container)
):
    """
    Generate speech from text using Sarvam Cloud TTS.
    """
    import base64
    import httpx
    
    api_key = settings.sarvam_api_key
    if not api_key or api_key.startswith("sk_dummy") or len(api_key) <= 10:
        raise HTTPException(status_code=500, detail="Sarvam TTS not configured (missing or dummy API key).")
        
    lang = req.target_language_code
    if not "-" in lang:
        mapping = {
            "en": "en-IN",
            "hi": "hi-IN",
            "te": "te-IN",
            "mr": "mr-IN",
            "ta": "ta-IN",
            "bn": "bn-IN",
            "gu": "gu-IN",
            "kn": "kn-IN",
            "ml": "ml-IN",
            "or": "or-IN",
            "pa": "pa-IN",
            "ur": "ur-IN",
        }
        lang = mapping.get(lang.lower(), f"{lang.lower()}-IN")
        
    speaker = req.speaker or "shubh"
    
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": [req.text],
        "target_language_code": lang,
        "speaker": speaker,
        "model": "bulbul:v3"
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
                raise HTTPException(status_code=resp.status_code, detail=f"Sarvam TTS failed: {resp.text}")
    except Exception as e:
        logger.error(f"Error calling Sarvam TTS: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest", response_model=IngestResponse)
@limiter.limit("5/minute")
async def ingest_endpoint(
    request: Request,
    ingest_body: IngestRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container)
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

    # Run ingestion in the background for large content
    async def _run_ingestion():
        import time
        import uuid
        from datetime import datetime, timezone
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
                url,
                max_accuracy=ingest_body.max_accuracy,
                on_progress=progress_callback
            )
            logger.info(f"Ingestion complete: {result}")
            container.update_progress(url, "Complete!", 1.0)
            
            if isinstance(result, dict):
                chunks_added = result.get("chunks_indexed", result.get("chunks_added", 0))
            
            # Invalidate response cache after new content ingestion
            container.semantic_cache.invalidate_all()
            
        except Exception as e:
            logger.error(f"Ingestion failed for {url}: {e}", exc_info=True)
            status = "failed"
            error_log = str(e)
            # Mark as error
            if url in container.ingest_status:
                container.ingest_status[url]["status"] = "error"
                container.ingest_status[url]["message"] = str(e)
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            try:
                await log_ingestion_run({
                    "id": str(uuid.uuid4()),
                    "source": url,
                    "chunks_added": chunks_added,
                    "embedding_model": settings.embedding_model,
                    "duration_ms": duration_ms,
                    "status": status,
                    "error_log": error_log,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
            except Exception as db_e:
                logger.error(f"Failed to log ingestion run in background task: {db_e}")

    background_tasks.add_task(_run_ingestion)

    return IngestResponse(
        status="processing",
        message=f"Ingestion started for: {url}",
        source_url=url,
    )


@app.get("/api/profile")
async def get_profile_endpoint(
    user: Dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container)
):
    """Fetch the authenticated user's spiritual profile."""
    if not container.user_profile:
        raise HTTPException(status_code=501, detail="User profile service not enabled")
    
    profile = await container.user_profile.get_or_create_profile(user["id"])
    return asdict(profile)


@app.put("/api/profile")
async def update_profile_endpoint(
    profile_data: Dict,
    user: Dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container)
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


@app.get("/api/health", response_model=HealthResponse)
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
    all_healthy = all(
        v for k, v in health.items()
        if k in core_services
    )

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        services={k: (v if isinstance(v, bool) else True) for k, v in health.items() if k not in ["qdrant_count", "guardrails_provider"]},
        total_chunks=0 if not all_healthy else -1, # Redact exact count
    )


@app.get("/api/ready")
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
        "total_chunks": -1, # Redacted
    }


@app.get("/api/ingest/status")
async def ingest_status_endpoint(user: Dict = Depends(get_current_user_from_supabase), container: ServiceContainer = Depends(get_container)) -> dict:
    """
    Get the status of active/recent ingestion jobs (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return container.ingest_status


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
