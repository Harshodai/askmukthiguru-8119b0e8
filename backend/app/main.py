"""
Mukthi Guru — FastAPI Application Bootstrap

This module is intentionally thin: route groups live in app.api.* modules,
lifespan and middleware wiring live here, and the app is exported as `app`.
"""

import asyncio
import faulthandler
import json
import logging
import re

faulthandler.enable()
import os
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Fix import paths — run from backend/ directory
sys.path.insert(0, ".")

# Configure threading limits before importing any heavy numerical libraries.
from app.core.threading_config import configure_threading

configure_threading()

# Set Python process memory limit early to prevent runaway OOM crashes.
# Controlled by PYTHON_MEMORY_LIMIT_MB env var (default 6144 = 6GB).
# Only effective on Linux (RLIMIT_AS); silently skipped on macOS/Windows.
try:
    import resource as _resource

    _mb = int(os.environ.get("PYTHON_MEMORY_LIMIT_MB", "6144"))
    if _mb > 0:
        _limit_bytes = _mb * 1024 * 1024
        if hasattr(_resource, "RLIMIT_DATA"):  # Safe heap limit (does not restrict mmap)
            _resource.setrlimit(_resource.RLIMIT_DATA, (_limit_bytes, _limit_bytes))
            logger_tmp = logging.getLogger(__name__)
            logger_tmp.info(
                "Python memory limit set to %dMB via RLIMIT_DATA (PYTHON_MEMORY_LIMIT_MB=%s)",
                _mb,
                os.environ.get("PYTHON_MEMORY_LIMIT_MB", "<unset>"),
            )
        elif hasattr(_resource, "RLIMIT_AS"):  # Fallback only
            _resource.setrlimit(_resource.RLIMIT_AS, (_limit_bytes, _limit_bytes))
except Exception:
    pass  # Non-fatal: Docker itself provides hard memory limits


# Tenant context is populated per-request via the ``set_tenant_from_request``
# dependency (wired into routers, e.g. app/api/chat.py and app/api/ingest.py).
# There is deliberately no module-level tenant init here — a bare module-level
# call would run without a request and set the wrong tenant.
# Backward-compatible module-level coalescer (tests patch app.main.coalescer).
from app.coalescer import build_coalescer as _build_coalescer
from app.config import settings
from app.context import correlation_id_var
from app.dependencies import async_shutdown, get_container, startup
from app.metrics import REQUEST_COUNT
from app.observability import init_observability
from app.security_utils import (
    ExponentialBackoffRateLimiter,
    RedisBackedRateLimiter,
    TTLRateLimiter,
    build_csp,
)
from app.telemetry_db import init_telemetry_db
from app.telemetry_sink import SupabaseTelemetrySink, TelemetryWorker
from services.auth_service import get_current_user_from_supabase  # noqa: F401

coalescer = _build_coalescer(redis_url=getattr(settings, "redis_url", None), ttl=60.0)

# Existing routers
from app.api.admin import admin_router
from app.api.assistants import router as assistants_router
from app.api.cache_metrics import router as cache_metrics_router
from app.api.cancel_flow import router as cancel_flow_router
from app.api.capabilities import router as capabilities_router

# Newly-extracted route groups
from app.api.chat import router as chat_router
from app.api.compliance import router as compliance_router
from app.api.endpoints.auth import router as auth_router
from app.api.feedback import router as feedback_router
from app.api.healing_course import router as healing_course_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.memory import router as memory_router
from app.api.metrics import router as metrics_router
from app.api.profile import router as profile_router
from app.api.push import router as push_router
from app.api.retention import router as retention_router
from app.api.speech import router as speech_router
from app.api.srs import router as srs_router
from app.api.support import router as support_router
from app.api.teachings import router as teachings_router
from app.api.waitlist import router as waitlist_router
from app.core.limiter import limiter
from routers.notebooks import router as notebooks_router

# Job and trace routers are imported where needed below to avoid
# heavy imports during module load.

telemetry_sink = SupabaseTelemetrySink()
telemetry_worker = TelemetryWorker(telemetry_sink)

logger = logging.getLogger(__name__)

# PII auto-redaction for log output (P1-SEC-3): every message emitted through
# the JSON formatter is scrubbed for emails/phones/IDs/IPs/query params.
from services.pii_scanner import PIIScanner

# === Graceful shutdown in-flight request tracker (R3) ===
_INFLIGHT = 0  # simple int — GIL protects single reads/writes in CPython
_DRAIN_TIMEOUT_S = 45  # max seconds to wait for in-flight requests during shutdown; 15s margin under Railway drainingSeconds:60 (P1-OPS-5)


