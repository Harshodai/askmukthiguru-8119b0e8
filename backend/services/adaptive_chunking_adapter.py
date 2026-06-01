"""
Mukthi Guru — Adaptive Chunking Adapter (ekimetrics-aligned)

Wraps the homegrown AdaptiveChunkingService and adds the three metrics defined
by ekimetrics/adaptive-chunking that were previously absent:

  - DCC  (Discourse Continuity Coherence): measures bigram overlap between
          consecutive chunks — high DCC means ideas flow across boundaries
  - BI   (Block Integrity): ratio of chunks that do NOT end mid-sentence —
          a splitter that breaks sentences hurts retrieval precision
  - RC   (Redundancy-Coherence): penalises chunks that are near-duplicates
          of each other (cosine similarity > 0.95 between any pair)

These are reported as INFO logs alongside SC + ICC from the base class.
They do NOT replace the existing scoring logic — the strategy selection
(Recursive vs Semantic) still uses SC + ICC.  DCC / BI / RC are additional
signals so we can tune thresholds in the future.

Interface: identical to AdaptiveChunkingService (duck-typed).
Usage in pipeline.py:
    from services.adaptive_chunking_adapter import AdaptiveChunkingAdapter
    self._adaptive_chunker = AdaptiveChunkingAdapter(self._embedder)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import numpy as np

from services.adaptive_chunking_service import AdaptiveChunkingService

if TYPE_CHECKING:
    from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class AdaptiveChunkingAdapter(AdaptiveChunkingService):
    """
    Drop-in replacement for AdaptiveChunkingService that adds DCC, BI, RC
    metrics logging (ekimetrics gap-fill) while keeping the existing
    chunk_document() duck-typed interface unchanged.
    """

    def __init__(self, embedding_service: EmbeddingService) -> None:
        super().__init__(embedding_service)
        logger.info("AdaptiveChunkingAdapter initialised (DCC+BI+RC metrics enabled)")

    # ------------------------------------------------------------------
    # Three missing ekimetrics metrics
    # ------------------------------------------------------------------

    def _score_dcc(self, chunks: list[str]) -> float:
        """
        Discourse Continuity Coherence (DCC).

        Measures bigram overlap between consecutive chunk boundaries.
        A score close to 1.0 means topics flow smoothly across splits;
        a score near 0 suggests the splitter is cutting in mid-thought.
        """
        if len(chunks) < 2:
            return 1.0

        def bigrams(text: str) -> set[str]:
            words = re.findall(r"\w+", text.lower())
            return {f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)}

        scores = []
        for i in range(len(chunks) - 1):
            tail = chunks[i][-300:]  # last 300 chars of current chunk
            head = chunks[i + 1][:300:]  # first 300 chars of next chunk
            bg_tail = bigrams(tail)
            bg_head = bigrams(head)
            if not bg_tail or not bg_head:
                scores.append(0.5)
                continue
            # Jaccard-like overlap
            overlap = len(bg_tail & bg_head) / len(bg_tail | bg_head)
            scores.append(overlap)

        return float(np.mean(scores)) if scores else 1.0

    def _score_bi(self, chunks: list[str]) -> float:
        """
        Block Integrity (BI).

        Ratio of chunks that end at a sentence boundary (period, !, ?, …).
        High BI means the splitter respects sentence structure.
        """
        if not chunks:
            return 1.0
        sentence_end = re.compile(r"[.!?…]\s*$")
        n_ok = sum(1 for c in chunks if sentence_end.search(c.rstrip()))
        return n_ok / len(chunks)

    def _score_rc(self, chunks: list[str]) -> float:
        """
        Redundancy-Coherence (RC).

        Fraction of chunk pairs whose cosine similarity is BELOW 0.95.
        A score of 1.0 = no near-duplicate chunks; 0.0 = all chunks are copies.
        Only samples up to the first 20 chunks to keep cost O(n) not O(n²).
        """
        sample = chunks[:20]
        if len(sample) < 2:
            return 1.0
        try:
            embs = self.embedding_service.encode(sample)
            n = len(embs)
            non_redundant = 0
            total_pairs = 0
            for i in range(n):
                for j in range(i + 1, n):
                    total_pairs += 1
                    sim = self._cosine_similarity(embs[i], embs[j])
                    if sim < 0.95:
                        non_redundant += 1
            return non_redundant / total_pairs if total_pairs else 1.0
        except Exception as e:
            logger.warning(f"RC scoring failed: {e}")
            return 1.0  # assume non-redundant on error

    # ------------------------------------------------------------------
    # Public interface — identical to base class
    # ------------------------------------------------------------------

    def chunk_document(self, text: str) -> list[str]:
        """
        Calls the base-class strategy selector (Recursive vs Semantic via SC+ICC),
        then logs the three additional ekimetrics metrics (DCC, BI, RC).

        Returns the same list[str] as the base class — no interface change.
        """
        chunks = super().chunk_document(text)

        if not chunks:
            return chunks

        # Log additional metrics without blocking the return path
        try:
            dcc = self._score_dcc(chunks)
            bi = self._score_bi(chunks)
            rc = self._score_rc(chunks)
            logger.info(
                f"Ekimetrics metrics | n={len(chunks)} | "
                f"DCC={dcc:.3f} (discourse flow) | "
                f"BI={bi:.3f} (sentence boundary integrity) | "
                f"RC={rc:.3f} (non-redundancy)"
            )
            # Surface as a combined quality score for future tuning
            combined = (dcc + bi + rc) / 3.0
            logger.info(f"Combined ekimetrics quality score: {combined:.3f}/1.000")
        except Exception as e:
            logger.warning(f"Ekimetrics extra metrics failed (non-fatal): {e}")

        return chunks
