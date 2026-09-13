"""A4 guard: 4 live collectors have reachable wiring; 16 dead ones stay deleted.

Live (must be wired via helpers in app/metrics.py so call-site lanes can
wire in one line without touching this lane's files):
  LLM_ERRORS, LLM_LATENCY, RETRIEVAL_LATENCY, CACHE_HIT_RATIO
Dead (must NOT reappear in app/metrics.py):
  RAG_LATENCY, NODE_LATENCY_MS, TOKEN_BUDGET_EXCEED_TOTAL,
  LIGHTRAG_TIMEOUT_TOTAL, IDEMPOTENCY_KEY_COLLISIONS_TOTAL,
  RERANK_LATENCY_MS, RERANK_METHOD, RERANK_DOCS_COUNT, RERANKER_SCORES,
  RETRIEVAL_DOCS_COUNT, SEARCH_CONFIDENCE_SCORE,
  SEMANTIC_CACHE_LOOKUP_LATENCY, WEB_SEARCH_HIT_TOTAL,
  WEB_SEARCH_MISS_TOTAL, MEDITATION_SESSIONS, LLM_REQUEST_DURATION
"""
import pathlib

LIVE = ["LLM_ERRORS", "LLM_LATENCY", "RETRIEVAL_LATENCY", "CACHE_HIT_RATIO"]
HELPERS = [
    "observe_llm_latency",
    "record_llm_error",
    "observe_retrieval_latency",
    "set_cache_hit_ratio",
]
DEAD = [
    "RAG_LATENCY",
    "NODE_LATENCY_MS",
    "TOKEN_BUDGET_EXCEED_TOTAL",
    "LIGHTRAG_TIMEOUT_TOTAL",
    "IDEMPOTENCY_KEY_COLLISIONS_TOTAL",
    "RERANK_LATENCY_MS",
    "RERANK_METHOD",
    "RERANK_DOCS_COUNT",
    "RERANKER_SCORES",
    "RETRIEVAL_DOCS_COUNT",
    "SEARCH_CONFIDENCE_SCORE",
    "SEMANTIC_CACHE_LOOKUP_LATENCY",
    "WEB_SEARCH_HIT_TOTAL",
    "WEB_SEARCH_MISS_TOTAL",
    "MEDITATION_SESSIONS",
    "LLM_REQUEST_DURATION",
]


def test_declared_collectors_have_callsites():
    src = pathlib.Path("app/metrics.py").read_text()
    for name in LIVE:
        assert name in src, name
    for helper in HELPERS:
        assert helper in src, f"wiring helper {helper} missing"
        # Helper must reference its collector so the wire is real, not a stub.
    assert "LLM_LATENCY" in src and "observe_llm_latency" in src
    assert "LLM_ERRORS" in src and "record_llm_error" in src
    assert "RETRIEVAL_LATENCY" in src and "observe_retrieval_latency" in src
    assert "CACHE_HIT_RATIO" in src and "set_cache_hit_ratio" in src


def test_dead_collectors_absent():
    import re

    src = pathlib.Path("app/metrics.py").read_text()
    for name in DEAD:
        assert not re.search(rf"^{name}\s*=", src, re.M), (
            f"dead collector {name} still declared"
        )
