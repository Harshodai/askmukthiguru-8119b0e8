from __future__ import annotations

"""
Mukthi Guru — FastAPI Dependency Injection

Design Patterns:
  - Dependency Injection: All services are singletons, injected via FastAPI Depends()
  - Service Locator: Central registry of all initialized services
  - Thread-safe Initialization: Uses threading.Lock for safe singleton creation

This module is the "composition root" — the only place where concrete
service instances are created. All other modules depend on abstractions.
"""

import asyncio
import logging
import threading

from app.config import settings
from guardrails import GuardrailsService
from ingest.pipeline import IngestionPipeline
from rag.graph import build_deep_graph, build_fast_graph, build_rag_graph
from services.cache_service import SemanticCacheAdapter, init_llm_cache
from services.circuit_breaker import initialize_circuit_breakers
from services.compliance_logger import get_compliance_logger  # Unit 24
from services.embedding_service import EmbeddingService
from services.ingestion_tracker import IngestionTracker
from services.ingestion_tracker import build_tracker as build_ingestion_tracker
from services.krutrim_service import KrutrimService
from services.language_router import LanguageRouter
from services.lightrag_service import lightrag_service
from services.model_registry import ModelRegistry  # Unit 25
from services.ocr_service import OCRService
from services.qdrant_service import QdrantService
from services.serene_mind_engine import SereneMindEngine
from services.user_profile_service import UserProfileService
from services.web_search_service import WebSearchService

logger = logging.getLogger(__name__)


def _create_llm_service():
    """
    Factory: Create the appropriate LLM service based on LLM_PROVIDER config.

    Uses LLMProviderFactory (Strategy Pattern) to decouple
    service creation from the concrete provider class.
    """
    from services.llm import LLMProviderFactory

    provider = settings.llm_provider.lower()
    logger.info(f"Using {provider} as LLM provider strategy (via LLMProviderFactory)")
    return LLMProviderFactory.create_provider(provider)


