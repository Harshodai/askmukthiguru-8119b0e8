"""Qdrant search quality benchmarking.

Measures NDCG@10 on golden queries across retrieval strategies:
- Dense-only (BGE-M3 dense vectors)
- Hybrid (dense + sparse with RRF)
- Hybrid + reranker (ColBERT/CrossEncoder re-ranking)

Run manually: python -m pytest tests/test_qdrant_search_quality.py -v
Baseline: memory/qdrant_quality_baseline.json (updated on success)
"""

import json
import logging
import os
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


def _extract_source_filename(r: dict) -> str:
    """Extract a source filename from a search result dict.

    Qdrant payload field precedence: "source_url" → "source" → "url"
    → payload.source_url → payload.source → payload.url → "".
    Multi-key fallback fixes the NDCG=0.0 measurement bug (2026-08-03) where
    all documents returned "" because some payloads use "source"/"url"
    instead of "source_url".
    """
    raw = (
        r.get("source_url")
        or r.get("source")
        or r.get("url")
        or (r.get("payload") or {}).get("source_url")
        or (r.get("payload") or {}).get("source")
        or (r.get("payload") or {}).get("url")
        or ""
    )
    if not isinstance(raw, str):
        raw = str(raw)
    return raw.split("/")[-1]


@pytest.fixture
def qdrant_searcher():
    """Real QdrantSearcher against the configured collection. Skips if
    unreachable or if the collection has no points (e.g. a fresh local
    container with no ingested corpus)."""
    from app.config import settings
    from services.qdrant.client import QdrantClientManager
    from services.qdrant.searcher import QdrantSearcher

    try:
        client_mgr = QdrantClientManager(collection=settings.qdrant_collection)
    except Exception as exc:
        pytest.skip(
            f"Qdrant client initialization failed ({type(exc).__name__}); "
            "skipping search-quality integration test"
        )

    # Verify the target collection through Qdrant REST metadata. This avoids
    # turning a client-side deserialization/connection artifact into a
    # misleading retrieval-quality result while preserving the real searcher
    # below for non-empty collections.
    try:
        import requests

        headers = {}
        api_key = getattr(settings, "qdrant_api_key", "") or ""
        if api_key:
            headers["api-key"] = api_key
        response = requests.get(
            f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}",
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        info = response.json().get("result", {})
    except Exception as exc:
        pytest.skip(
            f"Qdrant collection '{settings.qdrant_collection}' lookup failed "
            f"({type(exc).__name__}: {str(exc)[:180]}); "
            "skipping search-quality integration test"
        )
    points_count = info.get("points_count") if isinstance(info, dict) else None
    if not isinstance(points_count, int) or points_count <= 0:
        message = (
            f"Qdrant collection '{settings.qdrant_collection}' has no usable points "
            f"(points_count={points_count!r}) — retrieval evaluation corpus is unavailable"
        )
        if os.environ.get("REQUIRE_QDRANT_EVAL", "").lower() in {"1", "true", "yes"}:
            pytest.fail(message)
        pytest.skip(message)

    # A non-empty collection can still be the wrong corpus. The historical
    # golden set names approved markdown sources, while a production/live
    # collection may contain only video URLs or a different corpus release.
    # Do not turn that label mismatch into NDCG=0 and then overwrite the
    # baseline. Fail closed as unavailable unless the CI gate explicitly
    # requires the evaluation corpus, in which case the gate must fail.
    expected_sources = {
        source
        for query in QdrantSearchQualityTester.GOLDEN_QUERIES
        for source in query["relevant_sources"]
    }
    try:
        sample_points, _ = client_mgr.client.scroll(
            collection_name=settings.qdrant_collection,
            limit=min(512, points_count),
            with_payload=["source_url", "source", "url"],
            with_vectors=False,
        )
    except Exception as exc:
        message = (
            f"Could not inspect Qdrant evaluation labels for '{settings.qdrant_collection}' "
            f"({type(exc).__name__}: {str(exc)[:180]})"
        )
        if os.environ.get("REQUIRE_QDRANT_EVAL", "").lower() in {"1", "true", "yes"}:
            pytest.fail(message)
        pytest.skip(message)

    available_sources = set()
    for point in sample_points or []:
        payload = getattr(point, "payload", None) or {}
        for key in ("source_url", "source", "url"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                available_sources.add(value.rsplit("/", 1)[-1])
    if not expected_sources.intersection(available_sources):
        message = (
            f"Qdrant collection '{settings.qdrant_collection}' does not contain any "
            "source labels from the golden evaluation set — refusing to measure or "
            f"rewrite NDCG baseline; sampled_labels={sorted(available_sources)[:8]}"
        )
        if os.environ.get("REQUIRE_QDRANT_EVAL", "").lower() in {"1", "true", "yes"}:
            pytest.fail(message)
        pytest.skip(message)

    return QdrantSearcher(client_mgr.client, settings.qdrant_collection)


@pytest.fixture
def embedding_service():
    """Real EmbeddingService. Skips if the model can't be loaded (no network / no cache)."""
    from services.embedding_service import EmbeddingService

    try:
        svc = EmbeddingService()
        svc._ensure_encoder()
    except Exception as e:
        pytest.skip(f"Embedding model unavailable, skipping search-quality integration test: {e}")

    return svc


@pytest.fixture
def reranker_service(embedding_service):
    """Reuses EmbeddingService.rerank() — same object exposes both roles."""
    return embedding_service


class QdrantSearchQualityTester:
    """Golden query evaluation with NDCG@K metric."""

    # Golden queries with manual relevance labels (0=irrelevant, 3=perfect match)
    GOLDEN_QUERIES = [
        {
            "query": "What is beautiful state?",
            "relevant_sources": [
                "beautiful_state_and_health_challenges.md",
                "beautiful_state_glossary.md",
            ],
            "min_ndcg_threshold": 0.85,
        },
        {
            "query": "How do I connect to universal intelligence?",
            "relevant_sources": [
                "connecting_to_universal_intelligence.md",
                "feeling_one_with_universal_intelligence.md",
            ],
            "min_ndcg_threshold": 0.80,
        },
        {
            "query": "Dealing with suffering and pain",
            "relevant_sources": [
                "finding_truth_in_chaos.md",
                "inner_truth_and_being.md",
            ],
            "min_ndcg_threshold": 0.75,
        },
        {
            "query": "Practice of stillness and meditation",
            "relevant_sources": [
                "stillness_and_inner_truth.md",
                "gentle_spiritual_awakening.md",
            ],
            "min_ndcg_threshold": 0.80,
        },
        {
            "query": "Inner peace consciousness awareness",
            "relevant_sources": [
                "inner_peace_and_consciousness.md",
                "universal_intelligence.md",
            ],
            "min_ndcg_threshold": 0.78,
        },
    ]

    def __init__(self, qdrant_searcher, embedding_service, reranker_service=None):
        """Initialize with Qdrant components."""
        self._searcher = qdrant_searcher
        self._embedder = embedding_service
        self._reranker = reranker_service

    def ndcg_at_k(
        self, ranked_sources: list[str], relevant_sources: list[str], k: int = 10
    ) -> float:
        """Compute NDCG@K using standard log2(rank+1) formulation.

        Reference: Järvelin & Kekäläinen (2002), "Cumulated gain-based evaluation
        of IR techniques", ACM TOIS 20(4).

        Args:
            ranked_sources: Ordered list of source filenames from search results
            relevant_sources: Ground truth relevant source filenames
            k: Cutoff rank

        Returns:
            NDCG@K score in [0.0, 1.0]
        """
        import math

        # NDCG@K measures the top-k retrieved items: apply the cutoff to the
        # raw ranking FIRST, then deduplicate the top-k slice (preserve
        # order). Deduplicating before the cutoff would shrink the measured
        # list below k and distort DCG vs IDCG. Dedup after cutoff also keeps
        # duplicates from contributing multiple relevant hits.
        ranked_sources = list(dict.fromkeys(ranked_sources[:k]))
        relevant_sources = list(dict.fromkeys(relevant_sources))

        # Relevance: 1.0 if in relevant_sources, 0.0 otherwise
        relevances = [1.0 if src in relevant_sources else 0.0 for src in ranked_sources]

        # DCG: standard log2(rank+1) formulation (rank is 1-indexed)
        dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))

        # IDCG: best-case DCG (all relevant docs at top ranks)
        ideal_relevances = [1.0] * min(len(relevant_sources), k)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(len(ideal_relevances)))

        return dcg / idcg if idcg > 0 else 0.0

    def evaluate_strategy(self, strategy: str) -> dict:
        """Evaluate one retrieval strategy on golden queries.

        Args:
            strategy: 'dense' | 'hybrid' | 'hybrid_reranked'

        Returns:
            {
                'strategy': str,
                'ndcg_scores': list[float],
                'mean_ndcg': float,
                'min_ndcg': float,
                'passed_queries': int,
                'failed_queries': list[str],  # Failed query strings
            }
        """
        scores = []
        failed = []

        for q_def in self.GOLDEN_QUERIES:
            query = q_def["query"]
            relevant_sources = q_def["relevant_sources"]
            threshold = q_def["min_ndcg_threshold"]

            # Dense search: encode_single() returns dense vector only
            if strategy == "dense":
                query_vector = self._embedder.encode_single(query)
                results = self._searcher.search(query_vector=query_vector, limit=10)
            # Hybrid (dense + sparse RRF): encode_single_full() returns both in one call
            elif strategy == "hybrid":
                full = self._embedder.encode_single_full(query)
                results = self._searcher.search(
                    query_vector=full["dense"],
                    sparse_vector=full["sparse"],
                    limit=10,
                )
            # Hybrid + reranking
            elif strategy == "hybrid_reranked":
                full = self._embedder.encode_single_full(query)
                results = self._searcher.search(
                    query_vector=full["dense"],
                    sparse_vector=full["sparse"],
                    limit=10,
                )
                if self._reranker:
                    # services/embedding_service.py:rerank(query, documents, ...) is the
                    # real reranker API — takes {"text": ...} dicts, not raw strings.
                    results = self._reranker.rerank(query, results)
            else:
                raise ValueError(f"Unknown strategy: {strategy}")

            # Extract source filenames from results.
            ranked_sources = [_extract_source_filename(r) for r in results]

            # Log a diagnostic sample so future failures are debuggable
            n_empty = sum(1 for s in ranked_sources if not s)
            if n_empty > 0:
                sample = results[0] if results else {}
                payload_keys = (
                    list((sample.get("payload") or {}).keys()) if isinstance(sample, dict) else []
                )
                logger.warning(
                    "NDCG: %d/%d source filenames are empty — source extraction "
                    "incomplete; check Qdrant payload field names. Sample result keys: %s; payload keys: %s",
                    n_empty,
                    len(ranked_sources),
                    list(sample.keys()) if results else "(no results)",
                    payload_keys,
                )

            # Compute NDCG@10
            ndcg = self.ndcg_at_k(ranked_sources, relevant_sources, k=10)
            scores.append(ndcg)

            # Track failures
            if ndcg < threshold:
                failed.append(query)
                logger.warning(
                    f"{strategy} | {query[:40]}... | NDCG={ndcg:.3f} (threshold={threshold})"
                )

        return {
            "strategy": strategy,
            "ndcg_scores": scores,
            "mean_ndcg": sum(scores) / len(scores) if scores else 0.0,
            "min_ndcg": min(scores) if scores else 0.0,
            "passed_queries": len(scores) - len(failed),
            "failed_queries": failed,
        }

    def compare_strategies(self) -> dict:
        """Run all strategies and compare."""
        results = {}
        for strategy in ["dense", "hybrid", "hybrid_reranked"]:
            logger.info(f"Evaluating {strategy}...")
            results[strategy] = self.evaluate_strategy(strategy)

        return results


