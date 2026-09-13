"""Pure retrieval metrics shared by the live benchmark and release gate.

Keeping the calculations independent of Qdrant and embedding dependencies makes
their meaning reviewable and regression-testable.  Labels are source-level: a
retrieved chunk is relevant when its ``source_url`` belongs to the item's
approved ``correct_sources`` set.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from urllib.parse import urlparse


DEFAULT_KS = (1, 5, 10, 25, 50)

CANONICAL_FOUR_SECRETS_URL = (
    "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"
)

SOURCE_KEY_ALIASES = {
    "The_Four_Sacred_Secrets.pdf": CANONICAL_FOUR_SECRETS_URL,
}


def normalize_source_key(source: str) -> str:
    """Map a source_url to its canonical scoring key.

    The corpus keys the Four Sacred Secrets doc by canonical Amazon URL
    while older golden labels use the bare PDF filename (L-DOCKER-19: 70
    points under the URL, 0 under the bare name). Exact-match scoring
    without this map turns correct top-5 retrieval into a 0.0. URL keys
    are also lowercased on host with fragments stripped. Query strings are
    kept because the video id lives in YouTube's query string: blanket
    query-stripping would alias every video together.
    """
    key = (source or "").strip()
    if key in SOURCE_KEY_ALIASES:
        return SOURCE_KEY_ALIASES[key]
    parsed = urlparse(key)
    if parsed.scheme and parsed.netloc:
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path or ''}{query}"
    return key


def first_relevant_rank(retrieved_sources: Sequence[str], correct_sources: Iterable[str]) -> int | None:
    """Return the one-based rank of the first relevant source, if present."""
    correct = {normalize_source_key(source) for source in correct_sources if source}
    for rank, source in enumerate(retrieved_sources, start=1):
        if normalize_source_key(source) in correct:
            return rank
    return None


def summarize_rankings(
    rankings: Iterable[tuple[Sequence[str], Iterable[str]]], *, ks: Sequence[int] = DEFAULT_KS
) -> dict[str, object]:
    """Calculate source-level recall, precision, and MRR for ranked results.

    ``precision_at_k`` is chunk precision because a retrieval result is a
    chunk.  ``recall_at_k`` and MRR are source-level success measures: a query
    succeeds once any approved source appears.  This distinction prevents
    duplicate chunks from one source from inflating recall.
    """
    normalized_ks = tuple(sorted({int(k) for k in ks if int(k) > 0}))
    if not normalized_ks:
        raise ValueError("at least one positive k is required")

    rankings = list(rankings)
    query_count = len(rankings)
    hits = {k: 0 for k in normalized_ks}
    precision_totals = {k: 0.0 for k in normalized_ks}
    reciprocal_ranks: list[float] = []

    for retrieved_sources, correct_sources in rankings:
        correct = {normalize_source_key(source) for source in correct_sources if source}
        rank = first_relevant_rank(retrieved_sources, correct)
        reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
        for k in normalized_ks:
            top_k = [normalize_source_key(s) for s in retrieved_sources[:k]]
            if any(source in correct for source in top_k):
                hits[k] += 1
            precision_totals[k] += (
                sum(source in correct for source in top_k) / k if top_k else 0.0
            )

    def average(value: float) -> float:
        return round(value / query_count, 4) if query_count else 0.0

    return {
        "n_queries": query_count,
        "recall_at_k": {k: average(hits[k]) for k in normalized_ks},
        "precision_at_k": {k: average(precision_totals[k]) for k in normalized_ks},
        "mrr": round(sum(reciprocal_ranks) / query_count, 4) if query_count else 0.0,
    }
