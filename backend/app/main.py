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
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field

# Fix import paths — run from backend/ directory
sys.path.insert(0, ".")

from app.config import settings
from app.dependencies import get_container, startup, shutdown, ServiceContainer
from app.telemetry_db import init_telemetry_db, log_query_trace
from rag.graph import create_initial_state
import time
import uuid
import contextvars
from app.metrics import REQUEST_LATENCY, REQUEST_COUNT, metrics_endpoint

# Correlation ID context variable — accessible from anywhere in the async call chain
correlation_id_var = contextvars.ContextVar('correlation_id', default='-')
from services.cache_service import RedisCacheAdapter, InMemoryCacheAdapter, init_llm_cache

# Rate limiting and Auth
from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.api.endpoints.auth import router as auth_router
from services.auth_service import current_active_user
from models.user import User as AuthUser
from fastapi import Depends
from app.core.database import init_db

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)

# Global instances
class RequestCoalescer:
    """
    System Design Pattern 4.1: Coalesce Caching.
    Merges identical concurrent requests to avoid redundant RAG runs.
    """
    def __init__(self):
        self._locks = {}
        self._results = {}

    async def get_or_run(self, key: str, coro_func):
        if key in self._results:
            return self._results[key]
        
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        
        async with self._locks[key]:
            if key in self._results:
                return self._results[key]
            
            result = await coro_func()
            self._results[key] = result
            # Clean up after a short delay (or keep in semantic cache)
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
            
    import asyncio
    asyncio.create_task(asyncio.to_thread(prewarm_models))


    # 3. Async services initialization (LightRAG)
    try:
        await container.lightrag.initialize()
    except Exception as e:
        logger.warning(f"LightRAG initialization failed (GraphRAG unavailable): {e}")

    # 4. (Deprecated) Depression detector is now merged into Serene Mind Engine

    # 5. Observability tracing (Arize Phoenix / OpenInference) (BE-8)
    try:
        import phoenix as px
        from openinference.instrumentation.langchain import LangChainInstrumentor
        px.launch_app()  # Starts Phoenix server locally
        LangChainInstrumentor().instrument()
        logger.info("Arize Phoenix and OpenInference tracing successfully initialized.")
    except ImportError:
        logger.info("Arize Phoenix not installed — skipping observability tracing")
    except Exception as e:
        logger.warning(f"Failed to initialize Arize Phoenix tracing: {e}")

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
from starlette.middleware.base import BaseHTTPMiddleware

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID", str(uuid.uuid4())[:8])
        correlation_id_var.set(cid)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response

if settings.enable_correlation_ids:
    app.add_middleware(CorrelationIDMiddleware)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global error boundary catching all unhandled exceptions."""
    logger.error(f"Unhandled server error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later.", "error": str(exc)},
    )


from routers.admin import admin_router
from routers.feedback import router as feedback_router
app.include_router(auth_router, prefix="/api/auth")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(feedback_router, prefix="/api")

# Mount trace dashboard routes
from app.trace_dashboard import router as trace_router
app.include_router(trace_router)

@app.get("/metrics")
async def get_metrics():
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
    app.mount("/ingest", StaticFiles(directory=str(ui_path), html=True), name="ingest")
    logger.info(f"✅ Ingestion UI mounted at /ingest (from {ui_path})")
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
    app.mount("/chat", StaticFiles(directory=str(chat_ui_path), html=True), name="chat")
    logger.info(f"✅ Premium Chat UI mounted at /chat (from {chat_ui_path})")
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


# === Request/Response DTOs ===

class MessagePayload(BaseModel):
    """Single message in the conversation history."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class ChatRequest(BaseModel):
    """Chat API request body — matches frontend's sendMessage format."""
    messages: list[MessagePayload] = Field(..., description="Conversation history")
    user_message: str = Field(..., description="Current user message")
    meditation_step: int = Field(default=0, description="Current meditation step (0 = none)")


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

