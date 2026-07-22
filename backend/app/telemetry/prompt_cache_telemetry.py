"""Prompt Cache Telemetry Module.

Monitors prompt cache hit efficiency, prefix character overlap, and Time-To-First-Token (TTFT)
metrics across local NIM/vLLM instances and cloud LLM API providers.
"""

from __future__ import annotations

import hashlib
import threading
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Thread lock for safe concurrent access to accumulator
_cache_lock = threading.Lock()

# In-memory metrics accumulator for cache statistics
# NOTE: This accumulator is per-process. For multi-worker deployments,
# aggregate via Prometheus counter/histogram metrics.
_cache_stats: Dict[str, Any] = {
    "total_requests": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "total_cached_tokens": 0,
    "total_input_tokens": 0,
    "last_prefix_hash": None,
    "total_ttft_ms": 0.0,
    "ttft_count": 0,
}


def compute_prompt_prefix_hash(system_prompt: str, context_text: str) -> str:
    """Compute SHA-256 hash of the static system + document context prefix."""
    prefix = f"{system_prompt}\n---\n{context_text}"
    return hashlib.sha256(prefix.encode("utf-8")).hexdigest()


def record_prompt_cache_event(
    provider: str,
    prefix_hash: str,
    cached_tokens: int = 0,
    total_tokens: int = 0,
    ttft_ms: Optional[float] = None,
) -> Dict[str, Any]:
    """Record a prompt invocation event and compute cache hit status."""
    global _cache_stats
    with _cache_lock:
        _cache_stats["total_requests"] += 1
        _cache_stats["total_cached_tokens"] += cached_tokens
        _cache_stats["total_input_tokens"] += total_tokens

        # Hit detection: provider-reported cached_tokens > 0 is the single source of truth
        is_hit = cached_tokens > 0
        if is_hit:
            _cache_stats["cache_hits"] += 1
        else:
            _cache_stats["cache_misses"] += 1

        # Track prefix hash separately for prefix-reuse analysis (independent of hit/miss)
        _cache_stats["last_prefix_hash"] = prefix_hash

        # TTFT tracking: accumulate only when present
        if ttft_ms is not None:
            _cache_stats["total_ttft_ms"] += ttft_ms
            _cache_stats["ttft_count"] += 1

        hit_rate = (
            _cache_stats["cache_hits"] / _cache_stats["total_requests"]
            if _cache_stats["total_requests"] > 0
            else 0.0
        )

    avg_ttft = _cache_stats["total_ttft_ms"] / _cache_stats["ttft_count"] if _cache_stats["ttft_count"] > 0 else None

    logger.info(
        "[PromptCacheTelemetry] provider=%s hit=%s hit_rate=%.2f%% cached_tokens=%d total_tokens=%d ttft=%s",
        provider,
        is_hit,
        hit_rate * 100.0,
        cached_tokens,
        total_tokens,
        f"{ttft_ms:.1f}ms" if ttft_ms is not None else "N/A",
    )

    result = {
        "is_hit": is_hit,
        "hit_rate": hit_rate,
        "prefix_hash": prefix_hash,
        "cached_tokens": cached_tokens,
        "total_tokens": total_tokens,
    }
    if ttft_ms is not None:
        result["ttft_ms"] = ttft_ms

    return result


def get_prompt_cache_stats() -> Dict[str, Any]:
    """Retrieve cumulative prompt cache performance statistics."""
    with _cache_lock:
        total = _cache_stats["total_requests"]
        hits = _cache_stats["cache_hits"]
        ttft_count = _cache_stats["ttft_count"]
        avg_ttft = _cache_stats["total_ttft_ms"] / ttft_count if ttft_count > 0 else None

        result = {
            "total_requests": total,
            "cache_hits": hits,
            "cache_misses": _cache_stats["cache_misses"],
            "hit_rate": (hits / total) if total > 0 else 0.0,
            "total_cached_tokens": _cache_stats["total_cached_tokens"],
            "total_input_tokens": _cache_stats["total_input_tokens"],
        }
        if avg_ttft is not None:
            result["avg_ttft_ms"] = round(avg_ttft, 2)

        return result
