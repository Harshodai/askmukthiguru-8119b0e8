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

from app.config import settings
from services.qdrant_service import QdrantService
from services.embedding_service import EmbeddingService
from services.ocr_service import OCRService
from guardrails.rails import GuardrailsService
from ingest.pipeline import IngestionPipeline
from rag.graph import build_rag_graph
from services.lightrag_service import lightrag_service, LightRAGService
from services.cache_service import init_llm_cache
from services.serene_mind_engine import SereneMindEngine
from services.semantic_cache import SemanticCacheService

logger = logging.getLogger(__name__)


def _create_llm_service():
    """
    Factory: Create the appropriate LLM service based on LLM_PROVIDER config.
    
    Returns either SarvamCloudService or OllamaService — both share the same interface.
    """
    if settings.is_sarvam_cloud:
        from services.sarvam_service import SarvamCloudService
        logger.info("Using Sarvam Cloud API as LLM provider")
        return SarvamCloudService()
    else:
        from services.ollama_service import OllamaService
        logger.info("Using Ollama (local) as LLM provider")
        return OllamaService()


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

        # Initialize LLM caching (GPTCache)
        init_llm_cache()

        # Layer 1: Core services (no dependencies)
        self.qdrant = QdrantService()
        self.qdrant.init_collection()
        self.lightrag = lightrag_service

        # Layer 2: Model services (depend on config only)
        self.embedding = EmbeddingService()
        self.ollama = _create_llm_service()  # SarvamCloudService OR OllamaService
        self.ocr = OCRService()

        # Layer 3: Emotional Intelligence (depends on embedding, config-gated)
        if settings.serene_mind_enabled:
            self.serene_mind = SereneMindEngine(embedding_service=self.embedding)
        else:
            self.serene_mind = None
            logger.info("Serene Mind Engine disabled via config (SERENE_MIND_ENABLED=false)")

        # Layer 4: Guardrails (depends on config)
        self.guardrails = GuardrailsService()

        # Layer 4b: Semantic Cache (depends on embedding + redis)
        self.semantic_cache = SemanticCacheService(
            redis_url=settings.redis_url,
            embedding_service=self.embedding,
        )

        # Layer 5: Ingestion pipeline (depends on all services)
        self.ingestion = IngestionPipeline(
            qdrant_service=self.qdrant,
            embedding_service=self.embedding,
            ollama_service=self.ollama,
            ocr_service=self.ocr,
        )

        # Layer 6: RAG graph (depends on core services + serene mind)
        self.rag_graph = build_rag_graph(
            ollama_service=self.ollama,
            embedding_service=self.embedding,
            qdrant_service=self.qdrant,
            lightrag_service=self.lightrag,
            serene_mind_engine=self.serene_mind,
        )

        logger.info(
            f"All services initialized "
            f"(Serene Mind: {'enabled' if self.serene_mind else 'disabled'}, "
            f"Guardrails: {self.guardrails.provider_name}, "
            f"Semantic Cache: {'enabled' if self.semantic_cache.is_available else 'disabled'})"
        )

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
            "guardrails_provider": self.guardrails.provider_name,
            "semantic_cache": self.semantic_cache.is_available,
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
