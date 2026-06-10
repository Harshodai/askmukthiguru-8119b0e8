"""
Mukthi Guru — ServiceContainer Builder (Builder Pattern)

Decomposes ServiceContainer.__init__() into a fluent builder so that
initialization order, dependency wiring, and service variants are controlled
by the builder rather than a single monolithic constructor.

Design Patterns:
  - Builder Pattern: step-by-step, testable construction of ServiceContainer
  - Open/Closed: New services can be registered without changing the builder
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.dependencies import ServiceContainer

logger = logging.getLogger(__name__)


class ContainerBuilder:
    """
    Step-by-step builder that constructs a ServiceContainer.

    Each method wires a single concern (core services, model services,
    guardrails, etc.) into the container, keeping the constructor thin.
    """

    def __init__(self) -> None:
        self._container: ServiceContainer | None = None

    def build(self) -> ServiceContainer:
        """Execute all build steps and return the populated container."""
        from app.dependencies import ServiceContainer

        self._container = ServiceContainer.__new__(ServiceContainer)
        logger.info("ContainerBuilder: starting service construction")

        self._add_core_services()
        self._add_model_services()
        self._add_guardrails_and_caching()
        self._add_language_and_profiles()
        self._add_graphs()
        self._add_ingestion()

        logger.info("ContainerBuilder: all services built successfully")
        return self._container

    def _add_core_services(self) -> None:
        """Layer 1: Core infrastructure (no external deps)."""
        container = self._container
        from app.config import settings
        from services.cache_service import init_llm_cache
        from services.ingestion_tracker import build_tracker as build_ingestion_tracker
        from services.krutrim_service import KrutrimService
        from services.language_router import LanguageRouter
        from services.lightrag_service import lightrag_service
        from services.ocr_service import OCRService
        from services.qdrant_service import QdrantService

        container.ingestion_tracker = build_ingestion_tracker(
            redis_url=getattr(settings, "redis_url", None)
        )
        init_llm_cache()

        container.qdrant = QdrantService()
        try:
            container.qdrant.init_collection()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning(f"ContainerBuilder: Qdrant init_collection failed ({exc!r}); continuing degraded.")
        container.lightrag = lightrag_service
        container.ocr = OCRService()
        container.krutrim = KrutrimService()
        container.language_router = LanguageRouter()
        logger.info("ContainerBuilder: core services added")

    def _add_model_services(self) -> None:
        """Layer 2: LLM, embedding, and translation services."""
        from app.config import settings
        from services.embedding_service import EmbeddingService
        from services.llm import LLMProviderFactory, OllamaProvider
        from services.llm_factory import LLMServiceFactory
        from services.model_registry import ModelRegistry
        from services.translation import TranslationProviderFactory

        container = self._container
        container.embedding = EmbeddingService()

        # Wire LLMProvider using LLMProviderFactory
        provider_name = "sarvam_cloud" if settings.is_sarvam_cloud else "ollama"
        container.ollama = LLMProviderFactory.create_provider(provider_name)

        # Wire TranslationProvider using TranslationProviderFactory
        underlying_ollama = LLMServiceFactory.create("ollama")
        underlying_sarvam = LLMServiceFactory.create("sarvam_cloud")
        container.translation = TranslationProviderFactory.create_provider(
            ollama_service=underlying_ollama,
            sarvam_service=underlying_sarvam,
        )

        # OpenRouter free-tier service for fast/simple queries
        from services.openrouter_service import OpenRouterService
        container.openrouter = OpenRouterService()

        # Model registry only for Ollama
        if isinstance(container.ollama, OllamaProvider):
            container.model_registry = ModelRegistry(container.ollama._service, container.krutrim)
        else:
            container.model_registry = None
            logger.info("ModelRegistry not created: non-Ollama provider active")

        # Circuit breakers
        from services.circuit_breaker import initialize_circuit_breakers
        container.circuit_breaker_registry = initialize_circuit_breakers()
        logger.info("ContainerBuilder: model services added")


    def _add_guardrails_and_caching(self) -> None:
        """Layer 3: Guardrails, cache, A/B, prompt store, cost tracker."""
        from app.config import settings
        from guardrails import GuardrailsService
        from services.ab_testing import get_ab_router
        from services.cache_service import RedisCacheAdapter, SemanticCacheAdapter
        from services.compliance_logger import get_compliance_logger
        from services.cost_tracker import get_cost_tracker
        from services.prompt_store import get_prompt_store

        container = self._container
        container.guardrails = GuardrailsService()
        container.compliance_logger = get_compliance_logger()
        container.ab_router = get_ab_router()
        container.prompt_store = get_prompt_store()
        container.cost_tracker = get_cost_tracker()

        container.exact_cache = RedisCacheAdapter(redis_url=settings.redis_url)
        container.semantic_cache = SemanticCacheAdapter(
            redis_url=settings.redis_url,
            qdrant_url=settings.qdrant_url if not settings.qdrant_local_path else None,
            qdrant_path=settings.qdrant_local_path if settings.qdrant_local_path else None,
            embedding_service=container.embedding,
        )
        logger.info("ContainerBuilder: guardrails and caching added")

    def _add_language_and_profiles(self) -> None:
        """Layer 4: Emotional intelligence and user profiles."""
        from app.config import settings
        from services.memory_service import MemoryService
        from services.serene_mind_engine import SereneMindEngine
        from services.user_profile_service import UserProfileService

        container = self._container
        if settings.serene_mind_enabled:
            container.serene_mind = SereneMindEngine(embedding_service=container.embedding)
        else:
            container.serene_mind = None

        if settings.user_profile_enabled and settings.supabase_url and settings.supabase_key:
            try:
                from supabase import create_client
                supabase_client = create_client(settings.supabase_url, settings.supabase_key)
                container.user_profile = UserProfileService(supabase_client=supabase_client)
                container.memory_service = MemoryService(
                    supabase_client=supabase_client,
                    embedding_service=container.embedding,
                    llm_service=container.ollama,
                )
            except Exception as exc:
                logger.warning(f"Failed to initialize Supabase client: {exc}")
                container.user_profile = None
                container.memory_service = None
        else:
            container.user_profile = None
            container.memory_service = None
        logger.info("ContainerBuilder: language and profiles added")

    def _add_ingestion(self) -> None:
        """Layer 5: Ingestion pipeline."""
        from ingest.pipeline import IngestionPipeline

        container = self._container
        container.ingestion = IngestionPipeline(
            qdrant_service=container.qdrant,
            embedding_service=container.embedding,
            ollama_service=container.ollama,
            lightrag_service=container.lightrag,
            ocr_service=container.ocr,
        )
        logger.info("ContainerBuilder: ingestion added")

    def _add_graphs(self) -> None:
        """Layer 6: RAG graph variants."""
        from rag.graph_strategies import (
            DeepGraphStrategy,
            FastGraphStrategy,
            StandardGraphStrategy,
        )

        container = self._container
        strategies = {
            "fast": FastGraphStrategy(),
            "standard": StandardGraphStrategy(),
            "deep": DeepGraphStrategy(),
        }

        def build_graph(strategy):
            return strategy.build(
                ollama_service=container.ollama,
                embedding_service=container.embedding,
                qdrant_service=container.qdrant,
                lightrag_service=container.lightrag,
                serene_mind_engine=container.serene_mind,
            )

        container.fast_graph = build_graph(strategies["fast"])
        container.standard_graph = build_graph(strategies["standard"])
        container.deep_graph = build_graph(strategies["deep"])
        container.rag_graph = container.standard_graph  # backward-compat alias
        logger.info("ContainerBuilder: graph strategies added")
