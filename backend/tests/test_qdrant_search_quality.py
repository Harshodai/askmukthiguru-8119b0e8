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
from pathlib import Path
from typing import Optional

import pytest

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


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
        # health_check() returns False rather than raising on connection failure
        # (services/qdrant/client.py:335) — check the boolean, don't rely on an exception.
        if not client_mgr.health_check():
            pytest.skip("Qdrant unreachable, skipping search-quality integration test")
        # Verify the collection exists and has points — a reachable but
        # empty container (fresh local stack without ingested corpus) would
        # produce NDCG=0.0 and fail the threshold assertion without testing
        # real retrieval quality.
        try:
            info = client_mgr.client.get_collection(settings.qdrant_collection)
            if info.points_count == 0:
                pytest.skip(
                    f"Qdrant collection '{settings.qdrant_collection}' has 0 points "
                    "— ingest the corpus before running search-quality tests"
                )
        except Exception:
            pytest.skip(
                f"Qdrant collection '{settings.qdrant_collection}' not found "
                "— skipping search-quality integration test"
            )
    except Exception as e:
        pytest.skip(f"Qdrant unreachable, skipping search-quality integration test: {e}")

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

    def ndcg_at_k(self, ranked_sources: list[str], relevant_sources: list[str], k: int = 10) -> float:
        """Compute NDCG@K.

        Args:
            ranked_sources: Ordered list of source titles from search
            relevant_sources: Ground truth relevant sources
            k: Cutoff rank

        Returns:
            NDCG@K score in [0.0, 1.0]
        """
        # Relevance: 1.0 if in relevant_sources, 0.0 otherwise
        relevances = [1.0 if src in relevant_sources else 0.0 for src in ranked_sources[:k]]

        # DCG: sum of relevances / log2(rank+1)
        dcg = sum(rel / (2 ** (i + 1)) for i, rel in enumerate(relevances))

        # IDCG: best-case DCG (all relevant sources ranked first)
        ideal_relevances = [1.0] * min(len(relevant_sources), k)
        idcg = sum(1.0 / (2 ** (i + 1)) for i in range(len(ideal_relevances)))

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

            # Extract source titles from results
            ranked_sources = [r.get("source_url", "").split("/")[-1] for r in results]

            # Compute NDCG
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
def test_qdrant_search_quality_hybrid_reranked(qdrant_searcher, embedding_service, reranker_service):
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
            f"Hybrid NDCG regressed: {current['mean_ndcg']:.3f} "
            f"(baseline: {baseline_ndcg:.3f})"
        )

    # Update baseline
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


if __name__ == "__main__":
    # Self-check: can load test
    print("✓ test_qdrant_search_quality.py loads successfully")
