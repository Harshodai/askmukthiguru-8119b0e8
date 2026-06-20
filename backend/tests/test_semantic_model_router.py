"""Tests for SemanticModelRouter."""

import warnings

import pytest

from services.semantic_model_router import SemanticModelRouter, TIER

# Suppress spurious numpy matmul runtime warnings triggered by FakeEmbedding vectors
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*encountered in matmul.*")


class _FakeEmbedding:
    """Lightweight fake that returns deterministic vectors based on text hashes."""

    def __init__(self) -> None:
        self._calls = 0

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return a deterministic dense vector for each text."""
        import numpy as np

        vecs = []
        for t in texts:
            # deterministic pseudo-random vector seeded by text content
            np.random.seed(hash(t) % (2**32))
            vec = np.random.randn(32)
            # avoid near-zero norms that cause numerical issues in cosine sim
            norm = np.linalg.norm(vec)
            if norm < 1e-6:
                vec = np.ones_like(vec) / np.sqrt(len(vec))
            vecs.append(vec.tolist())
        self._calls += len(texts)
        return vecs

    def encode_single(self, text: str) -> list[float]:
        return self.encode([text])[0]


# ---------------------------------------------------------------------------
# Majority vote
# ---------------------------------------------------------------------------

def test_majority_vote_single():
    assert SemanticModelRouter._majority_vote(["fast"]) == "fast"
    assert SemanticModelRouter._majority_vote(["deep"]) == "deep"


def test_majority_vote_tie_standard_wins():
    assert SemanticModelRouter._majority_vote(["fast", "standard"]) == "standard"


def test_majority_vote_tie_fast_wins_deep():
    assert SemanticModelRouter._majority_vote(["fast", "deep"]) == "fast"


def test_majority_vote_three_way_tie():
    assert (
        SemanticModelRouter._majority_vote(["fast", "standard", "deep"]) == "standard"
    )


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def test_cosine_similarity_identical():
    q = [1.0, 0.0, 0.0]
    c = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    sims = SemanticModelRouter._cosine_similarity(q, c)
    assert pytest.approx(sims[0], 0.01) == 1.0
    assert pytest.approx(sims[1], 0.01) == 0.0


def test_cosine_similarity_empty_candidates():
    # Edge case: should handle gracefully (numpy will produce an empty array)
    sims = SemanticModelRouter._cosine_similarity([1.0, 0.0], [])
    assert sims == []


# ---------------------------------------------------------------------------
# Classify
# ---------------------------------------------------------------------------

def test_classify_empty_query():
    fake = _FakeEmbedding()
    router = SemanticModelRouter(fake)
    assert router.classify(None) == "standard"  # type: ignore[arg-type]
    assert router.classify("") == "standard"
    assert router.classify("   ") == "standard"


def test_classify_basic_routing():
    """Smoke test: classify should return one of the three tiers."""
    fake = _FakeEmbedding()
    router = SemanticModelRouter(fake)

    for query in [
        "What is deeksha?",
        "Tell me about the Four Sacred Secrets",
        "Compare deeksha and oneness blessing",
        "Hello",
    ]:
        result = router.classify(query)
        assert result in ("fast", "standard", "deep")


def test_classify_is_deterministic():
    """Routing should be deterministic for the same query."""
    fake = _FakeEmbedding()
    router = SemanticModelRouter(fake)
    query = "What is meditation?"
    results = [router.classify(query) for _ in range(10)]
    assert len(set(results)) == 1


def test_precompute_caches_vectors():
    fake = _FakeEmbedding()
    router = SemanticModelRouter(fake)
    total = sum(len(v) for v in router._TIER_UTTERANCES.values())
    assert len(router._utterance_vectors) == total
    assert len(router._tiers) == total


# ---------------------------------------------------------------------------
# classify_with_score
# ---------------------------------------------------------------------------

def test_classify_with_score_returns_confidence():
    fake = _FakeEmbedding()
    router = SemanticModelRouter(fake)
    tier, confidence = router.classify_with_score("What is deeksha?")
    assert tier in ("fast", "standard", "deep")
    assert 0.0 <= confidence <= 1.0


def test_classify_with_score_empty_returns_zero_confidence():
    fake = _FakeEmbedding()
    router = SemanticModelRouter(fake)
    tier, confidence = router.classify_with_score(None)  # type: ignore[arg-type]
    assert tier == "standard"
    assert confidence == 0.0
