"""Daily hallucination anomaly detector.

Reads recent chat_responses from Supabase, computes:
  - hallucination_rate = flagged responses / total responses
  - faithfulness_p50 = median faithfulness score

Alerts when:
  - hallucination_rate > settings.anomaly_hallucination_rate_threshold
  - faithfulness_p50 < settings.anomaly_faithfulness_p50_threshold

Returns JSON and exits non-zero when an anomaly is detected so cron / CI can
notify on-call.
"""

from __future__ import annotations

import json
import logging
import statistics
import sys
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from app.config import settings
from app.telemetry_db import _get_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_responses(
    since: datetime, until: Optional[datetime] = None
) -> Optional[list[dict[str, Any]]]:
    """Pull chat_responses with faithfulness / hallucination_flag in the window.

    Returns None (not []) on a connection/query failure, so the caller can
    distinguish "Supabase is broken" from "genuinely no responses in window" --
    collapsing both to [] previously made a broken connection report identically
    to "no anomaly."
    """
    client = _get_client()
    if not client:
        logger.error("Supabase client unavailable; cannot determine anomaly status.")
        return None

    query = (
        client.table("chat_responses")
        .select("hallucination_flag, faithfulness, created_at")
        .gte("created_at", _iso(since))
    )
    if until is not None:
        query = query.lte("created_at", _iso(until))

    try:
        return query.execute().data or []
    except Exception as e:
        logger.error(f"Failed to fetch chat_responses: {e}")
        return None


def _fetch_retrieval_events(
    since: datetime, until: Optional[datetime] = None
) -> Optional[list[dict[str, Any]]]:
    """Pull retrieval_events in the window, joined through chat_queries for created_at.

    retrieval_events (schema.sql) has no created_at of its own -- same join
    pattern as telemetry_db.py's other chat_queries!inner(created_at) queries.
    Retrieval-stage visibility only; failures here do not affect the
    hallucination-rate anomaly gate below (best-effort addition, not a new
    fail-closed condition -- that would need its own threshold decision).
    """
    client = _get_client()
    if not client:
        return None

    query = (
        client.table("retrieval_events")
        .select("source_docs, scores, top_k, retrieval_hit, chat_queries!inner(created_at)")
        .gte("chat_queries.created_at", _iso(since))
    )
    if until is not None:
        query = query.lte("chat_queries.created_at", _iso(until))

    try:
        return query.execute().data or []
    except Exception as e:
        logger.warning(f"Failed to fetch retrieval_events (non-fatal): {e}")
        return None


def _compute_retrieval_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """F19: source_count distribution, top_source_score p50, zero-source rate.

    AnswerEvidence (glue_stages.py) already computes source_count = len(citations)
    and top_source_score = max(scores) per response; this derives the daily
    aggregate from the same underlying data (retrieval_events.source_docs/scores)
    so the anomaly job gains retrieval-stage visibility, not new instrumentation.
    """
    total = len(rows)
    if total == 0:
        return {
            "total_retrieval_events": 0,
            "source_count_p50": None,
            "source_count_mean": None,
            "top_source_score_p50": None,
            "zero_source_rate": None,
        }

    source_counts = [len(r.get("source_docs") or []) for r in rows]
    top_scores = [max(r["scores"]) for r in rows if r.get("scores") and len(r["scores"]) > 0]
    zero_source = sum(1 for r in rows if not r.get("retrieval_hit"))

    return {
        "total_retrieval_events": total,
        "source_count_p50": statistics.median(source_counts) if source_counts else None,
        "source_count_mean": (sum(source_counts) / len(source_counts) if source_counts else None),
        "top_source_score_p50": statistics.median(top_scores) if top_scores else None,
        "zero_source_rate": zero_source / total,
    }


