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

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field

# Fix import paths — run from backend/ directory
sys.path.insert(0, ".")

from app.config import settings
from app.dependencies import get_container, startup, shutdown
from rag.graph import create_initial_state
from app.metrics import REQUEST_LATENCY, REQUEST_COUNT, metrics_endpoint
from services.depression_detector import DepressionDetector
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
depression_detector = DepressionDetector()
try:
    response_cache = RedisCacheAdapter(redis_url=settings.redis_url)
except Exception as e:
    logger.warning(f"Redis initialization failed ({e}). Falling back to InMemoryCacheAdapter.")
    response_cache = InMemoryCacheAdapter()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


# === Lifespan (startup/shutdown) ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=== Starting Mukthi Guru Backend ===")
    
    # 1. Initialize DB and Create tables if needed
    await init_db()
    
    # 2. Dependency injection container setup
    container = get_container()
    await container.initialize()
    
    # 3. Observability tracing (Arize Phoenix / OpenInference) (BE-8)
    try:
        import phoenix as px
        from openinference.instrumentation.langchain import LangChainInstrumentor
        px.launch_app()  # Starts Phoenix server locally
        LangChainInstrumentor().instrument()
        logger.info("Arize Phoenix and OpenInference tracing successfully initialized.")
    except Exception as e:
        logger.warning(f"Failed to initialize Arize Phoenix tracing: {e}")

    # 4. Schedule recurring jobs (BE-5)
    try:
        from infrastructure.scheduler import start_scheduler, shutdown_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Failed to initialize APScheduler: {e}")
        shutdown_scheduler = lambda: None

    # Initialize GPTCache to intercept identical LLM calls
    init_llm_cache()
    
    
    startup()
    container = get_container()
    await container.lightrag.initialize()
    # Load heavy models
    depression_detector.load()
    yield
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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router, prefix="/api/auth")

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
async def chat_endpoint(request: Request, chat_body: ChatRequest, user: AuthUser = Depends(current_active_user)) -> ChatResponse:
    """
    Main conversational endpoint.
    
    Full pipeline: NeMo Input Rail → LangGraph (11 layers) → NeMo Output Rail
    """
    container = get_container()
    user_msg = chat_body.user_message.strip()

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
    if await depression_detector.detect(user_msg):
        from rag.meditation import get_distress_response
        return ChatResponse(
            response=get_distress_response(),
            intent="DISTRESS",
            meditation_step=1,
        )

    # === Response Cache Check ===
    cached = response_cache.get(user_msg)
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
        with REQUEST_LATENCY.labels(stage="rag_pipeline").time():
            initial_state = create_initial_state(
                question=user_msg,
                chat_history=[m.model_dump() for m in chat_body.messages],
                meditation_step=chat_body.meditation_step,
            )

            # Invoke the compiled LangGraph
            result = await container.rag_graph.ainvoke(initial_state)

        final_answer = result.get("final_answer", "I apologize, something went wrong.")
        intent = result.get("intent", "CASUAL")
        med_step = result.get("meditation_step", 0)
        citations = result.get("citations", [])
        REQUEST_COUNT.labels(status="success").inc()

        # Populate cache for QUERY intents (not casual/distress/meditation)
        if intent == "QUERY":
            response_cache.put(user_msg, final_answer, intent, citations, med_step)

    except Exception as e:
        logger.error(f"RAG pipeline error: {e}", exc_info=True)
        REQUEST_COUNT.labels(status="error").inc()
        final_answer = (
            "I apologize, I'm experiencing a moment of stillness. 🙏 "
            "Please try asking your question again."
        )
        intent = "ERROR"
        med_step = 0
        citations = []

    # === Layer 12: NeMo Output Rail ===
    output_check = await container.guardrails.check_output(final_answer)
    if output_check["blocked"]:
        logger.info(f"Output moderated: {output_check['reason']}")
        final_answer = output_check["moderated_response"]

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
async def chat_stream_endpoint(request: Request, chat_body: ChatRequest, user: AuthUser = Depends(current_active_user)):
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

    container = get_container()
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

            # === Depression check ===
            if await depression_detector.detect(user_msg):
                from rag.meditation import get_distress_response
                resp = get_distress_response()
                yield f"event: token\ndata: {resp}\n\n"
                meta = json.dumps({"intent": "DISTRESS", "meditation_step": 1})
                yield f"event: done\ndata: {meta}\n\n"
                return

            # === Cache check ===
            cached = response_cache.get(user_msg)
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
                chat_history=[m.model_dump() for m in request.messages],
                meditation_step=request.meditation_step,
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
                response_cache.put(user_msg, final_answer, intent, citations, med_step)

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
    user: AuthUser = Depends(current_active_user)
) -> IngestResponse:
    """
    Content ingestion endpoint.
    
    Accepts YouTube video/playlist URLs and image URLs.
    Runs ingestion in the background so the API responds immediately.
    """
    container = get_container()
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
async def health_endpoint() -> HealthResponse:
    """
    Health check endpoint.
    
    Returns status of all backend services and total indexed chunks.
    """
    container = get_container()
    health = await container.health_status()

    all_healthy = all(
        v for k, v in health.items() if k != "qdrant_count"
    )

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        services={k: v for k, v in health.items() if k != "qdrant_count"},
        total_chunks=health.get("qdrant_count", 0),
    )


@app.get("/api/ingest/status")
async def ingest_status_endpoint() -> dict:
    """
    Get the status of active/recent ingestion jobs.
    Returns: {url: {status, message, progress, updated_at}}
    """
    container = get_container()
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
