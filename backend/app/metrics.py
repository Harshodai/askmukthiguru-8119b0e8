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
# Service-Level Prometheus Metrics (Unit 13)
# ===================================================================

RAG_LATENCY = Histogram(
    "rag_latency_seconds",
    "RAG pipeline node latency per node (P99 observability)",
    ["node"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60],
)

LLM_REQUEST_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration per provider (sarvam / ollama / krutrim)",
    ["provider"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120],
)

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

RETRIEVAL_DOCS_COUNT = Histogram(
    "guru_retrieval_docs_count",
    "Number of documents retrieved per query",
    ["phase"],
    buckets=[0, 1, 2, 3, 5, 10, 20, 50],
)

RERANKER_SCORES = Histogram(
    "guru_reranker_score",
    "Distribution of reranker scores",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

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

MEDITATION_SESSIONS = Counter(
    "guru_meditation_sessions_total",
    "Total meditation sessions started",
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

RERANK_LATENCY_MS = Histogram(
    "guru_rerank_latency_ms",
    "Rerank latency in ms",
    buckets=[10, 25, 50, 100, 200, 500, 1000, 2000],
)

RERANK_METHOD = Counter(
    "guru_rerank_method",
    "Rerank method used",
    ["method"],  # cross, hybrid
)

RERANK_DOCS_COUNT = Histogram(
    "guru_rerank_docs_count",
    "Number of documents being reranked",
    buckets=[1, 3, 5, 10, 20, 50, 100],
)

# ===================================================================
# Node Latency Metrics (Phase 2.2)
# ===================================================================

NODE_LATENCY_MS = Histogram(
    "guru_node_latency_ms",
    "Node execution latency in ms",
    ["node"],
    buckets=[10, 25, 50, 100, 200, 500, 1000, 2000, 5000, 10000],
)

# ===================================================================
# Search Confidence Metrics (Phase 1.1)
# ===================================================================

SEARCH_CONFIDENCE_SCORE = Histogram(
    "guru_search_confidence_score",
    "Intent confidence score distribution",
    buckets=[0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99],
)

# ===================================================================
# Semantic Cache Metrics (Phase 1.2)
# ===================================================================

SEMANTIC_CACHE_LOOKUP_LATENCY = Histogram(
    "guru_semantic_cache_lookup_latency",
    "Semantic cache lookup latency in ms",
    buckets=[1, 2, 5, 10, 20, 50, 100, 200],
)

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

IDEMPOTENCY_KEY_COLLISIONS_TOTAL = Counter(
    "guru_idempotency_key_collisions_total",
    "Idempotency key collisions",
)

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

WEB_SEARCH_HIT_TOTAL = Counter(
    "guru_web_search_hit_total",
    "Web search calls that returned at least 1 result",
    ["trigger"],  # coverage_gap, zero_docs
)

WEB_SEARCH_MISS_TOTAL = Counter(
    "guru_web_search_miss_total",
    "Web search calls that returned zero results or failed",
    ["reason"],  # empty, error
)

TOKEN_BUDGET_EXCEED_TOTAL = Counter(
    "guru_token_budget_exceed_total",
    "Times token budget soft limit was exceeded during generation",
    ["budget_type"],  # soft, hard
)

LIGHTRAG_TIMEOUT_TOTAL = Counter(
    "guru_lightrag_timeout_total",
    "LightRAG aquery calls that timed out (triggers web search fallback)",
)


def metrics_endpoint():
    """Expose Prometheus metrics in text format."""
    return generate_latest(), CONTENT_TYPE_LATEST

