"""
Mukthi Guru — Prometheus Metrics (Production Observability)

Tracks key metrics for monitoring the health and performance of:
  - Overall request pipeline (latency, count, errors)
  - LLM calls (per model, per operation, tokens consumed)
  - RAG pipeline stages (retrieval, reranking, grading, generation, verification)
  - Emotional intelligence (distress detections by severity)
  - Caching (hit rates for both exact and semantic caches)

Endpoint: GET /api/metrics → Prometheus text format
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# ===================================================================
# Request-Level Metrics
# ===================================================================

REQUEST_LATENCY = Histogram(
    "guru_request_latency_seconds",
    "Full end-to-end request latency",
    ["stage"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120],
)

# E3.3: TTFT histogram — time to first token for streaming responses (seconds).
# Distinct from REQUEST_LATENCY (full e2e) so TTFT can be observed independently.
TTFT_SECONDS = Histogram(
    "guru_ttft_seconds",
    "Time to first token (streaming) in seconds",
    ["provider"],
    buckets=[0.05, 0.1, 0.25, 0.5, 0.75, 1, 2, 3, 5, 10],
)

REQUEST_COUNT = Counter(
    "guru_requests_total",
    "Total requests by status",
    ["status"],
)

# ===================================================================
# SLO metrics (P1-OPS-1) — feed the alerting rules in
# infrastructure/prometheus/alerting-rules.yml
# ===================================================================

SLO_CHAT_LATENCY = Histogram(
    "slo_latency_seconds",
    "Chat request latency time-to-completion by tier (per-tier SLOs in SLO_THRESHOLDS)",
    ["tier"],  # fast | standard | hindi | cold | comparative | deep | fallback
    buckets=[0.5, 1, 2, 3, 4, 8, 12, 20, 25, 30, 65],
)

# A3 per-tier SLO thresholds (seconds, p95) derived from
# backend/benchmarks/reports/isolated_latency_2026-09-06.json (n=35):
#   fast/casual 0.02-0.03, distress 0.02-0.10, meditation 0.04-0.08,
#   off-topic 0.03 -> fast 1s (headroom over p100 0.10s)
#   doctrine-direct warm 1.48-2.08 (7/8 reps), doctrine-colloquial warm
#   1.8/2.78 -> standard 3s
#   hindi 9.65-10.79 (p100 10.79s) -> hindi 12s
#   doctrine-direct cold 15.65, doctrine-colloquial cold 7.59,
#   four-secrets 1.58/3.49/20.93, multi-teacher 5.7-9.41 -> cold 25s
#   comparative 14.67/15.38/64.74 (p100 64.74s) -> comparative 65s
# deep/fallback keep 30s (legacy single-8s SLO retired; le="8.0" bucket kept
# for alert-rule continuity during migration).
SLO_THRESHOLDS = {
    "fast": 1.0,
    "standard": 3.0,
    "hindi": 12.0,
    "cold": 25.0,
    "comparative": 65.0,
    "deep": 30.0,
    "fallback": 30.0,
}

SLO_TIERS = tuple(SLO_THRESHOLDS)


def observe_slo_latency(tier, seconds):
    """Observe whole-request wall time on SLO_CHAT_LATENCY.

    Call at the single point where whole-request wall time is known
    (PipelineCoordinator.execute, after latency_ms is final, cache-hit
    patched). Unknown/empty tiers normalize to "standard" so burn-rate
    queries never fragment on unbounded labels.
    """
    label = tier if tier in SLO_THRESHOLDS else "standard"
    SLO_CHAT_LATENCY.labels(tier=label).observe(max(0.0, float(seconds)))

HEALTH_CHECK_TOTAL = Counter(
    "health_check_total",
    "Total /api/health readiness probe results (SLO: ready > 99.5%)",
    ["result"],  # ready | not_ready
)

# A silently-failing telemetry sink is worse than a loud one: the hallucination
# anomaly job (scripts/ops/hallucination_anomaly.py) reads the rows this writes,
# so an empty table reads as "no hallucinations" rather than "no data". Counted
# so an alert can fire on the write path, not just the read path.
# §11 fallback visibility: nothing counted how often an answer left the pipeline
# as a fallback rather than a synthesized answer, so "fallback fires constantly"
# was only ever visible by reading logs one request at a time.
ANSWER_ROUTE_TOTAL = Counter(
    "answer_route_total",
    "Final answers by route and grounding outcome",
    ["route", "grounding_state"],
)

TELEMETRY_SINK_WRITES = Counter(
    "telemetry_sink_writes_total",
    "Telemetry sink write attempts by outcome",
    ["outcome"],  # ok | error
)

# ===================================================================
# Service-Level Prometheus Metrics (Unit 13)
# ===================================================================

# (A4 removed: RAG_LATENCY dead — no callsite; per-node latency lives in
# PIPELINE_STAGE_LATENCY which IS wired via rag/nodes/utils.log_metrics.)
# (A4 removed: LLM_REQUEST_DURATION dead — superseded by LLM_LATENCY
# + observe_llm_latency helper above.)

RETRIEVAL_LATENCY = Histogram(
    "retrieval_latency_seconds",
    "Vector DB retrieval latency",
    ["source"],  # qdrant, lightrag, fallback
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
)

GUARDRAILS_BLOCKED = Counter(
    "guardrails_blocked_total",
    "Messages blocked by guardrails",
    ["rail"],  # input / output
)

# Fires when the configured guardrails provider (e.g. nemo) fails to construct
# and the chain silently drops to a weaker active provider. Config advertises
# one posture; runtime delivers another. Without this counter the degradation
# is invisible — INFO logs get lost and health only reports the active provider.
GUARDRAILS_PROVIDER_DEGRADED = Counter(
    "guardrails_provider_degraded_total",
    "Guardrails ran a weaker provider than configured (construction fallback)",
    ["configured", "active"],
)

# MemoryServiceV2 falls back to a bounded in-memory LRU when Redis is down. Without
# this counter there is no way to tell thrashing (hot entries evicted before they are
# read) from a healthy cache, so _LRU_MAX_SIZE can never be tuned on evidence.
MEMORY_LRU_EVICTIONS = Counter(
    "memory_lru_evictions_total",
    "Entries evicted from the MemoryServiceV2 in-memory LRU fallback",
)

# ===================================================================
# LLM-Specific Metrics
# ===================================================================

LLM_LATENCY = Histogram(
    "guru_llm_latency_seconds",
    "LLM API call latency per model and operation",
    ["model", "operation"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

LLM_TOKENS = Counter(
    "guru_llm_tokens_total",
    "Total tokens consumed per model",
    ["model"],
)

LLM_ERRORS = Counter(
    "guru_llm_errors_total",
    "LLM API call errors per model",
    ["model", "error_type"],
)

# ===================================================================
# RAG Pipeline Stage Metrics
# ===================================================================

PIPELINE_STAGE_LATENCY = Histogram(
    "guru_pipeline_stage_latency_seconds",
    "Latency per RAG pipeline stage",
    ["stage"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)

# (A4 removed: RETRIEVAL_DOCS_COUNT dead — no callsite.)
# (A4 removed: RERANKER_SCORES dead — no callsite.)

RETRIEVAL_RELEVANCE_RATIO = Gauge(
    "guru_retrieval_relevance_ratio",
    "Ratio of relevant docs to total retrieved docs (precision proxy)",
)

# ===================================================================
# Emotional Intelligence Metrics
# ===================================================================

DISTRESS_DETECTIONS = Counter(
    "guru_distress_detections_total",
    "Distress detections by severity level",
    ["level"],
)

CONTRADICTION_DETECTIONS = Counter(
    "guru_contradiction_detections_total",
    "Total contradictions detected in the conversation history",
)


# ===================================================================
# Circuit Breaker Metrics
# ===================================================================

CIRCUIT_BREAKER_STATE_CHANGES = Counter(
    "guru_circuit_breaker_state_changes_total",
    "Circuit breaker state transitions",
    ["provider", "from_state", "to_state", "reason"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "guru_circuit_breaker_state",
    "Current circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["provider"],
)

CIRCUIT_BREAKER_FAILURES = Gauge(
    "guru_circuit_breaker_failures",
    "Current consecutive failures count",
    ["provider"],
)

# ===================================================================
# Cache Metrics
# ===================================================================

CACHE_OPERATIONS = Counter(
    "guru_cache_operations_total",
    "Cache operations by type and result",
    ["cache_type", "result"],  # cache_type: hot|exact|semantic, result: hit|miss
)

CACHE_HIT_RATIO = Gauge(
    "guru_cache_hit_ratio",
    "Current cache hit ratio",
    ["cache_type"],
)


# A4 wiring helpers — one-liner contracts so provider/retrieval/cache lanes
# can wire without touching this lane's files. Each helper references its
# collector so the wire is real, not a stub.
#   LLM call sites: services/openrouter_service.py, sarvam_service.py,
#     ollama_service.py (wrap generate/classify wall time; except path records)
#   Retrieval call sites: rag/nodes/retrieval.py vector/graph fetch,
#     services/qdrant client search (wrap wall time per source label)
#   Cache call sites: services/cache/* adapters + CacheCheckStage
#     (set ratio after hit/miss window; CACHE_OPERATIONS stays the counter)
def observe_llm_latency(model, operation, seconds):
    """Record LLM wall time. Call around each provider generate/classify."""
    LLM_LATENCY.labels(model=model, operation=operation).observe(max(0.0, float(seconds)))


def record_llm_error(model, error_type):
    """Count an LLM failure. Call on provider exception/timeout alongside."""
    LLM_ERRORS.labels(model=model, error_type=error_type).inc()


def observe_retrieval_latency(source, seconds):
    """Record vector/graph retrieval wall time per source label."""
    RETRIEVAL_LATENCY.labels(source=source).observe(max(0.0, float(seconds)))


def set_cache_hit_ratio(cache_type, ratio):
    """Set current cache hit ratio in [0, 1] per cache_type."""
    clamped = min(1.0, max(0.0, float(ratio)))
    CACHE_HIT_RATIO.labels(cache_type=cache_type).set(clamped)

# Namespace-aware Redis growth controls. Labels are fixed application namespaces,
# never user- or tenant-derived, so telemetry cardinality stays bounded.
REDIS_NAMESPACE_KEYS = Gauge(
    "guru_redis_namespace_keys",
    "Approximate Redis key cardinality for a monitored query-cache namespace",
    ["namespace"],
)

REDIS_NAMESPACE_NONEXPIRING_KEYS = Gauge(
    "guru_redis_namespace_nonexpiring_keys",
    "Redis query-cache keys with no TTL in a monitored namespace",
    ["namespace"],
)

REDIS_CACHE_BUDGET_REJECTIONS = Counter(
    "guru_redis_cache_budget_rejections_total",
    "Query-cache writes rejected after the namespace key budget was reached",
    ["namespace"],
)

# ===================================================================
# P90/P99 Hybrid Search Metrics (Phase 1.1)
# ===================================================================

SEARCH_PATH_TOTAL = Counter(
    "guru_search_path_total",
    "Requests routed to each search path",
    ["path"],  # p90, p99
)

SEARCH_LATENCY_MS = Histogram(
    "guru_search_latency_ms",
    "Search latency per path in ms",
    ["path"],  # p90, p99
    buckets=[5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000],
)

# ===================================================================
# Node Error / Fallback Metrics (Phase 2.2)
# ===================================================================

NODE_ERROR_TOTAL = Counter(
    "guru_node_error_total",
    "Node execution errors by node name",
    ["node"],
)

NODE_FALLBACK_TOTAL = Counter(
    "guru_node_fallback_total",
    "Node fallback activations by node name",
    ["node"],
)

# ===================================================================
# Embedding Cache Metrics (Phase 1.3)
# ===================================================================

EMBEDDING_CACHE_OPS = Counter(
    "guru_embedding_cache_ops_total",
    "Embedding cache operations by result",
    ["result"],  # hit, miss
)

EMBEDDING_CACHE_SIZE = Gauge(
    "guru_embedding_cache_size",
    "Current size of the embedding LRU cache",
)

EMBEDDING_LATENCY = Histogram(
    "guru_embedding_latency_seconds",
    "Embedding encode latency per operation",
    ["operation"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
)

EMBEDDING_ERRORS = Counter(
    "guru_embedding_errors_total",
    "Embedding operation errors by operation type",
    ["operation"],
)

EMBEDDING_MODEL_FALLBACK = Counter(
    "guru_embedding_model_fallback_total",
    "Embedding model fallback activations",
    ["from_model", "to_model"],
)

# ===================================================================
# Dependency Health Metrics (Phase 2.4)
# ===================================================================

DEPENDENCY_HEALTH = Gauge(
    "guru_dependency_health",
    "Dependency health status (0=unhealthy, 1=healthy)",
    ["name"],  # qdrant, redis, supabase, openrouter, sarvam
)

DEPENDENCY_PHI = Gauge(
    "guru_dependency_phi",
    "Dependency φ-Accural failure detector value",
    ["name"],
)

# ===================================================================
# Context Compression Metrics (Phase 3.2)
# ===================================================================

CONTEXT_COMPRESSION_RATIO = Histogram(
    "guru_context_compression_ratio",
    "Context compression ratio (chunks after / chunks before)",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ===================================================================
# Reranker Metrics (Phase 2.3)
# ===================================================================

# (A4 removed: RERANK_LATENCY_MS / RERANK_METHOD / RERANK_DOCS_COUNT dead —
# no callsites; rerank path currently uninstrumented by design.)

# (A4 removed: NODE_LATENCY_MS dead — superseded by PIPELINE_STAGE_LATENCY.)

# (A4 removed: SEARCH_CONFIDENCE_SCORE dead — no callsite.)

# (A4 removed: SEMANTIC_CACHE_LOOKUP_LATENCY dead — no callsite; cache
# latency lives in SEARCH_LATENCY_MS which IS observed in pipeline_coordinator.)

# ===================================================================
# Idempotency Metrics (Phase 3.3)
# ===================================================================

IDEMPOTENCY_CACHE_HIT_TOTAL = Counter(
    "guru_idempotency_cache_hit_total",
    "Idempotency cache hits",
)

IDEMPOTENCY_CACHE_MISS_TOTAL = Counter(
    "guru_idempotency_cache_miss_total",
    "Idempotency cache misses",
)

# (A4 removed: IDEMPOTENCY_KEY_COLLISIONS_TOTAL dead — hit/miss counters
# in middleware/idempotency.py are the wired signal.)

# ===================================================================
# Context Compression Extras (Phase 3.2)
# ===================================================================

CONTEXT_CHUNKS_BEFORE = Gauge(
    "guru_context_chunks_before",
    "Chunks before compression",
)

CONTEXT_CHUNKS_AFTER = Gauge(
    "guru_context_chunks_after",
    "Chunks after compression",
)

CONTEXT_TOKENS_SAVED = Gauge(
    "guru_context_tokens_saved",
    "Tokens saved by compression",
)

# ===================================================================
# Generation Metrics (Phase 2.1)
# ===================================================================

GENERATION_TEMPERATURE = Gauge(
    "guru_generation_temperature",
    "Generation temperature per strategy",
    ["strategy"],  # fast, standard, deep
)

GENERATION_TOP_K = Gauge(
    "guru_generation_top_k",
    "Generation top_k per strategy",
    ["strategy"],
)

# ===================================================================
# Verification Metrics
# ===================================================================

VERIFICATION_RESULTS = Counter(
    "guru_verification_results_total",
    "Self-RAG verification results",
    ["result"],  # faithful|hallucinated|soft_pass|rejected
)

ANSWER_ACCEPTED_UNVERIFIED = Counter(
    "guru_answer_accepted_unverified_total",
    "Answers accepted by format_final_answer while the faithfulness "
    "verifier wrote no verdict (is_faithful is None). Target: 0 — a cited "
    "answer may be accepted pending verification, but one accepted with "
    "citations_verified=False is rejected and must never reach this counter.",
)

CONFIDENCE_SCORES = Histogram(
    "guru_confidence_score",
    "Distribution of answer confidence scores",
    buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
)

FAITHFULNESS_SCORE = Histogram(
    "guru_faithfulness_score",
    "Graded faithfulness score (0-1)",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

RELEVANCY_SCORE = Histogram(
    "guru_relevancy_score",
    "Graded answer relevancy score (0-1)",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)


# ===================================================================
# Retrieval Quality & Coverage Metrics (Ingestion Audit Plan)
# ===================================================================

RETRIEVAL_SCORE_HISTOGRAM = Histogram(
    "guru_retrieval_score",
    "Distribution of raw retrieval cosine scores (pre-rerank) — used to detect coverage gaps",
    ["source"],  # qdrant, lightrag, okf, web
    buckets=[0.0, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 0.70, 1.0],
)

COVERAGE_GAP_TOTAL = Counter(
    "guru_coverage_gap_total",
    "Times ALL retrieved docs scored below coverage_gap threshold → web search triggered",
    ["intent"],
)

# (A4 removed: WEB_SEARCH_HIT/MISS_TOTAL dead — no callsites; coverage-gap
# signal lives in COVERAGE_GAP_TOTAL which IS observed in retrieval.py.)

# (A4 removed: TOKEN_BUDGET_EXCEED_TOTAL dead — no callsite.)

# (A4 removed: LIGHTRAG_TIMEOUT_TOTAL dead — no callsite.)


def metrics_endpoint():
    """Expose Prometheus metrics in text format."""
    return generate_latest(), CONTENT_TYPE_LATEST


# ===================================================================
# Runtime capacity and provider-accounting metrics (P0 launch gate)
# ===================================================================
PROCESS_RSS_BYTES = Gauge(
    "guru_process_rss_bytes",
    "Current resident memory observed by the backend process",
)
PROCESS_CPU_SECONDS = Gauge(
    "guru_process_cpu_seconds",
    "Cumulative user plus system CPU seconds consumed by the backend process",
)
REQUEST_CPU_SECONDS = Histogram(
    "guru_request_cpu_seconds",
    "CPU seconds consumed per completed HTTP request",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5],
)
QUEUE_DEPTH = Gauge(
    "guru_queue_depth",
    "Queued work depth by bounded priority class",
    ["priority"],
)
PROVIDER_REPORTED_COST_USD = Counter(
    "guru_provider_reported_cost_usd_total",
    "Actual non-negative cost reported by an LLM provider",
    ["provider"],
)

OPENROUTER_COST_UNKNOWN_TOTAL = Counter(
    "guru_openrouter_cost_unknown_total",
    "OpenRouter responses without provider cost or a known fallback rate",
    ["model", "operation"],
)

OPENROUTER_ESTIMATED_COST_USD = Counter(
    "guru_openrouter_estimated_cost_usd_total",
    "Fallback-estimated OpenRouter cost when provider cost is absent",
    ["model", "operation"],
)

OPENROUTER_CACHED_TOKENS_TOTAL = Counter(
    "guru_openrouter_cached_tokens_total",
    "Prompt tokens read from OpenRouter provider caches",
    ["model", "operation"],
)

OPENROUTER_CACHE_WRITE_TOKENS_TOTAL = Counter(
    "guru_openrouter_cache_write_tokens_total",
    "Prompt tokens written to OpenRouter provider caches",
    ["model", "operation"],
)

ANON_QUOTA_DEGRADED_MODE = Counter(
    "anon_quota_degraded_mode_total",
    "Total anonymous quota operations processed in degraded in-memory mode due to Redis outage/failure",
    ["event"],
)

INGEST_QUALITY_GATE_REJECTIONS_TOTAL = Counter(
    "ingest_quality_gate_rejections_total",
    "Total count of ingestion items rejected by data quality gate",
    ["reason", "tier"],
)


if __name__ == "__main__":
    for _tier, _th in sorted(SLO_THRESHOLDS.items()):
        assert isinstance(_th, (int, float)) and _th > 0, _tier
    observe_slo_latency("fast", 0.05)
    observe_slo_latency("bogus-tier", 0.05)
    observe_llm_latency("test/model", "generate", 0.1)
    record_llm_error("test/model", "timeout")
    observe_retrieval_latency("qdrant", 0.05)
    set_cache_hit_ratio("exact", 0.5)
    print("metrics self-check ok:", len(SLO_THRESHOLDS), "tiers")
