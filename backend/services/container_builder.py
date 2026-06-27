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

        # Create a bare instance without invoking the deprecated __init__.
        self._container = ServiceContainer.__new__(ServiceContainer)
        logger.info("ContainerBuilder: starting service construction")

        # Builder stages — dependency order matters.
        self._add_infrastructure()
        self._add_vector_services()
        self._add_llm_services()
        self._add_observability()
        self._add_guardrails_and_caching()
        self._add_language_and_profiles()
        self._add_ingestion()
        self._add_graphs()

        # Final verification that required singletons are present.
        self._container._di_health_check()

        logger.info("ContainerBuilder: all services built successfully")
        return self._container

    def _add_infrastructure(self) -> None:
        """Layer 1: Core infrastructure (no external deps)."""
        self._container._build_infrastructure()
        logger.info("ContainerBuilder: core services added")

    def _add_vector_services(self) -> None:
        """Layer 2: Embedding and semantic-router services."""
        self._container._build_vector_services()
        logger.info("ContainerBuilder: vector services added")

    def _add_llm_services(self) -> None:
        """Layer 3: LLM, translation, failover, and circuit-breaker services."""
        self._container._build_llm_services()
        logger.info("ContainerBuilder: LLM services added")

    def _add_observability(self) -> None:
        """Layer 4: Observability, cost tracking, A/B testing, and prompt store."""
        self._container._build_observability()
        logger.info("ContainerBuilder: observability services added")

    def _add_guardrails_and_caching(self) -> None:
        """Layer 5: Guardrails, exact/semantic caches, job queue, and web search."""
        self._container._build_guardrails_and_cache()

        if getattr(settings, "llm_queue_enabled", True) and self._container.llm_queue is not None:
            from app.services.llm_queue import QueuedLLMProvider
            self._container.ollama = QueuedLLMProvider(self._container.ollama, self._container.llm_queue)
            logger.info(
                "LLM provider wrapped with QueuedLLMProvider (max_concurrent=%d)",
                settings.llm_queue_max_concurrent,
            )

        logger.info("ContainerBuilder: guardrails, caching, and web search added")

    def _add_language_and_profiles(self) -> None:
        """Layer 6: Emotional intelligence and user profiles."""
        self._container._build_profiles()
        logger.info("ContainerBuilder: language and profiles added")

    def _add_ingestion(self) -> None:
        """Layer 7: Ingestion pipeline."""
        self._container._build_ingestion()
        logger.info("ContainerBuilder: ingestion added")

    def _add_graphs(self) -> None:
        """Layer 8: RAG graph variants."""
        self._container._build_graphs()
        logger.info("ContainerBuilder: graph strategies added")