@pytest.mark.integration
def test_qdrant_search_quality_dense(qdrant_searcher, embedding_service):
    """Dense-only search quality baseline."""
    tester = QdrantSearchQualityTester(qdrant_searcher, embedding_service)
    result = tester.evaluate_strategy("dense")

    assert result["mean_ndcg"] >= 0.70, f"Dense search mean NDCG too low: {result['mean_ndcg']}"
    logger.info(f"Dense NDCG@10: {result['mean_ndcg']:.3f}")


@pytest.mark.integration
def test_qdrant_search_quality_hybrid(qdrant_searcher, embedding_service):
    """Hybrid (dense + sparse) search quality."""
    tester = QdrantSearchQualityTester(qdrant_searcher, embedding_service)
    result = tester.evaluate_strategy("hybrid")

    assert result["mean_ndcg"] >= 0.75, f"Hybrid search mean NDCG too low: {result['mean_ndcg']}"
    logger.info(f"Hybrid NDCG@10: {result['mean_ndcg']:.3f}")


@pytest.mark.integration
def test_qdrant_search_quality_hybrid_reranked(
    qdrant_searcher, embedding_service, reranker_service
):
    """Hybrid + reranking search quality."""
    if reranker_service is None:
        pytest.skip("Reranker not available")

    tester = QdrantSearchQualityTester(qdrant_searcher, embedding_service, reranker_service)
    result = tester.evaluate_strategy("hybrid_reranked")

    assert result["mean_ndcg"] >= 0.78, f"Hybrid+reranked mean NDCG too low: {result['mean_ndcg']}"
    logger.info(f"Hybrid+Reranked NDCG@10: {result['mean_ndcg']:.3f}")