class ServiceContainer:
    """
    Composition Root: Creates and holds all singleton service instances.

    Design Pattern: Service Locator + Singleton Container.

    All services are created once during startup and shared across
    all request handlers. This avoids re-loading models on every request.
    """

    def __init__(self) -> None:
        """Initialize all services in dependency order."""
        import warnings
        warnings.warn(
            "ServiceContainer.__init__ is deprecated. Use ContainerBuilder().build() instead. "
            "This method will be removed in a future release. See golden-singing-puzzle.md for details.",
            DeprecationWarning,
            stacklevel=2,
        )
        logger.info("Initializing service container (DEPRECATED: use ContainerBuilder)...")

        # State: Active ingestion progress — shared across pods via Redis
        self.ingestion_tracker: IngestionTracker = build_ingestion_tracker(
            redis_url=getattr(settings, "redis_url", None)
        )

        # Initialize LLM caching (GPTCache)
        init_llm_cache()

        # Layer 1: Core services (no dependencies)
        self.qdrant = QdrantService()
        self.qdrant.init_collection()
        self.lightrag = lightrag_service

        # Layer 2: Model services (depend on config only)
        self.embedding = EmbeddingService()
        from services.semantic_model_router import SemanticModelRouter
        self.semantic_router = SemanticModelRouter(self.embedding)
        self.ollama = _create_llm_service()  # LLMProvider strategy wrapping Sarvam OR Ollama
        
        # Wire TranslationProvider using TranslationProviderFactory
        from services.translation import TranslationProviderFactory
        self.translation = TranslationProviderFactory.create_provider()
        
        self.ocr = OCRService()
        self.krutrim = KrutrimService()

        # Circuit Breaker Registry (provider-agnostic)
        self.circuit_breaker_registry = initialize_circuit_breakers()
        logger.info("CircuitBreakerRegistry initialized and active provider set")

        # Unit 25: Model failover registry (primary Ollama → fallback Ollama → Krutrim)
        from services.llm import OllamaProvider
        if isinstance(self.ollama, OllamaProvider):
            self.model_registry = ModelRegistry(self.ollama._service, self.krutrim)
        else:
            self.model_registry = None
            logger.info("ModelRegistry not created: non-Ollama provider active")


        # Unit 24: Compliance logger singleton
        self.compliance_logger = get_compliance_logger()
        logger.info("ComplianceLogger initialized (GDPR-safe audit logging active)")

        # Unit 16: A/B Testing Router
        from services.ab_testing import get_ab_router
        self.ab_router = get_ab_router()
        logger.info("ABTestRouter initialized")

        # Unit 22: Prompt versioning store (lazy seed on first use)
        from services.prompt_store import get_prompt_store
        self.prompt_store = get_prompt_store()
        logger.info("PromptStore initialized (SQLite-backed)")

        # Unit 23: Cost attribution tracker
        from services.cost_tracker import get_cost_tracker
        self.cost_tracker = get_cost_tracker()
        logger.info("CostTracker initialized")

        # Layer 3: Emotional Intelligence (depends on embedding, config-gated)
        if settings.serene_mind_enabled:
            self.serene_mind = SereneMindEngine(embedding_service=self.embedding)
        else:
            self.serene_mind = None
            logger.info("Serene Mind Engine disabled via config (SERENE_MIND_ENABLED=false)")

        # Layer 3b: Web Search (real-time temporal queries, config-gated)
        if settings.web_search_enabled:
            self.web_search = WebSearchService(
                allowed_domains=settings.web_search_allowed_domains_list,
                provider=settings.web_search_provider,
                max_results=settings.web_search_max_results,
                searxng_url=settings.searxng_url if settings.web_search_provider == "searxng" else None,
            )
        else:
            self.web_search = None
            logger.info("Web Search disabled via config (WEB_SEARCH_ENABLED=false)")

        # Layer 4: Guardrails (depends on config)
        self.guardrails = GuardrailsService()

        # Layer 4b: Semantic Cache & Exact Cache (depends on embedding + redis + qdrant)
        from services.cache_service import RedisCacheAdapter
        self.exact_cache = RedisCacheAdapter(redis_url=settings.redis_url)
        try:
            self.semantic_cache = SemanticCacheAdapter(
                redis_url=settings.redis_url,
                qdrant_url=settings.qdrant_url if not settings.qdrant_local_path else None,
                qdrant_path=settings.qdrant_local_path if settings.qdrant_local_path else None,
                embedding_service=self.embedding,
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize semantic cache: {exc}. Continuing without semantic caching.")
            self.semantic_cache = None

        # Layer 4b.5: Job Queue (Redis-backed)
        if settings.queue_enabled:
            from app.services.job_queue import JobQueueService
            self.job_queue = JobQueueService(
                redis_url=settings.redis_url,
                max_queue=settings.queue_max_size,
                max_concurrency=settings.queue_concurrency,
                job_ttl=settings.queue_job_ttl,
            )
        else:
            self.job_queue = None

        # Layer 4c: Language Router (no dependencies)
        self.language_router = LanguageRouter()

        # Layer 4d: User Profiles (depends on supabase)
        if settings.user_profile_enabled:
            from supabase import create_client

            from services.memory_service import MemoryService

            supabase_client = None
            if settings.supabase_url and settings.supabase_key:
                try:
                    supabase_client = create_client(settings.supabase_url, settings.supabase_key)
                except Exception as e:
                    logger.error(f"Failed to initialize Supabase client: {e}")

            self.user_profile = UserProfileService(supabase_client=supabase_client)
            self.memory_service = MemoryService(
                supabase_client=supabase_client,
                embedding_service=self.embedding,
                llm_service=self.ollama,
            )
        else:
            self.user_profile = None
            self.memory_service = None

        # Layer 5: Ingestion pipeline (depends on all services)
        self.ingestion = IngestionPipeline(
            qdrant_service=self.qdrant,
            embedding_service=self.embedding,
            ollama_service=self.ollama,
            lightrag_service=self.lightrag,
            ocr_service=self.ocr,
        )

        # Layer 6: RAG graph variants (depends on core services + serene mind)
        # LightRAG degraded-service flag: if Neo4j was unreachable during
        # lightrag.initialize(), the graph still builds but without graph
        # enrichment.  The service itself logs the warning.
        self.fast_graph = build_fast_graph(
            ollama_service=self.ollama,
            embedding_service=self.embedding,
            qdrant_service=self.qdrant,
            lightrag_service=self.lightrag,
            serene_mind_engine=self.serene_mind,
            web_search=self.web_search,
        )
        self.standard_graph = build_rag_graph(
            ollama_service=self.ollama,
            embedding_service=self.embedding,
            qdrant_service=self.qdrant,
            lightrag_service=self.lightrag,
            serene_mind_engine=self.serene_mind,
            web_search=self.web_search,
        )
        self.deep_graph = build_deep_graph(
            ollama_service=self.ollama,
            embedding_service=self.embedding,
            qdrant_service=self.qdrant,
            lightrag_service=self.lightrag,
            serene_mind_engine=self.serene_mind,
            web_search=self.web_search,
        )
        # Backward-compatible alias — defaults to standard graph
        self.rag_graph = self.standard_graph

        logger.info(
            f"All services initialized "
            f"(Serene Mind: {'enabled' if self.serene_mind else 'disabled'}, "
            f"Guardrails: {self.guardrails.provider_name}, "
            f"Semantic Cache: {'enabled' if self.semantic_cache.is_available else 'disabled'})"
        )

    @property
    def lightrag_degraded(self) -> bool:
        """Dynamic check of LightRAG initialization status."""
        return not self.lightrag._initialized

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
            "lightrag_degraded": self.lightrag_degraded,
            "embedding": True,
            "qdrant_count": qdrant_count,
        }

    def update_progress(self, url: str, message: str, percent: float) -> None:
        """Update progress for a specific ingestion URL."""

        self.ingestion_tracker.update(url, message, percent)

    def get_ingest_status(self) -> dict:
        """Retrieve ingestion status from shared storage (Redis or in-memory)."""
        return self.ingestion_tracker.get_all()

    def close(self) -> None:
        """
        Explicitly release resources held by services.

        Calls cleanup methods on services that implement them.
        Errors are logged but do not prevent other services from closing.

        Iteration order is LIFO (reverse of initialization) so that
        dependent services are released before their dependencies.
        """
        # LIFO order: rag_graph → ingestion → guardrails → ocr → ollama → embedding → qdrant
        for name in (
            "rag_graph",
            "ingestion",
            "guardrails",
            "ocr",
            "ollama",
            "embedding",
            "qdrant",
            "user_profile",
            "krutrim",
        ):
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
_container: ServiceContainer | None = None
_container_lock = threading.Lock()


def get_container() -> ServiceContainer:
    """
    Get or create the service container singleton.

    Thread-safe: uses a lock to ensure only one ServiceContainer is created
    even if multiple threads call this concurrently.

    Uses ContainerBuilder (Builder Pattern) for step-by-step, layered
    construction of the service container.
    """
    global _container
    if _container is not None:
        return _container
    with _container_lock:
        # Double-checked locking: re-check inside the lock
        if _container is None:
            from services.container_builder import ContainerBuilder
            _container = ContainerBuilder().build()
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