@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    container: ServiceContainer = Depends(get_container)
) -> ChatResponse:
    """
    Main conversational endpoint.
    
    Full pipeline: NeMo Input Rail → LangGraph (11 layers) → NeMo Output Rail
    """
    user_msg = chat_body.user_message.strip()
    start_time = time.time()

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # === Layer 1: NeMo Input Rail ===
    with REQUEST_LATENCY.labels(stage="guardrails").time():
        input_check = await container.guardrails.check_input(user_msg)
        
    if input_check["blocked"]:
        logger.info(f"Input blocked: {input_check['reason']}")
        REQUEST_COUNT.labels(status="blocked").inc()
        return ChatResponse(
            response=input_check["response"],
            blocked=True,
            block_reason=input_check["reason"],
        )

    # === Depression Detection (Council Recommendation) ===
    # Check directly here before RAG to fail-fast into meditation
    # Wrapped in try/except so detection failures don't crash the request
    try:
        if container.serene_mind:
            assessment = await container.serene_mind.aassess_distress(user_msg)
            if assessment.level.value >= 2:  # MODERATE or higher
                response = container.serene_mind.get_response(assessment)
                return ChatResponse(
                    response=response,
                    intent="DISTRESS",
                    meditation_step=1,
                )
    except Exception as e:
        # Don't crash the request if depression detection fails
        logger.warning(f"Serene Mind detection failed in stream (non-fatal): {e}")
        logger.warning(f"Depression detection failed (non-fatal): {e}")

    # === Response Cache Check ===
    cached = container.semantic_cache.get(user_msg)
    if cached is not None:
        REQUEST_COUNT.labels(status="cache_hit").inc()
        return ChatResponse(
            response=cached["response"],
            intent=cached.get("intent"),
            meditation_step=cached.get("meditation_step", 0),
            citations=cached.get("citations", []),
        )

    # === Layers 2-11: LangGraph RAG Pipeline ===
    try:
        # Coalesce identical concurrent requests (Sys 4.1)
        async def run_pipeline():
            initial_state = create_initial_state(
                question=user_msg,
                chat_history=[m.model_dump() for m in chat_body.messages],
                meditation_step=chat_body.meditation_step,
            )
            return await container.rag_graph.ainvoke(initial_state)

        result = await coalescer.get_or_run(user_msg, run_pipeline)

        final_answer = result.get("final_answer", "I apologize, something went wrong.")
        intent = result.get("intent", "CASUAL")
        med_step = result.get("meditation_step", 0)
        citations = result.get("citations", [])
        REQUEST_COUNT.labels(status="success").inc()

        # Populate cache for QUERY intents (not casual/distress/meditation)
        if intent == "QUERY":
            container.semantic_cache.put(
                query=user_msg,
                response=final_answer,
                intent=intent,
                citations=citations,
                meditation_step=med_step
            )

    except Exception as e:
        citations = []
        from services.sarvam_service import QuotaExceededError
        if isinstance(e, QuotaExceededError) or "credits" in str(e).lower() or "429" in str(e).lower():
            logger.warning(f"Sarvam API quota error intercepted: {e}")
            fallback_answer = "I apologize, our upstream provider is currently out of credits. Here is the relevant wisdom directly retrieved from our sacred knowledge base:\n\n"
            try:
                from app.dependencies import get_container
                container = get_container()
                query_enc = container.embedding.encode_single_full(user_msg)
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
            intent = "QUERY"
            med_step = 0
        else:
            logger.error(f"RAG pipeline error: {e}", exc_info=True)
            REQUEST_COUNT.labels(status="error").inc()
            final_answer = (
                "I apologize, I'm experiencing a moment of stillness. 🙏 "
                "Please try asking your question again. DEBUG ERROR: " + str(e)
            )
            intent = "ERROR"
            med_step = 0
            citations = []

    # === Layer 12: NeMo Output Rail ===
    output_check = await container.guardrails.check_output(final_answer)
    if output_check["blocked"]:
        logger.info(f"Output moderated: {output_check['reason']}")
        final_answer = output_check["moderated_response"]

    # --- Telemetry Logging ---
    import uuid
    try:
        session_uuid = str(uuid.UUID(chat_body.session_id)) if chat_body.session_id else str(uuid.uuid4())
    except (ValueError, TypeError, AttributeError):
        session_uuid = str(uuid.uuid4())

    query_id = str(uuid.uuid4())
    query_data = {
        "id": query_id,
        "session_id": session_uuid,
        "anon_user_id": str(uuid.uuid4()),
        "query_text": user_msg,
        "model": "askmukthiguru",
        "latency_ms": int((time.time() - start_time) * 1000),
        "status": "ok" if intent != "ERROR" else "error",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
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
@limiter.limit("20/minute")
async def chat_stream_endpoint(
    request: Request,
    chat_body: ChatRequest,
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

    if not user_msg:
        async def error_stream():
            yield f"event: error\ndata: Message cannot be empty\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def generate_sse():
        """SSE generator that runs the pipeline and streams results."""
        try:
            # === Layer 1: Input rail ===
            yield f"event: status\ndata: Checking message safety...\n\n"
            input_check = await container.guardrails.check_input(user_msg)

            if input_check["blocked"]:
                yield f"event: token\ndata: {input_check['response']}\n\n"
                meta = json.dumps({"blocked": True, "block_reason": input_check["reason"]})
                yield f"event: done\ndata: {meta}\n\n"
                return

            # === Depression check (non-fatal if detection fails) ===
            try:
                if container.serene_mind:
                    assessment = await container.serene_mind.aassess_distress(user_msg)
                    if assessment.level.value >= 2:
                        resp = container.serene_mind.get_response(assessment)
                        yield f"event: token\ndata: {resp}\n\n"
                        meta = json.dumps({"intent": "DISTRESS", "meditation_step": 1})
                        yield f"event: done\ndata: {meta}\n\n"
                        return
            except Exception as e:
                logger.warning(f"Serene Mind detection failed in stream (non-fatal): {e}")

            # === Cache check ===
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

            # === RAG Pipeline ===
            yield f"event: status\ndata: Understanding your question...\n\n"
            initial_state = create_initial_state(
                question=user_msg,
                chat_history=[m.model_dump() for m in chat_body.messages],
                meditation_step=chat_body.meditation_step,
            )

            yield f"event: status\ndata: Searching knowledge base...\n\n"
            result = await container.rag_graph.ainvoke(initial_state)

            final_answer = result.get("final_answer", "I apologize, something went wrong.")
            intent = result.get("intent", "CASUAL")
            med_step = result.get("meditation_step", 0)
            citations = result.get("citations", [])

            # Stream the answer token by token (simulate chunked delivery)
            yield f"event: status\ndata: Composing response...\n\n"

            # Split answer into small chunks for streaming effect
            chunk_size = 20  # chars per chunk
            for i in range(0, len(final_answer), chunk_size):
                chunk = final_answer[i:i + chunk_size]
                # Escape newlines for SSE format
                escaped = chunk.replace("\n", "\\n")
                yield f"event: token\ndata: {escaped}\n\n"

            # Cache QUERY results
            if intent == "QUERY":
                container.semantic_cache.put(user_msg, final_answer, intent, citations, meditation_step=med_step)

            REQUEST_COUNT.labels(status="success").inc()

            # Final metadata
            meta = json.dumps({
                "intent": intent,
                "citations": citations,
                "meditation_step": med_step,
            })
            yield f"event: done\ndata: {meta}\n\n"

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


@app.post("/api/ingest", response_model=IngestResponse)
@limiter.limit("5/minute")
async def ingest_endpoint(
    request: Request,
    ingest_body: IngestRequest,
    background_tasks: BackgroundTasks,
    container: ServiceContainer = Depends(get_container)
) -> IngestResponse:
    """
    Content ingestion endpoint.
    
    Accepts YouTube video/playlist URLs and image URLs.
    Runs ingestion in the background so the API responds immediately.
    """
    url = ingest_body.url.strip()

    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    # Run ingestion in the background for large content
    async def _run_ingestion():
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
            # Invalidate response cache after new content ingestion
            response_cache.invalidate_all()
            
        except Exception as e:
            logger.error(f"Ingestion failed for {url}: {e}", exc_info=True)
            # Mark as error
            if url in container.ingest_status:
                container.ingest_status[url]["status"] = "error"
                container.ingest_status[url]["message"] = str(e)

    background_tasks.add_task(_run_ingestion)

    return IngestResponse(
        status="processing",
        message=f"Ingestion started for: {url}",
        source_url=url,
    )


@app.get("/api/health", response_model=HealthResponse)
async def health_endpoint(container: ServiceContainer = Depends(get_container)) -> HealthResponse:
    """
    Health check endpoint.
    
    Returns status of all backend services and total indexed chunks.
    """
    health = await container.health_status()

    # Only core services determine healthy/degraded status
    # Optional services (OCR, guardrails) don't affect overall health
    core_services = {"qdrant", "ollama", "embedding"}
    all_healthy = all(
        v for k, v in health.items()
        if k in core_services
    )

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        services={k: v for k, v in health.items() if k != "qdrant_count"},
        total_chunks=health.get("qdrant_count", 0),
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
        "total_chunks": health.get("qdrant_count", 0),
    }


@app.get("/api/ingest/status")
async def ingest_status_endpoint(container: ServiceContainer = Depends(get_container)) -> dict:
    """
    Get the status of active/recent ingestion jobs.
    Returns: {url: {status, message, progress, updated_at}}
    """
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