class JSONFormatter(logging.Formatter):
    def format(self, record):
        msg = record.getMessage()
        if hasattr(PIIScanner, "redact"):
            msg = PIIScanner.redact(msg)
        else:
            msg = PIIScanner().redact(msg)
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": msg,
        }
        # Include correlation ID if available
        try:
            cid = correlation_id_var.get()
            if cid != "-":
                log_obj["correlation_id"] = cid
        except Exception as _e:
            logger.debug("[startup/shutdown] suppressed non-critical error: %s", _e)
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


class PIIScrubber(logging.Filter):
    """Defense-in-depth: scrubs record.msg before any handler (even ones that
    bypass JSONFormatter) formats it. Never raises — redaction must not break
    logging."""

    def filter(self, record):
        try:
            redacted = PIIScanner.redact(record.getMessage())
            record.msg = redacted
            record.args = ()
        except Exception as _e:
            logger.debug("[startup/shutdown] suppressed non-critical error: %s", _e)
        return True


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"))
logging.basicConfig(level=logging.INFO, handlers=[handler])

# Defense in depth: PIIScrubber on the root logger AND on its handlers.
# Logger-level filters only run for records emitted by that logger itself, so
# the handler-level filter is what actually scrubs records from child loggers
# (e.g. app.*) before any handler — including ones that bypass JSONFormatter —
# formats them.
logging.getLogger().addFilter(PIIScrubber())
for _hdlr in logging.getLogger().handlers:
    _hdlr.addFilter(PIIScrubber())


# === NodeObserver wiring (called during startup) ===


def _register_node_observers() -> None:
    """
    Wire NodeObserver instances for the RAG pipeline.

    MetricsObserver and LoggingObserver are registered globally so that
    any NodeCommand execution emits telemetry automatically.
    This is a no-op if NodeRegistry has not been populated yet.
    """
    try:
        from rag.telemetry_observer import LoggingObserver, MetricsObserver, SelfCorrectionObserver

        # Register observers globally (used at node-execution time)
        global _node_observers
        _node_observers = [
            MetricsObserver(),
            LoggingObserver(),
            SelfCorrectionObserver(max_retries=3),
        ]
        logger.info(f"Registered {len(_node_observers)} NodeObserver(s) for pipeline telemetry")
    except Exception as exc:
        logger.warning(f"NodeObserver wiring skipped: {exc}")


def _wire_graph_observers() -> None:
    """
    Attach registered observers to compiled LangGraph nodes.

    This is a best-effort wiring that maps the GraphState keys back to
    NodeCommand wrappers so observers can fire for each graph step.
    Observers are stored in the module-level _node_observers list from
    _register_node_observers() and consumed by Command wrappers at runtime.
    """
    try:
        from rag.node_registry import registry

        node_names = registry.list()
        # Wiring is lazy — see rag.node_command for observer dispatch
        logger.info(f"Graph observers wired for {len(node_names)} registered node(s)")
    except Exception as exc:
        logger.warning(f"Graph observer wiring skipped: {exc}")


# === Startup state (checked by health endpoint) ===
_startup_complete = False
_startup_error: str | None = None


def _get_qdrant_service_client(container) -> object | None:
    """Get the raw Qdrant gRPC/REST client from QdrantService."""
    _qdrant_svc = getattr(container, "qdrant", None)
    if _qdrant_svc and hasattr(_qdrant_svc, "_client"):
        return _qdrant_svc._client
    return None


