"""T2-03: one structured ``answer_outcome`` record per chat turn.

Separates "HTTP 200 but poor" from a served teaching. The record carries ids,
counts and labels only: never seeker text, answer text, user id or session id
(privacy invariant, see tests/test_no_seeker_text_in_logs.py).
"""

from __future__ import annotations

import logging
from typing import Any

from app.metrics import (
    ANSWER_LATENCY_SECONDS,
    ANSWER_OUTCOME_TOTAL,
    INTEGRITY_BREACH_TOTAL,
)

logger = logging.getLogger(__name__)

_CRISIS = {"distress", "crisis_preempted", "crisis"}
_BOUNDARY = {"adversarial", "safety_violation", "blocked", "casual", "instant_greeting"}
_ERROR = {"error", "timeout"}
_ABSTAIN_STATES = {"abstained", "no_context", "refused"}
_VERBATIM_MODELS = {"", "none"}


def lane_for(route: str) -> str:
    """Coarse, bounded lane label derived from the canonical route decision."""
    if route == "first_person_bridge":
        return "first_person"
    if route in _CRISIS:
        return "crisis"
    if route in _BOUNDARY:
        return "boundary"
    if route in _ERROR:
        return "error"
    if route == "meditation":
        return "meditation"
    return "teaching"


def classify_outcome(route: str, grounding_state: str, blocked: bool, errored: bool) -> str:
    if errored or route in _ERROR:
        return "error"
    if route in _CRISIS:
        return "crisis"
    if blocked or route in _BOUNDARY:
        return "boundary"
    if grounding_state in _ABSTAIN_STATES or route == "no_context_short_circuit":
        return "abstained"
    return "served"


def _cid(citation: Any) -> str | None:
    for key in ("clip_id", "point_id", "span_id", "id"):
        if isinstance(citation, dict):
            val = citation.get(key)
        else:
            val = getattr(citation, key, None)
        if val:
            return str(val)
    return None


def build_answer_outcome(
    *,
    request_id: str | None,
    route_decision: str | None,
    route_reason: str | None,
    grounding_state: str | None,
    citations: list | None,
    verification: dict | None,
    cache_hit: bool,
    latency_ms: float | int | None,
    model_used: str | None,
    blocked: bool = False,
    errored: bool = False,
) -> dict[str, Any]:
    """Build the record. Takes no text or identity arguments by design."""
    route = str(route_decision or "error")
    state = str(grounding_state or "unknown")
    ver = verification if isinstance(verification, dict) else {}
    ids = [i for i in (_cid(c) for c in (citations or [])) if i]
    return {
        "request_id": request_id,
        "lane": lane_for(route),
        "route_decision": route,
        "route_reason": route_reason,
        "outcome": classify_outcome(route, state, blocked, errored),
        "grounding_state": state,
        "citation_count": len(citations or []),
        "span_ids": ids,
        "verification_method": ver.get("method"),
        "verification_passed": ver.get("passed"),
        "cache_hit": bool(cache_hit),
        "latency_ms": latency_ms,
        "model_used": model_used,
    }


def is_integrity_breach(record: dict[str, Any], *, first_person_only: bool) -> bool:
    """Teaching-lane turn answered with generated text while FP-only is on."""
    if not first_person_only or record.get("lane") != "teaching":
        return False
    if record.get("outcome") != "served":
        return False
    model = str(record.get("model_used") or "").strip().lower()
    return model not in _VERBATIM_MODELS


def emit_answer_outcome(record: dict[str, Any], *, first_person_only: bool) -> None:
    """Prometheus + structured log. Never raises."""
    try:
        lane, outcome = record["lane"], record["outcome"]
        ANSWER_OUTCOME_TOTAL.labels(lane=lane, outcome=outcome).inc()
        if record.get("latency_ms") is not None:
            ANSWER_LATENCY_SECONDS.labels(lane=lane, outcome=outcome).observe(
                float(record["latency_ms"]) / 1000.0
            )
        if is_integrity_breach(record, first_person_only=first_person_only):
            INTEGRITY_BREACH_TOTAL.labels(lane=lane).inc()
            logger.error("integrity_breach: generated answer in first-person-only mode")
        logger.info("answer_outcome %s", record)
    except Exception as exc:  # telemetry must never break a response
        logger.debug("answer_outcome not emitted: %s", exc)
