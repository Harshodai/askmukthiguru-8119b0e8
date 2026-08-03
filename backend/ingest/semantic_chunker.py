"""Semantic Embedding-Distance Topic-Shift Chunker.

Calculates sentence-level embedding cosine similarity across a document to identify
natural topic transitions. Cuts chunks at distance spikes (e.g. 90th percentile)
rather than fixed token or character limits.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Sequence

import numpy as np

from app.config import settings
from ingest.boundary_chunker import BoundaryChunker

if TYPE_CHECKING:
    from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n\n+")


def _cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(v1))
    norm_b = float(np.linalg.norm(v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (norm_a * norm_b))


class SemanticChunker:
    """Topic-shift chunker using sentence-level embedding cosine distance."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        min_chunk_chars: int = 300,
        max_chunk_chars: int = 1800,
        distance_percentile_threshold: float = 85.0,
    ) -> None:
        self._embedder = embedding_service
        self._min_chunk_chars = min_chunk_chars
        self._max_chunk_chars = max_chunk_chars
        self._percentile_threshold = distance_percentile_threshold
        self._fallback_chunker = BoundaryChunker(
            target_size=settings.rag_chunk_size,
            overlap_sentences=1,
        )

    def split(self, text: str) -> list[str]:
        """Split text into semantic topic-shift chunks."""
        if not text or not text.strip():
            return []

        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
        if len(sentences) <= 3 or self._embedder is None:
            return self._fallback_chunker.chunk(text)

        try:
            # 1. Encode sentences in batch
            batch_res = self._embedder.encode_batch(sentences)
            dense_vectors = batch_res.get("dense", [])
            if not dense_vectors or len(dense_vectors) != len(sentences):
                return self._fallback_chunker.chunk(text)

            vec_arr = np.array(dense_vectors)
            
            # 2. Compute consecutive sentence cosine distances (1 - cosine_similarity)
            distances = []
            for i in range(len(sentences) - 1):
                sim = _cosine_similarity(vec_arr[i], vec_arr[i + 1])
                distances.append(1.0 - sim)

            if not distances:
                return self._fallback_chunker.chunk(text)

            # 3. Determine topic-shift boundary threshold
            cutoff = float(np.percentile(distances, self._percentile_threshold))
            
            # 4. Group sentences into topic chunks based on distance spikes & size limits
            chunks: list[str] = []
            curr_sentences: list[str] = [sentences[0]]
            curr_len = len(sentences[0])

            for i in range(len(distances)):
                next_sentence = sentences[i + 1]
                next_len = len(next_sentence)
                is_spike = distances[i] >= cutoff

                # Cut chunk if distance spike detected AND min size met, OR max size exceeded
                if (is_spike and curr_len >= self._min_chunk_chars) or (curr_len + next_len > self._max_chunk_chars):
                    chunks.append(" ".join(curr_sentences))
                    curr_sentences = [next_sentence]
                    curr_len = next_len
                else:
                    curr_sentences.append(next_sentence)
                    curr_len += 1 + next_len

            if curr_sentences:
                chunks.append(" ".join(curr_sentences))

            return chunks
        except Exception as exc:
            logger.warning("SemanticChunker failed (%s); falling back to BoundaryChunker", exc)
            return self._fallback_chunker.chunk(text)