async def _background_startup_body(container, fastapi_app) -> None:
    """Run deferred initialization (ontology seeding, queues, telemetry).

    Called inline from lifespan before yield, wrapped in asyncio.wait_for(180s).
    """
    import app.dependencies as _app_deps

    # Advisory-only: warn if Qdrant server predates sparse-vector support (>= 1.8)
    try:
        from app.qdrant_version_check import check_qdrant_version

        _vclient = _get_qdrant_service_client(container)
        if _vclient:
            check_qdrant_version(_vclient)
    except Exception as e:
        logger.info(f"Lifespan: Qdrant version check skipped (non-critical): {e}")

    # Startup is strictly read-only: schema mutations and migrations are handled
    # via the standalone maintenance runner (backend/migrations/maintenance_runner.py).

    # Embedding model drift detection: write/verify model fingerprint
    # If embedding model changed, all existing vectors are stale — alert on mismatch.
    logger.info("Lifespan: checking embedding model fingerprint...")
    try:
        import hashlib as _hashlib
        import json as _json

        _embed_model_name = getattr(settings, "embedding_model", "BAAI/bge-m3")
        _embed_dim = getattr(settings, "embedding_dimension", 1024)
        _fingerprint = _hashlib.md5(
            f"{_embed_model_name}:{_embed_dim}".encode(), usedforsecurity=False
        ).hexdigest()
        _fp_redis_key = "embedding_model_fingerprint"

        # Use Redis for durable cross-deploy persistence; fall back to /tmp on failure
        _stored_fp = None
        try:
            import redis as _redis_lib

            _r = _redis_lib.Redis.from_url(
                settings.redis_url, socket_timeout=3, socket_connect_timeout=3
            )
            _stored_raw = _r.get(_fp_redis_key)
            if _stored_raw:
                _stored = _json.loads(_stored_raw)
                _stored_fp = _stored.get("fingerprint")
        except Exception:
            _fp_path = "/tmp/embedding_model_fingerprint.json"
            if __import__("os").path.exists(_fp_path):
                try:
                    with open(_fp_path) as _f:
                        _stored = _json.load(_f)
                        _stored_fp = _stored.get("fingerprint")
                except Exception as _e:
                    logger.debug("[startup/shutdown] suppressed non-critical error: %s", _e)

        if _stored_fp is not None:
            if _stored_fp != _fingerprint:
                logger.critical(
                    "⚠️  EMBEDDING MODEL CHANGED: stored=%s current=%s model=%s dim=%d. "
                    "Full re-indexing of spiritual_wisdom required to avoid retrieval degradation!",
                    _stored_fp,
                    _fingerprint,
                    _embed_model_name,
                    _embed_dim,
                )
            else:
                logger.info("Lifespan: embedding model fingerprint OK (%s)", _fingerprint[:8])
        else:
            # Store fingerprint in Redis (primary) and /tmp (fallback)
            try:
                import redis as _redis_lib2

                _r2 = _redis_lib2.Redis.from_url(
                    settings.redis_url, socket_timeout=3, socket_connect_timeout=3
                )
                _r2.set(
                    _fp_redis_key,
                    _json.dumps(
                        {"model": _embed_model_name, "dim": _embed_dim, "fingerprint": _fingerprint}
                    ),
                )
            except Exception:
                _fp_path = "/tmp/embedding_model_fingerprint.json"
                try:
                    with open(_fp_path, "w") as _f:
                        _json.dump(
                            {
                                "model": _embed_model_name,
                                "dim": _embed_dim,
                                "fingerprint": _fingerprint,
                            },
                            _f,
                        )
                except Exception as _e:
                    logger.debug("[startup/shutdown] suppressed non-critical error: %s", _e)
            logger.info("Lifespan: embedding model fingerprint stored (%s)", _fingerprint[:8])
    except Exception as e:
        logger.warning(f"Lifespan: embedding model drift check error (non-critical): {e}")

    # Verify multilingual reranker model is cached (fail fast on cold start to surface missing models)
    logger.info("Lifespan: verifying reranker model availability...")
    try:
        import os as _os

        _reranker_model = getattr(
            settings, "reranker_model_cpu", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
        )
        _model_cache = _os.environ.get(
            "SENTENCE_TRANSFORMERS_HOME", "/app/model_cache/sentence_transformers"
        )
        # Convert model ID to cache path format (slashes → dashes)
        _model_dir = _os.path.join(_model_cache, _reranker_model.replace("/", "_"))
        _alt_model_dir = _os.path.join(_model_cache, _reranker_model.replace("/", "__"))
        if _os.path.isdir(_model_dir) or _os.path.isdir(_alt_model_dir):
            logger.info("Lifespan: reranker model %s found in cache — OK", _reranker_model)
        else:
            logger.warning(
                "Lifespan: reranker model %s NOT in cache at %s — will download on first use (cold start latency expected)",
                _reranker_model,
                _model_cache,
            )
    except Exception as e:
        logger.warning(f"Lifespan: reranker cache check error (non-critical): {e}")

    # Pre-warm LettuceDetect if enabled to prevent 20s cold-start latency spike on first user turn
    if getattr(settings, "lettucedetect_enabled", False) and getattr(
        container, "lettuce_detect", None
    ):
        try:
            logger.info("Lifespan: pre-warming LettuceDetect model...")
            await asyncio.to_thread(container.lettuce_detect._load_real_detector)
            logger.info("Lifespan: LettuceDetect model pre-warmed — OK")
        except Exception as e:
            logger.warning(f"Lifespan: LettuceDetect pre-warming skipped (non-critical): {e}")

    # Observability tracing (OpenTelemetry + Jaeger)

    logger.info("Lifespan: about to init observability...")
    init_observability(fastapi_app)
    logger.info("Lifespan: observability done")

    # Schedule recurring jobs
    logger.info("Lifespan: about to start scheduler...")
    try:
        from infrastructure.scheduler import shutdown_scheduler, start_scheduler

        start_scheduler()
        fastapi_app.state.scheduler_shutdown = shutdown_scheduler
        logger.info("Lifespan: scheduler started")
    except Exception as e:
        logger.warning(f"Failed to initialize APScheduler: {e}")

    # Start Telemetry Background Worker
    logger.info("Lifespan: about to start telemetry worker...")
    telemetry_worker.start()
    logger.info("Lifespan: telemetry worker started")

    # Config Watcher
    logger.info("Lifespan: about to start config watcher...")
    from services.config_watcher import start_config_watcher

    await start_config_watcher()
    logger.info("Lifespan: config watcher started")

    # Start Job Queue workers
    if getattr(container, "job_queue", None):
        try:
            from app.orchestrator import queue_worker_factory

            logger.info(f"About to start JobQueue: job_queue={container.job_queue!r}")
            await container.job_queue.start(queue_worker_factory)
            logger.info("JobQueue workers started")
        except Exception as e:
            logger.warning(f"Failed to start JobQueue workers: {e}")

    # Start LLM Queue
    if getattr(container, "llm_queue", None):
        try:
            await container.llm_queue.start()
            logger.info("LLMQueue started")
        except Exception as e:
            logger.warning(f"Failed to start LLMQueue: {e}")

    # Start Request Queue
    if getattr(container, "request_queue", None):
        try:
            await container.request_queue.start()
            logger.info("RequestQueue started")
        except Exception as e:
            logger.warning(f"Failed to start RequestQueue: {e}")

    # Embedding warm-up canary — fires the ONNX model cold-start cost at deploy time,
    # not on the first user request. Also validates the dimension contract before traffic.
    try:
        if getattr(container, "embedding", None):
            _t0 = time.time()
            _test_vec = await asyncio.to_thread(
                container.embedding.encode_single, "consciousness stillness awareness"
            )
            _latency_ms = int((time.time() - _t0) * 1000)
            _dim = len(_test_vec) if hasattr(_test_vec, "__len__") else -1
            if _dim != settings.embedding_dimension:
                logger.error(
                    "EMBEDDING DIMENSION MISMATCH: got %d, expected %d — "
                    "Qdrant dense search will fail. Check HF_REVISION and ONNX model pin.",
                    _dim,
                    settings.embedding_dimension,
                )
                _app_deps.startup_error = (
                    f"Embedding dimension mismatch: got {_dim}, expected "
                    f"{settings.embedding_dimension} — Qdrant dense search will fail"
                )
            else:
                logger.info("Embedding warm-up OK: dim=%d, latency=%dms", _dim, _latency_ms)
        else:
            logger.warning("Embedding service not available for warm-up canary")
    except Exception as _warmup_err:
        logger.warning("Embedding warm-up canary failed (non-fatal): %s", _warmup_err)

    # Intent-model warm-up canary — the classifier is otherwise lazy-loaded on
    # the first non-English/keyword-miss query. Prewarm with a native Indic
    # sample so the first user request does not absorb model initialization.
    try:
        from rag.nodes.on_device_intent import classify_with_reason

        _t0 = time.time()
        _intent_probe = await asyncio.to_thread(classify_with_reason, "शांति क्या है?")
        logger.info(
            "On-device intent warm-up complete: result=%s latency=%dms",
            _intent_probe[0] if _intent_probe else "none",
            int((time.time() - _t0) * 1000),
        )
    except Exception as _intent_warmup_err:
        logger.warning("On-device intent warm-up failed (non-fatal): %s", _intent_warmup_err)

    # Semantic-router warm-up canary — its first classify_with_score call may
    # initialize a model/embedding path lazily and previously added an observed
    # multi-second graph-selection tail to the first short Indic request. Warm
    # it during deployment while preserving the existing router policy; failures
    # remain non-fatal and fall back to the current routing path.
    try:
        semantic_router = getattr(container, "semantic_router", None)
        if getattr(settings, "use_semantic_router", True) and semantic_router is not None:
            _t0 = time.time()
            _semantic_probe = await asyncio.to_thread(
                semantic_router.classify_with_score, "What is meditation?"
            )
            logger.info(
                "Semantic-router warm-up complete: tier=%s confidence=%s latency=%dms",
                _semantic_probe[0]
                if isinstance(_semantic_probe, tuple) and _semantic_probe
                else "none",
                _semantic_probe[1]
                if isinstance(_semantic_probe, tuple) and len(_semantic_probe) > 1
                else "none",
                int((time.time() - _t0) * 1000),
            )
    except Exception as _semantic_warmup_err:
        logger.warning("Semantic-router warm-up failed (non-fatal): %s", _semantic_warmup_err)

    _app_deps.startup_complete = True
    logger.info("=== Mukthi Guru Backend Ready ===")


