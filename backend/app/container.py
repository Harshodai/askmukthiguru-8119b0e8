from __future__ import annotations

# When run as `python app/container.py`, sys.path[0] is `app/`, which causes
# `app/queue/` to shadow stdlib `queue` (urllib3 needs queue.LifoQueue). Drop
# the script dir from sys.path and add the backend root so `app` imports as a
# package. No-op when run via `python -m app.container`.
import os as _os
import sys as _sys
_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _SCRIPT_DIR in _sys.path:
    _sys.path.remove(_SCRIPT_DIR)
_BACKEND = _os.path.dirname(_SCRIPT_DIR)
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

"""
Mukthi Guru — ServiceContainer (Composition Root / data-holder)

Holds all singleton service instances and the layered build stages
used by ContainerBuilder. Health-check and cleanup logic live in
sibling modules (app.health, app.lifecycle) and are delegated to from
here so the container stays a thin data-holder with thin delegating
methods.

Design Patterns:
  - Service Locator + Singleton Container
  - Builder Pattern (construction delegated to services/container_builder.py)
"""

import asyncio
import logging
from typing import Any, Optional

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

    Health-check logic lives in app.health.ContainerHealthChecker and
    cleanup logic lives in app.lifecycle (close_container). The methods
    on this class are thin delegators.
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
        # State: Active ingestion progress — backed by Supabase ingest_jobs table
        self.ingestion_tracker: IngestionTracker = build_ingestion_tracker(
            supabase_url=getattr(settings, "supabase_url", None),
            supabase_key=getattr(settings, "supabase_key", None),
        )

        # Vector / graph infrastructure
        self.qdrant = QdrantService()
        self.qdrant.init_collection()
        self.lightrag = lightrag_service

        # Shared Neo4j driver — constructing a driver does a handshake/routing-table
        # fetch, so lazily create one per process (via the `neo4j_driver` property)
        # and reuse it everywhere instead of every call site opening its own.
        self._neo4j_driver = None

        # Other infrastructure
        self.ocr = OCRService()
        self.krutrim = KrutrimService()
        self.language_router = LanguageRouter()

        # Initialize Supabase client early for dynamic settings loading
        from supabase import create_client
        self.supabase_client = None
        if settings.supabase_url and settings.supabase_key:
            try:
                self.supabase_client = create_client(settings.supabase_url, settings.supabase_key)
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client early: {e}")

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

        # Cross-provider failover via NIM was removed per security audit:
        # external API calls must not be introduced as a silent fallback.
        # self.ollama stays unwrapped so isinstance checks below work directly.

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
        from services.doctrine_cache import DoctrineCache

        self.guardrails = GuardrailsService()

        # Cache adapters honor the configured cache_mode setting.
        self.exact_cache = CacheFactory.create_exact_cache()
        self.semantic_cache = CacheFactory.create_semantic_cache(
            embedding_service=self.embedding,
        )

        # Built once at startup — DoctrineCache._load_from_supabase() is a
        # blocking call and must never run per-request inside the event loop.
        self.doctrine_cache = DoctrineCache(supabase_client=self.supabase_client)
        from services.doctrine_service import DoctrineService
        self.doctrine_service = DoctrineService(supabase_client=self.supabase_client)

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

        # Request Queue (Phase 1 — horizontal scaling stub)
        if settings.use_request_queue:
            from app.queue.redis_stream_queue import RedisStreamQueue
            self.request_queue = RedisStreamQueue(
                redis_url=settings.redis_url,
                consumer_group="backend-workers",
            )
            logger.info("RequestQueue: initialized RedisStreamQueue")
        else:
            from app.queue.in_process_queue import InProcessQueue
            self.request_queue = InProcessQueue()
            logger.info("RequestQueue: initialized InProcessQueue (no-op — USE_REQUEST_QUEUE=false)")

        # Request coalescer — single instance shared across pipeline and orchestrator
        from app.coalescer import build_coalescer
        self.coalescer = build_coalescer(redis_url=getattr(settings, "redis_url", None), ttl=60.0)

        # LLM Gateway — same-provider model-tier fallback, opt-in cross-provider
        # fallback, coalescing. See services/llm_gateway.py.
        from services.llm_gateway import LLMGateway
        _primary_provider_name = settings.llm_provider.lower()
        self.llm_gateway = LLMGateway(
            primary=self.ollama,
            coalescer=self.coalescer,
            secondary=self.openrouter,
            primary_name=_primary_provider_name,
            secondary_name="openrouter",
            primary_model_fallback=(
                settings.openrouter_generation_model_fallback
                if _primary_provider_name == "openrouter"
                else None
            ),
            cross_provider_fallback_enabled=settings.llm_gateway_cross_provider_fallback,
        )
        logger.info(
            f"LLMGateway initialized (primary={_primary_provider_name}, "
            f"cross_provider_fallback={settings.llm_gateway_cross_provider_fallback})"
        )

        # Second Brain (Mukthi Vault) — owner-blind encrypted per-user KG.
        # Degrades to None (endpoints 503) rather than failing container build:
        # BRAIN_KEK absence only blocks Mode-A provisioning at request time, and
        # a Qdrant hiccup here should not take down the whole backend.
        self.second_brain = None
        if self.supabase_client is not None:
            try:
                from services.second_brain.second_brain_service import SecondBrainService
                from services.second_brain.vault_index import VaultIndex

                vault_index = VaultIndex(qdrant_service=self.qdrant)
                try:
                    vault_index.ensure_collection()
                except Exception as exc:
                    logger.warning(f"SecondBrain: vault_index.ensure_collection() failed (will retry lazily): {exc}")
                self.second_brain = SecondBrainService(
                    supabase_client=self.supabase_client,
                    embedding_service=self.embedding,
                    llm_service=self.llm_gateway,
                    qdrant_client=vault_index,
                )
                logger.info("SecondBrainService initialized")
            except Exception as exc:
                logger.warning(f"SecondBrain: initialization failed, vault endpoints will 503: {exc}")
        else:
            logger.info("SecondBrain: skipped (no supabase_client configured)")

        # GraphRAG Fusion — multi-hop vector + knowledge-graph retrieval
        self.graphrag_fusion = None
        try:
            from services.graphrag_fusion import GraphRAGFusion
            from domain.spiritual_ontology import SEED_CONCEPTS

            async def _resolve_entities(q: str) -> list[str]:
                ql = q.lower()
                return [c.uri for c in SEED_CONCEPTS
                        if any(w in ql for w in c.label.lower().split())]

            async def _vector_search(q: str, k: int):
                vec = await asyncio.to_thread(self.embedding.encode_single_full, q)
                try:
                    hits = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.qdrant.search,
                            query_vector=vec["dense"],
                            limit=k,
                            sparse_vector=vec["sparse"],
                            query=q,
                            timeout=10,
                        ),
                        timeout=15,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Qdrant vector search timed out after 15s")
                    return []
                return [{"id": h.get("id"), "text": h.get("text", ""),
                         "score": h.get("score", 0.0), "source": h.get("source", "")} for h in hits]

            async def _traverse_graph(uris: list[str], max_hops: int):
                if not isinstance(max_hops, int) or max_hops < 1:
                    max_hops = 2
                # max_hops must be interpolated as literal in Cypher variable-length pattern
                cypher = f"""
                MATCH path = (c:Concept {{uri: $uri}})-[r*1..{max_hops}]-(n)
                RETURN n.text AS text, n.uri AS uri, type(last(relationships(path))) AS relation,
                       length(path) AS hop, n.source AS source
                LIMIT 40
                """
                rows = []
                driver = self.neo4j_driver
                if driver is None:
                    return rows
                for u in uris:
                    def _run(u=u):
                        with driver.session() as session:
                            return list(session.run(cypher, {"uri": u}, timeout=10))
                    try:
                        records = await asyncio.wait_for(
                            asyncio.to_thread(_run),
                            timeout=15,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Neo4j graph traversal timed out after 15s for URI: {u}")
                        continue
                    for record in records:
                        rows.append({
                            "uri": record.get("uri"),
                            "text": record.get("text"),
                            "relation": record.get("relation"),
                            "hop": record.get("hop", 0),
                            "source": record.get("source"),
                        })
                return rows

            self.graphrag_fusion = GraphRAGFusion(
                vector_search=_vector_search,
                resolve_entities=_resolve_entities,
                traverse_graph=_traverse_graph,
                max_hops=settings.graphrag_max_hops,
                token_budget=settings.graphrag_token_budget,
                enable_graph=getattr(settings, "knowledge_graph_query_enabled", False),
            )
        except Exception as exc:
            logger.warning(f"GraphRAGFusion init failed (non-fatal): {exc}")

        # Web Search (real-time temporal queries, config-gated)
        if settings.web_search_enabled:
            # Load dynamic allowed domains from Supabase settings table, fallback to env config list
            allowed_domains = settings.web_search_allowed_domains_list
            if self.supabase_client:
                try:
                    res = self.supabase_client.table("app_settings").select("value").eq("key", "global").execute()
                    if res.data and len(res.data) > 0:
                        db_val = res.data[0]["value"]
                        if "web_search_allowed_domains" in db_val:
                            allowed_domains = db_val["web_search_allowed_domains"]
                            logger.info(f"Loaded allowed web search domains from DB: {allowed_domains}")
                except Exception as e:
                    logger.error(f"Failed to load allowed web search domains from database at startup: {e}")

            self.web_search = WebSearchService(
                allowed_domains=allowed_domains,
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
            self.user_profile = UserProfileService(supabase_client=self.supabase_client)
            self.memory_service = MemoryServiceV2(
                supabase_client=self.supabase_client,
                embedding_service=self.embedding,
                llm_service=self.ollama,
            )
            # Fix: global_memory collection was never created — every
            # set_global_memory/search_global call silently failed. Idempotent.
            self.memory_service.ensure_global_memory_collection()
            from services.memory import EpisodicMemoryService
            from services.notebook_service import NotebookService

            # ponytail: reuse the same supabase_client built above — no new connection.
            self.episodic_memory_service = EpisodicMemoryService(supabase_client=self.supabase_client)
            self.notebook_service = NotebookService(supabase_client=self.supabase_client)
            from services.srs_service import SRSService
            self.srs_service = SRSService(supabase_client=self.supabase_client, ollama_service=self.ollama)
        else:
            self.user_profile = None
            self.memory_service = None
            self.episodic_memory_service = None
            self.notebook_service = None
            self.srs_service = None

        # Push notification service — lightweight (lazy FCM/APNs init), no heavy deps.
        from services.push_service import PushService
        self.push_service = PushService()

        # Retention service — streak tracking + lifecycle events.
        # Degrades gracefully to None if supabase_client is unavailable.
        self.retention_service = None
        if self.supabase_client is not None:
            try:
                from services.retention_service import RetentionService
                self.retention_service = RetentionService(supabase_client=self.supabase_client)
                logger.info("RetentionService initialized")
            except Exception as exc:
                logger.warning(f"RetentionService init failed (non-fatal): {exc}")

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
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        # LightRAG degraded-service flag: if Neo4j was unreachable during
        # lightrag.initialize(), the graph still builds but without graph
        # enrichment. The service itself logs the warning.
        logger.info("ContainerBuilder: building FAST graph...")
        self.fast_graph = build_fast_graph(
            ollama_service=self.ollama,
            embedding_service=self.embedding,
            qdrant_service=self.qdrant,
            lightrag_service=self.lightrag,
            serene_mind_engine=self.serene_mind,
            web_search=self.web_search,
            doctrine_service=self.doctrine_service,
            llm_gateway=self.llm_gateway,
            graphrag_fusion=self.graphrag_fusion,
        )
        logger.info("ContainerBuilder: FAST graph built")

        logger.info("ContainerBuilder: building STANDARD graph...")
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(
                build_rag_graph,
                ollama_service=self.ollama,
                embedding_service=self.embedding,
                qdrant_service=self.qdrant,
                lightrag_service=self.lightrag,
                serene_mind_engine=self.serene_mind,
                web_search=self.web_search,
                doctrine_service=self.doctrine_service,
                llm_gateway=self.llm_gateway,
                graphrag_fusion=self.graphrag_fusion,
            )
            try:
                self.standard_graph = fut.result(timeout=60.0)
                logger.info("ContainerBuilder: STANDARD graph built")
            except FutureTimeoutError:
                logger.warning("ContainerBuilder: STANDARD graph compilation timed out after 60s — falling back to FAST graph")
                self.standard_graph = self.fast_graph
            except Exception as e:
                logger.warning(f"ContainerBuilder: STANDARD graph compilation failed: {e} — falling back to FAST graph")
                self.standard_graph = self.fast_graph

        logger.info("ContainerBuilder: building DEEP graph...")
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(
                build_deep_graph,
                ollama_service=self.ollama,
                embedding_service=self.embedding,
                qdrant_service=self.qdrant,
                lightrag_service=self.lightrag,
                serene_mind_engine=self.serene_mind,
                web_search=self.web_search,
                doctrine_service=self.doctrine_service,
                llm_gateway=self.llm_gateway,
                graphrag_fusion=self.graphrag_fusion,
            )
            try:
                self.deep_graph = fut.result(timeout=60.0)
                logger.info("ContainerBuilder: DEEP graph built")
            except FutureTimeoutError:
                logger.warning("ContainerBuilder: DEEP graph compilation timed out after 60s — falling back to STANDARD graph")
                self.deep_graph = self.standard_graph
            except Exception as e:
                logger.warning(f"ContainerBuilder: DEEP graph compilation failed: {e} — falling back to STANDARD graph")
                self.deep_graph = self.standard_graph
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

    @property
    def neo4j_driver(self):
        """Shared Neo4j driver, lazily created once and reused by all callers."""
        if self._neo4j_driver is None:
            from neo4j import GraphDatabase

            try:
                self._neo4j_driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                )
            except Exception as e:
                logger.warning(f"ServiceContainer: Failed to create shared Neo4j driver: {e}")
                self._neo4j_driver = None
        return self._neo4j_driver

    async def health_status(self) -> dict:
        """Check health of all services (non-blocking). Thin delegator."""
        from app.health import ContainerHealthChecker

        return await ContainerHealthChecker().check(self)

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
        Explicitly release resources held by services. Thin delegator —
        the cleanup logic lives in app.lifecycle.close_container().
        """
        from app.lifecycle import close_container

        close_container(self)


if __name__ == "__main__":
    # Self-check: module imports cleanly and the class is accessible.
    print("C2 OK")