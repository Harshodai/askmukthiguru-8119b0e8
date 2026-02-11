"""
Mukthi Guru — FastAPI Dependency Injection

Design Patterns:
  - Dependency Injection: All services are singletons, injected via FastAPI Depends()
  - Service Locator: Central registry of all initialized services
  - Thread-safe Initialization: Uses threading.Lock for safe singleton creation

This module is the "composition root" — the only place where concrete
service instances are created. All other modules depend on abstractions.
"""

import logging
import asyncio
import threading
from typing import Optional

from services.qdrant_service import QdrantService
from services.embedding_service import EmbeddingService
from services.ollama_service import OllamaService
from services.ocr_service import OCRService
from guardrails.rails import GuardrailsService
from ingest.pipeline import IngestionPipeline
from rag.graph import build_rag_graph

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Composition Root: Creates and holds all singleton service instances.
    
    Design Pattern: Service Locator + Singleton Container.
    
    All services are created once during startup and shared across
    all request handlers. This avoids re-loading models on every request.
    """

    def __init__(self) -> None:
        """Initialize all services in dependency order."""
        logger.info("Initializing service container...")
        
        # State: Active ingestion progress
        # Format: {url: {status, message, progress, updated_at}}
        self.ingest_status = {}

        # Layer 1: Core services (no dependencies)
        self.qdrant = QdrantService()
        self.qdrant.init_collection()

        # Layer 2: Model services (depend on config only)
        self.embedding = EmbeddingService()
        self.ollama = OllamaService()
        self.ocr = OCRService()

        # Layer 3: Guardrails (depends on config)
        self.guardrails = GuardrailsService()

        # Layer 4: Ingestion pipeline (depends on all services)
        self.ingestion = IngestionPipeline(
            qdrant_service=self.qdrant,
            embedding_service=self.embedding,
            ollama_service=self.ollama,
            ocr_service=self.ocr,
        )

        # Layer 5: RAG graph (depends on core services)
        self.rag_graph = build_rag_graph(
            ollama_service=self.ollama,
            embedding_service=self.embedding,
            qdrant_service=self.qdrant,
        )

        logger.info("All services initialized")

    async def health_status(self) -> dict:
        """Check health of all services (non-blocking)."""
        loop = asyncio.get_running_loop()
        
        # Run blocking checks in thread pool
        try:
            qdrant_ok = await loop.run_in_executor(None, self.qdrant.health_check)
            qdrant_count = await loop.run_in_executor(None, self.qdrant.count)
            ocr_ok = await loop.run_in_executor(None, self.ocr.health_check)
        except Exception:
            qdrant_ok = False
            qdrant_count = 0
            ocr_ok = False
            
        return {
            "qdrant": qdrant_ok,
            "ollama": await self.ollama.health_check(),  # Already async
            "ocr": ocr_ok,
            "guardrails": self.guardrails.is_available,
            "embedding": True,
            "qdrant_count": qdrant_count,
        }

    def update_progress(self, url: str, message: str, percent: float) -> None:
        """Update progress for a specific ingestion URL."""
        import time
        self.ingest_status[url] = {
            "url": url,
            "message": message,
            "progress": percent,
            "updated_at": time.time(),
            "status": "processing" if percent < 1.0 else "success"
        }

    def close(self) -> None:
        """
        Explicitly release resources held by services.
        
        Calls cleanup methods on services that implement them.
        Errors are logged but do not prevent other services from closing.
        
        Iteration order is LIFO (reverse of initialization) so that
        dependent services are released before their dependencies.
        """
        # LIFO order: rag_graph → ingestion → guardrails → ocr → ollama → embedding → qdrant
        for name in ("rag_graph", "ingestion", "guardrails", "ocr", "ollama", "embedding", "qdrant"):
            svc = getattr(self, name, None)
            if svc is None:
                continue
            for method_name in ("close", "shutdown", "disconnect"):
                method = getattr(svc, method_name, None)
                if callable(method):
                    try:
                        method()
                        logger.debug(f"Closed {name} via {method_name}()")
                    except Exception as exc:
                        logger.warning(f"Error closing {name}.{method_name}(): {exc}")
                    break  # Only call the first available cleanup method
        logger.info("All services closed")


# Module-level singleton with thread-safe initialization
_container: Optional[ServiceContainer] = None
_container_lock = threading.Lock()


def get_container() -> ServiceContainer:
    """
    Get or create the service container singleton.
    
    Thread-safe: uses a lock to ensure only one ServiceContainer is created
    even if multiple threads call this concurrently.
    """
    global _container
    if _container is not None:
        return _container
    with _container_lock:
        # Double-checked locking: re-check inside the lock
        if _container is None:
            _container = ServiceContainer()
    return _container


def startup() -> None:
    """Initialize the service container on application startup."""
    get_container()
    logger.info("Service container ready")


def shutdown() -> None:
    """Cleanup on application shutdown — releases service resources."""
    global _container
    with _container_lock:
        if _container is not None:
            _container.close()
            _container = None
    logger.info("Service container shutdown")
