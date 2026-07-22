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
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import settings
from app.telemetry_db import _get_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_responses(since: datetime, until: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Pull chat_responses with faithfulness / hallucination_flag in the window."""
    client = _get_client()
    if not client:
        logger.warning("Supabase client unavailable; returning empty response set.")
        return []

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
        return []


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
    metrics = _compute_metrics(rows)

    rate_alert = metrics["hallucination_rate"] > settings.anomaly_hallucination_rate_threshold
    faith_alert = metrics["faithfulness_p50"] < settings.anomaly_faithfulness_p50_threshold
    anomaly = rate_alert or faith_alert

    result = {
        "checked_at": _iso(_utc_now()),
        "lookback_days": lookback,
        "window_start": _iso(since),
        "thresholds": {
            "hallucination_rate": settings.anomaly_hallucination_rate_threshold,
            "faithfulness_p50": settings.anomaly_faithfulness_p50_threshold,
        },
        "metrics": metrics,
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
        default=int(os.environ.get("ANOMALY_LOOKBACK_DAYS", settings.anomaly_lookback_days)),
    )
    parser.add_argument(
        "--out",
        type=str,
        default=os.environ.get("ANOMALY_OUT_PATH", "hallucination_anomaly.json"),
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
    sys.exit(main())
