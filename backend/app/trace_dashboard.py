"""
Mukthi Guru — Query Trace Dashboard

Endpoints:
  GET /api/metrics/summary  — High-level pipeline metrics summary (JSON)
  GET /api/trace/<request_id> — Detailed trace for a specific request (JSON)

Trace data is stored in Redis with 24h TTL. Each request generates a trace
containing all pipeline stages with timing, doc counts, and decisions.
"""

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["observability"])

# In-memory trace storage (fallback when Redis unavailable)
_traces: dict = {}
_MAX_TRACES = 100


class TraceCollector:
    """
    Collects trace data for a single request pipeline execution.

    Usage:
        trace = TraceCollector(request_id)
        trace.add_stage("intent_router", duration=1.5, metadata={"intent": "QUERY"})
        trace.add_stage("retrieve", duration=3.2, metadata={"docs": 5})
        trace.finalize()
    """

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.stages: list[dict] = []
        self.start_time = time.time()
        self.metadata: dict = {}

    def add_stage(self, name: str, duration: float, metadata: Optional[dict] = None):
        """Record a pipeline stage completion."""
        self.stages.append({
            "stage": name,
            "duration_ms": round(duration * 1000, 1),
            "timestamp": time.time(),
            **(metadata or {}),
        })

    def set_metadata(self, key: str, value):
        """Set top-level trace metadata."""
        self.metadata[key] = value

    def finalize(self) -> dict:
        """Finalize the trace and return the full trace data."""
        total_duration = time.time() - self.start_time
        trace_data = {
            "request_id": self.request_id,
            "total_duration_ms": round(total_duration * 1000, 1),
            "stages": self.stages,
            "stage_count": len(self.stages),
            "timestamp": self.start_time,
            **self.metadata,
        }

        # Store in memory (capped)
        _traces[self.request_id] = trace_data
        if len(_traces) > _MAX_TRACES:
            oldest_key = min(_traces, key=lambda k: _traces[k]["timestamp"])
            del _traces[oldest_key]

        # Store in Redis if available
        try:
            _store_trace_redis(self.request_id, trace_data)
        except Exception:
            pass  # Redis optional

        return trace_data


def _store_trace_redis(request_id: str, trace_data: dict):
    """Store trace in Redis with 24h TTL."""
    try:
        import redis
        r = redis.from_url(settings.redis_url, decode_responses=True)
        key = f"mukthiguru:trace:{request_id}"
        r.setex(key, 86400, json.dumps(trace_data, default=str))
    except Exception:
        pass


def _get_trace_redis(request_id: str) -> Optional[dict]:
    """Get trace from Redis."""
    try:
        import redis
        r = redis.from_url(settings.redis_url, decode_responses=True)
        key = f"mukthiguru:trace:{request_id}"
        data = r.get(key)
        return json.loads(data) if data else None
    except Exception:
        return None


# ===================================================================
# API Routes
# ===================================================================

@router.get("/trace/{request_id}")
async def get_trace(request_id: str):
    """Get detailed trace for a specific request."""
    # Check memory first
    if request_id in _traces:
        return _traces[request_id]

    # Check Redis
    trace = _get_trace_redis(request_id)
    if trace:
        return trace

    return {"error": "Trace not found", "request_id": request_id}


@router.get("/metrics/summary")
async def get_metrics_summary():
    """
    High-level pipeline metrics summary.

    Returns JSON with:
      - Average pipeline latency
      - Cache hit rates
      - Distress detection counts
      - Recent trace summaries
    """
    from app.metrics import (
        REQUEST_LATENCY, REQUEST_COUNT, CACHE_OPERATIONS,
        DISTRESS_DETECTIONS, LLM_LATENCY, LLM_TOKENS,
    )

    # Compute summary from Prometheus metrics
    summary = {
        "pipeline": {
            "total_requests": _safe_counter_value(REQUEST_COUNT, ["success"])
                + _safe_counter_value(REQUEST_COUNT, ["error"]),
            "successful_requests": _safe_counter_value(REQUEST_COUNT, ["success"]),
            "error_requests": _safe_counter_value(REQUEST_COUNT, ["error"]),
            "blocked_requests": _safe_counter_value(REQUEST_COUNT, ["blocked"]),
            "cache_hit_requests": _safe_counter_value(REQUEST_COUNT, ["cache_hit"]),
        },
        "cache": {
            "exact_hits": _safe_counter_value(CACHE_OPERATIONS, ["exact", "hit"]),
            "exact_misses": _safe_counter_value(CACHE_OPERATIONS, ["exact", "miss"]),
            "semantic_hits": _safe_counter_value(CACHE_OPERATIONS, ["semantic", "hit"]),
            "semantic_misses": _safe_counter_value(CACHE_OPERATIONS, ["semantic", "miss"]),
        },
        "distress": {
            "mild": _safe_counter_value(DISTRESS_DETECTIONS, ["MILD"]),
            "moderate": _safe_counter_value(DISTRESS_DETECTIONS, ["MODERATE"]),
            "severe": _safe_counter_value(DISTRESS_DETECTIONS, ["SEVERE"]),
            "crisis": _safe_counter_value(DISTRESS_DETECTIONS, ["CRISIS"]),
        },
        "recent_traces": _get_recent_traces(limit=5),
    }

    return summary


def _safe_counter_value(counter, labels: list) -> int:
    """Safely get a counter value, returning 0 if labels don't exist."""
    try:
        return int(counter.labels(*labels)._value.get())
    except Exception:
        return 0


def _get_recent_traces(limit: int = 5) -> list:
    """Get the most recent trace summaries."""
    sorted_traces = sorted(
        _traces.values(),
        key=lambda t: t.get("timestamp", 0),
        reverse=True,
    )
    return [
        {
            "request_id": t["request_id"],
            "total_duration_ms": t["total_duration_ms"],
            "stage_count": t["stage_count"],
            "intent": t.get("intent", "unknown"),
        }
        for t in sorted_traces[:limit]
    ]
