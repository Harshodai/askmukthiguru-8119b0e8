"""Retry analysis utility — groups negative feedback by query similarity.

Usage:
    from ops.retry_analysis import analyze_retry_patterns
    results = analyze_retry_patterns(since_days=7)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _get_client():
    from app.telemetry_db import _get_client as _supa_client

    return _supa_client()


def _tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens of length >= 3."""
    return {w for w in re.findall(r"\b[a-z0-9]{3,}\b", text.lower())}


def _word_overlap(a: str, b: str) -> float:
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b))


def analyze_retry_patterns(since_days: int = 7) -> list[dict[str, Any]]:
    """Query feedback_events table and group negative feedback by query similarity.

    Returns a list of complaint clusters sorted by frequency (descending).
    Each cluster has:
        - representative_query: the first query in the cluster
        - frequency: number of queries in this cluster
        - sample_queries: up to 5 example queries
    """
    client = _get_client()
    if not client:
        logger.warning("Supabase client unavailable — returning empty retry analysis")
        return []

    cutoff = (datetime.now(UTC) - timedelta(days=since_days)).isoformat()

    try:
        rows = (
            client.table("feedback_events")
            .select("query_text, feedback_type, created_at")
            .eq("feedback_type", "negative")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
            .data
            or []
        )
    except Exception as e:
        logger.error("Failed to query feedback_events: %s", e)
        return []

    if not rows:
        return []

    # Cluster queries by word overlap
    clusters: list[dict[str, Any]] = []
    for row in rows:
        query = row.get("query_text") or ""
        if not query.strip():
            continue

        matched = False
        for cluster in clusters:
            if _word_overlap(query, cluster["representative_query"]) >= 0.5:
                cluster["frequency"] += 1
                if len(cluster["sample_queries"]) < 5:
                    cluster["sample_queries"].append(query)
                matched = True
                break

        if not matched:
            clusters.append(
                {
                    "representative_query": query,
                    "frequency": 1,
                    "sample_queries": [query],
                }
            )

    clusters.sort(key=lambda c: c["frequency"], reverse=True)
    return clusters


if __name__ == "__main__":
    results = analyze_retry_patterns(since_days=7)
    print(f"Found {len(results)} complaint cluster(s):")
    for i, cluster in enumerate(results, 1):
        print(
            f"  {i}. [{cluster['frequency']}x] {cluster['representative_query'][:80]}"
        )
        for sq in cluster["sample_queries"][1:3]:
            print(f"     - {sq[:80]}")
