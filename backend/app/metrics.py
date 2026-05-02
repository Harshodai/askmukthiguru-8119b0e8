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

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# ===================================================================
# Request-Level Metrics
# ===================================================================

REQUEST_LATENCY = Histogram(
    "guru_request_latency_seconds",
    "Full end-to-end request latency",
    ["stage"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120],
)

REQUEST_COUNT = Counter(
    "guru_requests_total",
    "Total requests by status",
    ["status"],
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

# ===================================================================
# Cache Metrics
# ===================================================================

CACHE_OPERATIONS = Counter(
    "guru_cache_operations_total",
    "Cache operations by type and result",
    ["cache_type", "result"],  # cache_type: exact|semantic, result: hit|miss
)

CACHE_HIT_RATIO = Gauge(
    "guru_cache_hit_ratio",
    "Current cache hit ratio",
    ["cache_type"],
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


def metrics_endpoint():
    """Expose Prometheus metrics in text format."""
    return generate_latest(), CONTENT_TYPE_LATEST