# === Lifespan (startup/shutdown) ===


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Starting Mukthi Guru Backend ===")

    # 1. Initialize telemetry DB (Supabase — single operational DB)
    await init_telemetry_db()

    # 2. Create service container (fast, synchronous — no network calls beyond Qdrant handshake)
    startup()
    container = get_container()
    from app import dependencies as app_dependencies

    app_dependencies.startup_complete = False
    app_dependencies.startup_error = None

    # Validate release manifest readiness
    from app.release_manifest import get_release_manifest, validate_release_manifest

    validate_release_manifest()
    logger.info(
        "Lifespan: release manifest validated (release_id=%s)", get_release_manifest().release_id
    )

    # Safety assertion: semantic cache similarity floor must not drop below 0.92 in production
    cache_similarity = getattr(settings, "semantic_cache_similarity", 0.92)
    if cache_similarity < 0.92:
        msg = (
            f"semantic_cache_similarity={cache_similarity} is below the 0.92 correctness floor. "
            "Below 0.92 dissimilar queries false-hit and serve incorrect answers."
        )
        logger.error("Startup safety assertion failed: %s", msg)
        if os.environ.get("ENVIRONMENT") != "test":
            raise RuntimeError(msg)

    # Register a global shutdown_scheduler noop so cleanup always works
    def shutdown_scheduler():
        return None

    # 3. Initialize LightRAG inline with timeout (critical for answer quality)
    try:
        logger.info("Lifespan: initializing LightRAG (timeout 120s)...")
        await asyncio.wait_for(container.lightrag.initialize(), timeout=120)
        logger.info("Lifespan: LightRAG initialized")
    except TimeoutError:
        logger.warning("Lifespan: LightRAG init timed out — degraded mode")
    except Exception as e:
        logger.warning(f"Lifespan: LightRAG init failed — {e}")

    # Wire NodeObservers (sync, fast)
    _register_node_observers()

    # 4. Run remaining background init inline with timeout
    # The start_railway.py wrapper returns 200 for /api/healthz for 90s
    # so Railway won't kill us during init. The /api/health endpoint returns
    # ready:false until startup_complete=True at the end of this block.
    try:
        await asyncio.wait_for(_background_startup_body(container, app), timeout=180)
    except TimeoutError:
        logger.warning("Background init timed out after 180s")
        app_dependencies.startup_error = "Background init timed out"
    except Exception as e:
        logger.warning(f"Background init failed: {e}")
        app_dependencies.startup_error = str(e)

    # YIELD NOW — Railway health check can reach /api/health
    logger.info("=== Server accepting requests ===")
    yield

    logger.info("Shutting down — waiting for in-flight requests (R3 graceful drain)...")
    drain_waited = 0.0
    while _INFLIGHT > 0 and drain_waited < _DRAIN_TIMEOUT_S:
        await asyncio.sleep(0.25)
        drain_waited += 0.25
    if _INFLIGHT > 0:
        logger.warning(
            f"Graceful drain timeout after {_DRAIN_TIMEOUT_S}s — {_INFLIGHT} request(s) still active"
        )
    else:
        logger.info(f"Graceful drain complete in {drain_waited:.1f}s")

    try:
        scheduler_shutdown = getattr(app.state, "scheduler_shutdown", None) or shutdown_scheduler
        if callable(scheduler_shutdown):
            scheduler_shutdown()
    except Exception as e:
        logger.warning(f"Scheduler shutdown error: {e}")

    telemetry_worker.stop()

    try:
        from services.config_watcher import stop_config_watcher

        await stop_config_watcher()
    except Exception as e:
        logger.warning(f"Config watcher shutdown error: {e}")

    if getattr(container, "job_queue", None) and getattr(container.job_queue, "_running", False):
        try:
            await container.job_queue.stop()
            logger.info("JobQueue workers stopped")
        except Exception as e:
            logger.warning(f"JobQueue shutdown error: {e}")

    if getattr(container, "llm_queue", None):
        try:
            await container.llm_queue.stop()
            logger.info("LLMQueue stopped")
        except Exception as e:
            logger.warning(f"LLMQueue shutdown error: {e}")

    if getattr(container, "request_queue", None):
        try:
            await container.request_queue.stop()
            logger.info("RequestQueue stopped")
        except Exception as e:
            logger.warning(f"RequestQueue shutdown error: {e}")

    try:
        lightrag = getattr(container, "lightrag", None)
        rag = getattr(lightrag, "rag", None)
        finalize_storages = getattr(rag, "finalize_storages", None)
        if callable(finalize_storages):
            await finalize_storages()
            logger.info("Lifespan: LightRAG storages finalized")
    except Exception as exc:
        logger.warning("LightRAG shutdown cleanup error: %s", exc)
    try:
        memory_service = getattr(container, "memory_service", None)
        close_memory = getattr(memory_service, "close", None)
        if callable(close_memory):
            await close_memory()
            logger.info("Lifespan: MemoryServiceV2 closed")
    except Exception as exc:
        logger.warning("MemoryServiceV2 shutdown cleanup error: %s", exc)

    await async_shutdown()


