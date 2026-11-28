"""T2-03: one structured ``answer_outcome`` record per chat turn.

Separates "HTTP 200 but poor" from a served teaching. The record carries ids,
counts and labels only: never seeker text, answer text, user id or session id
(privacy invariant, see tests/test_no_seeker_text_in_logs.py).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.metrics import (
    ANSWER_LATENCY_SECONDS,
    ANSWER_OUTCOME_TOTAL,
    INTEGRITY_BREACH_TOTAL,
    USEFUL_ANSWER_TOTAL,
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


def classify_outcome(
    route: str,
    grounding_state: str,
    blocked: bool,
    errored: bool,
    served_clip: bool = False,
    system_unavailable: bool = False,
) -> str:
    if errored or route in _ERROR or system_unavailable:
        # NEW-ANS-2: an abstain whose check could not run is an error.
        return "error"
    if route in _CRISIS:
        return "crisis"
    if blocked or route in _BOUNDARY:
        return "boundary"
    if served_clip:
        # NEW-ANS-1 (ANS-011): a verified clip served under "Related, not a direct
        # answer" has verification.passed=False (no calibration profile), so the
        # public grounding_state reads "abstained". The seeker still got a
        # teaching: count it as served, or useful_answer can never fire.
        return "served"
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
    stage_latencies_ms: dict[str, float] | None = None,
    llm_calls: list[dict[str, Any]] | None = None,
    trace: Any | None = None,
) -> dict[str, Any]:
    """Build the record. Takes no text or identity arguments by design.

    ``trace`` (a ``TurnTrace``, only when LOG_TURN_TRACE_ENABLED) adds the additive
    ``turn``/``fp``/``summary`` blocks and per-call timing; without it the record is
    exactly what it was before.
    """
    route = str(route_decision or "error")
    state = str(grounding_state or "unknown")
    ver = verification if isinstance(verification, dict) else {}
    ids = [i for i in (_cid(c) for c in (citations or [])) if i]
    served_clip = bool(
        route == "first_person_bridge" and ids and ver.get("citations_verified") is True
    )

    # Clean and bounded per-stage latencies
    clean_stages = {
        str(k)[:40]: round(float(v), 2)
        for k, v in (stage_latencies_ms or {}).items()
        if isinstance(v, (int, float)) and v >= 0
    }

    # Clean and bounded per-call LLM accounting (operation, model, tokens, cost)
    clean_calls = []
    for call in llm_calls or []:
        if not isinstance(call, dict):
            continue
        clean_calls.append(
            {
                "prompt_id": str(call.get("prompt_id") or "unknown")[:80],
                "model": str(call.get("model") or "unknown")[:80],
                "tokens_in": max(0, int(call.get("tokens_in") or 0)),
                "tokens_out": max(0, int(call.get("tokens_out") or 0)),
                "cost_usd": round(max(0.0, float(call.get("cost_usd") or 0.0)), 6),
            }
        )

    outcome = classify_outcome(
        route,
        state,
        blocked,
        errored,
        served_clip=served_clip,
        system_unavailable=ver.get("abstain_cause") == "system_unavailable",
    )
    record = {
        "request_id": request_id,
        "lane": lane_for(route),
        "route_decision": route,
        "route_reason": route_reason,
        "outcome": outcome,
        "grounding_state": state,
        "citation_count": len(citations or []),
        "span_ids": ids,
        "verification_method": ver.get("method"),
        "verification_passed": ver.get("passed"),
        "cache_hit": bool(cache_hit),
        "latency_ms": latency_ms,
        "model_used": model_used,
        "stage_latencies_ms": clean_stages,
        "llm_calls": clean_calls,
        "total_tokens_in": sum(c["tokens_in"] for c in clean_calls),
        "total_tokens_out": sum(c["tokens_out"] for c in clean_calls),
        "total_cost_usd": round(sum(c["cost_usd"] for c in clean_calls), 6),
    }
    if trace is not None:
        _add_trace(record, trace, llm_calls or [], outcome)
    return record


_CALL_STATUSES = {"ok", "timeout", "cancelled", "refusal", "error"}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _gate_that_rejected(fp: dict[str, Any], rejected: dict[str, int], scores: list[int]) -> Any:
    """A label for humans, derived at build time; it decides nothing."""
    reason = fp.get("abstain_reason")
    if reason and reason not in ("none", "no_verified_clips"):
        return reason
    if rejected and not fp.get("n_scored"):
        return max(rejected, key=lambda name: rejected[name])
    min_score = fp.get("min_score")
    if scores and isinstance(min_score, (int, float)) and all(s < min_score for s in scores):
        return "relevance_min_score"
    if fp.get("answerability") in ("no", "indeterminate"):
        return "answerability"
    return reason if reason and reason != "none" else None


def _add_trace(
    record: dict[str, Any], trace: Any, raw_calls: list[dict[str, Any]], outcome: str
) -> None:
    """Merge the turn trace into ``record``. Total: a failure leaves the base record intact."""
    try:
        snap = trace.snapshot()
        turn = dict(snap.get("turn") or {})
        fp = dict(snap.get("fp") or {})
        rejected = {k: int(v) for k, v in (snap.get("rejected") or {}).items() if v}
        scores = list(snap.get("scores") or [])
        for key in ("job_id", "correlation_id", "pid"):
            if key in turn:
                record[key] = turn.pop(key)
        turn["stage_ms"] = snap.get("stage_ms") or {}
        if scores:
            fp["scores"] = scores
            fp["n_scored"] = fp.get("n_scored", len(scores))
        if rejected:
            fp["rejected"] = rejected
        if fp:
            fp["gate_that_rejected"] = (
                None if outcome == "served" else _gate_that_rejected(fp, rejected, scores)
            )
            record["fp"] = fp
        record["turn"] = turn

        # Per-call timing rides the existing llm_calls rows (bounded, no text).
        durations: list[float] = []
        throttle = retries = 0.0
        raw_dicts = [c for c in raw_calls if isinstance(c, dict)]
        if record.get("route_reason") is not None:
            record["route_reason"] = str(record["route_reason"])[:80]
        for row, raw in zip(record["llm_calls"], raw_dicts, strict=False):
            duration = _num(raw.get("duration_ms"))
            attempts = _num(raw.get("attempts"))
            limiter = _num(raw.get("limiter_wait_ms"))
            status = str(raw.get("status") or "")
            if duration is not None:
                row["duration_ms"] = round(max(0.0, duration), 1)
                durations.append(row["duration_ms"])
            if attempts is not None:
                row["attempts"] = int(attempts)
                retries += max(0, int(attempts) - 1)
            if limiter is not None:
                row["limiter_wait_ms"] = round(max(0.0, limiter), 1)
                throttle += row["limiter_wait_ms"]
            if status in _CALL_STATUSES:
                row["status"] = status
        record["summary"] = {
            "llm_calls_n": len(record["llm_calls"]),
            "llm_ms_sum": round(sum(durations), 1),
            "llm_ms_max": round(max(durations), 1) if durations else 0.0,
            "throttle_wait_ms_sum": round(throttle, 1),
            "retries_sum": int(retries),
        }
    except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as exc:
        logger.debug("turn trace not merged: %s", type(exc).__name__)


def compute_useful_answer(
    *,
    outcome: str,
    helpful: bool | None = None,
    played_seconds: float | int = 0,
    saved: bool = False,
    reported: bool = False,
) -> tuple[bool, str]:
    """T2-03: Evaluate whether an outcome is a 'useful_answer'.

    useful_answer = served AND (helpful OR played >= 20 s OR saved) AND NOT reported.
    Returns (is_useful, reason).
    """
    if outcome != "served":
        return False, "not_served"
    if reported:
        return False, "reported"
    if helpful is True:
        return True, "helpful"
    try:
        played = float(played_seconds or 0)
    except (TypeError, ValueError):
        played = 0.0
    if played >= 20.0:
        return True, "played_20s"
    if saved:
        return True, "saved"
    return False, "unconfirmed"


def record_useful_answer_signal(lane: str, signal: str) -> None:
    """T2-03: record a useful answer signal in Prometheus metrics."""
    try:
        USEFUL_ANSWER_TOTAL.labels(
            lane=str(lane or "teaching"), signal=str(signal or "unknown")
        ).inc()
    except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as exc:
        logger.debug("useful_answer metric not recorded: %s", exc)


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
        if "turn" in record:
            # Turn trace on: valid JSON in the message (greppable on any handler) plus the
            # same fields as top-level attributes for the JSON formatter.
            logger.info(
                "answer_outcome %s",
                json.dumps(record, default=str, separators=(",", ":")),
                extra={"fields": record},
            )
        else:
            logger.info("answer_outcome %s", record)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
    ) as exc:  # telemetry must never break a response
        logger.debug("answer_outcome not emitted: %s", exc)
