"""
Mukthi Guru — Lightweight adaptive chunking for ingestion.

Ported from ekimetrics/adaptive-chunking (MIT License, 2026).
Core idea: evaluate a small set of chunking candidates per document using cheap
intrinsic metrics and pick the one that maximises a combined quality score.
No LLM calls are made; the only model used is the shared sentence embedder.

The original framework scores chunkings with five intrinsic metrics:
  - Size Compliance (SC)
  - Intrachunk Cohesion (ICC)
  - Contextual / Discourse Coherence (DCC)
  - Block Integrity (BI)
  - Redundancy Control (RC)

This lightweight implementation keeps the same spirit but uses character counts
and a reduced, fixed-size evaluation sample to stay within local, free-tier
constraints.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

if TYPE_CHECKING:
    from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

SentenceBoundaryPattern = re.compile(r"(?<=[.!?])\s+")
EndOfSentencePattern = re.compile(r"[.!?…]\s*$")


def _cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = float(np.linalg.norm(v1))
    norm_b = float(np.linalg.norm(v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (norm_a * norm_b))


def _centroid(embeddings: np.ndarray) -> np.ndarray:
    """Mean of a stack of normalized embeddings."""
    return np.mean(embeddings, axis=0)


class AdaptiveChunker:
    """
    Selects the best chunking strategy per document using cheap intrinsic
    metrics and applies it to the full text.

    Interface duck-types the previous service implementations:
      - chunk_document(text) -> list[str]
      - split(text) -> list[str]
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        min_chunk_chars: int = 200,
        max_chunk_chars: int = 1600,
        sample_chars: int = 8000,
    ) -> None:
        self._embedder = embedding_service
        self._chunk_size = chunk_size or settings.rag_chunk_size
        self._chunk_overlap = chunk_overlap or settings.rag_chunk_overlap
        self._min_chunk_chars = min_chunk_chars
        self._max_chunk_chars = max_chunk_chars
        self._sample_chars = sample_chars

        self._recursive = RecursiveCharacterTextSplitter(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self._recursive_small = RecursiveCharacterTextSplitter(
            chunk_size=max(self._chunk_size // 2, self._min_chunk_chars),
            chunk_overlap=self._chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def split(self, text: str) -> list[str]:
        """Chunk *text* using the best candidate strategy per document."""
        return self.chunk_document(text)

    def chunk_document(self, text: str) -> list[str]:
        """
        Evaluate recursive and semantic candidates on a sample, pick the best,
        and apply it to the whole document.
        """
        if not text or not text.strip():
            return []

        doc_len = len(text)
        min_chars = getattr(settings, "adaptive_chunking_min_chars", 800)
        if doc_len < min_chars or not getattr(settings, "use_adaptive_chunking", True):
            logger.info(
                "Adaptive chunking disabled for short document (len=%s). "
                "Falling back to recursive splitter.",
                doc_len,
            )
            return self._recursive.split_text(text)

        start_time = __import__("time").perf_counter()
        sample = text[: min(doc_len, self._sample_chars)]

        candidates = self._build_candidates(sample)
        best_name, _best_chunks = self._pick_best(candidates, sample)
        result = self._apply_strategy(best_name, text)

        duration = __import__("time").perf_counter() - start_time
        logger.info(
            "Adaptive chunking selected '%s' for %s-char document in %.3fs (%s chunks)",
            best_name,
            doc_len,
            duration,
            len(result),
        )
        return result

    # ------------------------------------------------------------------
    # Candidate strategies
    # ------------------------------------------------------------------
    def _build_candidates(self, sample: str) -> dict[str, list[str]]:
        """Generate the candidate chunk sets that will be scored."""
        return {
            "recursive": self._recursive.split_text(sample),
            "recursive_small": self._recursive_small.split_text(sample),
            "semantic": self._semantic_split(sample),
        }

    def _apply_strategy(self, name: Literal["recursive", "recursive_small", "semantic"], text: str) -> list[str]:
        """Apply the winning strategy to the full document."""
        if name == "semantic":
            return self._semantic_split(text)
        if name == "recursive_small":
            return self._recursive_small.split_text(text)
        return self._recursive.split_text(text)

    def _semantic_split(self, text: str, percentile: int = 25) -> list[str]:
        """
        Sentence-level semantic chunking.

        Splits at low-similarity boundaries between consecutive sentences.
        The threshold is chosen from the distribution of sentence-to-sentence
        similarities so it adapts to each document.
        """
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return sentences

        try:
            embeddings = self._encode(sentences)
        except Exception as exc:  # pragma: no cover - embedder failures handled upstream
            logger.warning("Semantic split embedding failed: %s. Falling back to recursive.", exc)
            return self._recursive.split_text(text)

        similarities = self._consecutive_similarities(embeddings)
        if not similarities:
            return sentences

        threshold = max(float(np.percentile(similarities, percentile)), 0.0)

        chunks: list[str] = []
        current: list[str] = [sentences[0]]
        for idx, sim in enumerate(similarities):
            current_len = sum(len(s) for s in current)
            next_sentence = sentences[idx + 1]
            if sim < threshold or current_len + len(next_sentence) > self._max_chunk_chars:
                chunks.append(" ".join(current))
                current = [next_sentence]
            else:
                current.append(next_sentence)

        if current:
            chunks.append(" ".join(current))

        return self._merge_tiny_chunks(chunks)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def _pick_best(
        self,
        candidates: dict[str, list[str]],
        full_text: str,
    ) -> tuple[str, list[str]]:
        """Score every candidate and return the name/chunks with highest score."""
        if not candidates:
            return "recursive", []

        first_name, first_chunks = next(iter(candidates.items()))
        best_name = first_name
        best_score = -1.0
        best_chunks = first_chunks

        for name, chunks in candidates.items():
            score = self._score(chunks, full_text)
            logger.debug("Adaptive chunking candidate '%s': score=%.4f, n=%d", name, score, len(chunks))
            if score > best_score:
                best_score = score
                best_name = name
                best_chunks = chunks

        return best_name, best_chunks

    def _score(self, chunks: list[str], full_text: str) -> float:
        """Combined intrinsic quality score in [0, 1]."""
        if not chunks:
            return 0.0

        try:
            chunk_embeddings = self._encode(chunks)
        except Exception as exc:
            logger.warning("Could not embed chunks for scoring: %s", exc)
            return self._fallback_score(chunks)

        sc = self._size_compliance(chunks)
        icc = self._intrachunk_cohesion(chunks, chunk_embeddings)
        dcc = self._discourse_coherence(chunks)
        bi = self._block_integrity(chunks)
        rc = self._redundancy_control(chunks, chunk_embeddings)

        # Weights mirror the original framework emphasis: cohesion and
        # discourse continuity are strong signals for retrieval quality;
        # size compliance and block integrity keep chunks usable.
        score = 0.20 * sc + 0.30 * icc + 0.20 * dcc + 0.15 * bi + 0.15 * rc
        return float(np.clip(score, 0.0, 1.0))

    def _fallback_score(self, chunks: list[str]) -> float:
        """Score used when embeddings are unavailable (e.g. offline tests)."""
        return 0.6 * self._size_compliance(chunks) + 0.4 * self._block_integrity(chunks)

    def _size_compliance(self, chunks: Sequence[str]) -> float:
        """Fraction of chunks inside the target character bounds."""
        if not chunks:
            return 0.0
        ok = sum(
            1 for c in chunks if self._min_chunk_chars <= len(c) <= self._max_chunk_chars
        )
        return ok / len(chunks)

    def _intrachunk_cohesion(
        self,
        chunks: Sequence[str],
        chunk_embeddings: np.ndarray,
    ) -> float:
        """
        Mean cosine similarity of each sentence to its chunk centroid.
        High cohesion means the sentences in a chunk talk about the same topic.
        """
        scores: list[float] = []
        for chunk, chunk_emb in zip(chunks, chunk_embeddings):
            sentences = self._split_sentences(chunk)
            if len(sentences) <= 1:
                scores.append(1.0)
                continue
            try:
                sent_embs = self._encode(sentences)
                centroid = _centroid(sent_embs)
                sims = [_cosine_similarity(emb, centroid) for emb in sent_embs]
                scores.append(float(np.mean(sims)))
            except Exception as exc:
                logger.debug("Intrachunk cohesion failed for a chunk: %s", exc)
                scores.append(0.5)

        return float(np.mean(scores)) if scores else 0.5

    def _discourse_coherence(self, chunks: Sequence[str]) -> float:
        """
        Discourse continuity: bigram overlap between adjacent chunk boundaries.
        High values indicate the splitter is not cutting in mid-thought.
        """
        if len(chunks) < 2:
            return 1.0

        def bigrams(text: str) -> set[str]:
            words = re.findall(r"\w+", text.lower())
            return {f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)}

        scores: list[float] = []
        for i in range(len(chunks) - 1):
            tail = chunks[i][-300:]
            head = chunks[i + 1][:300]
            bg_tail = bigrams(tail)
            bg_head = bigrams(head)
            if not bg_tail or not bg_head:
                scores.append(0.5)
                continue
            overlap = len(bg_tail & bg_head) / len(bg_tail | bg_head)
            scores.append(overlap)

        return float(np.mean(scores)) if scores else 1.0

    def _block_integrity(self, chunks: Sequence[str]) -> float:
        """Fraction of chunks that end at a sentence boundary."""
        if not chunks:
            return 1.0
        ok = sum(1 for c in chunks if EndOfSentencePattern.search(c.rstrip()))
        return ok / len(chunks)

    def _redundancy_control(
        self,
        chunks: Sequence[str],
        chunk_embeddings: np.ndarray,
        sample_limit: int = 20,
    ) -> float:
        """
        Fraction of chunk pairs whose cosine similarity is below 0.95.
        Sampling is used to keep this O(n) in chunk count.
        """
        n = min(len(chunks), sample_limit)
        if n < 2:
            return 1.0

        sample_embs = chunk_embeddings[:n]
        non_redundant = 0
        total_pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                total_pairs += 1
                if _cosine_similarity(sample_embs[i], sample_embs[j]) < 0.95:
                    non_redundant += 1

        return non_redundant / total_pairs if total_pairs else 1.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        """Encode texts through the injected embedding service."""
        return np.asarray(self._embedder.encode(list(texts)))

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Simple, language-agnostic sentence boundary split."""
        return [s.strip() for s in SentenceBoundaryPattern.split(text) if s.strip()]

    @staticmethod
    def _consecutive_similarities(embeddings: np.ndarray) -> list[float]:
        """Cosine similarity between each embedding and the next one."""
        return [
            _cosine_similarity(embeddings[i], embeddings[i + 1])
            for i in range(len(embeddings) - 1)
        ]

    def _merge_tiny_chunks(self, chunks: Sequence[str], min_chars: int = 250) -> list[str]:
        """Merge chunks that are too small to stand on their own."""
        if not chunks:
            return []

        merged: list[str] = [chunks[0]]
        for chunk in chunks[1:]:
            if len(merged[-1]) + len(chunk) < min_chars:
                merged[-1] = merged[-1] + " " + chunk
            else:
                merged.append(chunk)
        return merged