# === App Creation ===

# Gate Swagger docs in production to avoid exposing the full API schema.
_docs_url = "/docs" if (not settings.is_production or settings.show_swagger) else None
_redoc_url = "/redoc" if (not settings.is_production or settings.show_swagger) else None
_openapi_url = "/openapi.json" if (not settings.is_production or settings.show_swagger) else None

app = FastAPI(
    title="Mukthi Guru API",
    description="AI Spiritual Guide — Sri Preethaji & Sri Krishnaji's teachings",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# Trusted Host — validate Host header (only in production)
if settings.is_production:
    _allowed = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
    # Railway health checker uses *.railway.app hostnames — always allow them
    _allowed.extend(["localhost", "127.0.0.1", ".railway.app", "healthcheck.railway.app"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed)

# CORS — allow frontend origins (enforcing explicit allowlist and secure headers in production)
cors_origins = settings.cors_origins_list


def _build_origin_regex(origins: list[str]) -> str | None:
    """Build a regex for wildcard origins, leaving all other metacharacters literal."""
    wildcard_patterns = []
    for origin in origins:
        if "*" not in origin:
            continue
        escaped = re.escape(origin)
        # re.escape turns '*' into '\*'; replace the escaped wildcard with a
        # subdomain-segment matcher so '*.example.com' matches 'app.example.com'.
        pattern = escaped.replace(r"\*", r"[^/]+")
        wildcard_patterns.append(pattern)
    return "|".join(wildcard_patterns) if wildcard_patterns else None


if settings.is_production:
    # In production, strictly enforce explicit origins (no wildcard origins with credentials)
    cors_origins_exact = [o for o in cors_origins if o != "*" and "*" not in o]
    cors_origins_regex = _build_origin_regex(cors_origins)
    if len(cors_origins_exact) < len(cors_origins):
        removed = [o for o in cors_origins if o == "*" or "*" in o]
        logger.warning(
            "CORS wildcard origins removed in production: %s",
            removed,
        )
    if not cors_origins_exact:
        logger.warning(
            "CORS exact-origins allowlist is empty in production; requests from browsers may be blocked.",
        )
    cors_allow_headers = [
        "Authorization",
        "Content-Type",
        "X-Session-Id",
        "X-Correlation-Id",
        "Idempotency-Key",
    ]
else:
    cors_origins_exact = [o for o in cors_origins if "*" not in o]
    cors_origins_regex = _build_origin_regex(cors_origins)
    cors_allow_headers = [
        "Authorization",
        "Content-Type",
        "X-Session-Id",
        "X-Correlation-Id",
        "Idempotency-Key",
        "X-Test-Key",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_exact,
    allow_origin_regex=cors_origins_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=cors_allow_headers,
)


# Correlation ID middleware — generates UUID per request
class CorrelationIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        cid = None
        for k, v in headers:
            if k.lower() == b"x-correlation-id":
                cid = v.decode("utf-8")
                break
        if not cid:
            cid = str(uuid.uuid4())[:8]

        correlation_id_var.set(cid)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                msg_headers = list(message.get("headers", []))
                msg_headers.append((b"x-correlation-id", cid.encode("utf-8")))
                message["headers"] = msg_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


if settings.enable_correlation_ids:
    app.add_middleware(CorrelationIDMiddleware)

# ── Security Headers Middleware (auto-added by security_audit.py) ──
# CSP is generated per-request with a fresh nonce so 'unsafe-inline' is not needed.
_SECURITY_HEADERS_STATIC = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-XSS-Protection": "1; mode=block",
}


class SecurityHeadersMiddleware:
    """Adds OWASP-recommended security headers to every response.
    Generates a per-request nonce for the Content-Security-Policy."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        nonce = secrets.token_urlsafe(16)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                msg_headers = list(message.get("headers", []))
                msg_headers.extend(
                    (name.lower().encode("ascii"), value.encode("utf-8"))
                    for name, value in _SECURITY_HEADERS_STATIC.items()
                )
                csp = build_csp(nonce)
                msg_headers.append((b"content-security-policy", csp.encode("utf-8")))
                message["headers"] = msg_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)

# ── Distributed rate limiters (Redis-backed sliding window) ──
# Falls back to process-local TTLRateLimiter automatically if Redis is unavailable.
# Replaces former ExponentialBackoffRateLimiter + TTLRateLimiter (process-local, audit P0-6).
_redis_url_for_rl = (
    settings.redis_url
    if (settings.redis_url and settings.redis_url.startswith(("redis://", "rediss://", "unix://")))
    else None
)

if _redis_url_for_rl:
    _AUTH_RATE_LIMITER = RedisBackedRateLimiter(
        redis_url=_redis_url_for_rl,
        ttl=60.0,
        max_requests=5,
        backoff_base=settings.auth_backoff_base_seconds,
        backoff_multiplier=settings.auth_backoff_multiplier,
    )
    _ADMIN_RATE_LIMITER = RedisBackedRateLimiter(
        redis_url=_redis_url_for_rl,
        ttl=60.0,
        max_requests=int(settings.admin_rate_limit.split("/")[0]),
    )
    logger.info("Auth/Admin rate limiters: Redis-backed distributed sliding window")
else:
    # No Redis configured — fall back to process-local limiters (acceptable for single-worker dev)
    _AUTH_RATE_LIMITER = ExponentialBackoffRateLimiter(
        ttl=60.0,
        max_requests=5,
        backoff_base=settings.auth_backoff_base_seconds,
        backoff_multiplier=settings.auth_backoff_multiplier,
    )
    _ADMIN_RATE_LIMITER = TTLRateLimiter(
        ttl=60.0, max_requests=int(settings.admin_rate_limit.split("/")[0])
    )
    logger.warning(
        "Auth/Admin rate limiters: process-local (Redis not configured) — not safe for multi-worker deploy"
    )


# Auth endpoint rate limiter middleware — tight limits on login/reset/register
_AUTH_LIMIT_PATHS: frozenset[str] = frozenset(
    {
        "/api/auth/jwt/login",
        "/api/auth/register",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
    }
)


@app.middleware("http")
async def auth_rate_limit_middleware(request: Request, call_next):
    if request.method == "POST" and request.url.path in _AUTH_LIMIT_PATHS:
        client_ip = request.client.host if request.client else "unknown"
        ip_key = f"auth_rl:ip:{request.url.path}:{client_ip}"

        ip_allowed, ip_retry_after = _AUTH_RATE_LIMITER.is_allowed(ip_key)
        if not ip_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": "Auth rate limit exceeded. Try again later.",
                },
                headers={"Retry-After": str(int(ip_retry_after))},
            )

        acct_key = None
        try:
            body = await request.json()
            email = body.get("email") or body.get("username") or ""
            if email:
                acct_key = f"auth_rl:acct:{email}"
                acct_allowed, acct_retry_after = _AUTH_RATE_LIMITER.is_allowed(acct_key)
                if not acct_allowed:
                    _AUTH_RATE_LIMITER.record_attempt(ip_key, success=False)
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "Too Many Requests",
                            "message": "Too many login attempts for this account. Try again later.",
                        },
                        headers={"Retry-After": str(int(acct_retry_after))},
                    )
        except (json.JSONDecodeError, RuntimeError):
            pass

        resp = await call_next(request)

        success = resp.status_code < 400
        _AUTH_RATE_LIMITER.record_attempt(ip_key, success=success)
        if acct_key is not None:
            _AUTH_RATE_LIMITER.record_attempt(acct_key, success=success)
        return resp
    return await call_next(request)


# Admin endpoint rate limiter — tighter limits to prevent admin API abuse
_ADMIN_LIMIT_PATH = "/api/admin/"


@app.middleware("http")
async def admin_rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith(_ADMIN_LIMIT_PATH):
        client_ip = request.client.host if request.client else "unknown"
        key = f"admin_rl:{client_ip}"
        result = _ADMIN_RATE_LIMITER.is_allowed(key)
        # RedisBackedRateLimiter returns (allowed, retry_after); TTLRateLimiter returns bool.
        allowed = result[0] if isinstance(result, tuple) else result
        retry_after = result[1] if isinstance(result, tuple) else 60
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": "Admin rate limit exceeded. Try again later.",
                },
                headers={"Retry-After": str(int(retry_after))},
            )
    return await call_next(request)


# Token-bucket rate limiter for /api/chat (only when Redis is configured)
from app.middleware.rate_limit import TokenBucketMiddleware

if settings.redis_url and settings.redis_url.startswith(("redis://", "rediss://", "unix://")):
    app.add_middleware(
        TokenBucketMiddleware, redis_url=settings.redis_url, capacity=20, refill_per_sec=20 / 60
    )

# Audit logging middleware — logs method, path, status, duration for all requests
from app.middleware.audit import AuditLogMiddleware

app.add_middleware(AuditLogMiddleware)

# Idempotency middleware for mutating endpoints (Phase 3.3)
from app.middleware.idempotency import IdempotencyMiddleware

if settings.redis_url and settings.redis_url.startswith(("redis://", "rediss://", "unix://")):
    app.add_middleware(IdempotencyMiddleware, redis_url=settings.redis_url)


# In-flight tracker middleware for graceful drain (R3)
@app.middleware("http")
async def inflight_tracker(request: Request, call_next):
    """Increment/decrement global in-flight counter for graceful shutdown drain."""
    global _INFLIGHT
    _INFLIGHT += 1
    try:
        return await call_next(request)
    finally:
        _INFLIGHT -= 1


# ── Global request-level timeout middleware ──
# Caps every HTTP request at pipeline_timeout (default 180s).
# Streaming (SSE) paths are excluded — they intentionally hold the connection open.
_STREAMING_PATHS: frozenset[str] = frozenset({"/api/chat/stream"})


@app.middleware("http")
async def request_timeout_middleware(request: Request, call_next):
    """Global request timeout — belt-and-suspenders safety net for all routes."""
    if request.url.path in _STREAMING_PATHS:
        return await call_next(request)
    timeout_val: float = float(getattr(settings, "pipeline_timeout", 180))
    try:
        return await asyncio.wait_for(call_next(request), timeout=timeout_val)
    except TimeoutError:
        logger.error(
            f"Global request timeout ({timeout_val:.0f}s) on {request.method} {request.url.path}"
        )
        REQUEST_COUNT.labels(status="timeout").inc()
        return JSONResponse(
            status_code=504,
            content={
                "error": "Gateway Timeout",
                "message": "The request took too long to process. Please try again.",
            },
        )


# SlowAPI limiter wiring
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global error boundary catching all unhandled exceptions."""
    error_id = f"err_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    logger.error(
        f"Unhandled server error on {request.url.path} (error_id: {error_id}): {exc}", exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "An internal error occurred",
            "message": "We encountered an issue processing your request. Please try again.",
            "error_id": error_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    safe_errors = []
    for err in exc.errors():
        safe_err = {k: v for k, v in err.items() if k != "input"}
        safe_errors.append(safe_err)
    logger.warning(f"Validation error on {request.url.path}: {safe_errors}")
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "message": "Invalid request data."},
    )


