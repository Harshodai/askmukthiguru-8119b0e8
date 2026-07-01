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
from typing import Any

from app.config import settings
from guardrails import GuardrailsService
from ingest.pipeline import IngestionPipeline
from rag.graph import build_deep_graph, build_fast_graph, build_rag_graph
from services.circuit_breaker import initialize_circuit_breakers
from services.embedding_service import EmbeddingService
from services.ingestion_tracker import IngestionTracker
from services.ingestion_tracker import build_tracker as build_ingestion_tracker
from services.krutrim_service import KrutrimService
from services.language_router import LanguageRouter
from services.lightrag_service import lightrag_service
from services.model_registry import ModelRegistry  # Unit 25
from services.sarvam_failover import SarvamFailoverService
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


class _NoopTranslationProvider:
    """Pass-through translation provider used when no external translation service is configured."""

    async def translate_text(self, *, text: str, source_lang: str, target_lang: str, **kwargs):
        return text

    async def health_check(self) -> bool:
        return True


# Required singletons that must be non-None after container construction.
_REQUIRED_SINGLETONS = frozenset({
    "ingestion_tracker",
    "qdrant",
    "embedding",
    "ollama",
    "guardrails",
    "exact_cache",
    "circuit_breaker_registry",
})


class ServiceContainer:
    """
    Composition Root: Creates and holds all singleton service instances.

    Design Pattern: Service Locator + Singleton Container.

    All services are created once during startup and shared across
    all request handlers. This avoids re-loading models on every request.

    Construction is split into builder stages so initialization order and
    dependency wiring are explicit and testable. Use ContainerBuilder
    (services/container_builder.py) to construct instances; this class
    no longer has a public constructor.
    """

    def __init__(self) -> None:
        """Prevent direct instantiation — use ContainerBuilder().build()."""
        raise NotImplementedError(
            "ServiceContainer must be constructed via ContainerBuilder().build(). "
            "Direct instantiation is not supported."
        )

    # === Builder stages =======================================================

    def _build_infrastructure(self) -> None:
        """Layer 1: Core infrastructure services with no external dependencies."""
        # State: Active ingestion progress — shared across pods via Redis
        self.ingestion_tracker: IngestionTracker = build_ingestion_tracker(
            redis_url=getattr(settings, "redis_url", None)
        )

        # Vector / graph infrastructure
        self.qdrant = QdrantService()
        self.qdrant.init_collection()
        self.lightrag = lightrag_service

        # Other infrastructure
        self.ocr = OCRService()
        self.krutrim = KrutrimService()
        self.language_router = LanguageRouter()

    def _build_vector_services(self) -> None:
        """Layer 2: Embedding and semantic-router services."""
        from services.semantic_model_router import SemanticModelRouter

        self.embedding = EmbeddingService()
        self.semantic_router = SemanticModelRouter(self.embedding)

        # Initialize GPTCache with the shared embedding service to avoid
        # loading BGE-M3 a second time in a separate SBERT instance.
        from services.cache import init_llm_cache
        init_llm_cache(embedding_func=self.embedding.encode_single)

    def _build_llm_services(self) -> None:
        """Layer 3: LLM, translation, failover, and circuit-breaker services."""
        from services.llm import LLMProviderFactory, OllamaProvider
        from services.llm_factory import LLMServiceFactory
        from services.openrouter_service import OpenRouterService
        from services.translation import TranslationProviderFactory

        self.ollama = _create_llm_service()  # LLMProvider strategy wrapping Sarvam OR Ollama

        # Wire TranslationProvider using TranslationProviderFactory
        if settings.is_sarvam_cloud:
            self.sarvam_cloud = LLMServiceFactory.create("sarvam_cloud")
            self.translation = TranslationProviderFactory.create_provider(
                sarvam_service=self.sarvam_cloud,
            )
        else:
            logger.info("Sarvam Cloud not active; skipping Sarvam service initialization")
            self.sarvam_cloud = None
            if isinstance(self.ollama, OllamaProvider):
                from services.translation import OllamaTranslationProvider
                self.translation = OllamaTranslationProvider(self.ollama._service)
            else:
                # Non-Ollama provider without Sarvam: keep a placeholder that passes text through
                self.translation = _NoopTranslationProvider()

        # OpenRouter free-tier service for fast/simple queries
        self.openrouter = OpenRouterService()

        # Multi-provider LLM failover router (circuit breakers + rate limiting)
        self.multi_provider_llm = None
        try:
            from services.multi_provider_llm import get_llm_service as get_multi_provider_llm
            self.multi_provider_llm = get_multi_provider_llm()
            logger.info("MultiProviderLLMService initialized (failover ready)")
        except Exception as e:
            logger.warning(f"MultiProviderLLMService init skipped: {e}")

        # Model registry with cross-provider failover
        if isinstance(self.ollama, OllamaProvider):
            self.model_registry = ModelRegistry(self.ollama._service, self.krutrim)
        else:
            self.model_registry = SarvamFailoverService(self.ollama._service, self.krutrim)
            logger.info("SarvamFailoverService active: cross-provider failover enabled")

        # Circuit Breaker Registry (provider-agnostic)
        self.circuit_breaker_registry = initialize_circuit_breakers()
        logger.info("CircuitBreakerRegistry initialized and active provider set")

    def _build_observability(self) -> None:
        """Layer 4: Observability, cost tracking, A/B testing, and prompt store."""
        from services.ab_testing import get_ab_router
        from services.compliance_logger import get_compliance_logger
        from services.cost_tracker import get_cost_tracker
        from services.prompt_store import get_prompt_store

        self.compliance_logger = get_compliance_logger()
        logger.info("ComplianceLogger initialized (GDPR-safe audit logging active)")

        self.ab_router = get_ab_router()
        logger.info("ABTestRouter initialized")

        self.prompt_store = get_prompt_store()
        logger.info("PromptStore initialized (SQLite-backed)")

        self.cost_tracker = get_cost_tracker()
        logger.info("CostTracker initialized")

    def _build_guardrails_and_cache(self) -> None:
        """Layer 5: Guardrails, exact/semantic caches, job queue, and web search."""
        from services.cache import CacheFactory

        self.guardrails = GuardrailsService()

        # Cache adapters honor the configured cache_mode setting.
        self.exact_cache = CacheFactory.create_exact_cache()
        self.semantic_cache = CacheFactory.create_semantic_cache(
            embedding_service=self.embedding,
        )

        # Job Queue (Redis-backed)
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

        # LLM Queue (concurrency gating)
        if settings.llm_queue_enabled:
            from app.services.llm_queue import LLMQueueService
            self.llm_queue = LLMQueueService(
                max_concurrent=settings.llm_queue_max_concurrent,
                queue_maxsize=settings.llm_queue_maxsize,
            )
        else:
            self.llm_queue = None

        # Web Search (real-time temporal queries, config-gated)
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

    def _build_profiles(self) -> None:
        """Layer 6: Emotional intelligence and user profiles."""
        from services.memory_service_v2 import MemoryServiceV2

        if settings.serene_mind_enabled:
            self.serene_mind = SereneMindEngine(embedding_service=self.embedding)
        else:
            self.serene_mind = None
            logger.info("Serene Mind Engine disabled via config (SERENE_MIND_ENABLED=false)")

        if settings.user_profile_enabled:
            from supabase import create_client

            supabase_client = None
            if settings.supabase_url and settings.supabase_key:
                try:
                    supabase_client = create_client(settings.supabase_url, settings.supabase_key)
                except Exception as e:
                    logger.error(f"Failed to initialize Supabase client: {e}")

            self.user_profile = UserProfileService(supabase_client=supabase_client)
            self.memory_service = MemoryServiceV2(
                supabase_client=supabase_client,
                embedding_service=self.embedding,
                llm_service=self.ollama,
            )
            from services.memory import EpisodicMemoryService
            from services.notebook_service import NotebookService

            # ponytail: reuse the same supabase_client built above — no new connection.
            self.episodic_memory_service = EpisodicMemoryService(supabase_client=supabase_client)
            self.notebook_service = NotebookService(supabase_client=supabase_client)
        else:
            self.user_profile = None
            self.memory_service = None
            self.episodic_memory_service = None
            self.notebook_service = None

    def _build_ingestion(self) -> None:
        """Layer 7: Ingestion pipeline (depends on core services)."""
        self.ingestion = IngestionPipeline(
            qdrant_service=self.qdrant,
            embedding_service=self.embedding,
            ollama_service=self.ollama,
            lightrag_service=self.lightrag,
            ocr_service=self.ocr,
            semantic_cache_service=self.semantic_cache,
        )

    def _build_graphs(self) -> None:
        """Layer 8: RAG graph variants (depends on core services + serene mind)."""
        # LightRAG degraded-service flag: if Neo4j was unreachable during
        # lightrag.initialize(), the graph still builds but without graph
        # enrichment. The service itself logs the warning.
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

    def _di_health_check(self) -> None:
        """Verify that required singletons are non-None."""
        missing: list[str] = []
        for name in _REQUIRED_SINGLETONS:
            value = getattr(self, name, None)
            if value is None:
                missing.append(name)
                logger.error(f"DI health check: required singleton '{name}' is None")
            else:
                logger.debug(f"DI health check: '{name}' OK")

        if missing:
            raise RuntimeError(
                f"DI health check failed for {len(missing)} required singleton(s): {missing}. "
                f"Required: {sorted(_REQUIRED_SINGLETONS)}"
            )
        logger.info("DI health check passed: all required singletons are initialized")

    # === Public API ==========================================================

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
            "semantic_cache": self.semantic_cache.is_available if self.semantic_cache else False,
            "lightrag_degraded": self.lightrag_degraded,
            "embedding": True,
            "qdrant_count": qdrant_count,
        }

    def update_progress(
        self,
        url: str,
        message: str,
        percent: float,
        tags: Optional[list[str]] = None,
    ) -> None:
        """Update progress for a specific ingestion URL."""
        self.ingestion_tracker.update(url, message, percent, tags=tags)

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
    """Cleanup on application shutdown - releases service resources."""
    global _container
    with _container_lock:
        if _container is not None:
            _container.close()
            _container = None
    logger.info("Service container shutdown")