def _compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive hallucination rate and faithfulness p50 from response rows."""
    total = len(rows)
    if total == 0:
        return {
            "total_responses": 0,
            "flagged_count": 0,
            "hallucination_rate": 0.0,
            "faithfulness_p50": 0.0,
            "faithfulness_mean": 0.0,
        }

    flagged = sum(1 for r in rows if r.get("hallucination_flag"))
    faithfulness_values = [
        float(r.get("faithfulness") or 0.0)
        for r in rows
        if isinstance(r.get("faithfulness"), (int, float))
    ]

    return {
        "total_responses": total,
        "flagged_count": flagged,
        "hallucination_rate": flagged / total,
        "faithfulness_p50": statistics.median(faithfulness_values) if faithfulness_values else 0.0,
        "faithfulness_mean": (
            sum(faithfulness_values) / len(faithfulness_values) if faithfulness_values else 0.0
        ),
    }


def run_anomaly_check(lookback_days: Optional[int] = None) -> dict[str, Any]:
    """Run the daily hallucination anomaly check."""
    lookback = lookback_days if lookback_days is not None else settings.anomaly_lookback_days
    since = _utc_now() - timedelta(days=max(1, lookback))
    rows = _fetch_responses(since)

    if rows is None:
        # Connection/query failure -- must not read the same as "no anomaly
        # found." Reported as an anomaly so cron/CI alerts on-call instead of
        # silently going quiet.
        return {
            "checked_at": _iso(_utc_now()),
            "lookback_days": lookback,
            "window_start": _iso(since),
            "thresholds": {
                "hallucination_rate": settings.anomaly_hallucination_rate_threshold,
                "faithfulness_p50": settings.anomaly_faithfulness_p50_threshold,
            },
            "metrics": _compute_metrics([]),
            "anomaly": True,
            "alerts": {"connection_error": True},
        }

    metrics = _compute_metrics(rows)

    total = metrics.get("total_responses", 0)
    if total == 0:
        # B2/B3: an empty window is indeterminate, never a pass. Failing closed
        # keeps "no traffic" and "broken query" from reading as healthy and
        # forces the workflow gate to page on a silent pipeline instead.
        return {
            "checked_at": _iso(_utc_now()),
            "lookback_days": lookback,
            "window_start": _iso(since),
            "thresholds": {
                "hallucination_rate": settings.anomaly_hallucination_rate_threshold,
                "faithfulness_p50": settings.anomaly_faithfulness_p50_threshold,
            },
            "metrics": metrics,
            "anomaly": True,
            "alerts": {"no_data": True},
        }

    rate_alert = metrics["hallucination_rate"] > settings.anomaly_hallucination_rate_threshold
    faith_alert = metrics["faithfulness_p50"] < settings.anomaly_faithfulness_p50_threshold
    anomaly = rate_alert or faith_alert

    # F19 (TrustNLP 2026): the gap was stage coverage, not scheduling -- this
    # job watched generation-stage outputs only. Retrieval-stage visibility
    # added here; deliberately does NOT feed the anomaly/alerts gate above --
    # that would need its own threshold decision, this pass only closes the
    # "nothing monitors retrieval quality" visibility gap.
    retrieval_rows = _fetch_retrieval_events(since)
    retrieval_metrics = (
        _compute_retrieval_metrics(retrieval_rows) if retrieval_rows is not None else None
    )

    result = {
        "checked_at": _iso(_utc_now()),
        "lookback_days": lookback,
        "window_start": _iso(since),
        "thresholds": {
            "hallucination_rate": settings.anomaly_hallucination_rate_threshold,
            "faithfulness_p50": settings.anomaly_faithfulness_p50_threshold,
        },
        "metrics": metrics,
        "retrieval_metrics": retrieval_metrics,
        "anomaly": anomaly,
        "alerts": {
            "hallucination_rate_spike": rate_alert,
            "faithfulness_p50_drop": faith_alert,
        },
    }
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Daily hallucination anomaly check.")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=settings.anomaly_lookback_days,
    )
    parser.add_argument(
        "--out",
        type=str,
        default=getattr(settings, "anomaly_output_path", "hallucination_anomaly.json"),
    )
    args = parser.parse_args(argv)

    result = run_anomaly_check(lookback_days=args.lookback_days)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))

    return 1 if result["anomaly"] else 0


if __name__ == "__main__":
    # Self-check: ensure helper logic handles empty / edge cases.
    empty = _compute_metrics([])
    assert empty["total_responses"] == 0
    assert empty["hallucination_rate"] == 0.0

    sample = [
        {"hallucination_flag": True, "faithfulness": 0.4},
        {"hallucination_flag": False, "faithfulness": 0.9},
        {"hallucination_flag": False, "faithfulness": 0.95},
    ]
    m = _compute_metrics(sample)
    assert m["hallucination_rate"] == 1 / 3
    assert m["faithfulness_p50"] == 0.9

    empty_retrieval = _compute_retrieval_metrics([])
    assert empty_retrieval["total_retrieval_events"] == 0
    assert empty_retrieval["zero_source_rate"] is None

    retrieval_sample = [
        {"source_docs": ["a", "b"], "scores": [0.9, 0.7], "retrieval_hit": True},
        {"source_docs": [], "scores": [], "retrieval_hit": False},
        {"source_docs": ["a"], "scores": [0.5], "retrieval_hit": True},
    ]
    rm = _compute_retrieval_metrics(retrieval_sample)
    assert rm["total_retrieval_events"] == 3
    assert rm["source_count_p50"] == 1
    assert rm["top_source_score_p50"] == 0.7  # median of [0.9, 0.5]
    assert rm["zero_source_rate"] == 1 / 3

    sys.exit(main())