# === Routers ===

app.include_router(auth_router, prefix="/api/auth")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(feedback_router, prefix="/api")
app.include_router(health_router, prefix="")
app.include_router(capabilities_router, prefix="/api")
app.include_router(cache_metrics_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(assistants_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")
app.include_router(speech_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(teachings_router, prefix="/api")
app.include_router(support_router, prefix="/api")
app.include_router(waitlist_router, prefix="/api")
app.include_router(notebooks_router, prefix="/api")
app.include_router(srs_router, prefix="/api")
app.include_router(push_router, prefix="/api")
app.include_router(cancel_flow_router, prefix="/api")
app.include_router(compliance_router)
app.include_router(retention_router)
app.include_router(metrics_router)
app.include_router(healing_course_router)
from app.api.kg import router as kg_router

app.include_router(kg_router, prefix="/api")

from app.api.second_brain import router as second_brain_router

app.include_router(second_brain_router, prefix="/api")

from app.api.job_routes import router as job_router

app.include_router(job_router)

# Mount trace dashboard routes
from app.trace_dashboard import router as trace_router

app.include_router(trace_router)

from app.api.search_routes import router as search_router

app.include_router(search_router)


@app.get("/.well-known/jwks.json", tags=["auth"])
async def get_jwks():
    from services.auth_service import get_jwks_dict

    return get_jwks_dict()


# === Mount Ingestion UI ===

# Try to find the directory (Docker vs Local/Colab)
ui_possible_paths = [
    Path("/app/ingest-ui"),  # Docker (absolute)
    Path("ingest-ui"),  # Local (relative to CWD)
    Path("../ingest-ui"),  # Colab/Dev (relative to CWD backend/)
]

ui_path = None
for p in ui_possible_paths:
    if p.exists():
        ui_path = p
        break

if ui_path:
    app.mount("/static-ingest", StaticFiles(directory=str(ui_path), html=True), name="ingest")
    logger.info(f"✅ Ingestion UI mounted at /static-ingest (from {ui_path})")
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
    app.mount("/static-chat", StaticFiles(directory=str(chat_ui_path), html=True), name="chat")
    logger.info(f"✅ Premium Chat UI mounted at /static-chat (from {chat_ui_path})")
else:
    logger.warning("⚠️ Chat UI directory not found.")

# === Mount Gradio UI (gated; disabled by default in production) ===
if os.getenv("ENABLE_GRADIO_UI", "false").lower() in ("1", "true", "yes"):
    try:
        import gradio as gr

        from app.gradio_ui import create_demo

        _gradio_user = os.getenv("GRADIO_USER")
        _gradio_pass = os.getenv("GRADIO_PASS")
        _auth = (_gradio_user, _gradio_pass) if _gradio_user and _gradio_pass else None
        if _auth is None:
            logger.warning(
                "Gradio UI enabled without GRADIO_USER/GRADIO_PASS — refusing to mount unauthenticated UI."
            )
        else:
            gr.mount_gradio_app(app, create_demo(), path="/ui", auth=_auth)
            logger.info("✅ Gradio Chat UI mounted at /ui (basic auth enabled)")
    except Exception as e:
        logger.warning(f"Failed to mount Gradio UI: {e}")
else:
    logger.info("Gradio UI disabled (set ENABLE_GRADIO_UI=true to enable)")


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