@pytest.mark.integration
def test_qdrant_search_quality_baseline_regression(qdrant_searcher, embedding_service):
    """Regression: ensure search quality doesn't degrade week-to-week."""
    baseline_path = Path(__file__).parent.parent.parent / "memory" / "qdrant_quality_baseline.json"

    tester = QdrantSearchQualityTester(qdrant_searcher, embedding_service)
    current = tester.evaluate_strategy("hybrid")

    # Load baseline if it exists
    if baseline_path.exists():
        with open(baseline_path) as f:
            baseline = json.load(f)
        baseline_ndcg = baseline.get("hybrid", {}).get("mean_ndcg", 0.0)

        # Regression threshold: allow 2% drop
        assert current["mean_ndcg"] >= baseline_ndcg - 0.02, (
            f"Hybrid NDCG regressed: {current['mean_ndcg']:.3f} (baseline: {baseline_ndcg:.3f})"
        )

    # Baseline updates are an explicit benchmark-authoring action, never a side
    # effect of staging verification. This keeps CI evidence reproducible and
    # protects the checked-in baseline from accidental mutation.
    if os.environ.get("UPDATE_QDRANT_BASELINE", "0").lower() not in {"1", "true", "yes"}:
        logger.info("Baseline update disabled; retrieval gate ran read-only")
        return

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baselines = {}
    if baseline_path.exists():
        with open(baseline_path) as f:
            baselines = json.load(f)

    baselines["hybrid"] = {
        "mean_ndcg": current["mean_ndcg"],
        "min_ndcg": current["min_ndcg"],
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }

    with open(baseline_path, "w") as f:
        json.dump(baselines, f, indent=2)

    logger.info(f"Baseline updated: {baseline_path}")


