"""Privacy-safe operational telemetry projections for the admin API.

The standard admin experience receives aggregate quality, latency, route, and
release evidence only. Raw seeker prompts, answers, source excerpts, identifiers,
and free-text evaluator notes remain outside these projections.
"""

from __future__ import annotations

from typing import Any


_QUERY_FIELDS = (
    "id",
    "created_at",
    "model",
    "status",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "cost_estimate",
    "prompt_version_id",
)
_RESPONSE_FIELDS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "hallucination_flag",
    "confidence",
    "created_at",
)
_SPAN_FIELDS = ("id", "name", "span_name", "start_ms", "duration_ms", "created_at")
_TRIGGER_FIELDS = ("id", "trigger_name", "trigger_type", "created_at")
_SAFETY_FIELDS = ("id", "type", "severity", "rule", "action", "created_at")
_RETRIEVAL_FIELDS = ("id", "top_k", "retrieval_hit")


def _allow(row: dict[str, Any] | None, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {field: row[field] for field in fields if field in row and row[field] is not None}


def _safe_spans(spans: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result = []
    for span in spans or []:
        safe = _allow(span, _SPAN_FIELDS)
        if "name" not in safe and span.get("span_name"):
            safe["name"] = span["span_name"]
        result.append(safe)
    return result


def trace_summary(row: dict[str, Any]) -> dict[str, Any]:
    """Project one flat trace row into the public-to-admin operational contract."""
    summary = _allow(row, _QUERY_FIELDS + _RESPONSE_FIELDS)
    summary["spans"] = _safe_spans(row.get("spans"))
    return summary


def trace_detail(trace: dict[str, Any]) -> dict[str, Any]:
    """Return a trace detail without prompt, completion, source, or identity data."""
    query = _allow(trace.get("query"), _QUERY_FIELDS)
    response = _allow(trace.get("response"), _RESPONSE_FIELDS)
    retrieval = _allow(trace.get("retrieval"), _RETRIEVAL_FIELDS)
    triggers = [_allow(item, _TRIGGER_FIELDS) for item in trace.get("triggers", [])]
    safety = [_allow(item, _SAFETY_FIELDS) for item in trace.get("safety", [])]
    return {
        "trace_id": query.get("id"),
        "query": query,
        "response": response,
        "retrieval": retrieval,
        "spans": _safe_spans(trace.get("spans")),
        "triggers": triggers,
        "safety": safety,
    }


def operations_snapshot(
    traces: list[dict[str, Any]],
    *,
    model_policy_id: str,
    budget_guard_enabled: bool,
) -> dict[str, Any]:
    """Derive bounded aggregate evidence for the operations overview."""
    safe_traces = [trace_summary(trace) for trace in traces]
    latencies = [float(item["latency_ms"]) for item in safe_traces if item.get("latency_ms") is not None]
    failures = sum(1 for item in safe_traces if item.get("status") not in {None, "ok", "success"})
    total_cost = sum(float(item.get("cost_estimate") or 0.0) for item in safe_traces)
    return {
        "sample_size": len(safe_traces),
        "failure_count": failures,
        "failure_rate": round(failures / len(safe_traces), 4) if safe_traces else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "cost_estimate_usd": round(total_cost, 6),
        "model_policy_id": model_policy_id,
        "budget_guard_enabled": budget_guard_enabled,
    }
