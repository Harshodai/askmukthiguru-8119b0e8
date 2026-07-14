"""Mukthi Guru — Semantic Model Router

Embeddings-only query classification that replaces the LLM-based router
in ``orchestrator_utils.py``.  Sub-100 ms, zero inference-calls, and
robust to paraphrases / typos because it is based on cosine similarity
rather than keyword matching.

Design (derived from AWS / Google Cloud / arXiv 2502.00409 best practices):

1. **Pre-compute** representative utterance embeddings per tier at start-up.
2. At runtime, embed the incoming query once via the existing
   :class:`~services.embedding_service.EmbeddingService`.
3. Classify by majority vote of the **top-k** most similar utterances.
4. No LLM call, no regex list, no keyword maintenance.

Usage::

    from services.semantic_model_router import SemanticModelRouter
    from app.dependencies import get_container

    router = SemanticModelRouter(get_container().embedding)
    tier = router.classify("What is deeksha?")   # "fast"

**Thread-safe**: the router is stateless after init and safe to share
across requests.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Literal, Sequence

import numpy as np

if TYPE_CHECKING:
    from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

TIER = Literal["fast", "standard", "deep"]


class SemanticModelRouter:
    """
    Route incoming user queries to one of three graph strategies
    (fast / standard / deep) using only embedding similarity.
    """

    # Representative seed utterances per tier.
    # These are *coarse* seeds.  In production they should be periodically
    # refined by sampling real user queries from telemetry.
    _TIER_UTTERANCES: dict[TIER, list[str]] = {
        "fast": [
            # Simple definitions / founder facts
            "What is deeksha?",
            "Who is Preethaji?",
            "Who is Krishnaji?",
            "What is the Beautiful State?",
            "What is oneness?",
            "What is the Four Sacred Secrets?",
            "What is Ekam?",
            # Short practice questions
            "How do I do soul sync?",
            "How do I meditate?",
            "Teach me breathing techniques",
            # Greetings / casual
            "Hello",
            "Namaste",
            "Good morning",
            "What can you help me with?",
            "Tell me about yourself",
            # Simple emotional status
            "I am feeling sad today",
            "I need peace",
            "Help me relax",
        ],
        "standard": [
            # Doctrine detail (still factual, needs retrieval)
            "Explain the Four Sacred Secrets in detail",
            "How does deeksha affect the brain?",
            "What happens during oneness deeksha?",
            "Tell me about the 12 powers",
            "What is the significance of Varadaiahpalem?",
            "Explain the Beautiful State teachings",
            "What did Sri Preethaji say about suffering?",
            "How do the Four Sacred Secrets relate to each other?",
            # Multi-sentence factual
            "I have been practising soul sync for a month and feel calmer. "
            "What should I focus on next?",
        ],
        "deep": [
            # Comparative / analytical / multi-hop
            "Compare deeksha and the oneness blessing",
            "What are the similarities between the Four Sacred Secrets "
            "and other spiritual traditions?",
            "Analyze the evolution of Preethaji's teachings over time",
            "What is the relationship between karma and dharma "
            "in the Beautiful State framework?",
            "Contrast the meditation techniques taught by Krishnaji "
            "with traditional Vipassana",
            "How do the 12 powers map to modern neuro-scientific findings?",
            "Pros and cons of the soul sync practice",
            # Complex emotional / reflective
            "I am going through a divorce and feel lost. "
            "How can the Beautiful State help me rebuild my life?",
        ],
    }

    def __init__(
        self,
        embedding_service: EmbeddingService,
        top_k: int = 3,
    ) -> None:
        """
        Args:
            embedding_service: existing singleton embedding service.
            top_k: how many nearest utterances participate in the vote.
        """
        self._embedding = embedding_service
        self._top_k = top_k
        self._tiers: list[TIER] = []
        self._utterance_texts: list[str] = []
        self._utterance_vectors: list[list[float]] = []
        # Deferred precompute: avoid eager model load at startup (OOM risk on
        # memory-constrained containers). Seed vectors are built on first classify().
        self._precomputed: bool = False
        self._precompute_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, query: str | None) -> TIER:
        """
        Toss: classify into one tier, trusting any non-empty result
 """
        tier, _ = self.classify_with_score(query)
        return tier

    def classify_with_score(self, query: str | None) -> tuple[TIER, float]:
        """
        Classify a user query into one of the three tiers.

        Returns:
            ``(tier, max_similarity)`` — max_similarity is the highest
            cosine similarity to any seed utterance (useful for confidence
            thresholding in the caller).
        """
        if not query or not query.strip():
            return "standard", 0.0

        # Lazy precompute with double-checked locking so only one call runs
        # _precompute() even under concurrent first-classification traffic.
        if not self._precomputed:
            with self._precompute_lock:
                if not self._precomputed:
                    self._precompute()

        query_vec = self._embedding.encode_single(query)
        similarities = self._cosine_similarity(query_vec, self._utterance_vectors)
        max_similarity = float(max(similarities))  # keep for caller confidence check
        top_indices = np.argsort(similarities)[-self._top_k :]
        top_tiers: list[TIER] = [self._tiers[i] for i in top_indices]

        tier = self._majority_vote(top_tiers)
        logger.debug(
            f"SemanticModelRouter: classified as '{tier}' "
            f"(max_sim={max_similarity:.3f}, query: {query[:60]}...)"
        )
        return tier, max_similarity

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _precompute(self) -> None:
        """Encode all seed utterances once. Caller holds ``_precompute_lock``.

        Builds tier metadata + utterance vectors in local variables, performs
        the encoding, then atomically publishes to the shared instance state —
        so a concurrent ``classify_with_score`` never observes a half-populated
        ``_tiers`` list if encoding raises mid-way.
        """
        all_texts: list[str] = []
        local_tiers: list[TIER] = []
        for tier, texts in self._TIER_UTTERANCES.items():
            all_texts.extend(texts)
            local_tiers.extend([tier] * len(texts))

        logger.info(
            f"SemanticModelRouter: pre-computing embeddings for "
            f"{len(all_texts)} seed utterances ..."
        )
        # Encode first; on failure the shared state stays empty and _precomputed
        # remains False, so the next call retries.
        local_vectors = self._embedding.encode(all_texts)

        # Atomic publish — assign all shared fields, then flip the completion flag.
        self._utterance_texts = all_texts
        self._utterance_vectors = local_vectors
        self._tiers = local_tiers
        self._precomputed = True
        logger.info(
            f"SemanticModelRouter: ready — {len(self._utterance_texts)} utterance vectors cached."
        )

    @staticmethod
    def _cosine_similarity(
        query_vec: list[float],
        candidate_vecs: list[list[float]],
    ) -> list[float]:
        """Return cosine similarity between ``query_vec`` and every candidate."""
        if not candidate_vecs:
            return []
        q = np.array(query_vec)
        c = np.array(candidate_vecs)
        # Normalise vectors to unit length
        q_norm = q / (np.linalg.norm(q) + 1e-10)
        c_norm = c / (np.linalg.norm(c, axis=1, keepdims=True) + 1e-10)
        # Suppress rare spurious numpy matmul warnings on edge-case vectors
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            return (c_norm @ q_norm).tolist()

    @staticmethod
    def _majority_vote(tiers: Sequence[TIER]) -> TIER:
        """Return the most common tier; tie-breaks prefer *standard* > *fast* > *deep*."""
        counts: dict[TIER, int] = {"fast": 0, "standard": 0, "deep": 0}
        for t in tiers:
            counts[t] += 1
        # Preference order on ties: standard(2) > fast(1) > deep(0)
        return max(counts, key=lambda k: (counts[k], {"standard": 2, "fast": 1, "deep": 0}[k]))