def test_ndcg_duplicate_sources_cannot_exceed_one():
    """Unit regression: duplicate relevant filenames in the ranked list must
    not let DCG exceed IDCG (score in [0.0, 1.0])."""
    tester = QdrantSearchQualityTester(None, None)

    assert tester.ndcg_at_k(["a.md", "a.md", "b.md"], ["a.md"]) == 1.0

    score = tester.ndcg_at_k(["a.md", "a.md", "a.md!", "b.md"], ["a.md"])
    assert score <= 1.0


def test_ndcg_duplicate_relevant_sources_do_not_inflate_idcg():
    """Unit regression: duplicate entries in relevant_sources must not inflate the IDCG denominator."""
    tester = QdrantSearchQualityTester(None, None)
    assert tester.ndcg_at_k(["a.md", "b.md"], ["a.md", "a.md"]) == 1.0


def test_ndcg_perfect_match_and_no_match_bounds():
    """Unit: perfect top-rank match scores exactly 1.0; no relevant hits score 0.0."""
    tester = QdrantSearchQualityTester(None, None)

    assert tester.ndcg_at_k(["a.md"], ["a.md"]) == 1.0
    assert tester.ndcg_at_k(["a.md", "b.md", "c.md"], ["a.md"]) == 1.0
    assert tester.ndcg_at_k(["x.md", "y.md"], ["a.md"]) == 0.0


def test_extract_source_filename_payload_url():
    """Unit regression: URL nested only under payload["url"] is extracted."""
    assert (
        _extract_source_filename({"payload": {"url": "https://x/y/meditation.md"}})
        == "meditation.md"
    )


def test_extract_source_filename_precedence():
    """Unit: top-level and payload.source_url keep precedence over payload.url."""
    assert _extract_source_filename({"source_url": "a.md", "payload": {"url": "b.md"}}) == "a.md"
    assert _extract_source_filename({"payload": {"source_url": "a.md", "url": "b.md"}}) == "a.md"
    assert _extract_source_filename({"payload": {"source": "c.md", "url": "b.md"}}) == "c.md"


if __name__ == "__main__":
    # Self-check: can load test
    print("✓ test_qdrant_search_quality.py loads successfully")
