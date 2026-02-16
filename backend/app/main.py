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

# Global instance
depression_detector = DepressionDetector()

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


# === Lifespan (startup/shutdown) ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: init services on start, cleanup on stop."""
    logger.info("🚀 Mukthi Guru starting up...")
    startup()
    # Load heavy models
    depression_detector.load()
    logger.info("🙏 Mukthi Guru is ready")
    yield
    logger.info("Shutting down...")
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
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Main conversational endpoint.
    
    Full pipeline: NeMo Input Rail → LangGraph (11 layers) → NeMo Output Rail
    
    This is the thin controller — all intelligence lives in the graph.
    """
    container = get_container()
    user_msg = request.user_message.strip()

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # === Layer 1: NeMo Input Rail ===
    with REQUEST_LATENCY.labels(stage="guardrails").time():
        input_check = await container.guardrails.check_input(user_msg)
        
    if input_check["blocked"]:
        logger.info(f"Input blocked: {input_check['reason']}")
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

    # === Layers 2-11: LangGraph RAG Pipeline ===
    try:
        with REQUEST_LATENCY.labels(stage="rag_pipeline").time():
            initial_state = create_initial_state(
                question=user_msg,
                chat_history=[m.model_dump() for m in request.messages],
                meditation_step=request.meditation_step,
            )
            REQUEST_COUNT.labels(status="success").inc()

            # Invoke the compiled LangGraph
            result = await container.rag_graph.ainvoke(initial_state)

        final_answer = result.get("final_answer", "I apologize, something went wrong.")
        intent = result.get("intent", "CASUAL")
        med_step = result.get("meditation_step", 0)
        citations = result.get("citations", [])

    except Exception as e:
        logger.error(f"RAG pipeline error: {e}", exc_info=True)
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


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest_endpoint(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
) -> IngestResponse:
    """
    Content ingestion endpoint.
    
    Accepts YouTube video/playlist URLs and image URLs.
    Runs ingestion in the background so the API responds immediately.
    """
    container = get_container()
    url = request.url.strip()

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
                max_accuracy=request.max_accuracy,
                on_progress=progress_callback
            )
            logger.info(f"Ingestion complete: {result}")
            container.update_progress(url, "Complete!", 1.0)
            
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
